"""Screen capture utilities using mss."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import mss
from loguru import logger
from PIL import Image


@dataclass(frozen=True, slots=True)
class ScreenCapture:
    """JPEG bytes and base64 representation of a captured screen."""

    jpeg_bytes: bytes
    base64_data: str
    width: int
    height: int


class ScreenCaptureError(Exception):
    """Raised when screen capture fails."""


def capture_primary_monitor(jpeg_quality: int = 85) -> ScreenCapture:
    """Capture the primary monitor and return encoded image data."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)

            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            jpeg_bytes = buffer.getvalue()

            base64_data = base64.b64encode(jpeg_bytes).decode("ascii")
            logger.debug(
                "Captured screen: {}x{} ({} KB)",
                screenshot.width,
                screenshot.height,
                len(jpeg_bytes) // 1024,
            )

            return ScreenCapture(
                jpeg_bytes=jpeg_bytes,
                base64_data=base64_data,
                width=screenshot.width,
                height=screenshot.height,
            )
    except Exception as exc:
        logger.exception("Screen capture failed")
        raise ScreenCaptureError("Unable to capture screen") from exc
