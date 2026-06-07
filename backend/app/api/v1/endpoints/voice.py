import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.ai.speech.voice_pipeline import VoicePipeline
from app.core.dependencies import get_current_active_user
from app.database.session import get_db
from app.models.expense import ExpenseSource
from app.models.user import User
from app.schemas.expense import ExpenseResponse
from app.schemas.voice import VoiceConfirmRequest, VoiceExtractResponse
from app.services.expense_service import ExpenseService
from app.utils.file_validator import validate_audio_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice Expense Entry"])

# Module-level pipeline instance — initialized once, reused across requests
# (avoids re-initializing Gemini model on every request)
_pipeline: VoicePipeline | None = None


def get_pipeline() -> VoicePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = VoicePipeline()
    return _pipeline


@router.post(
    "/process",
    response_model=VoiceExtractResponse,
    summary="Process audio and extract expense data",
    description=(
        "Upload an audio file. Returns extracted expense fields with confidence score. "
        "Nothing is saved to the database — call /voice/confirm after user review."
    ),
)
async def process_voice(
    audio: UploadFile = File(..., description="Audio file (mp3, wav, webm, flac, ogg, m4a)"),
    language: Optional[str] = Form(
        None,
        description="ISO-639-1 language hint for better transcription (e.g. 'en', 'hi', 'ta')",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),  # kept for potential usage logging
) -> VoiceExtractResponse:
    """
    Stage 1 of voice expense entry:
    1. Validate audio file
    2. Transcribe with Whisper
    3. Extract structured fields with Gemini
    4. Score confidence
    5. Return for user review
    """
    # Validate file before sending to AI (saves API cost on invalid uploads)
    audio_bytes = await validate_audio_file(audio)

    logger.info(
        f"Voice process request: user={current_user.id}, "
        f"file={audio.filename}, size={len(audio_bytes)}b, lang={language}"
    )

    try:
        pipeline = get_pipeline()
        result = await pipeline.process(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            language_hint=language,
        )
    except ValueError as e:
        # Whisper rejected the audio
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Voice pipeline unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Voice processing failed. Please try again.",
        )

    return VoiceExtractResponse(
        transcript=result.transcript,
        language=result.language,
        audio_duration_seconds=result.audio_duration_seconds,
        amount=result.amount,
        category=result.category,
        description=result.description,
        merchant=result.merchant,
        date=result.date,
        confidence=result.confidence,
        missing_fields=result.missing_fields,
        low_confidence_fields=result.low_confidence_fields,
        suggestions=result.suggestions,
        extraction_notes=result.extraction_notes,
        needs_review=result.needs_review,
        is_empty_audio=result.is_empty_audio,
    )


@router.post(
    "/confirm",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a reviewed voice expense to the database",
    description=(
        "Called after the user reviews and confirms the extracted expense. "
        "Saves to DB with source=VOICE and the original AI confidence score."
    ),
)
async def confirm_voice_expense(
    data: VoiceConfirmRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseResponse:
    """
    Stage 2 of voice expense entry:
    User has reviewed the extracted data, optionally edited fields,
    and confirmed. Now we save to DB.
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
            "source":      ExpenseSource.VOICE,
        },
        confidence=data.original_confidence,
    )

    logger.info(
        f"Voice expense saved: user={current_user.id}, "
        f"expense_id={expense.id}, amount={expense.amount}, "
        f"confidence={data.original_confidence:.2f}"
    )

    return expense
