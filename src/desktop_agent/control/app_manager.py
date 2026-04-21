"""Application lifecycle management — launch, activate, verify, close."""

from __future__ import annotations

import asyncio
import subprocess

from desktop_agent.log import get_logger

log = get_logger(__name__)


class AppManager:
    """Manage macOS application lifecycle."""

    async def open_app(self, name: str) -> str:
        """Launch an app by name. Tries open -a, then Spotlight."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["open", "-a", name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return f"Failed to open {name}: {result.stderr.strip()}"

            await asyncio.sleep(2.0)

            if not await self.is_running(name):
                return f"Launched {name} but process not confirmed"

            await self.activate(name)
            await asyncio.sleep(0.5)

            # TextEdit special: always create a new document
            if name.lower() == "textedit":
                await self._textedit_new_doc()

            return f"Opened {name}"
        except subprocess.TimeoutExpired:
            return f"Timeout opening {name}"
        except Exception as e:
            return f"Failed: {e}"

    async def activate(self, name: str) -> str:
        """Bring an app to the foreground."""
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", f'tell application "{name}" to activate'],
                capture_output=True,
                timeout=5,
            )
            return f"Activated {name}"
        except Exception as e:
            return f"Activate failed: {e}"

    async def is_running(self, name: str) -> bool:
        """Check if an app process is running."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                f"pgrep -ix '{name}'",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    async def get_frontmost(self) -> str:
        """Return name of the frontmost application."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    async def close_app(self, name: str) -> str:
        """Quit an application gracefully."""
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-e", f'tell application "{name}" to quit'],
                capture_output=True,
                timeout=10,
            )
            return f"Closed {name}"
        except Exception as e:
            return f"Close failed: {e}"

    async def spotlight_search(self, query: str) -> str:
        """Open Spotlight and search."""
        import pyautogui

        pyautogui.hotkey("command", "space")
        await asyncio.sleep(1.0)
        pyautogui.typewrite(query, interval=0.06)
        await asyncio.sleep(1.0)
        pyautogui.press("enter")
        await asyncio.sleep(1.5)
        return f"Spotlight: {query}"

    async def _textedit_new_doc(self) -> None:
        """Create a new blank TextEdit document."""
        try:
            await asyncio.to_thread(
                subprocess.run,
                [
                    "osascript",
                    "-e",
                    'tell application "TextEdit"\n  make new document\n  activate\nend tell',
                ],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass
