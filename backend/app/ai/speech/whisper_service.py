import logging
import tempfile
import os
import asyncio
from dataclasses import dataclass

import whisper

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float | None
    is_empty: bool
    raw_response: dict


class WhisperService:
    """
    Local Whisper transcription service.

    Uses OpenAI Whisper model running locally.
    No API key required.
    No internet required after model download.
    """

    NOISE_THRESHOLD_CHARS = 3

    NOISE_PATTERNS = {
        "",
        ".",
        "...",
        "[silence]",
        "[noise]",
        "[music]",
        "thank you",
        "thanks for watching",
        "you",
    }

    def __init__(self):
        logger.info("Loading Whisper model...")

        # tiny = fastest
        # base = good balance
        # small = better accuracy
        self.model = whisper.load_model("base")

        logger.info("Whisper model loaded successfully")

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio locally using Whisper.
        """

        temp_path = None

        try:
            suffix = os.path.splitext(filename)[1] or ".webm"

            with tempfile.NamedTemporaryFile(
                suffix=suffix,
                delete=False,
            ) as tmp:
                tmp.write(audio_bytes)
                temp_path = tmp.name

            logger.info(
                f"Transcribing audio locally: "
                f"{len(audio_bytes)} bytes, format={suffix}"
            )

            result = await asyncio.to_thread(
                self.model.transcribe,
                temp_path,
                language=language,
            )

            transcript = result.get("text", "").strip()

            is_empty = (
                len(transcript) < self.NOISE_THRESHOLD_CHARS
                or transcript.lower() in self.NOISE_PATTERNS
            )

            detected_language = result.get(
                "language",
                language or "unknown",
            )

            logger.info(
                f"Transcription complete: "
                f"{len(transcript)} chars, "
                f"lang={detected_language}, "
                f"empty={is_empty}"
            )

            return TranscriptionResult(
                text=transcript,
                language=detected_language,
                duration_seconds=None,
                is_empty=is_empty,
                raw_response=result,
            )

        except Exception as e:
            logger.exception(f"Whisper transcription failed: {e}")
            raise ValueError(
                f"Transcription failed: {str(e)}"
            ) from e

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass