"""
Gemini-only transcription service — no OpenAI required.
Drop this file as whisper_service.py to use Gemini instead of Whisper.
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_seconds: float | None
    is_empty: bool
    raw_response: dict


NOISE_PATTERNS = {
    "", ".", "...", "[silence]", "[noise]", "[music]",
    "thank you", "thanks for watching", "you", "[inaudible]",
}

AUDIO_MIME_TYPES = {
    ".mp3": "audio/mp3", ".wav": "audio/wav", ".webm": "audio/webm",
    ".ogg": "audio/ogg", ".flac": "audio/flac",
    ".m4a": "audio/mp4", ".mp4": "audio/mp4",
}

PROMPT = """Listen to this audio. The person is describing a personal expense.
Transcribe exactly what is said and detect the language.
Return ONLY valid JSON, no markdown:
{"transcript": "<exact words>", "language": "<ISO-639-1 code>", "is_empty": <true/false>}
If audio is silent or noise-only: {"transcript": "", "language": "en", "is_empty": true}"""


class WhisperService:
    """Gemini 1.5 Flash audio transcription — free tier, no OpenAI billing needed."""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY not configured")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=256,
            ),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8), reraise=True)
    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        language: str | None = None,
        prompt: str | None = None,
    ) -> TranscriptionResult:
        temp_path = None
        try:
            ext = os.path.splitext(filename)[1].lower()
            mime_type = AUDIO_MIME_TYPES.get(ext, "audio/webm")

            with tempfile.NamedTemporaryFile(suffix=ext or ".webm", delete=False) as tmp:
                tmp.write(audio_bytes)
                temp_path = tmp.name

            logger.info(f"Gemini transcribing: {len(audio_bytes)}b, {mime_type}")
            audio_file = genai.upload_file(temp_path, mime_type=mime_type)

            prompt_text = PROMPT
            if language:
                prompt_text += f"\nLanguage hint: {language}"

            response = await self.model.generate_content_async([prompt_text, audio_file])
            return self._parse(response.text.strip())

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _parse(self, raw: str) -> TranscriptionResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return TranscriptionResult(
                text=raw[:500], language="en",
                duration_seconds=None, is_empty=not bool(raw.strip()),
                raw_response={"raw": raw},
            )

        transcript = (data.get("transcript") or "").strip()
        is_empty = (
            data.get("is_empty", False)
            or len(transcript) < 3
            or transcript.lower() in NOISE_PATTERNS
        )
        return TranscriptionResult(
            text=transcript,
            language=data.get("language") or "en",
            duration_seconds=None,
            is_empty=is_empty,
            raw_response=data,
        )
