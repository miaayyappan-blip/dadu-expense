import io
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.services.export_service import ExportService
from app.services.csv_generator import generate_csv
from app.services.pdf_generator import generate_pdf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["Export"])


def _date_range_filename(prefix: str, ext: str, date_from=None, date_to=None) -> str:
    """Build a descriptive filename like: expenses_2026-06-01_to_2026-06-30.csv"""
    if date_from and date_to:
        return f"{prefix}_{date_from}_to_{date_to}.{ext}"
    elif date_from:
        return f"{prefix}_from_{date_from}.{ext}"
    else:
        return f"{prefix}_all_time.{ext}"


@router.get(
    "/csv",
    summary="Export all expenses as CSV",
    description=(
        "Returns a UTF-8 CSV file with all expenses for the authenticated user. "
        "Includes a summary section at the bottom. "
        "Excel-compatible (UTF-8 BOM, ₹ symbol preserved)."
    ),
    response_class=StreamingResponse,
)
async def export_csv(
    date_from: Optional[date] = Query(None, description="Filter from this date (YYYY-MM-DD)"),
    date_to:   Optional[date] = Query(None, description="Filter to this date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"CSV export: user={current_user.id}, from={date_from}, to={date_to}")

    service = ExportService(db)
    summary = await service.get_export_data(
        user_id=current_user.id,
        user_name=current_user.full_name,
        date_from=date_from,
        date_to=date_to,
    )

    try:
        csv_bytes = generate_csv(summary)
    except Exception as e:
        logger.exception(f"CSV generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate CSV export",
        )

    filename = _date_range_filename("expenses", "csv", date_from, date_to)

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={
            # attachment triggers browser download dialog
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(csv_bytes)),
        },
    )


@router.get(
    "/pdf",
    summary="Export expense report as PDF",
    description=(
        "Returns a formatted PDF report with summary stats, "
        "category breakdown, and full expense list. "
        "Includes page numbers and user name in footer."
    ),
    response_class=StreamingResponse,
)
async def export_pdf(
    date_from: Optional[date] = Query(None, description="Filter from this date (YYYY-MM-DD)"),
    date_to:   Optional[date] = Query(None, description="Filter to this date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"PDF export: user={current_user.id}, from={date_from}, to={date_to}")

    service = ExportService(db)
    summary = await service.get_export_data(
        user_id=current_user.id,
        user_name=current_user.full_name,
        date_from=date_from,
        date_to=date_to,
    )

    try:
        pdf_bytes = generate_pdf(summary)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"PDF generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate PDF report",
        )

    filename = _date_range_filename("expense_report", "pdf", date_from, date_to)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
