import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.ai.extraction.receipt_extractor import ReceiptExtractor
from app.ai.ocr.image_preprocessor import ImagePreprocessor, ImageQuality
from app.ai.ocr.ocr_confidence_scorer import OcrConfidenceBreakdown, OcrConfidenceScorer
from app.ai.ocr.paddle_ocr_service import PaddleOcrService
from app.models.expense import ExpenseCategory

logger = logging.getLogger(__name__)


@dataclass
class OcrProcessingResult:
    """
    Full result of the OCR pipeline.
    Returned to frontend for user review — DB write happens only after confirm.
    """
    # Raw OCR output
    raw_ocr_text: str
    ocr_line_count: int
    ocr_quality: str             # "high" | "medium" | "low"

    # Image metadata
    image_quality_score: float
    was_image_enhanced: bool
    is_partial_receipt: bool

    # Extracted expense fields
    amount: Optional[Decimal]
    category: Optional[ExpenseCategory]
    description: Optional[str]
    merchant: Optional[str]
    date: Optional[date]
    items_detected: int

    # Confidence breakdown
    confidence: float
    ocr_confidence_score: float
    extraction_score: float
    missing_fields: list[str]
    low_confidence_fields: list[str]
    suggestions: str
    extraction_notes: Optional[str]

    # Warnings for specific fields
    amount_warning: Optional[str]
    date_warning: Optional[str]

    # Review flags
    needs_review: bool
    is_empty_image: bool


