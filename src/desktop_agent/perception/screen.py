"""Screen capture with high-quality encoding and metadata."""

from __future__ import annotations

import asyncio
import base64
import os
from io import BytesIO
from pathlib import Path

import pyautogui
from PIL import Image

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


class ScreenCapture:
    """High-quality screenshot capture with configurable format and resolution."""

    def __init__(self) -> None:
        self._step = 0
        self._screenshot_dir = Path("screenshots")
        self._screenshot_dir.mkdir(exist_ok=True)
        screen = pyautogui.size()
        self.width = screen.width
        self.height = screen.height

    async def capture(self, *, save: bool = True) -> tuple[str, Image.Image]:
        """Capture the screen and return (base64_encoded, PIL.Image).

        Uses the configured format and quality settings.
        """
        settings = get_settings()
        self._step += 1

        img = await asyncio.to_thread(pyautogui.screenshot)

        # Convert RGBA → RGB for JPEG compat
        if img.mode == "RGBA":
            img = img.convert("RGB")

        # Resize to configured max dimensions (maintain aspect ratio)
        # BILINEAR is ~3x faster than LANCZOS with negligible quality difference for VLMs
        img.thumbnail(
            (settings.screen.max_width, settings.screen.max_height),
            Image.BILINEAR,
        )

        buf = BytesIO()
        fmt = settings.screen.screenshot_format.upper()
        if fmt == "PNG":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.save(buf, format="JPEG", quality=settings.screen.screenshot_quality)

        raw_bytes = buf.getvalue()
        b64 = base64.b64encode(raw_bytes).decode("utf-8")

        if save:
            ext = "png" if fmt == "PNG" else "jpg"
            path = self._screenshot_dir / f"step_{self._step:04d}.{ext}"
            path.write_bytes(raw_bytes)
            log.debug("screenshot_saved", path=str(path), size_kb=len(raw_bytes) // 1024)

        return b64, img

    async def capture_region(
        self, x: int, y: int, w: int, h: int
    ) -> tuple[str, Image.Image]:
        """Capture a specific screen region."""
        img = await asyncio.to_thread(pyautogui.screenshot, region=(x, y, w, h))
        if img.mode == "RGBA":
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, img

    @property
    def step(self) -> int:
        return self._step

    @property
    def mime_type(self) -> str:
        settings = get_settings()
        return "image/png" if settings.screen.screenshot_format == "png" else "image/jpeg"
