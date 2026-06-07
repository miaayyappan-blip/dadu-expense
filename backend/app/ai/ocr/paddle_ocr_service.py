import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OcrTextLine:
    """Single line of recognized text with position and confidence."""
    text: str
    confidence: float        # 0.0–1.0 per-character average from PaddleOCR
    y_position: float        # normalized vertical position (0=top, 1=bottom)
    x_position: float        # normalized horizontal position
    is_likely_total: bool    # True if line pattern matches a total/amount line
    is_likely_date: bool     # True if line pattern matches a date
    is_likely_merchant: bool # True if in top 15% of receipt (merchant area)


@dataclass
class OcrResult:
    """Full OCR result from a receipt image."""
    raw_text: str                    # All lines joined — for LLM input
    lines: list[OcrTextLine]         # Structured lines with positions
    avg_confidence: float            # Overall OCR quality score
    low_confidence_lines: list[str]  # Lines with confidence < 0.6
    char_count: int
    line_count: int
    is_partial: bool                 # True if top or bottom looks cut off
    ocr_quality: str                 # "high" | "medium" | "low"


@lru_cache(maxsize=1)
def _get_paddle_ocr():
    import easyocr

    logger.info("Initializing EasyOCR...")
    reader = easyocr.Reader(['en'], gpu=False)
    logger.info("EasyOCR initialized successfully")

    return reader

class PaddleOcrService:
    """
    Wraps PaddleOCR for receipt text extraction.

    Key design decisions:
    - Preserves vertical ordering: receipt structure matters (merchant=top, total=bottom)
    - Computes aggregate confidence from per-box scores
    - Flags likely total/date/merchant lines to help the LLM extractor
    - Handles empty results (blank receipts, photos of wrong surface)
    - Thread-safe: PaddleOCR instance is shared via lru_cache
    """

    # Lines with confidence below this are flagged as uncertain
    LOW_CONFIDENCE_THRESHOLD = 0.6

    # Patterns that suggest a line contains a monetary total
    TOTAL_PATTERNS = [
        "total", "amount", "grand total", "net amount", "payable",
        "subtotal", "sub-total", "sum", "bill amount", "to pay",
        "balance due", "amount due",
    ]

    # Patterns that suggest a date line
    DATE_PATTERNS = [
        r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}",  # 12/06/2026
        r"\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}",      # 2026-06-12
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    ]

    def extract_text(self, image_array: np.ndarray) -> OcrResult:
        """
        Run PaddleOCR on a preprocessed image array.

        Args:
            image_array: BGR numpy array from ImagePreprocessor

        Returns:
            OcrResult with structured text and quality metrics
        """
        import re

        ocr = _get_paddle_ocr()

        logger.info(f"Running EasyOCR on {image_array.shape} array")

        try:
            results = ocr.readtext(image_array)

            raw_result = []
            for result in results:
                box, text, confidence = result
                raw_result.append([box, (text, confidence)])
        except Exception as e:
            logger.error(f"PaddleOCR inference failed: {e}")
            raise ValueError(f"OCR processing failed: {e}")

        # PaddleOCR returns: [[[box, (text, confidence)], ...]]
        # Unwrap the outer list
        if not raw_result or raw_result == [None] or raw_result == [[None]]:
            logger.warning("PaddleOCR returned empty result")
            return self._empty_result()

        # Flatten nested result structure
        detections = raw_result
        

        if not detections:
            return self._empty_result()

        # ── Extract image dimensions for normalization ────────────────────────
        img_h, img_w = image_array.shape[:2]

        # ── Parse each detection ──────────────────────────────────────────────
        lines: list[OcrTextLine] = []
        all_confidences: list[float] = []
        low_confidence_lines: list[str] = []

        for detection in detections:
            try:
                box, (text, confidence) = detection
                text = text.strip()
                import re
                # Remove currency symbols
                text = text.replace("₹", "")
                text = text.replace("Rs.", "")
                text = text.replace("Rs", "")
                text = text.replace("INR", "")
                # Remove stray OCR currency artifacts
                text = re.sub(r"[₹$€£]", "", text)
                if not text:
                    continue

                confidence = float(confidence)
                all_confidences.append(confidence)

                if confidence < self.LOW_CONFIDENCE_THRESHOLD:
                    low_confidence_lines.append(f"'{text}' ({confidence:.0%})")

                # Compute normalized position from bounding box
                # Box format: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                ys = [pt[1] for pt in box]
                xs = [pt[0] for pt in box]
                y_center = (min(ys) + max(ys)) / 2 / img_h
                x_center = (min(xs) + max(xs)) / 2 / img_w

                text_lower = text.lower()

                # Flag line types for LLM context
                is_total = any(p in text_lower for p in self.TOTAL_PATTERNS)
                is_date = any(
                    bool(re.search(p, text_lower, re.IGNORECASE))
                    for p in self.DATE_PATTERNS
                )
                # Merchant names are almost always in the top 15% of a receipt
                is_merchant = y_center < 0.15 and len(text) > 3

                lines.append(OcrTextLine(
                    text=text,
                    confidence=confidence,
                    y_position=y_center,
                    x_position=x_center,
                    is_likely_total=is_total,
                    is_likely_date=is_date,
                    is_likely_merchant=is_merchant,
                ))

            except (TypeError, ValueError, IndexError) as e:
                logger.debug(f"Skipping malformed detection: {e}")
                continue

        if not lines:
            return self._empty_result()

        # ── Sort lines top-to-bottom (preserve receipt layout) ────────────────
        lines.sort(key=lambda l: l.y_position)

        # ── Build raw text preserving layout ─────────────────────────────────
        raw_text = "\n".join(line.text for line in lines)

        # ── Aggregate metrics ─────────────────────────────────────────────────
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

        # Detect partial receipt: check if top or bottom has very few lines
        top_lines = sum(1 for l in lines if l.y_position < 0.1)
        bottom_lines = sum(1 for l in lines if l.y_position > 0.9)
        is_partial = top_lines == 0 or bottom_lines == 0

        # ── Quality classification ────────────────────────────────────────────
        if avg_confidence >= 0.85:
            ocr_quality = "high"
        elif avg_confidence >= 0.65:
            ocr_quality = "medium"
        else:
            ocr_quality = "low"

        logger.info(
            f"OCR complete: {len(lines)} lines, avg_conf={avg_confidence:.2f}, "
            f"quality={ocr_quality}, partial={is_partial}"
        )

        return OcrResult(
            raw_text=raw_text,
            lines=lines,
            avg_confidence=round(avg_confidence, 3),
            low_confidence_lines=low_confidence_lines,
            char_count=len(raw_text),
            line_count=len(lines),
            is_partial=is_partial,
            ocr_quality=ocr_quality,
        )

    def _empty_result(self) -> OcrResult:
        return OcrResult(
            raw_text="",
            lines=[],
            avg_confidence=0.0,
            low_confidence_lines=[],
            char_count=0,
            line_count=0,
            is_partial=True,
            ocr_quality="low",
        )
