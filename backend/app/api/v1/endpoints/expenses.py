from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date
from decimal import Decimal

from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.expense import ExpenseCategory, ExpenseSource
from app.models.user import User
from app.schemas.expense import (
    ExpenseCreateRequest,
    ExpenseFilterParams,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseUpdateRequest,
)
from app.schemas.user import MessageResponse
from app.services.expense_service import ExpenseService

router = APIRouter(prefix="/expenses", tags=["Expenses"])


@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually create an expense",
)
async def create_expense(
    data: ExpenseCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseResponse:
    service = ExpenseService(db)
    return await service.create(current_user.id, data)


@router.get(
    "",
    response_model=ExpenseListResponse,
    summary="List expenses with filtering and pagination",
)
async def list_expenses(
    # All filter params come from query string
    category: Optional[ExpenseCategory] = Query(None),
    source: Optional[ExpenseSource] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    search: Optional[str] = Query(None, min_length=1, max_length=100),
    min_amount: Optional[Decimal] = Query(None, gt=0),
    max_amount: Optional[Decimal] = Query(None, gt=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseListResponse:
    filters = ExpenseFilterParams(
        category=category,
        source=source,
        date_from=date_from,
        date_to=date_to,
        search=search,
        min_amount=min_amount,
        max_amount=max_amount,
        page=page,
        page_size=page_size,
    )
    service = ExpenseService(db)
    return await service.list_expenses(current_user.id, filters)


@router.get(
    "/{expense_id}",
    response_model=ExpenseResponse,
    summary="Get a single expense by ID",
)
async def get_expense(
    expense_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseResponse:
    service = ExpenseService(db)
    return await service.get_by_id(expense_id, current_user.id)


@router.patch(
    "/{expense_id}",
    response_model=ExpenseResponse,
    summary="Update an expense (partial update)",
)
async def update_expense(
    expense_id: int,
    data: ExpenseUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseResponse:
    service = ExpenseService(db)
    return await service.update(expense_id, current_user.id, data)


@router.delete(
    "/{expense_id}",
    response_model=MessageResponse,
    summary="Delete an expense",
)
async def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = ExpenseService(db)
    await service.delete(expense_id, current_user.id)
    return MessageResponse(message="Expense deleted successfully")
