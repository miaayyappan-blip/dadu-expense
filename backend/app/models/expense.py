import enum
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Text, Numeric, Date, DateTime, ForeignKey,
    Enum as SAEnum, Float, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class ExpenseSource(str, enum.Enum):
    """How the expense was entered. Used for analytics and UI display."""
    VOICE = "VOICE"
    OCR = "OCR"
    MANUAL = "MANUAL"


class ExpenseCategory(str, enum.Enum):
    """
    Fixed category set — allows reliable aggregation and budget matching.
    'Other' is the catch-all for LLM uncertainty.
    """
    FOOD = "Food"
    TRANSPORT = "Transport"
    SHOPPING = "Shopping"
    ENTERTAINMENT = "Entertainment"
    HEALTH = "Health"
    UTILITIES = "Utilities"
    EDUCATION = "Education"
    TRAVEL = "Travel"
    OTHER = "Other"


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        SAEnum(ExpenseCategory, name="expense_category"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[ExpenseSource] = mapped_column(
        SAEnum(ExpenseSource, name="expense_source"),
        default=ExpenseSource.MANUAL,
        nullable=False,
    )

    # Date the expense actually occurred (not when it was entered)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # AI confidence score — stored for transparency and filtering
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="expenses", lazy="noload")

    # Composite index for the most common query: user's expenses in a date range
    __table_args__ = (
        Index("ix_expenses_user_date", "user_id", "date"),
        Index("ix_expenses_user_category", "user_id", "category"),
    )

    def __repr__(self) -> str:
        return f"<Expense id={self.id} amount={self.amount} category={self.category}>"
