"""Strongly-typed action schema.

Every action the agent can take is a Pydantic model.  The executor model
outputs JSON that is validated against these schemas before execution.
This replaces the old dict-based approach with compile-time guarantees.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


# ── Coordinate system ────────────────────────────────────────────
# All coordinates are on a 0-1000 normalised scale.
# The control layer converts to actual screen pixels.

Coord = Annotated[int, Field(ge=0, le=1000)]


class ActionType(str, Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    PASTE_TEXT = "paste_text"
    SMART_TYPE = "smart_type"
    SELECT_ALL_AND_TYPE = "select_all_and_type"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    DRAG = "drag"
    OPEN_APP = "open_app"
    SPOTLIGHT_SEARCH = "spotlight_search"
    WAIT = "wait"
    SAVE_DATA = "save_data"
    ADVANCE_PLAN = "advance_plan"
    REPLAN = "replan"
    DONE = "done"
    EXECUTE_SKILL = "execute_skill"
    SCHEDULE_TASK = "schedule_task"


# ── Individual action models ─────────────────────────────────────


class ClickAction(BaseModel):
    action: Literal[ActionType.CLICK] = ActionType.CLICK
    x: Coord
    y: Coord
    desc: str = ""
    thought: str = ""


class DoubleClickAction(BaseModel):
    action: Literal[ActionType.DOUBLE_CLICK] = ActionType.DOUBLE_CLICK
    x: Coord
    y: Coord
    desc: str = ""
    thought: str = ""


class RightClickAction(BaseModel):
    action: Literal[ActionType.RIGHT_CLICK] = ActionType.RIGHT_CLICK
    x: Coord
    y: Coord
    desc: str = ""
    thought: str = ""


class TypeTextAction(BaseModel):
    action: Literal[ActionType.TYPE_TEXT] = ActionType.TYPE_TEXT
    text: str
    press_enter: bool = False
    thought: str = ""


class PasteTextAction(BaseModel):
    action: Literal[ActionType.PASTE_TEXT] = ActionType.PASTE_TEXT
    text: str
    press_enter: bool = False
    thought: str = ""


class SmartTypeAction(BaseModel):
    action: Literal[ActionType.SMART_TYPE] = ActionType.SMART_TYPE
    text: str
    press_enter: bool = False
    thought: str = ""


class SelectAllAndTypeAction(BaseModel):
    action: Literal[ActionType.SELECT_ALL_AND_TYPE] = ActionType.SELECT_ALL_AND_TYPE
    text: str
    thought: str = ""


class PressKeyAction(BaseModel):
    action: Literal[ActionType.PRESS_KEY] = ActionType.PRESS_KEY
    key: str
    thought: str = ""


class HotkeyAction(BaseModel):
    action: Literal[ActionType.HOTKEY] = ActionType.HOTKEY
    keys: list[str]
    thought: str = ""


class ScrollAction(BaseModel):
    action: Literal[ActionType.SCROLL] = ActionType.SCROLL
    direction: Literal["up", "down", "left", "right"] = "down"
    amount: int = Field(3, ge=1, le=20)
    thought: str = ""


class DragAction(BaseModel):
    action: Literal[ActionType.DRAG] = ActionType.DRAG
    from_x: Coord
    from_y: Coord
    to_x: Coord
    to_y: Coord
    thought: str = ""


class OpenAppAction(BaseModel):
    action: Literal[ActionType.OPEN_APP] = ActionType.OPEN_APP
    app_name: str
    thought: str = ""


class SpotlightSearchAction(BaseModel):
    action: Literal[ActionType.SPOTLIGHT_SEARCH] = ActionType.SPOTLIGHT_SEARCH
    query: str
    thought: str = ""


class WaitAction(BaseModel):
    action: Literal[ActionType.WAIT] = ActionType.WAIT
    ms: int = Field(2000, ge=100, le=30_000)
    thought: str = ""


class SaveDataAction(BaseModel):
    action: Literal[ActionType.SAVE_DATA] = ActionType.SAVE_DATA
    key: str
    value: str
    thought: str = ""


class AdvancePlanAction(BaseModel):
    action: Literal[ActionType.ADVANCE_PLAN] = ActionType.ADVANCE_PLAN
    to: int | None = None
    thought: str = ""


class ReplanAction(BaseModel):
    action: Literal[ActionType.REPLAN] = ActionType.REPLAN
    reason: str
    thought: str = ""


class DoneAction(BaseModel):
    action: Literal[ActionType.DONE] = ActionType.DONE
    result: str = ""
    thought: str = ""


# ── Skill / scheduling actions ───────────────────────────────────


class ExecuteSkillAction(BaseModel):
    action: Literal[ActionType.EXECUTE_SKILL] = ActionType.EXECUTE_SKILL
    skill_name: str
    params: dict = Field(default_factory=dict)
    thought: str = ""


class ScheduleTaskAction(BaseModel):
    action: Literal[ActionType.SCHEDULE_TASK] = ActionType.SCHEDULE_TASK
    task: str
    cron: str = ""  # cron expression
    delay_seconds: int = 0
    thought: str = ""


# ── Discriminated union ──────────────────────────────────────────

AgentAction = Annotated[
    Union[
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
        SaveDataAction,
        AdvancePlanAction,
        ReplanAction,
        DoneAction,
        ExecuteSkillAction,
        ScheduleTaskAction,
    ],
    Field(discriminator="action"),
]


def parse_action(raw: dict) -> AgentAction:
    """Parse a raw dict into a validated AgentAction.

    Applies pre-repair for common VLM JSON malformations before validation.
    """
    import re

    # Pre-repair: fix "x": 525, 145 → "x": 525, "y": 145
    raw_str = str(raw)
    if isinstance(raw.get("x"), list):
        coords = raw["x"]
        if len(coords) >= 2:
            raw["x"] = coords[0]
            raw["y"] = coords[1]
        elif coords:
            raw["x"] = coords[0]

    if isinstance(raw.get("y"), list):
        coords = raw["y"]
        if len(coords) >= 2:
            raw["x"] = coords[0]
            raw["y"] = coords[1]
        elif coords:
            raw["y"] = coords[0]

    # Ensure action field exists
    if "action" not in raw:
        raw["action"] = "wait"

    # Normalise action name
    action_name = raw["action"]
    if isinstance(action_name, str):
        raw["action"] = action_name.lower().strip()

    # Remap common invalid action names from LLM hallucinations
    _ACTION_ALIASES = {
        "verify": "done",
        "check": "done",
        "screenshot": "wait",
        "observe": "wait",
        "look": "wait",
        "type": "smart_type",
        "enter": "press_key",
        "open": "open_app",
        "search": "spotlight_search",
        "navigate": "open_app",
        "browser_navigate": "open_app",
        "browser_extract": "wait",
        "browser_click": "click",
        "browser_type": "smart_type",
        "run_command": "wait",
    }
    if raw["action"] in _ACTION_ALIASES:
        original = raw["action"]
        raw["action"] = _ACTION_ALIASES[original]
        # Carry over relevant fields for remapped actions
        if original == "verify" and "condition" in raw:
            raw.setdefault("result", raw.pop("condition"))
        if original == "enter":
            raw.setdefault("key", "Enter")
        if original in ("open", "navigate", "browser_navigate") and "url" in raw:
            raw.setdefault("app_name", "Safari")

    from pydantic import TypeAdapter

    adapter = TypeAdapter(AgentAction)
    return adapter.validate_python(raw)
