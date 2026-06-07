import io
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

# ── Audio format signatures (magic bytes) ─────────────────────────────────────
# Whisper accepts: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac
AUDIO_MAGIC_BYTES: dict[bytes, str] = {
    b"ID3":          "mp3",
    b"\xff\xfb":     "mp3",
    b"\xff\xf3":     "mp3",
    b"\xff\xf2":     "mp3",
    b"RIFF":         "wav",
    b"fLaC":         "flac",
    b"OggS":         "ogg",
    b"\x1aE\xdf\xa3": "webm",
}

ALLOWED_AUDIO_MIME = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/wave",
    "audio/x-wav", "audio/flac", "audio/ogg", "audio/webm",
    "audio/mp4", "audio/m4a", "audio/x-m4a", "video/webm",
}

# ── Image format signatures ────────────────────────────────────────────────────
IMAGE_MAGIC_BYTES: dict[bytes, str] = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG":      "png",
    b"GIF8":         "gif",
    b"RIFF":         "webp",   # checked together with offset bytes
    b"%PDF":         "pdf",
}

ALLOWED_IMAGE_MIME = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/gif", "application/pdf",
}


async def validate_audio_file(file: UploadFile) -> bytes:
    """
    Read the upload, validate type + size, return raw bytes.
    Raises HTTPException on any violation so the caller never
    receives invalid data.
    """
    content = await file.read()

    # Size check first — cheapest
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    if len(content) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is too small to be a valid audio file",
        )

    # Magic byte validation — check first 4 bytes
    header = content[:4]
    is_valid = any(header.startswith(magic) for magic in AUDIO_MAGIC_BYTES)

    # MIME type as secondary check
    if not is_valid and file.content_type:
        is_valid = file.content_type.lower() in ALLOWED_AUDIO_MIME

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid audio file. Supported formats: mp3, wav, flac, ogg, webm, m4a",
        )

    return content


async def validate_image_file(file: UploadFile) -> bytes:
    """Same pattern for receipt images."""
    content = await file.read()

    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit",
        )

    header = content[:4]
    is_valid = any(header.startswith(magic) for magic in IMAGE_MAGIC_BYTES)

    if not is_valid and file.content_type:
        is_valid = file.content_type.lower() in ALLOWED_IMAGE_MIME

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: jpeg, png, webp, pdf",
        )

    return content
