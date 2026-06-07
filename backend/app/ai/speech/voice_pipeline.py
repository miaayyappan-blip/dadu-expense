import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.ai.extraction.local_extractor import LocalExtractor
from app.ai.extraction.confidence_scorer import ConfidenceBreakdown, ConfidenceScorer
from app.ai.extraction.gemini_extractor import GeminiExtractor
from app.ai.speech.whisper_service import WhisperService, TranscriptionResult
from app.models.expense import ExpenseCategory

logger = logging.getLogger(__name__)


@dataclass
class VoiceProcessingResult:
    """
    Full result of the voice pipeline.
    Returned to the frontend for user review — nothing is saved yet.
    """
    # Transcription
    transcript: str
    language: str
    audio_duration_seconds: Optional[float]

    # Extracted fields (all Optional — user fills in what's missing)
    amount: Optional[Decimal]
    category: Optional[ExpenseCategory]
    description: Optional[str]
    merchant: Optional[str]
    date: Optional[date]

    # Confidence
    confidence: float
    missing_fields: list[str]
    low_confidence_fields: list[str]
    suggestions: str

    # Flags
    needs_review: bool          # True if confidence < 0.85
    is_empty_audio: bool        # True if Whisper returned noise/silence
    extraction_notes: Optional[str]  # LLM's own ambiguity notes


class VoicePipeline:
    """
    Orchestrates the full voice-to-expense pipeline:
    
        Audio bytes
            ↓ WhisperService.transcribe()
        Transcript
            ↓ GeminiExtractor.extract()
        Raw field dict
            ↓ ConfidenceScorer.score()
        VoiceProcessingResult (returned to frontend for review)
    
    The pipeline is deliberately fault-tolerant:
    - If Whisper fails → raises (no point continuing)
    - If Gemini fails → returns low-confidence result with empty fields
    - If scoring fails → defaults to 0.0 confidence (always triggers review)
    
    NOTHING is written to the database here. The API endpoint
    returns this result; a separate /confirm endpoint saves to DB.
    """

    # Below this threshold, frontend shows a mandatory review dialog
    REVIEW_THRESHOLD = 0.85

    def __init__(self):
        self.whisper = WhisperService()
        try:
            self.extractor = GeminiExtractor()
        except Exception:
            logger.warning("Gemini unavailable, using LocalExtractor")
            self.extractor = LocalExtractor()
        self.scorer = ConfidenceScorer()

    async def process(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        language_hint: Optional[str] = None,
    ) -> VoiceProcessingResult:
        """
        Run the full pipeline on raw audio bytes.
        
        Args:
            audio_bytes: Validated audio file content
            filename: Original filename for format detection
            language_hint: ISO-639-1 code (e.g. "en", "hi") for Whisper accuracy
        """
        today = date.today()

        # ── Stage 1: Transcription ────────────────────────────────────────────
        logger.info("Voice pipeline: starting transcription")
        transcription: TranscriptionResult = await self.whisper.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language_hint,
        )

        # Empty audio — return early with a clear signal
        if transcription.is_empty:
            logger.warning("Voice pipeline: empty/noise audio detected")
            return VoiceProcessingResult(
                transcript=transcription.text,
                language=transcription.language,
                audio_duration_seconds=transcription.duration_seconds,
                amount=None,
                category=None,
                description=None,
                merchant=None,
                date=None,
                confidence=0.0,
                missing_fields=["amount", "category", "description", "date"],
                low_confidence_fields=[],
                suggestions=(
                    "The audio appears to be empty or contains only noise. "
                    "Please try recording again in a quieter environment."
                ),
                needs_review=True,
                is_empty_audio=True,
                extraction_notes=None,
            )

        # ── Stage 2: LLM Extraction ───────────────────────────────────────────
        logger.info(f"Voice pipeline: extracting from transcript: '{transcription.text[:80]}...'")
        try:
            extracted = await self.extractor.extract(transcription.text)
        except Exception as e:
            logger.warning(
                f"Gemini failed, falling back to LocalExtractor: {e}"
            )

            local = LocalExtractor()
            extracted = local.extract(transcription.text)

        # ── Stage 3: Defaults for missing optional fields ─────────────────────
        # Date defaults to today when not mentioned (logged in confidence scorer)
        expense_date = extracted.get("date") or today

        # ── Stage 4: Confidence scoring ───────────────────────────────────────
        try:
            breakdown: ConfidenceBreakdown = self.scorer.score(
                amount=extracted.get("amount"),
                category=extracted.get("category"),
                description=extracted.get("description"),
                merchant=extracted.get("merchant"),
                expense_date=expense_date,
                raw_text=transcription.text,
            )
        except Exception as e:
            logger.error(f"Voice pipeline: confidence scoring failed: {e}")
            breakdown = ConfidenceBreakdown(
                score=0.0,
                missing_fields=["amount", "category"],
                low_confidence_fields=[],
                suggestions="Could not score extraction. Please review all fields.",
                field_scores={},
            )

        logger.info(
            f"Voice pipeline complete: confidence={breakdown.score}, "
            f"missing={breakdown.missing_fields}"
        )

        return VoiceProcessingResult(
            transcript=transcription.text,
            language=transcription.language,
            audio_duration_seconds=transcription.duration_seconds,
            amount=extracted.get("amount"),
            category=extracted.get("category"),
            description=extracted.get("description"),
            merchant=extracted.get("merchant"),
            date=expense_date,
            confidence=breakdown.score,
            missing_fields=breakdown.missing_fields,
            low_confidence_fields=breakdown.low_confidence_fields,
            suggestions=breakdown.suggestions,
            needs_review=breakdown.score < self.REVIEW_THRESHOLD,
            is_empty_audio=False,
            extraction_notes=extracted.get("extraction_notes"),
        )

    def _build_extraction_failure_result(
        self, transcription: TranscriptionResult, error: str
    ) -> VoiceProcessingResult:
        """Returns a degraded result when Gemini fails — lets user fill in manually."""
        return VoiceProcessingResult(
            transcript=transcription.text,
            language=transcription.language,
            audio_duration_seconds=transcription.duration_seconds,
            amount=None,
            category=None,
            description=transcription.text[:200] if transcription.text else None,
            merchant=None,
            date=date.today(),
            confidence=0.1,
            missing_fields=["amount", "category", "description", "merchant", "date"],
            low_confidence_fields=[],
            suggestions=(
                f"Transcription succeeded but extraction failed. "
                f"Your transcript: \"{transcription.text[:100]}\". "
                f"Please fill in the expense details manually."
            ),
            needs_review=True,
            is_empty_audio=False,
            extraction_notes=f"Extraction error: {error}",
        )
