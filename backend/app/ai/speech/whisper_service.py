import io
import logging
import tempfile
import os
from dataclasses import dataclass

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float | None
    is_empty: bool       # True when Whisper returns blank/noise transcript
    raw_response: dict   # Full Whisper response for debugging


class WhisperService:
    """
    Wraps the OpenAI Whisper API.
    
    Design decisions:
    - Uses verbose_json response format to get language + duration metadata
    - Writes audio to a named temp file because OpenAI SDK requires a file-like
      object with a .name attribute for format detection
    - Retries on transient errors (rate limits, timeouts) with exponential backoff
    - Cleans up temp files in finally block — never leaks disk space
    """

    # Whisper's minimum meaningful transcript length
    NOISE_THRESHOLD_CHARS = 3
    # These are common Whisper outputs for silence/noise-only audio
    NOISE_PATTERNS = {
        "", ".", "...", "[silence]", "[noise]", "[music]",
        "thank you", "thanks for watching", "you",
    }

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    @retry(
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        language: str | None = None,   # ISO-639-1 hint, e.g. "en", "hi"
        prompt: str | None = None,     # Domain hint to improve accuracy
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes using Whisper API.
        
        Args:
            audio_bytes: Raw audio file content
            filename: Original filename (used for format detection by OpenAI)
            language: Optional ISO-639-1 language hint (improves accuracy)
            prompt: Optional context prompt (e.g. "expense tracking app, amounts in rupees")
        
        Returns:
            TranscriptionResult with text and metadata
        
        Raises:
            APIError: On non-retryable Whisper API failures
            ValueError: If audio content is invalid
        """
        temp_path = None
        try:
            # Write to named temp file — OpenAI SDK reads .name for MIME detection
            suffix = os.path.splitext(filename)[1] or ".webm"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                temp_path = tmp.name

            logger.info(f"Transcribing audio: {len(audio_bytes)} bytes, format={suffix}")

            with open(temp_path, "rb") as audio_file:
                # verbose_json gives us segments, language, duration
                response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    language=language,
                    prompt=prompt or (
                        "Expense tracking. The user is describing a purchase. "
                        "Listen for: amount, category (food, transport, shopping), "
                        "merchant name, and date."
                    ),
                    temperature=0.0,  # Deterministic — expenses need accuracy, not creativity
                )

            transcript = response.text.strip() if response.text else ""
            is_empty = (
                len(transcript) < self.NOISE_THRESHOLD_CHARS
                or transcript.lower() in self.NOISE_PATTERNS
            )

            if is_empty:
                logger.warning(f"Whisper returned likely-empty transcript: '{transcript}'")

            logger.info(
                f"Transcription complete: {len(transcript)} chars, "
                f"lang={response.language}, empty={is_empty}"
            )

            return TranscriptionResult(
                text=transcript,
                language=response.language or "unknown",
                duration_seconds=getattr(response, "duration", None),
                is_empty=is_empty,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
            )

        except APITimeoutError:
            logger.error("Whisper API timeout — will retry")
            raise
        except RateLimitError:
            logger.warning("Whisper rate limit hit — will retry with backoff")
            raise
        except APIError as e:
            logger.error(f"Whisper API error (non-retryable): {e}")
            raise ValueError(f"Transcription failed: {e.message}") from e
        finally:
            # Always clean up temp file
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
                logger.debug(f"Cleaned up temp file: {temp_path}")
