from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.expense import ExpenseCategory
from app.schemas.expense import ExpenseResponse


# ── Dashboard ─────────────────────────────────────────────────────────────────

class CategoryBreakdown(BaseModel):
    category: ExpenseCategory
    total: Decimal
    percentage: float
    count: int


class DailyTrend(BaseModel):
    date: str        # ISO format YYYY-MM-DD
    total: Decimal


class DashboardMetrics(BaseModel):
    total_spend_all_time: Decimal
    total_spend_this_month: Decimal
    total_spend_last_month: Decimal
    month_over_month_change: float      # percentage change
    total_expenses_count: int
    average_expense_amount: Decimal
    category_breakdown: list[CategoryBreakdown]
    daily_trend_30d: list[DailyTrend]
    recent_expenses: list[ExpenseResponse]


# ── Budget ────────────────────────────────────────────────────────────────────

class BudgetCreateRequest(BaseModel):
    category: ExpenseCategory
    monthly_limit: Decimal


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: ExpenseCategory
    monthly_limit: Decimal
    is_active: bool


class BudgetStatusResponse(BaseModel):
    """Enriched budget response with current month's spending."""
    budget: BudgetResponse
    spent_this_month: Decimal
    percentage_used: float
    is_warning: bool      # >= 80%
    is_exceeded: bool     # >= 100%
    remaining: Decimal


# ── AI Assistant ──────────────────────────────────────────────────────────────

class AssistantQueryRequest(BaseModel):
    query: str


class AssistantQueryResponse(BaseModel):
    answer: str
    data: Optional[dict] = None      # structured data if applicable
    query_type: str                   # "summary" | "comparison" | "search" | "trend"
