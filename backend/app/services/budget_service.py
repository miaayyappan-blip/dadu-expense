from fastapi import HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.expense import ExpenseCategory
from app.schemas.dashboard import BudgetCreateRequest


class BudgetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, user_id: int, data: BudgetCreateRequest) -> Budget:
        """
        Create or update a budget for a category.
        Upsert pattern: one budget per category per user (enforced by DB constraint too).
        """
        result = await self.db.execute(
            select(Budget).where(
                and_(Budget.user_id == user_id, Budget.category == data.category)
            )
        )
        budget = result.scalar_one_or_none()

        if budget:
            budget.monthly_limit = data.monthly_limit
            budget.is_active = True
        else:
            budget = Budget(
                user_id=user_id,
                category=data.category,
                monthly_limit=data.monthly_limit,
            )
            self.db.add(budget)

        await self.db.flush()
        await self.db.refresh(budget)
        return budget

    async def delete(self, user_id: int, category: ExpenseCategory) -> None:
        result = await self.db.execute(
            select(Budget).where(
                and_(Budget.user_id == user_id, Budget.category == category)
            )
        )
        budget = result.scalar_one_or_none()
        if not budget:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
        await self.db.delete(budget)

    async def list_budgets(self, user_id: int) -> list[Budget]:
        result = await self.db.execute(
            select(Budget).where(
                and_(Budget.user_id == user_id, Budget.is_active == True)
            )
        )
        return list(result.scalars().all())