class OcrPipeline:
    """
    Orchestrates the full receipt OCR pipeline:

        Image bytes
            ↓ ImagePreprocessor.preprocess()   — enhance for OCR
        Numpy array
            ↓ PaddleOcrService.extract_text()  — character recognition
        OcrResult (text + positions + line confidence)
            ↓ Build structural hints             — flag total/date/merchant lines
            ↓ ReceiptExtractor.extract()        — LLM parses receipt structure
        Raw field dict
            ↓ OcrConfidenceScorer.score()       — 2D confidence (OCR + extraction)
        OcrProcessingResult (returned to frontend for review)

    NOTHING is written to the DB here.
    The /ocr/confirm endpoint handles the DB write.
    """

    REVIEW_THRESHOLD = 0.85

    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.ocr_service = PaddleOcrService()
        self.extractor = ReceiptExtractor()
        self.scorer = OcrConfidenceScorer()

    async def process(self, image_bytes: bytes) -> OcrProcessingResult:
        """
        Run full OCR pipeline on raw image bytes.

        Args:
            image_bytes: Validated image bytes (jpeg/png/webp)

        Returns:
            OcrProcessingResult ready for frontend review
        """
        today = date.today()

        # ── Stage 1: Image preprocessing ─────────────────────────────────────
        logger.info("OCR pipeline: preprocessing image")
        try:
            preprocess_result = self.preprocessor.preprocess(image_bytes)
        except ValueError as e:
            logger.error(f"OCR pipeline: image preprocessing failed: {e}")
            raise

        was_enhanced = len(preprocess_result.enhancements_applied) > 2

        # ── Stage 2: OCR text extraction ──────────────────────────────────────
        logger.info(
            f"OCR pipeline: running PaddleOCR on "
            f"{preprocess_result.width}x{preprocess_result.height} image, "
            f"quality={preprocess_result.quality.value}"
        )
        try:
            ocr_result = self.ocr_service.extract_text(preprocess_result.image_array)
        except ValueError as e:
            logger.error(f"OCR pipeline: PaddleOCR failed: {e}")
            raise

        # Empty image — early return
        if ocr_result.char_count == 0:
            logger.warning("OCR pipeline: no text found in image")
            return self._empty_image_result(preprocess_result.quality_score)

        # ── Stage 3: Build structural hints for LLM ────────────────────────────
        hints = self._build_extraction_hints(ocr_result)

        # ── Stage 4: LLM extraction ────────────────────────────────────────────
        logger.info(
            f"OCR pipeline: extracting from {ocr_result.line_count} lines of OCR text"
        )
        try:
            extracted = await self.extractor.extract(
                ocr_text=ocr_result.raw_text,
                flagged_hints=hints,
            )
        except Exception as e:
            logger.error(f"OCR pipeline: Gemini extraction failed: {e}")
            return self._extraction_failure_result(ocr_result, preprocess_result.quality_score)

        # ── Stage 5: Date default ─────────────────────────────────────────────
        expense_date = extracted.get("date") or today

        # ── Stage 6: Confidence scoring ───────────────────────────────────────
        try:
            breakdown: OcrConfidenceBreakdown = self.scorer.score(
                ocr_result=ocr_result,
                amount=extracted.get("amount"),
                category=extracted.get("category"),
                description=extracted.get("description"),
                merchant=extracted.get("merchant"),
                expense_date=expense_date,
                is_partial_receipt=extracted.get("is_partial_receipt", False),
            )
        except Exception as e:
            logger.error(f"OCR pipeline: confidence scoring failed: {e}")
            breakdown = OcrConfidenceBreakdown(
                final_score=0.0,
                ocr_quality_score=ocr_result.avg_confidence,
                extraction_score=0.0,
                missing_fields=["amount", "category"],
                low_confidence_fields=[],
                suggestions="Scoring failed. Please review all fields.",
                is_partial_receipt=ocr_result.is_partial,
                amount_warning=None,
                date_warning=None,
            )

        logger.info(
            f"OCR pipeline complete: confidence={breakdown.final_score}, "
            f"ocr_quality={ocr_result.ocr_quality}, "
            f"missing={breakdown.missing_fields}"
        )

        return OcrProcessingResult(
            raw_ocr_text=ocr_result.raw_text,
            ocr_line_count=ocr_result.line_count,
            ocr_quality=ocr_result.ocr_quality,
            image_quality_score=preprocess_result.quality_score,
            was_image_enhanced=was_enhanced,
            is_partial_receipt=breakdown.is_partial_receipt,
            amount=extracted.get("amount"),
            category=extracted.get("category"),
            description=extracted.get("description"),
            merchant=extracted.get("merchant"),
            date=expense_date,
            items_detected=extracted.get("items_detected", 0),
            confidence=breakdown.final_score,
            ocr_confidence_score=breakdown.ocr_quality_score,
            extraction_score=breakdown.extraction_score,
            missing_fields=breakdown.missing_fields,
            low_confidence_fields=breakdown.low_confidence_fields,
            suggestions=breakdown.suggestions,
            extraction_notes=extracted.get("extraction_notes"),
            amount_warning=breakdown.amount_warning,
            date_warning=breakdown.date_warning,
            needs_review=breakdown.final_score < self.REVIEW_THRESHOLD,
            is_empty_image=False,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_extraction_hints(self, ocr_result) -> dict:
        """
        Build structural hints from PaddleOCR line analysis.
        These are passed to the LLM to improve extraction accuracy.
        """
        hints = {}

        total_lines = [l.text for l in ocr_result.lines if l.is_likely_total]
        if total_lines:
            hints["likely_total_lines"] = total_lines[:5]  # top 5 candidates

        date_lines = [l.text for l in ocr_result.lines if l.is_likely_date]
        if date_lines:
            hints["likely_date_lines"] = date_lines[:3]

        merchant_lines = [l.text for l in ocr_result.lines if l.is_likely_merchant]
        if merchant_lines:
            hints["likely_merchant"] = merchant_lines[0]  # usually first top line

        return hints

    def _empty_image_result(self, quality_score: float) -> OcrProcessingResult:
        return OcrProcessingResult(
            raw_ocr_text="",
            ocr_line_count=0,
            ocr_quality="low",
            image_quality_score=quality_score,
            was_image_enhanced=True,
            is_partial_receipt=True,
            amount=None, category=None, description=None,
            merchant=None, date=None, items_detected=0,
            confidence=0.0,
            ocr_confidence_score=0.0,
            extraction_score=0.0,
            missing_fields=["amount", "category", "description", "merchant", "date"],
            low_confidence_fields=[],
            suggestions=(
                "No text was detected in the image. "
                "Please ensure the receipt is well-lit, flat, and fully in frame."
            ),
            extraction_notes=None,
            amount_warning=None,
            date_warning=None,
            needs_review=True,
            is_empty_image=True,
        )

    def _extraction_failure_result(self, ocr_result, quality_score: float) -> OcrProcessingResult:
        return OcrProcessingResult(
            raw_ocr_text=ocr_result.raw_text,
            ocr_line_count=ocr_result.line_count,
            ocr_quality=ocr_result.ocr_quality,
            image_quality_score=quality_score,
            was_image_enhanced=True,
            is_partial_receipt=ocr_result.is_partial,
            amount=None, category=None,
            description=ocr_result.raw_text[:100] if ocr_result.raw_text else None,
            merchant=None, date=date.today(), items_detected=0,
            confidence=0.1,
            ocr_confidence_score=ocr_result.avg_confidence,
            extraction_score=0.0,
            missing_fields=["amount", "category", "merchant"],
            low_confidence_fields=[],
            suggestions=(
                "Receipt text was read but structured extraction failed. "
                "Please fill in the details manually."
            ),
            extraction_notes="LLM extraction error",
            amount_warning=None,
            date_warning=None,
            needs_review=True,
            is_empty_image=False,
        )
