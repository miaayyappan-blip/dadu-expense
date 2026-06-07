from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.ai.ocr.paddle_ocr_service import OcrResult
from app.models.expense import ExpenseCategory


@dataclass
class OcrConfidenceBreakdown:
    """
    Two-dimensional confidence for receipt OCR.
    
    ocr_quality_score:   How well PaddleOCR read the image (image quality signal)
    extraction_score:    How complete the LLM extraction was (field completeness signal)
    final_score:         Weighted combination
    
    Both dimensions matter independently:
    - High OCR quality + low extraction = LLM failed to parse a good image
    - Low OCR quality + high extraction = LLM guessed well from noisy text (lower trust)
    """
    final_score: float
    ocr_quality_score: float
    extraction_score: float

    missing_fields: list[str]
    low_confidence_fields: list[str]
    suggestions: str
    is_partial_receipt: bool

    # Specific warnings for the UI
    amount_warning: Optional[str]
    date_warning: Optional[str]


class OcrConfidenceScorer:
    """
    Computes receipt-specific confidence scores.

    OCR quality weight:  40% — image quality is a hard ceiling on accuracy
    Extraction weight:   60% — field completeness drives usability

    Field weights within extraction score:
        amount      0.40  — critical, can't save without it
        category    0.20
        date        0.20
        merchant    0.10
        description 0.10
    """

    OCR_WEIGHT = 0.40
    EXTRACTION_WEIGHT = 0.60

    FIELD_WEIGHTS = {
        "amount":      0.40,
        "category":    0.20,
        "date":        0.20,
        "merchant":    0.10,
        "description": 0.10,
    }

    def score(
        self,
        ocr_result: OcrResult,
        amount: Optional[Decimal],
        category: Optional[ExpenseCategory],
        description: Optional[str],
        merchant: Optional[str],
        expense_date: Optional[date],
        is_partial_receipt: bool,
    ) -> OcrConfidenceBreakdown:

        missing_fields: list[str] = []
        low_confidence_fields: list[str] = []
        issues: list[str] = []
        amount_warning: Optional[str] = None
        date_warning: Optional[str] = None

        # ── OCR quality score ─────────────────────────────────────────────────
        # Start with PaddleOCR's average confidence, penalize for partial receipts
        ocr_score = ocr_result.avg_confidence

        if is_partial_receipt or ocr_result.is_partial:
            ocr_score *= 0.75
            issues.append("Receipt appears to be partially captured")

        if ocr_result.ocr_quality == "low":
            ocr_score *= 0.7
            issues.append("Image quality is poor — OCR may have errors")

        if len(ocr_result.low_confidence_lines) > 3:
            ocr_score *= 0.85
            issues.append(
                f"{len(ocr_result.low_confidence_lines)} lines had low OCR confidence"
            )

        if ocr_result.line_count < 3:
            ocr_score *= 0.5
            issues.append("Very few text lines detected — check image quality")

        # ── Field extraction score ────────────────────────────────────────────
        field_scores: dict[str, float] = {}

        # Amount
        if amount is None:
            field_scores["amount"] = 0.0
            missing_fields.append("amount")
            issues.append("Total amount not found in receipt")
        elif amount > Decimal("100000"):
            field_scores["amount"] = 0.6
            low_confidence_fields.append("amount")
            amount_warning = f"Amount ₹{amount:,.2f} seems unusually high — please verify"
        else:
            field_scores["amount"] = 1.0

        # Category
        if category is None:
            field_scores["category"] = 0.0
            missing_fields.append("category")
        elif category.value == "Other":
            field_scores["category"] = 0.5
            low_confidence_fields.append("category")
        else:
            field_scores["category"] = 1.0

        # Date
        if expense_date is None:
            field_scores["date"] = 0.0
            missing_fields.append("date")
            date_warning = "Date not found — defaulted to today"
        else:
            today = date.today()
            days_old = (today - expense_date).days
            if expense_date > today:
                field_scores["date"] = 0.2
                low_confidence_fields.append("date")
                date_warning = f"Date {expense_date} is in the future — OCR may have misread it"
            elif days_old > 365:
                field_scores["date"] = 0.5
                low_confidence_fields.append("date")
                date_warning = f"Date {expense_date} is over a year ago — please verify"
            else:
                field_scores["date"] = 1.0

        # Merchant
        if merchant is None:
            field_scores["merchant"] = 0.0
            missing_fields.append("merchant")
        else:
            field_scores["merchant"] = 1.0

        # Description
        if not description:
            field_scores["description"] = 0.0
            missing_fields.append("description")
        else:
            field_scores["description"] = 1.0

        # Weighted extraction score
        extraction_score = sum(
            self.FIELD_WEIGHTS[f] * field_scores.get(f, 0.0)
            for f in self.FIELD_WEIGHTS
        )

        # ── Final combined score ──────────────────────────────────────────────
        final_score = (
            self.OCR_WEIGHT * ocr_score +
            self.EXTRACTION_WEIGHT * extraction_score
        )
        final_score = round(min(1.0, max(0.0, final_score)), 3)

        # ── Build suggestion message ──────────────────────────────────────────
        if final_score >= 0.85:
            suggestion = "Receipt scanned successfully. Please review and confirm."
        elif final_score >= 0.60:
            parts = ["Some details need review."]
            if issues:
                parts.append(f"Issues: {'; '.join(issues[:2])}")
            suggestion = " ".join(parts)
        else:
            parts = ["Low confidence scan."]
            if missing_fields:
                parts.append(f"Missing: {', '.join(missing_fields)}.")
            if issues:
                parts.append(issues[0])
            suggestion = " ".join(parts)

        return OcrConfidenceBreakdown(
            final_score=final_score,
            ocr_quality_score=round(ocr_score, 3),
            extraction_score=round(extraction_score, 3),
            missing_fields=missing_fields,
            low_confidence_fields=low_confidence_fields,
            suggestions=suggestion,
            is_partial_receipt=is_partial_receipt or ocr_result.is_partial,
            amount_warning=amount_warning,
            date_warning=date_warning,
        )
