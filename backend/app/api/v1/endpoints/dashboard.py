from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.expense import ExpenseCategory
from app.models.user import User
from app.schemas.dashboard import (
    BudgetCreateRequest,
    BudgetStatusResponse,
    DashboardMetrics,
)
from app.schemas.user import MessageResponse
from app.services.budget_service import BudgetService
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard & Budgets"])


@router.get(
    "/dashboard",
    response_model=DashboardMetrics,
    summary="Get full dashboard metrics and charts data",
)
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardMetrics:
    service = DashboardService(db)
    return await service.get_metrics(current_user.id)


@router.get(
    "/budgets/status",
    response_model=list[BudgetStatusResponse],
    summary="Get all active budgets with current month spending status",
)
async def get_budget_statuses(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetStatusResponse]:
    service = DashboardService(db)
    return await service.get_budget_statuses(current_user.id)


@router.post(
    "/budgets",
    response_model=BudgetStatusResponse,
    summary="Create or update a category budget",
)
async def upsert_budget(
    data: BudgetCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetStatusResponse:
    budget_service = BudgetService(db)
    await budget_service.upsert(current_user.id, data)

    # Return enriched status immediately
    dashboard_service = DashboardService(db)
    statuses = await dashboard_service.get_budget_statuses(current_user.id)
    return next(s for s in statuses if s.budget.category == data.category)


@router.delete(
    "/budgets/{category}",
    response_model=MessageResponse,
    summary="Delete a category budget",
)
async def delete_budget(
    category: ExpenseCategory,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = BudgetService(db)
    await service.delete(current_user.id, category)
    return MessageResponse(message=f"Budget for {category} deleted")
