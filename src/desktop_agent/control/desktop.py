"""Unified desktop controller — facade over mouse, keyboard, app manager.

Translates AgentAction models into actual desktop operations.
"""

from __future__ import annotations

import asyncio

import pyautogui

from desktop_agent.control.mouse import Mouse
from desktop_agent.control.keyboard import Keyboard
from desktop_agent.control.app_manager import AppManager
from desktop_agent.core.actions import (
    AgentAction,
    ClickAction,
    DoubleClickAction,
    RightClickAction,
    TypeTextAction,
    PasteTextAction,
    SmartTypeAction,
    SelectAllAndTypeAction,
    PressKeyAction,
    HotkeyAction,
    ScrollAction,
    DragAction,
    OpenAppAction,
    SpotlightSearchAction,
    WaitAction,
)
from desktop_agent.log import get_logger

log = get_logger(__name__)


class DesktopController:
    """High-level desktop controller — facade over all input subsystems."""

    def __init__(self) -> None:
        screen = pyautogui.size()
        self.screen_width = screen.width
        self.screen_height = screen.height

        self.mouse = Mouse(self.screen_width, self.screen_height)
        self.keyboard = Keyboard()
        self.apps = AppManager()

    async def execute(self, action: AgentAction) -> str:
        """Execute any AgentAction and return a human-readable result string."""
        match action:
            case ClickAction():
                px, py = self.mouse.norm_to_pixel(action.x, action.y)
                return await self.mouse.click(px, py)

            case DoubleClickAction():
                px, py = self.mouse.norm_to_pixel(action.x, action.y)
                return await self.mouse.double_click(px, py)

            case RightClickAction():
                px, py = self.mouse.norm_to_pixel(action.x, action.y)
                return await self.mouse.right_click(px, py)

            case TypeTextAction():
                return await self.keyboard.type_text(
                    action.text, press_enter=action.press_enter
                )

            case PasteTextAction():
                return await self.keyboard.paste_text(
                    action.text, press_enter=action.press_enter
                )

            case SmartTypeAction():
                return await self.keyboard.smart_type(
                    action.text, press_enter=action.press_enter
                )

            case SelectAllAndTypeAction():
                return await self.keyboard.select_all_and_type(action.text)

            case PressKeyAction():
                return await self.keyboard.press_key(action.key)

            case HotkeyAction():
                return await self.keyboard.hotkey(*action.keys)

            case ScrollAction():
                return await self.mouse.scroll(action.direction, action.amount)

            case DragAction():
                fx, fy = self.mouse.norm_to_pixel(action.from_x, action.from_y)
                tx, ty = self.mouse.norm_to_pixel(action.to_x, action.to_y)
                return await self.mouse.drag(fx, fy, tx, ty)

            case OpenAppAction():
                if action.app_name.lower() == "calculator":
                    return "Calculator disabled. Use Spotlight to search for calculations instead."
                return await self.apps.open_app(action.app_name)

            case SpotlightSearchAction():
                return await self.apps.spotlight_search(action.query)

            case WaitAction():
                await asyncio.sleep(action.ms / 1000)
                return f"Waited {action.ms}ms"

            case _:
                return f"Unhandled action type: {type(action).__name__}"
