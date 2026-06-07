import io
import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

logger = logging.getLogger(__name__)


class ImageQuality(str, Enum):
    GOOD = "good"        # Clear, well-lit, straight
    MODERATE = "moderate"  # Some blur or skew, OCR should still work
    POOR = "poor"        # Heavy blur, very dark, or severely skewed


@dataclass
class PreprocessResult:
    image_array: np.ndarray   # Ready for PaddleOCR
    quality: ImageQuality
    quality_score: float      # 0.0–1.0
    width: int
    height: int
    was_resized: bool
    was_rotated: bool
    enhancements_applied: list[str]


class ImagePreprocessor:
    """
    Prepares receipt images for PaddleOCR.

    Pipeline (applied in order):
    1. EXIF rotation correction  — phone photos often arrive sideways
    2. Resize to OCR-optimal dimensions — PaddleOCR accuracy peaks at ~1200-2400px height
    3. Grayscale conversion       — receipts are monochrome; color adds noise
    4. Contrast enhancement       — faded thermal paper is common
    5. Sharpening                 — motion blur from handheld shots
    6. Binarization (optional)    — threshold to pure black/white for very noisy receipts
    7. Deskew (lightweight)       — correct slight rotation using Hough transform

    Design: Each step is a separate method so we can A/B test and skip steps
    for high-quality images (avoid over-processing).
    """

    # PaddleOCR performs best when the long edge is in this range
    MIN_LONG_EDGE = 1000
    MAX_LONG_EDGE = 10000
    TARGET_LONG_EDGE = 4000

    def preprocess(self, image_bytes: bytes) -> PreprocessResult:
        """
        Run the full preprocessing pipeline on raw image bytes.

        Args:
            image_bytes: Raw bytes of jpeg/png/webp/pdf-page image

        Returns:
            PreprocessResult with numpy array ready for PaddleOCR
        """
        enhancements: list[str] = []

        try:
            img = Image.open(io.BytesIO(image_bytes))
            
        except Exception as e:
            raise ValueError(f"Cannot open image: {e}")

        original_size = img.size
        logger.info(f"Preprocessing image: {img.size}, mode={img.mode}, format={img.format}")

        # ── Step 1: Fix EXIF rotation ─────────────────────────────────────────
        img, was_rotated = self._fix_exif_rotation(img)
        if was_rotated:
            enhancements.append("exif_rotation_fix")

        # ── Step 2: Convert to RGB (handle RGBA, palette modes) ───────────────
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
            enhancements.append("mode_conversion")

        # ── Step 3: Assess initial quality ────────────────────────────────────
        quality_score = self._assess_quality(img)

        # ── Step 4: Resize to optimal dimensions ──────────────────────────────
        img, was_resized = self._resize_for_ocr(img)
        if was_resized:
            enhancements.append("resize")

        # ── Step 5: Convert to grayscale ──────────────────────────────────────
        img = img.convert("L")
        enhancements.append("grayscale")

        # ── Step 6: Enhance contrast (critical for thermal paper receipts) ────
        if quality_score < 0.7:
            img = self._enhance_contrast(img)
            enhancements.append("contrast_enhancement")

        # ── Step 7: Sharpen (helps with slightly blurry photos) ───────────────
        if quality_score < 0.8:
            img = self._sharpen(img)
            enhancements.append("sharpening")

        # ── Step 8: Denoise for very poor quality images ──────────────────────
        if quality_score < 0.4:
            img = self._denoise(img)
            enhancements.append("denoising")

        # ── Step 9: Auto-level (normalize brightness) ─────────────────────────
        img = ImageOps.autocontrast(img, cutoff=2)
        enhancements.append("autocontrast")

        # ── Step 10: Convert to numpy array for PaddleOCR ─────────────────────
        # PaddleOCR expects BGR numpy array (OpenCV convention)
        img_array = np.array(img)
        if len(img_array.shape) == 2:
            # Grayscale → BGR by stacking channels
            img_array = np.stack([img_array] * 3, axis=-1)

        quality = self._quality_enum(quality_score)
        logger.info(
            f"Preprocessing complete: {original_size} → {img.size}, "
            f"quality={quality.value}({quality_score:.2f}), "
            f"enhancements={enhancements}"
        )

        return PreprocessResult(
            image_array=img_array,
            quality=quality,
            quality_score=quality_score,
            width=img.size[0],
            height=img.size[1],
            was_resized=was_resized,
            was_rotated=was_rotated,
            enhancements_applied=enhancements,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fix_exif_rotation(self, img: Image.Image) -> tuple[Image.Image, bool]:
        """
        Phones embed rotation in EXIF tag 274. PIL doesn't auto-apply it.
        Without this, a portrait-mode photo arrives as landscape.
        """
        try:
            exif = img._getexif()  # type: ignore
            if exif:
                orientation = exif.get(274)  # EXIF orientation tag
                rotations = {3: 180, 6: 270, 8: 90}
                if orientation in rotations:
                    img = img.rotate(rotations[orientation], expand=True)
                    return img, True
        except (AttributeError, Exception):
            pass
        return img, False

    def _resize_for_ocr(
        self, img: Image.Image
    ) -> tuple[Image.Image, bool]:
        """
        Resize so the long edge is TARGET_LONG_EDGE pixels.
        - Too small: OCR misses thin characters
        - Too large: slow with no accuracy benefit
        """
        w, h = img.size
        long_edge = max(w, h)

        if long_edge <= self.MAX_LONG_EDGE:
            return img, False

        scale = self.TARGET_LONG_EDGE / long_edge
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        return img, True

    def _assess_quality(self, img: Image.Image) -> float:
        """
        Estimate image quality using Laplacian variance (blur detection).
        High variance = sharp. Low variance = blurry.
        Returns 0.0–1.0.
        """
        gray = img.convert("L") if img.mode != "L" else img
        arr = np.array(gray, dtype=np.float32)

        # Laplacian variance: high = sharp, low = blurry
        laplacian = np.array([
            [0,  1, 0],
            [1, -4, 1],
            [0,  1, 0],
        ], dtype=np.float32)
        from scipy.signal import convolve2d
        try:
            lap = convolve2d(arr, laplacian, mode="valid")
            variance = float(np.var(lap))
        except Exception:
            # scipy not available — use simpler std dev
            variance = float(np.std(arr))

        # Normalize: < 50 = very blurry, > 500 = sharp
        score = min(1.0, max(0.0, (variance - 50) / 450))
        return round(score, 3)

    def _enhance_contrast(self, img: Image.Image) -> Image.Image:
        """
        Boost contrast for faded thermal paper receipts.
        Factor 1.5 is conservative — avoids blowing out already-good images.
        """
        enhancer = ImageEnhance.Contrast(img)
        return enhancer.enhance(1.5)

    def _sharpen(self, img: Image.Image) -> Image.Image:
        """Unsharp mask — more targeted than simple sharpen filter."""
        return img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

    def _denoise(self, img: Image.Image) -> Image.Image:
        """Median filter removes salt-and-pepper noise without blurring edges."""
        return img.filter(ImageFilter.MedianFilter(size=3))

    def _quality_enum(self, score: float) -> ImageQuality:
        if score >= 0.6:
            return ImageQuality.GOOD
        elif score >= 0.3:
            return ImageQuality.MODERATE
        return ImageQuality.POOR
