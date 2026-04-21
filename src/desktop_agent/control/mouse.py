"""Human-like mouse control with Bézier-curve movement."""

from __future__ import annotations

import asyncio
import math
import random

import pyautogui

from desktop_agent.log import get_logger

log = get_logger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class Mouse:
    """Human-like mouse control: Bézier curves, jitter, variable speed."""

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._x, self._y = pyautogui.position()

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(x, self._screen_w - 1)),
            max(0, min(y, self._screen_h - 1)),
        )

    def norm_to_pixel(self, nx: int, ny: int) -> tuple[int, int]:
        """Convert 0-1000 normalised coordinates to screen pixels."""
        return (
            int(nx * self._screen_w / 1000),
            int(ny * self._screen_h / 1000),
        )

    async def move(self, x: int, y: int) -> None:
        """Human-like Bézier curve mouse movement."""
        x, y = self._clamp(x, y)
        sx, sy = self._x, self._y
        dist = math.hypot(x - sx, y - sy)

        if dist < 5:
            pyautogui.moveTo(x, y)
            self._x, self._y = x, y
            return

        steps = max(8, min(int(dist / 8), 60))
        mid_x, mid_y = (sx + x) / 2, (sy + y) / 2
        perp = min(dist * 0.3, 120)
        angle = math.atan2(y - sy, x - sx) + math.pi / 2
        offset = random.uniform(-perp, perp)

        cp_x = mid_x + math.cos(angle) * offset + random.uniform(-15, 15)
        cp_y = mid_y + math.sin(angle) * offset + random.uniform(-15, 15)

        for i in range(1, steps + 1):
            t = i / steps
            inv = 1 - t
            bx = inv * inv * sx + 2 * inv * t * cp_x + t * t * x
            by = inv * inv * sy + 2 * inv * t * cp_y + t * t * y

            jitter = max(1, 3 - int(t * 3))
            bx += random.uniform(-jitter, jitter)
            by += random.uniform(-jitter, jitter)
            bx, by = self._clamp(int(bx), int(by))

            pyautogui.moveTo(bx, by, _pause=False)
            base_delay = random.uniform(3, 12)
            ease = 1 - 4 * (t - 0.5) ** 2
            await asyncio.sleep(base_delay * (0.5 + ease) / 1000)

        pyautogui.moveTo(x, y, _pause=False)
        self._x, self._y = x, y

    async def click(self, x: int, y: int) -> str:
        x, y = self._clamp(x, y)
        hx = x + random.randint(-2, 2)
        hy = y + random.randint(-2, 2)
        hx, hy = self._clamp(hx, hy)
        await self.move(hx, hy)
        pyautogui.click(hx, hy)
        await asyncio.sleep(random.uniform(0.3, 0.6))
        return f"Clicked ({x},{y})"

    async def double_click(self, x: int, y: int) -> str:
        x, y = self._clamp(x, y)
        await self.move(x, y)
        pyautogui.doubleClick(x, y)
        await asyncio.sleep(random.uniform(0.3, 0.5))
        return f"Double-clicked ({x},{y})"

    async def right_click(self, x: int, y: int) -> str:
        x, y = self._clamp(x, y)
        await self.move(x, y)
        pyautogui.rightClick(x, y)
        await asyncio.sleep(random.uniform(0.3, 0.5))
        return f"Right-clicked ({x},{y})"

    async def drag(
        self, from_x: int, from_y: int, to_x: int, to_y: int
    ) -> str:
        from_x, from_y = self._clamp(from_x, from_y)
        to_x, to_y = self._clamp(to_x, to_y)
        await self.move(from_x, from_y)
        pyautogui.mouseDown()
        await asyncio.sleep(0.1)
        await self.move(to_x, to_y)
        pyautogui.mouseUp()
        await asyncio.sleep(0.3)
        return f"Dragged ({from_x},{from_y})→({to_x},{to_y})"

    async def scroll(
        self, direction: str = "down", amount: int = 3
    ) -> str:
        amount = min(amount, 20)
        clicks = amount * 3
        if direction in ("up", "left"):
            clicks = -clicks
        pyautogui.scroll(-clicks)
        await asyncio.sleep(random.uniform(0.3, 0.6))
        return f"Scrolled {direction} {amount}"
