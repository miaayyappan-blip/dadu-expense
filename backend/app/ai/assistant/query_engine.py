import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, func, and_, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.assistant.date_resolver import DateRange, DateResolver
from app.ai.assistant.intent_classifier import ClassifiedIntent, QueryIntent
from app.models.budget import Budget
from app.models.expense import Expense, ExpenseCategory

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """
    Structured data returned from a safe DB query.
    Passed to the response generator — never used for control flow.
    """
    intent: QueryIntent
    data: dict[str, Any]           # structured numbers/lists for the response generator
    date_range: DateRange
    found_results: bool
    row_count: int


class QueryEngine:
    """
    Executes safe, parameterized DB queries based on classified intent.

    Security guarantees:
    1. User input NEVER reaches this class — only validated ClassifiedIntent fields
    2. Every query is explicitly scoped to user_id (row-level security)
    3. All string values used as ILIKE patterns, not string interpolation
    4. All queries use SQLAlchemy's parameterized API — no raw SQL
    5. Result counts are capped — no unbounded queries
    6. UNKNOWN intent returns immediately without any DB access

    Query templates (one per QueryIntent):
        TOTAL_SPEND_PERIOD    → SUM(amount) WHERE user_id AND date IN range
        CATEGORY_SPEND_PERIOD → SUM(amount) WHERE user_id AND category AND date IN range
        TOP_EXPENSES          → SELECT TOP N WHERE user_id AND date IN range ORDER BY amount DESC
        CATEGORY_COMPARISON   → SUM per category WHERE user_id AND date IN range
        SPENDING_TREND        → SUM current period vs SUM previous period
        MERCHANT_SPEND        → SUM + list WHERE user_id AND merchant ILIKE pattern
        RECENT_EXPENSES       → SELECT TOP N WHERE user_id ORDER BY date DESC
        BUDGET_STATUS         → JOIN budgets + expenses for current month
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.date_resolver = DateResolver()

    async def execute(
        self, intent: ClassifiedIntent, user_id: int
    ) -> QueryResult:
        """
        Route to the correct query template based on intent.
        user_id is always passed separately from intent — never from LLM output.
        """
        if intent.intent == QueryIntent.UNKNOWN:
            return QueryResult(
                intent=QueryIntent.UNKNOWN,
                data={},
                date_range=self.date_resolver.resolve(intent.time_period),
                found_results=False,
                row_count=0,
            )

        date_range = self.date_resolver.resolve(intent.time_period)

        logger.info(
            f"Executing query: intent={intent.intent.value}, "
            f"user={user_id}, period={date_range.label}, "
            f"category={intent.category}"
        )

        match intent.intent:
            case QueryIntent.TOTAL_SPEND_PERIOD:
                return await self._total_spend(user_id, date_range, intent)

            case QueryIntent.CATEGORY_SPEND_PERIOD:
                return await self._category_spend(user_id, date_range, intent)

            case QueryIntent.TOP_EXPENSES:
                return await self._top_expenses(user_id, date_range, intent)

            case QueryIntent.CATEGORY_COMPARISON:
                return await self._category_comparison(user_id, date_range, intent)

            case QueryIntent.SPENDING_TREND:
                return await self._spending_trend(user_id, intent)

            case QueryIntent.MERCHANT_SPEND:
                return await self._merchant_spend(user_id, date_range, intent)

            case QueryIntent.RECENT_EXPENSES:
                return await self._recent_expenses(user_id, intent)

            case QueryIntent.BUDGET_STATUS:
                return await self._budget_status(user_id, intent)

            case _:
                return self._empty_result(QueryIntent.UNKNOWN, date_range)

    # ── Query templates ───────────────────────────────────────────────────────

    async def _total_spend(
        self, user_id: int, dr: DateRange, intent: ClassifiedIntent
    ) -> QueryResult:
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
                func.count().label("count"),
            ).where(and_(
                Expense.user_id == user_id,
                Expense.date >= dr.start,
                Expense.date <= dr.end,
            ))
        )
        row = result.one()
        total = float(row.total)
        return QueryResult(
            intent=intent.intent,
            data={"total": total, "count": row.count, "period": str(dr)},
            date_range=dr,
            found_results=row.count > 0,
            row_count=row.count,
        )

    async def _category_spend(
        self, user_id: int, dr: DateRange, intent: ClassifiedIntent
    ) -> QueryResult:
        conditions = [
            Expense.user_id == user_id,
            Expense.date >= dr.start,
            Expense.date <= dr.end,
        ]
        if intent.category:
            conditions.append(Expense.category == intent.category)

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
                func.count().label("count"),
                func.coalesce(func.avg(Expense.amount), 0).label("avg"),
            ).where(and_(*conditions))
        )
        row = result.one()

        # Also fetch top merchants for this category
        merchants = await self.db.execute(
            select(
                Expense.merchant,
                func.sum(Expense.amount).label("total"),
            ).where(
                and_(*conditions, Expense.merchant.isnot(None))
            ).group_by(Expense.merchant)
            .order_by(desc("total"))
            .limit(3)
        )

        return QueryResult(
            intent=intent.intent,
            data={
                "total": float(row.total),
                "count": row.count,
                "avg": float(row.avg),
                "category": intent.category.value if intent.category else "all",
                "period": str(dr),
                "top_merchants": [
                    {"merchant": r.merchant, "total": float(r.total)}
                    for r in merchants.all()
                ],
            },
            date_range=dr,
            found_results=row.count > 0,
            row_count=row.count,
        )

    async def _top_expenses(
        self, user_id: int, dr: DateRange, intent: ClassifiedIntent
    ) -> QueryResult:
        limit = min(intent.limit, 10)  # hard cap
        conditions = [
            Expense.user_id == user_id,
            Expense.date >= dr.start,
            Expense.date <= dr.end,
        ]
        if intent.category:
            conditions.append(Expense.category == intent.category)

        result = await self.db.execute(
            select(Expense)
            .where(and_(*conditions))
            .order_by(desc(Expense.amount))
            .limit(limit)
        )
        expenses = result.scalars().all()

        return QueryResult(
            intent=intent.intent,
            data={
                "expenses": [
                    {
                        "date": str(e.date),
                        "amount": float(e.amount),
                        "description": e.description,
                        "category": e.category.value,
                        "merchant": e.merchant,
                    }
                    for e in expenses
                ],
                "period": str(dr),
                "limit": limit,
            },
            date_range=dr,
            found_results=len(expenses) > 0,
            row_count=len(expenses),
        )

    async def _category_comparison(
        self, user_id: int, dr: DateRange, intent: ClassifiedIntent
    ) -> QueryResult:
        # Use compare_categories if provided, else all categories
        categories = intent.compare_categories or [c.value for c in ExpenseCategory]

        result = await self.db.execute(
            select(
                Expense.category,
                func.sum(Expense.amount).label("total"),
                func.count().label("count"),
            ).where(and_(
                Expense.user_id == user_id,
                Expense.date >= dr.start,
                Expense.date <= dr.end,
                Expense.category.in_(categories),
            ))
            .group_by(Expense.category)
            .order_by(desc("total"))
        )
        rows = result.all()

        grand_total = sum(float(r.total) for r in rows) or 1.0

        return QueryResult(
            intent=intent.intent,
            data={
                "categories": [
                    {
                        "category": r.category.value,
                        "total": float(r.total),
                        "count": r.count,
                        "percentage": round(float(r.total) / grand_total * 100, 1),
                    }
                    for r in rows
                ],
                "period": str(dr),
                "grand_total": grand_total,
            },
            date_range=dr,
            found_results=len(rows) > 0,
            row_count=len(rows),
        )

    async def _spending_trend(
        self, user_id: int, intent: ClassifiedIntent
    ) -> QueryResult:
        current_dr, prev_dr = self.date_resolver.resolve_comparison_periods(
            intent.time_period
        )

        async def _sum(dr: DateRange) -> float:
            r = await self.db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(
                    Expense.user_id == user_id,
                    Expense.date >= dr.start,
                    Expense.date <= dr.end,
                ))
            )
            return float(r.scalar_one())

        current_total = await _sum(current_dr)
        prev_total = await _sum(prev_dr)

        change_pct = (
            ((current_total - prev_total) / prev_total * 100)
            if prev_total > 0 else (100.0 if current_total > 0 else 0.0)
        )

        return QueryResult(
            intent=intent.intent,
            data={
                "current_total": current_total,
                "previous_total": prev_total,
                "change_amount": current_total - prev_total,
                "change_percent": round(change_pct, 1),
                "is_increase": current_total > prev_total,
                "current_period": str(current_dr),
                "previous_period": str(prev_dr),
            },
            date_range=current_dr,
            found_results=current_total > 0 or prev_total > 0,
            row_count=2,
        )

    async def _merchant_spend(
        self, user_id: int, dr: DateRange, intent: ClassifiedIntent
    ) -> QueryResult:
        if not intent.merchant:
            return self._empty_result(intent.intent, dr)

        # ILIKE with parameterized binding — not string interpolation
        pattern = f"%{intent.merchant}%"
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
                func.count().label("count"),
                Expense.merchant,
            ).where(and_(
                Expense.user_id == user_id,
                Expense.date >= dr.start,
                Expense.date <= dr.end,
                Expense.merchant.ilike(pattern),
            ))
            .group_by(Expense.merchant)
            .order_by(desc("total"))
            .limit(5)
        )
        rows = result.all()

        grand_total = sum(float(r.total) for r in rows)
        count = sum(r.count for r in rows)

        return QueryResult(
            intent=intent.intent,
            data={
                "merchant_query": intent.merchant,
                "total": grand_total,
                "count": count,
                "matched_merchants": [
                    {"merchant": r.merchant, "total": float(r.total), "count": r.count}
                    for r in rows
                ],
                "period": str(dr),
            },
            date_range=dr,
            found_results=count > 0,
            row_count=count,
        )

    async def _recent_expenses(
        self, user_id: int, intent: ClassifiedIntent
    ) -> QueryResult:
        limit = min(intent.limit, 10)
        dr = self.date_resolver.resolve(intent.time_period)

        result = await self.db.execute(
            select(Expense)
            .where(and_(
                Expense.user_id == user_id,
                Expense.date >= dr.start,
            ))
            .order_by(desc(Expense.date), desc(Expense.created_at))
            .limit(limit)
        )
        expenses = result.scalars().all()

        return QueryResult(
            intent=intent.intent,
            data={
                "expenses": [
                    {
                        "date": str(e.date),
                        "amount": float(e.amount),
                        "description": e.description,
                        "category": e.category.value,
                        "merchant": e.merchant,
                        "source": e.source.value,
                    }
                    for e in expenses
                ],
                "limit": limit,
            },
            date_range=dr,
            found_results=len(expenses) > 0,
            row_count=len(expenses),
        )

    async def _budget_status(
        self, user_id: int, intent: ClassifiedIntent
    ) -> QueryResult:
        today = date.today()
        month_start = today.replace(day=1)
        dr = DateRange(month_start, today, "this month")

        # Get all budgets (or specific category)
        budget_conditions = [Budget.user_id == user_id, Budget.is_active == True]
        if intent.category:
            budget_conditions.append(Budget.category == intent.category)

        budgets_result = await self.db.execute(
            select(Budget).where(and_(*budget_conditions))
        )
        budgets = budgets_result.scalars().all()

        budget_statuses = []
        for budget in budgets:
            spent_result = await self.db.execute(
                select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(
                    Expense.user_id == user_id,
                    Expense.category == budget.category,
                    Expense.date >= month_start,
                    Expense.date <= today,
                ))
            )
            spent = float(spent_result.scalar_one())
            limit_val = float(budget.monthly_limit)
            pct = round(spent / limit_val * 100, 1) if limit_val > 0 else 0.0

            budget_statuses.append({
                "category": budget.category.value,
                "limit": limit_val,
                "spent": spent,
                "remaining": max(0.0, limit_val - spent),
                "percentage": pct,
                "is_exceeded": pct >= 100,
                "is_warning": pct >= 80,
            })

        return QueryResult(
            intent=intent.intent,
            data={"budgets": budget_statuses, "period": "this month"},
            date_range=dr,
            found_results=len(budget_statuses) > 0,
            row_count=len(budget_statuses),
        )

    def _empty_result(self, intent: QueryIntent, dr: DateRange) -> QueryResult:
        return QueryResult(
            intent=intent, data={}, date_range=dr,
            found_results=False, row_count=0,
        )
