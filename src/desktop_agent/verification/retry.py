"""Retry manager — escalating retry strategies for failed actions.

Provides multiple fallback strategies:
1. Simple retry
2. Retry with adjusted coordinates
3. Alternative action (e.g., keyboard instead of click)
4. Escalation to planner
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from desktop_agent.core.actions import (
    AgentAction,
    ClickAction,
    HotkeyAction,
    OpenAppAction,
    PressKeyAction,
    SmartTypeAction,
    SpotlightSearchAction,
    parse_action,
)
from desktop_agent.log import get_logger

log = get_logger(__name__)


@dataclass
class RetryContext:
    action: AgentAction
    attempt: int = 0
    max_attempts: int = 3
    strategies_tried: list[str] = field(default_factory=list)


class RetryManager:
    """Manages retry logic with escalating strategies."""

    def suggest_retry(self, ctx: RetryContext) -> AgentAction | None:
        """Suggest a retry action, or None if all strategies exhausted.

        Returns a new action to try, or None to escalate to planner.
        """
        if ctx.attempt >= ctx.max_attempts:
            return None

        act = ctx.action.action.value if hasattr(ctx.action.action, "value") else str(ctx.action.action)
        ctx.attempt += 1

        strategies = {
            "click": self._retry_click,
            "double_click": self._retry_click,
            "smart_type": self._retry_type,
            "type_text": self._retry_type,
            "open_app": self._retry_open_app,
        }

        handler = strategies.get(act)
        if handler:
            return handler(ctx)

        # Default: no intelligent retry
        return None

    def _retry_click(self, ctx: RetryContext) -> AgentAction | None:
        """Retry click with offset or alternative."""
        action = ctx.action
        x = getattr(action, "x", 500)
        y = getattr(action, "y", 500)

        if ctx.attempt == 1 and "offset" not in ctx.strategies_tried:
            # Small random offset
            ctx.strategies_tried.append("offset")
            dx = random.randint(-15, 15)
            dy = random.randint(-15, 15)
            log.info("retry_click_offset", dx=dx, dy=dy)
            return ClickAction(
                x=max(0, min(1000, x + dx)),
                y=max(0, min(1000, y + dy)),
                desc=f"Retry click near ({x},{y})",
                thought=f"Retrying click with offset ({dx},{dy})",
            )

        if ctx.attempt == 2 and "keyboard" not in ctx.strategies_tried:
            # Try Tab + Enter
            ctx.strategies_tried.append("keyboard")
            log.info("retry_click_keyboard")
            return PressKeyAction(
                key="Return",
                thought="Retry: pressing Enter instead of clicking",
            )

        return None

    def _retry_type(self, ctx: RetryContext) -> AgentAction | None:
        """Retry typing with focus check or paste."""
        text = getattr(ctx.action, "text", "")

        if ctx.attempt == 1 and "click_focus" not in ctx.strategies_tried:
            # Click to focus first
            ctx.strategies_tried.append("click_focus")
            return ClickAction(x=500, y=500, desc="Click to focus", thought="Retry: click to focus before typing")

        if ctx.attempt == 2 and "paste" not in ctx.strategies_tried:
            ctx.strategies_tried.append("paste")
            from desktop_agent.core.actions import PasteTextAction
            return PasteTextAction(
                text=text,
                thought="Retry: using paste instead of type",
            )

        return None

    def _retry_open_app(self, ctx: RetryContext) -> AgentAction | None:
        """Retry app opening with Spotlight."""
        app_name = getattr(ctx.action, "app_name", "")

        if ctx.attempt == 1 and "spotlight" not in ctx.strategies_tried:
            ctx.strategies_tried.append("spotlight")
            return SpotlightSearchAction(query=app_name, thought="Retry: using Spotlight")

        return None
