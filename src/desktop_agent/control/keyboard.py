"""Keyboard control — typing, hotkeys, key presses.

Uses macOS System Events AppleScript to avoid the fn/emoji-picker issue
that pyautogui triggers on Apple Silicon.
"""

from __future__ import annotations

import asyncio
import random
import subprocess

import pyautogui

from desktop_agent.log import get_logger

log = get_logger(__name__)

_KEY_MAP = {
    "Enter": "enter",
    "Return": "enter",
    "Tab": "tab",
    "Escape": "escape",
    "Esc": "escape",
    "Backspace": "backspace",
    "Delete": "delete",
    "Space": "space",
    "Up": "up",
    "Down": "down",
    "Left": "left",
    "Right": "right",
    "Meta": "command",
    "Command": "command",
    "Cmd": "command",
    "Control": "ctrl",
    "Ctrl": "ctrl",
    "Alt": "alt",
    "Option": "option",
    "Shift": "shift",
    **{f"F{i}": f"f{i}" for i in range(1, 13)},
}


class Keyboard:
    """Keyboard control with AppleScript fallback for reliable typing on macOS."""

    async def type_text(self, text: str, *, press_enter: bool = False) -> str:
        """Type text using macOS System Events (avoids fn/emoji on Apple Silicon)."""
        await self._type_via_applescript(text)
        if press_enter:
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await self._press_return_applescript()
            await asyncio.sleep(random.uniform(0.5, 1.0))
        return f"Typed {len(text)} chars" + (" + Enter" if press_enter else "")

    async def paste_text(self, text: str, *, press_enter: bool = False) -> str:
        """Paste text via clipboard — fast for long content."""
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        await asyncio.sleep(0.1)
        pyautogui.hotkey("command", "v")
        await asyncio.sleep(0.3)
        if press_enter:
            pyautogui.press("enter")
            await asyncio.sleep(0.5)
        preview = text[:80] + "…" if len(text) > 80 else text
        return f"Pasted {len(text)} chars: {preview!r}" + (" + Enter" if press_enter else "")

    async def smart_type(self, text: str, *, press_enter: bool = False) -> str:
        """Try paste first; verify; fall back to AppleScript typing if needed."""
        # --- Attempt 1: Clipboard paste ---
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        await asyncio.sleep(0.1)
        pyautogui.hotkey("command", "v")
        await asyncio.sleep(0.5)

        paste_ok = False
        if "\n" not in text and len(text) < 120:
            # Short text: trust paste
            paste_ok = True
        else:
            # Verify paste by round-trip clipboard check
            try:
                clear = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                clear.communicate(b"")
                await asyncio.sleep(0.1)

                pyautogui.hotkey("command", "a")
                await asyncio.sleep(0.15)
                pyautogui.hotkey("command", "c")
                await asyncio.sleep(0.15)

                result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
                first_line = text.split("\n")[0][:30]
                if first_line and first_line in result.stdout:
                    paste_ok = True
                elif not result.stdout.strip():
                    paste_ok = False

                pyautogui.press("right")
                await asyncio.sleep(0.1)
            except Exception:
                paste_ok = True  # Optimistic fallback

        if paste_ok:
            if press_enter:
                pyautogui.press("enter")
                await asyncio.sleep(0.5)
            return f"Smart-typed (paste OK, {len(text)} chars)" + (" + Enter" if press_enter else "")

        # --- Attempt 2: Fallback to AppleScript typing ---
        pyautogui.hotkey("command", "a")
        await asyncio.sleep(0.1)
        pyautogui.press("delete")
        await asyncio.sleep(0.2)

        await self._type_via_applescript(text)

        if press_enter:
            await asyncio.sleep(random.uniform(0.3, 0.7))
            pyautogui.press("enter")
            await asyncio.sleep(random.uniform(0.5, 1.0))

        return f"Smart-typed (applescript fallback, {len(text)} chars)" + (
            " + Enter" if press_enter else ""
        )

    async def select_all_and_type(self, text: str) -> str:
        pyautogui.hotkey("command", "a")
        await asyncio.sleep(0.15)
        await self._type_via_applescript(text)
        return f"Select-all + typed {len(text)} chars"

    async def press_key(self, key: str) -> str:
        mapped = _KEY_MAP.get(key, key.lower())
        pyautogui.press(mapped)
        await asyncio.sleep(0.3)
        return f"Pressed {key}"

    async def hotkey(self, *keys: str) -> str:
        mapped = [_KEY_MAP.get(k, k.lower()) for k in keys]
        pyautogui.hotkey(*mapped)
        await asyncio.sleep(0.4)
        return f"Hotkey {'+'.join(keys)}"

    # ── Internal helpers ──────────────────────────────────────────

    async def _type_via_applescript(self, text: str) -> None:
        """Type via macOS System Events keystroke (reliable on Apple Silicon)."""
        lines = text.split("\n")
        parts = ['tell application "System Events"']
        for i, line in enumerate(lines):
            if line:
                escaped = line.replace("\\", "\\\\").replace('"', '\\"')
                parts.append(f'    keystroke "{escaped}"')
            if i < len(lines) - 1:
                parts.append("    key code 36")  # Return
        parts.append("end tell")
        script = "\n".join(parts)
        await asyncio.to_thread(
            subprocess.run,
            ["osascript", "-e", script],
            timeout=30,
            capture_output=True,
        )

    async def _press_return_applescript(self) -> None:
        await asyncio.to_thread(
            subprocess.run,
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 36',
            ],
            timeout=5,
            capture_output=True,
        )
