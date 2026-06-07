from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense, ExpenseCategory
from app.models.budget import Budget
from app.schemas.dashboard import (
    DashboardMetrics,
    CategoryBreakdown,
    DailyTrend,
    BudgetStatusResponse,
    BudgetResponse,
)
from app.schemas.expense import ExpenseResponse


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_metrics(self, user_id: int) -> DashboardMetrics:
        today = date.today()
        current_month_start = today.replace(day=1)

        # Last month boundaries
        last_month_end = current_month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        # ── Total all-time ────────────────────────────────────────────────────
        total_all_time = await self._sum_expenses(user_id)

        # ── This month ───────────────────────────────────────────────────────
        total_this_month = await self._sum_expenses(
            user_id, date_from=current_month_start, date_to=today
        )

        # ── Last month ───────────────────────────────────────────────────────
        total_last_month = await self._sum_expenses(
            user_id, date_from=last_month_start, date_to=last_month_end
        )

        # ── MoM change ───────────────────────────────────────────────────────
        if total_last_month > 0:
            mom_change = float(
                (total_this_month - total_last_month) / total_last_month * 100
            )
        else:
            mom_change = 100.0 if total_this_month > 0 else 0.0

        # ── Count and average ─────────────────────────────────────────────────
        count_result = await self.db.execute(
            select(func.count()).where(Expense.user_id == user_id)
        )
        total_count = count_result.scalar_one()

        avg_result = await self.db.execute(
            select(func.coalesce(func.avg(Expense.amount), 0)).where(
                Expense.user_id == user_id
            )
        )
        avg_amount = avg_result.scalar_one()

        # ── Category breakdown (all time) ─────────────────────────────────────
        category_breakdown = await self._get_category_breakdown(user_id)

        # ── Daily trend (last 30 days) ────────────────────────────────────────
        thirty_days_ago = today - timedelta(days=29)
        daily_trend = await self._get_daily_trend(user_id, thirty_days_ago, today)

        # ── Recent 5 expenses ─────────────────────────────────────────────────
        recent_result = await self.db.execute(
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(desc(Expense.date), desc(Expense.created_at))
            .limit(5)
        )
        recent_expenses = list(recent_result.scalars().all())

        return DashboardMetrics(
            total_spend_all_time=total_all_time,
            total_spend_this_month=total_this_month,
            total_spend_last_month=total_last_month,
            month_over_month_change=round(mom_change, 1),
            total_expenses_count=total_count,
            average_expense_amount=Decimal(str(round(avg_amount, 2))),
            category_breakdown=category_breakdown,
            daily_trend_30d=daily_trend,
            recent_expenses=recent_expenses,
        )

    async def get_budget_statuses(self, user_id: int) -> list[BudgetStatusResponse]:
        """For each active budget, compute current month's spending vs limit."""
        today = date.today()
        month_start = today.replace(day=1)

        budgets_result = await self.db.execute(
            select(Budget).where(
                and_(Budget.user_id == user_id, Budget.is_active == True)
            )
        )
        budgets = list(budgets_result.scalars().all())

        statuses = []
        for budget in budgets:
            spent = await self._sum_expenses(
                user_id,
                date_from=month_start,
                date_to=today,
                category=budget.category,
            )
            pct = float(spent / budget.monthly_limit * 100) if budget.monthly_limit > 0 else 0.0
            statuses.append(
                BudgetStatusResponse(
                    budget=BudgetResponse.model_validate(budget),
                    spent_this_month=spent,
                    percentage_used=round(pct, 1),
                    is_warning=pct >= 80,
                    is_exceeded=pct >= 100,
                    remaining=max(Decimal("0"), budget.monthly_limit - spent),
                )
            )
        return statuses

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _sum_expenses(
        self,
        user_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        category: ExpenseCategory | None = None,
    ) -> Decimal:
        conditions = [Expense.user_id == user_id]
        if date_from:
            conditions.append(Expense.date >= date_from)
        if date_to:
            conditions.append(Expense.date <= date_to)
        if category:
            conditions.append(Expense.category == category)

        result = await self.db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(*conditions))
        )
        return Decimal(str(result.scalar_one()))

    async def _get_category_breakdown(self, user_id: int) -> list[CategoryBreakdown]:
        result = await self.db.execute(
            select(
                Expense.category,
                func.sum(Expense.amount).label("total"),
                func.count().label("count"),
            )
            .where(Expense.user_id == user_id)
            .group_by(Expense.category)
            .order_by(desc("total"))
        )
        rows = result.all()

        grand_total = sum(row.total for row in rows) or Decimal("1")
        return [
            CategoryBreakdown(
                category=row.category,
                total=Decimal(str(row.total)),
                percentage=round(float(row.total / grand_total * 100), 1),
                count=row.count,
            )
            for row in rows
        ]

    async def _get_daily_trend(
        self, user_id: int, date_from: date, date_to: date
    ) -> list[DailyTrend]:
        result = await self.db.execute(
            select(
                Expense.date.label("day"),
                func.sum(Expense.amount).label("total"),
            )
            .where(
                and_(
                    Expense.user_id == user_id,
                    Expense.date >= date_from,
                    Expense.date <= date_to,
                )
            )
            .group_by(Expense.date)
            .order_by(Expense.date)
        )
        rows = result.all()

        # Fill in zero-spend days so the chart is continuous
        trend_map = {str(row.day): Decimal(str(row.total)) for row in rows}
        trends = []
        current = date_from
        while current <= date_to:
            day_str = str(current)
            trends.append(
                DailyTrend(date=day_str, total=trend_map.get(day_str, Decimal("0")))
            )
            current += timedelta(days=1)

        return trends
