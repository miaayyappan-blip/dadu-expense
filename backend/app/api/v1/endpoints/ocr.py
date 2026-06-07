import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.ocr.ocr_pipeline import OcrPipeline
from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.expense import ExpenseSource
from app.models.user import User
from app.schemas.expense import ExpenseResponse
from app.schemas.ocr import OcrConfirmRequest, OcrExtractResponse
from app.services.expense_service import ExpenseService
from app.utils.file_validator import validate_image_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["Receipt OCR"])

# Module-level singleton — PaddleOCR model loaded once
_pipeline: OcrPipeline | None = None


def get_pipeline() -> OcrPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = OcrPipeline()
    return _pipeline


@router.post(
    "/process",
    response_model=OcrExtractResponse,
    summary="Scan a receipt image and extract expense data",
    description=(
        "Upload a receipt photo. Returns extracted fields with confidence score. "
        "Nothing is saved — call /ocr/confirm after user review."
    ),
)
async def process_receipt(
    image: UploadFile = File(
        ...,
        description="Receipt image (jpeg, png, webp). Max 10MB.",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> OcrExtractResponse:
    """
    Stage 1 — Receipt scanning:
    1. Validate image file
    2. Preprocess (enhance contrast, correct rotation)
    3. PaddleOCR text extraction
    4. Gemini structured extraction
    5. Confidence scoring
    6. Return for user review
    """
    image_bytes = await validate_image_file(image)

    logger.info(
        f"OCR process: user={current_user.id}, "
        f"file={image.filename}, size={len(image_bytes)}b"
    )

    try:
        pipeline = get_pipeline()
        result = await pipeline.process(image_bytes)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"OCR pipeline unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Receipt processing failed. Please try again with a clearer image.",
        )

    return OcrExtractResponse(
        raw_ocr_text=result.raw_ocr_text,
        ocr_line_count=result.ocr_line_count,
        ocr_quality=result.ocr_quality,
        image_quality_score=result.image_quality_score,
        was_image_enhanced=result.was_image_enhanced,
        is_partial_receipt=result.is_partial_receipt,
        items_detected=result.items_detected,
        amount=result.amount,
        category=result.category,
        description=result.description,
        merchant=result.merchant,
        date=result.date,
        confidence=result.confidence,
        ocr_confidence_score=result.ocr_confidence_score,
        extraction_score=result.extraction_score,
        missing_fields=result.missing_fields,
        low_confidence_fields=result.low_confidence_fields,
        suggestions=result.suggestions,
        extraction_notes=result.extraction_notes,
        amount_warning=result.amount_warning,
        date_warning=result.date_warning,
        needs_review=result.needs_review,
        is_empty_image=result.is_empty_image,
    )


@router.post(
    "/confirm",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a reviewed OCR expense to the database",
)
async def confirm_ocr_expense(
    data: OcrConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseResponse:
    """
    Stage 2 — Save confirmed receipt expense.
    User has reviewed and edited any fields. Now persists to DB with source=OCR.
    """
    service = ExpenseService(db)
    expense = await service.create_from_ai(
        user_id=current_user.id,
        data={
            "amount":      data.amount,
            "category":    data.category,
            "description": data.description,
            "merchant":    data.merchant,
            "date":        data.date,
            "source":      ExpenseSource.OCR,
        },
        confidence=data.original_confidence,
    )

    logger.info(
        f"OCR expense saved: user={current_user.id}, "
        f"expense_id={expense.id}, amount={expense.amount}, "
        f"confidence={data.original_confidence:.2f}"
    )

    return expense
