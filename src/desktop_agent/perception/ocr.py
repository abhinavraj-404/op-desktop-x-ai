"""OCR integration — extract text from screenshot regions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np
from PIL import Image

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


@dataclass
class OCRResult:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


class OCREngine:
    """Lazy-loaded OCR using EasyOCR."""

    def __init__(self) -> None:
        self._reader = None
        self._init_failed = False

    def _get_reader(self):
        if self._reader is None:
            if self._init_failed:
                return None
            settings = get_settings()
            if settings.ocr.engine == "easyocr":
                try:
                    import easyocr

                    self._reader = easyocr.Reader(
                        settings.ocr.languages,
                        gpu=False,
                        verbose=False,
                    )
                except Exception as e:
                    log.warning("ocr_init_failed", error=str(e))
                    self._init_failed = True
                    return None
            else:
                raise ValueError(f"Unsupported OCR engine: {settings.ocr.engine}")
        return self._reader

    async def extract_text(self, image: Image.Image) -> list[OCRResult]:
        """Run OCR on a PIL image and return detected text regions."""
        settings = get_settings()
        if not settings.ocr.enabled or self._init_failed:
            return []

        try:
            return await asyncio.to_thread(self._run_ocr, image)
        except Exception as e:
            log.warning("ocr_failed", error=str(e))
            return []

    def _run_ocr(self, image: Image.Image) -> list[OCRResult]:
        reader = self._get_reader()
        img_array = np.array(image)
        results = reader.readtext(img_array)

        ocr_results = []
        for bbox, text, confidence in results:
            if confidence < 0.3:
                continue
            # bbox is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x = int(min(xs))
            y = int(min(ys))
            w = int(max(xs) - x)
            h = int(max(ys) - y)
            ocr_results.append(OCRResult(text=text, x=x, y=y, width=w, height=h, confidence=confidence))

        return ocr_results

    def format_for_prompt(self, results: list[OCRResult], screen_w: int, screen_h: int) -> str:
        """Format OCR results as text for the LLM prompt."""
        if not results:
            return ""

        lines = ["## On-Screen Text (OCR)"]
        for r in results[:60]:
            nx = int((r.x + r.width / 2) * 1000 / screen_w) if screen_w else 0
            ny = int((r.y + r.height / 2) * 1000 / screen_h) if screen_h else 0
            lines.append(f"  \"{r.text}\" @ ({nx},{ny}) conf={r.confidence:.0%}")
        return "\n".join(lines)
