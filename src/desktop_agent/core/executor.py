"""Executor — fast vision model that decides one action per step.

Receives a screenshot + context and outputs a single JSON action.
Uses the smaller/faster model for speed; escalates to planner on failure.
"""

from __future__ import annotations

import json
import os
import re
import time

from openai import OpenAI

from desktop_agent.config import get_settings
from desktop_agent.core.actions import AgentAction, parse_action
from desktop_agent.log import get_logger

log = get_logger(__name__)


def _strip_think_tags(text: str) -> str:
    think_content = ""
    m = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    if m:
        think_content = m.group(1).strip()
    elif text.lstrip().startswith("<think>"):
        think_content = text.lstrip()[len("<think>"):].strip()
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped.lstrip().startswith("<think>"):
        stripped = stripped.lstrip()[len("<think>"):].strip()
    return stripped if stripped else think_content


SYSTEM_PROMPT = """You are an expert AI desktop agent controlling macOS.

## How you work
1. You receive a screenshot of the current screen + context.
2. You visually analyse what's on screen.
3. You output EXACTLY ONE action as JSON.

Screen: {width}x{height}px. Coordinates use 0-1000 scale (0=left/top, 1000=right/bottom).

## Output Format
You MUST output a single JSON object with these keys:
- "thought": (REQUIRED) 1-2 sentences describing what you see on screen and why you chose this action
- "action": the action name
- plus any action-specific parameters

Example: {{"thought": "I see Safari is open with Google visible. I need to click the search bar to type the URL.", "action": "click", "x": 500, "y": 50, "desc": "Safari address bar"}}

## Available Actions
```json
{{"thought": "...", "action": "click", "x": 500, "y": 300, "desc": "element name"}}
{{"thought": "...", "action": "double_click", "x": 500, "y": 300, "desc": "..."}}
{{"thought": "...", "action": "right_click", "x": 500, "y": 300, "desc": "..."}}
{{"thought": "...", "action": "smart_type", "text": "content", "press_enter": false}}
{{"thought": "...", "action": "type_text", "text": "short text", "press_enter": false}}
{{"thought": "...", "action": "paste_text", "text": "long content", "press_enter": true}}
{{"thought": "...", "action": "select_all_and_type", "text": "replacement"}}
{{"thought": "...", "action": "press_key", "key": "Enter"}}
{{"thought": "...", "action": "hotkey", "keys": ["Meta", "a"]}}
{{"thought": "...", "action": "scroll", "direction": "down", "amount": 3}}
{{"thought": "...", "action": "drag", "from_x": 100, "from_y": 200, "to_x": 400, "to_y": 500}}
{{"thought": "...", "action": "open_app", "app_name": "Safari"}}
{{"thought": "...", "action": "spotlight_search", "query": "Terminal"}}
{{"thought": "...", "action": "execute_skill", "skill_name": "save_to_desktop", "params": {{"filename": "test.txt"}}}}
{{"thought": "...", "action": "wait", "ms": 2000}}
{{"thought": "...", "action": "save_data", "key": "name", "value": "data"}}
{{"thought": "...", "action": "advance_plan"}}
{{"thought": "...", "action": "replan", "reason": "approach not working"}}
{{"thought": "...", "action": "done", "result": "Task completed. Result: ..."}}
```

## Critical Rules
- Output ONLY valid JSON with "thought" and "action" keys — "thought" MUST be non-empty
- The "thought" field is MANDATORY — describe what you see on screen and why you chose this action
- NEVER click disabled/grayed-out elements — fix prerequisites first
- Use smart_type for text entry (tries paste first, falls back to typing)
- Use save_data to store extracted info BEFORE scrolling past it
- For web tasks: use open_app to open Safari, then interact with the browser visually
- Safari address bar is at the TOP CENTER of the screen. Use Cmd+L to focus it before typing a URL.
- Safari tabs are shown BELOW the address bar. The HIGHLIGHTED/ACTIVE tab is the current one — do NOT assume it is the first tab. Look at which tab is visually selected.
- To open a new tab in Safari: Cmd+T. To close current tab: Cmd+W.
- After opening any app, check if it is fullscreen. If not, use hotkey Ctrl+Cmd+F to make it fullscreen before interacting.
- NEVER fabricate data — only use what you can see or extract
- If screen unchanged after action → it FAILED → try different approach
- There is NO "verify" action — use "done" when the task is complete
- In Finder: NEVER press Enter on a file — that renames it. Double-click to open files
- To open files in Finder: click to select, then double_click to open

## IMPORTANT: No Assumptions
- NEVER pre-assume what will happen after an action. Always LOOK at the screen first.
- Do NOT insert speculative "wait" steps hoping something will finish (e.g. downloads, installs).
- Do NOT auto-navigate to the next step unless you can SEE on screen that the previous action succeeded.
- ONE action at a time. After each action, you will get a new screenshot — decide your next move ONLY from what you see.
- If you need to confirm something happened (download finished, file saved, app opened), LOOK at the screen — do not guess.
- A file ending in ".download" or ".crdownload" means it is STILL downloading — do NOT try to open it.
- If a download dialog or progress bar is visible, wait for it to finish before interacting with the file.

{ax_tree}
{ocr_text}
{knowledge}

## System Info
Home: {home} | User: {user}
"""


