"""Simple macOS TTS using the built-in `say` command."""

from __future__ import annotations

import asyncio
import subprocess

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)

_current_process: subprocess.Popen | None = None


async def speak(text: str, *, wait: bool = True) -> None:
    """Speak text using macOS `say`.

    Args:
        text: The text to speak.
        wait: If True (default), wait for speech to finish before returning.
    """
    settings = get_settings()
    if not settings.tts.enabled:
        return

    global _current_process
    # Kill any ongoing speech so it doesn't queue up
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()

    # Keep it short for snappy feedback
    text = text[:200]

    try:
        _current_process = await asyncio.to_thread(
            subprocess.Popen,
            ["say", "-r", str(settings.tts.rate), "-v", settings.tts.voice, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if wait and _current_process:
            await asyncio.to_thread(_current_process.wait)
    except Exception as e:
        log.debug("tts_failed", error=str(e))


async def stop() -> None:
    """Stop any ongoing speech."""
    global _current_process
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()
        _current_process = None
