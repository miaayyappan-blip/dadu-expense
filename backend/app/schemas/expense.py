from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.models.expense import ExpenseCategory, ExpenseSource


# ── Base ──────────────────────────────────────────────────────────────────────

class ExpenseBase(BaseModel):
    amount: Decimal
    category: ExpenseCategory
    description: str
    merchant: Optional[str] = None
    date: date

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return round(v, 2)


# ── Create / Update ───────────────────────────────────────────────────────────

class ExpenseCreateRequest(ExpenseBase):
    source: ExpenseSource = ExpenseSource.MANUAL


class ExpenseUpdateRequest(BaseModel):
    """All fields optional for PATCH semantics."""
    amount: Optional[Decimal] = None
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    date: Optional[date] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v


# ── AI Parsed Result (pre-confirmation) ──────────────────────────────────────

class AIExtractedExpense(BaseModel):
    """
    Structured output from voice/OCR AI pipeline.
    Returned to frontend for user confirmation before DB write.
    confidence < 0.6 triggers a warning in the UI.
    """
    amount: Optional[Decimal] = None
    category: Optional[ExpenseCategory] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    date: Optional[date] = None
    confidence: float  # 0.0 – 1.0
    raw_text: Optional[str] = None       # original transcription / OCR text
    missing_fields: list[str] = []       # fields the LLM couldn't determine
    suggestions: Optional[str] = None    # LLM's note about ambiguity


class AIExpenseConfirmRequest(BaseModel):
    """
    User-confirmed version of an AI extracted expense.
    All fields required at this stage.
    """
    amount: Decimal
    category: ExpenseCategory
    description: str
    merchant: Optional[str] = None
    date: date
    source: ExpenseSource


# ── Response ──────────────────────────────────────────────────────────────────

class ExpenseResponse(ExpenseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    source: ExpenseSource
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime


# ── List + Pagination ─────────────────────────────────────────────────────────

class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Filters ───────────────────────────────────────────────────────────────────

class ExpenseFilterParams(BaseModel):
    """Query params for GET /expenses — all optional."""
    category: Optional[ExpenseCategory] = None
    source: Optional[ExpenseSource] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = None          # full-text search on description/merchant
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    page: int = 1
    page_size: int = 20

    @model_validator(mode="after")
    def validate_date_range(self) -> "ExpenseFilterParams":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before date_to")
        return self
