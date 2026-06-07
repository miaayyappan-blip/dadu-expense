import math
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.schemas.expense import (
    ExpenseCreateRequest,
    ExpenseUpdateRequest,
    ExpenseListResponse,
    ExpenseFilterParams,
)


class ExpenseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: int, data: ExpenseCreateRequest) -> Expense:
        expense = Expense(
            user_id=user_id,
            amount=data.amount,
            category=data.category,
            description=data.description,
            merchant=data.merchant,
            source=data.source,
            date=data.date,
        )
        self.db.add(expense)
        await self.db.flush()
        await self.db.refresh(expense)
        return expense

    async def create_from_ai(
        self,
        user_id: int,
        data: dict,
        confidence: float,
    ) -> Expense:
        """Create expense from confirmed AI extraction, storing confidence score."""
        from app.schemas.expense import ExpenseCreateRequest
        expense = Expense(
            user_id=user_id,
            amount=data["amount"],
            category=data["category"],
            description=data["description"],
            merchant=data.get("merchant"),
            source=data["source"],
            date=data["date"],
            confidence=confidence,
        )
        self.db.add(expense)
        await self.db.flush()
        await self.db.refresh(expense)
        return expense

    async def get_by_id(self, expense_id: int, user_id: int) -> Expense:
        """Fetch a single expense. Enforces ownership — users can't see other users' data."""
        result = await self.db.execute(
            select(Expense).where(
                and_(Expense.id == expense_id, Expense.user_id == user_id)
            )
        )
        expense = result.scalar_one_or_none()
        if not expense:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Expense not found",
            )
        return expense

    async def update(
        self, expense_id: int, user_id: int, data: ExpenseUpdateRequest
    ) -> Expense:
        expense = await self.get_by_id(expense_id, user_id)

        # Only update fields that were explicitly provided (PATCH semantics)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(expense, field, value)

        await self.db.flush()
        await self.db.refresh(expense)
        return expense

    async def delete(self, expense_id: int, user_id: int) -> None:
        expense = await self.get_by_id(expense_id, user_id)
        await self.db.delete(expense)

    async def list_expenses(
        self, user_id: int, filters: ExpenseFilterParams
    ) -> ExpenseListResponse:
        """
        Paginated, filtered expense list.
        Uses COUNT + SELECT in parallel via two queries to avoid subquery overhead.
        """
        # Build WHERE conditions dynamically
        conditions = [Expense.user_id == user_id]

        if filters.category:
            conditions.append(Expense.category == filters.category)
        if filters.source:
            conditions.append(Expense.source == filters.source)
        if filters.date_from:
            conditions.append(Expense.date >= filters.date_from)
        if filters.date_to:
            conditions.append(Expense.date <= filters.date_to)
        if filters.min_amount:
            conditions.append(Expense.amount >= filters.min_amount)
        if filters.max_amount:
            conditions.append(Expense.amount <= filters.max_amount)
        if filters.search:
            search_term = f"%{filters.search}%"
            conditions.append(
                or_(
                    Expense.description.ilike(search_term),
                    Expense.merchant.ilike(search_term),
                )
            )

        where_clause = and_(*conditions)

        # Count query
        count_result = await self.db.execute(
            select(func.count()).select_from(Expense).where(where_clause)
        )
        total = count_result.scalar_one()

        # Data query with pagination
        offset = (filters.page - 1) * filters.page_size
        result = await self.db.execute(
            select(Expense)
            .where(where_clause)
            .order_by(desc(Expense.date), desc(Expense.created_at))
            .offset(offset)
            .limit(filters.page_size)
        )
        expenses = list(result.scalars().all())

        return ExpenseListResponse(
            items=expenses,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=math.ceil(total / filters.page_size) if total > 0 else 0,
        )

    async def get_monthly_total(
        self, user_id: int, year: int, month: int, category=None
    ) -> Decimal:
        """Used by budget alerts and dashboard."""
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)

        conditions = [
            Expense.user_id == user_id,
            Expense.date >= start,
            Expense.date <= end,
        ]
        if category:
            conditions.append(Expense.category == category)

        result = await self.db.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(*conditions))
        )
        return result.scalar_one()