class Executor:
    """Fast vision model for step-by-step action decisions."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.llm.executor_api_key:
            raise ValueError("No executor API key configured")

        self._client = OpenAI(
            api_key=settings.llm.executor_api_key,
            base_url=settings.llm.executor_base_url,
            timeout=settings.llm.api_timeout,
            max_retries=2,
        )
        self._model = settings.llm.executor_model
        self._max_tokens = settings.llm.executor_max_tokens
        self._temperature = settings.llm.executor_temperature
        self._conversation: list[dict] = []

    def reset(self) -> None:
        self._conversation = []

    def decide_action(
        self,
        *,
        screenshot_b64: str,
        task: str,
        current_goal: str,
        last_result: str = "",
        step: int = 0,
        max_steps: int = 50,
        memory_context: str = "",
        stuck_warning: str = "",
        failed_targets_warning: str = "",
        ax_tree_text: str = "",
        ocr_text: str = "",
        knowledge_text: str = "",
        screen_width: int = 1920,
        screen_height: int = 1080,
        mime_type: str = "image/png",
    ) -> AgentAction:
        """Send screenshot + context to vision model, get next action."""
        settings = get_settings()
        home = os.path.expanduser("~")
        user = os.path.basename(home)

        system_prompt = SYSTEM_PROMPT.format(
            width=screen_width,
            height=screen_height,
            ax_tree=ax_tree_text,
            ocr_text=ocr_text,
            knowledge=knowledge_text,
            home=home,
            user=user,
        )

        context_text = f"""## Step {step}/{max_steps}
**Task:** {task}
**Current sub-goal:** {current_goal}
**Last result:** {last_result or "N/A"}
{memory_context}
{stuck_warning}
{failed_targets_warning}

Analyse the screenshot. Follow your plan. Output ONE JSON action with a "thought" field explaining your reasoning."""

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{screenshot_b64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": context_text},
            ],
        }

        # Build messages: system + text-only history + current with screenshot
        messages = [{"role": "system", "content": system_prompt}]

        # Add recent history (text-only, no old screenshots — keep short)
        for msg in self._conversation[-6:]:
            if msg["role"] == "assistant":
                messages.append(msg)
            elif msg["role"] == "user":
                if isinstance(msg["content"], list):
                    text_parts = [p["text"] for p in msg["content"] if p.get("type") == "text"]
                    if text_parts:
                        messages.append({"role": "user", "content": text_parts[0]})
                else:
                    messages.append(msg)

        messages.append(user_message)
        self._conversation.append(user_message)

        # API call with retry
        reply = None
        for attempt in range(3):
            try:
                start = time.time()
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
                reply = response.choices[0].message.content.strip()
                elapsed = time.time() - start
                log.debug("executor_call", elapsed=f"{elapsed:.1f}s", attempt=attempt + 1)
                break
            except Exception as e:
                log.warning("executor_api_error", attempt=attempt + 1, error=str(e))
                if attempt == 2:
                    reply = '{"action": "wait", "ms": 3000, "thought": "API error"}'

        self._conversation.append({"role": "assistant", "content": reply})

        # Parse
        raw = self._extract_json(reply or "")
        try:
            return parse_action(raw)
        except Exception as e:
            log.warning("action_parse_failed", error=str(e), raw=reply[:200] if reply else "")
            from desktop_agent.core.actions import WaitAction
            return WaitAction(thought=f"Parse error: {e}")

    def _extract_json(self, text: str) -> dict:
        """Extract JSON action from model response."""
        text = _strip_think_tags(text)

        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # Any JSON object with "action" key
        m = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback
        if "done" in text.lower():
            return {"action": "done", "result": text[:200]}
        return {"action": "wait", "ms": 2000, "thought": f"Could not parse: {text[:100]}"}
