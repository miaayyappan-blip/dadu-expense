from datetime import date as Date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.expense import ExpenseCategory


class OcrExtractResponse(BaseModel):
    """
    Returned after receipt processing.
    Frontend renders review form pre-filled with these values.
    Nothing has been saved to DB yet.
    """
    # OCR metadata — shown in UI for transparency
    raw_ocr_text: str
    ocr_line_count: int
    ocr_quality: str             # "high" | "medium" | "low"
    image_quality_score: float
    was_image_enhanced: bool
    is_partial_receipt: bool
    items_detected: int

    # Extracted expense fields
    amount: Optional[Decimal] = None
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    date: Optional[Date] = None

    # Confidence signals
    confidence: float
    ocr_confidence_score: float    # PaddleOCR quality signal
    extraction_score: float        # LLM field completeness signal
    missing_fields: list[str]
    low_confidence_fields: list[str]
    suggestions: str
    extraction_notes: Optional[str] = None

    # Field-specific warnings
    amount_warning: Optional[str] = None
    date_warning: Optional[str] = None

    # Review flags
    needs_review: bool
    is_empty_image: bool


class OcrConfirmRequest(BaseModel):
    """
    User-confirmed expense from OCR review.
    All core fields required at this point.
    """
    amount: Decimal
    category: ExpenseCategory
    description: str
    merchant: Optional[str] = None
    date: Date

    # Pass back original signals for storage
    original_confidence: float
    original_ocr_text: str

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Description cannot be empty")
        return v.strip()
