"""Planner — uses the large thinking model to generate plans and handle escalation.

Responsible for:
- Breaking tasks into concrete sub-steps
- Research query generation
- Research synthesis
- Escalation handling when executor gets stuck
- Replanning when approach fails
"""

from __future__ import annotations

import json
import os
import re
import time

from openai import OpenAI

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks.  If nothing remains outside,
    return content from inside the tags."""
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


class Planner:
    """Large-model planner for task decomposition, research, and escalation."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.llm.planner_api_key:
            raise ValueError("No planner API key configured")

        self._client = OpenAI(
            api_key=settings.llm.planner_api_key,
            base_url=settings.llm.planner_base_url,
            timeout=settings.llm.api_timeout,
            max_retries=2,
        )
        self._model = settings.llm.planner_model
        self._max_tokens = settings.llm.planner_max_tokens
        self._temperature = settings.llm.planner_temperature

    def _call(self, messages: list[dict], *, max_tokens: int | None = None) -> str:
        start = time.time()
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens or self._max_tokens,
                temperature=self._temperature,
            )
        except Exception as e:
            log.error("planner_api_error", error=str(e), model=self._model)
            raise
        reply = response.choices[0].message.content.strip()
        elapsed = time.time() - start
        log.debug("planner_call", elapsed=f"{elapsed:.1f}s", tokens=len(reply.split()))
        return _strip_think_tags(reply)

    # ── Plan creation ─────────────────────────────────────────────

    def create_plan(
        self,
        task: str,
        *,
        context: str = "",
        screenshot_b64: str = "",
        memory_context: str = "",
        skill_context: str = "",
    ) -> list[str]:
        """Break a task into 3-15 concrete sub-steps."""
        home = os.path.expanduser("~")
        user = os.path.basename(home)

        prompt = f"""You are a planning assistant for an AI desktop agent controlling macOS.
Break the task into concrete, ordered sub-steps (3-15 steps).

{"Screenshot of current screen is attached — use it to understand the current state." if screenshot_b64 else ""}

Task: {task}

{f"Context: {context}" if context else ""}
{memory_context}
{skill_context}

System info: home={home}, user={user}

RULES:
- Each step = ONE specific atomic action
- Use open_app to launch applications
- For web searches: use open_app to open Safari, then interact visually
- NEVER use Calculator app
- Include actual content to type for writing tasks
- Use smart_type for text entry, \\n for newlines
- End with a done step that reports the result- NEVER add speculative wait steps (e.g. "wait 5 seconds for download")
- Do NOT assume outcomes — each step should react to what is visible on screen
- Do NOT pre-plan file-explorer navigation, confirmation dialogs, or post-download actions
- Keep the plan minimal: the agent will observe the screen after each step and adapt
Output ONLY a JSON array of strings:
["Step 1: ...", "Step 2: ...", ...]

/no_think"""

        messages = []
        if screenshot_b64 and "-vl" in self._model.lower():
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}", "detail": "high"},
                    },
                    {"type": "text", "text": prompt},
                ],
            })
        else:
            messages.append({"role": "user", "content": prompt})

        try:
            reply = self._call(messages)
            match = re.search(r"\[.*\]", reply, re.DOTALL)
            if match:
                plan = json.loads(match.group(0))
                if isinstance(plan, list) and len(plan) >= 2:
                    return [str(s) for s in plan]
        except Exception as e:
            log.error("planning_failed", error=str(e))

        # Fallback plan
        return [
            f"Step 1: Analyse the task: {task}",
            "Step 2: Open the required application",
            "Step 3: Perform the main action",
            "Step 4: Check the result and call done",
        ]

    # ── Escalation ────────────────────────────────────────────────

    def escalate(
        self,
        *,
        screenshot_b64: str,
        problem: str,
        task: str,
        memory_context: str = "",
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> dict:
        """Handle escalation from executor — provide guidance or replan.

        Returns dict with:
            - guidance: "action" | "replan" | "advice"
            - action: dict (if guidance == "action")
            - plan: list[str] (if guidance == "replan")
            - advice: str (if guidance == "advice")
        """
        prompt = f"""You are the senior planner for an AI desktop agent.
The executor model encountered a problem and needs your help.

Task: {task}
Problem: {problem}
{memory_context}

Screenshot attached. Screen: {screen_width}x{screen_height}. Coordinates use 0-1000 scale.

Respond with ONE JSON object:
- To provide a direct action: {{"guidance": "action", "action": {{"action": "...", ...}}, "explanation": "..."}}
- To replan: {{"guidance": "replan", "plan": ["step1", "step2", ...], "explanation": "..."}}
- To advise: {{"guidance": "advice", "advice": "...", "explanation": "..."}}

/no_think"""

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}", "detail": "high"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            reply = self._call(messages)
            match = re.search(r"\{.*\}", reply, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            log.error("escalation_failed", error=str(e))

        return {"guidance": "advice", "advice": "Try a completely different approach."}
