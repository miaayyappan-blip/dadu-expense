from datetime import date as DateType
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.expense import ExpenseCategory, ExpenseSource


# ── Step 1 response: what the pipeline extracted (pre-save) ───────────────────

class VoiceExtractResponse(BaseModel):
    """
    Returned after audio processing. Frontend shows this for user review.
    Nothing has been saved to DB yet.
    """
    # Transcription metadata
    transcript: str
    language: str
    audio_duration_seconds: Optional[float] = None

    # Extracted expense fields (all optional — user completes missing ones)
    amount: Optional[Decimal] = None
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    date: Optional[DateType] = None

    # Confidence signals
    confidence: float
    missing_fields: list[str]
    low_confidence_fields: list[str]
    suggestions: str
    extraction_notes: Optional[str] = None

    # Review flags
    needs_review: bool
    is_empty_audio: bool


# ── Step 2 request: user-confirmed expense (triggers DB save) ─────────────────

class VoiceConfirmRequest(BaseModel):
    """
    Sent by frontend after user reviews and confirms the extracted expense.
    All fields required — frontend must ensure this before submitting.
    """
    # The expense data (user may have edited any field)
    amount: Decimal
    category: ExpenseCategory
    description: str
    merchant: Optional[str] = None
    date: DateType

    # Pass back the original AI confidence for storage
    original_confidence: float

    # The original transcript — stored for audit trail
    transcript: str

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
