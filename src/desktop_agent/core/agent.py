"""Agent orchestrator — the central brain tying all systems together.

Coordinates: perception → executor → control → verification → memory.
Implements stuck detection, escalation, replanning, and skill recording.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

from desktop_agent.config import get_settings
from desktop_agent.core.actions import (
    ActionType,
    AgentAction,
    AdvancePlanAction,
    DoneAction,
    ExecuteSkillAction,
    ReplanAction,
    SaveDataAction,
    parse_action,
)
from desktop_agent.core.executor import Executor
from desktop_agent.core.planner import Planner
from desktop_agent.control.desktop import DesktopController
from desktop_agent.memory.short_term import ShortTermMemory
from desktop_agent.memory.long_term import LongTermMemory
from desktop_agent.memory.skill_store import SkillLibrary
from desktop_agent.perception.screen import ScreenCapture
from desktop_agent.perception.accessibility import AccessibilityTree
from desktop_agent.perception.ocr import OCREngine
from desktop_agent.perception.screen_diff import ScreenDiff
from desktop_agent.task_logger import TaskLogger
from desktop_agent.tts import speak as tts_speak
from desktop_agent.log import get_logger

log = get_logger(__name__)


class StepResult:
    """Result of a single agent step."""

    def __init__(
        self,
        action: AgentAction,
        result: str,
        *,
        verified: bool = True,
        done: bool = False,
        done_result: str = "",
    ) -> None:
        self.action = action
        self.result = result
        self.verified = verified
        self.done = done
        self.done_result = done_result


class Agent:
    """Main agent orchestrator."""

    def __init__(self) -> None:
        # Core
        self.planner = Planner()
        self.executor = Executor()
        self.desktop = DesktopController()

        # Perception
        self.screen = ScreenCapture()
        self.accessibility = AccessibilityTree()
        self.ocr = OCREngine()
        self.screen_diff = ScreenDiff()

        # Memory
        self.short_memory = ShortTermMemory()
        self.long_memory = LongTermMemory()
        self.skills = SkillLibrary()

        # State
        self._consecutive_failures = 0
        self._recent_actions: list[str] = []
        self._failed_targets: list[tuple[int, int]] = []
        self._step_callback: Callable | None = None
        self._task_log = TaskLogger()

    def on_step(self, callback: Callable) -> None:
        """Register a callback to be called after each step."""
        self._step_callback = callback

    # ── Task lifecycle ────────────────────────────────────────────

    async def run_task(self, task: str) -> str:
        """Execute a complete task end-to-end. Returns the final result string."""
        settings = get_settings()
        self._reset(task)
        log.info("task_started", task=task)
        self._task_log.start_task(task)
        await tts_speak(f"New task: {task[:80]}")

        # Phase 2: Plan (screenshot + memory lookup in parallel)
        async def _capture():
            return await self.screen.capture()

        async def _memory_ctx():
            return await asyncio.to_thread(self.long_memory.format_for_prompt, task)

        async def _skill_ctx():
            return await asyncio.to_thread(self.skills.format_for_prompt, task)

        (screenshot_b64, _), memory_ctx, skill_ctx = await asyncio.gather(
            _capture(), _memory_ctx(), _skill_ctx()
        )

        plan = await asyncio.to_thread(
            self.planner.create_plan,
            task,
            screenshot_b64=screenshot_b64,
            memory_context=memory_ctx,
            skill_context=skill_ctx,
        )
        self.short_memory.set_plan(plan)
        log.info("plan_created", steps=len(plan))
        self._task_log.log_plan(plan)

        # Phase 3: Execute step by step
        last_result = "Desktop ready."
        final_result = "Task did not complete."

        for step in range(1, settings.agent.max_steps + 1):
            step_result = await self._execute_step(step, last_result)
            last_result = step_result.result

            if self._step_callback:
                self._step_callback(step, step_result)

            if step_result.done:
                final_result = step_result.done_result
                self._on_task_complete(task, step, success=True)
                log.info("task_completed", steps=step, result=final_result[:200])
                self._task_log.end_task(success=True, result=final_result, total_steps=step)
                await tts_speak(final_result[:120])
                return final_result

        self._on_task_complete(task, settings.agent.max_steps, success=False)
        log.warning("task_timeout", max_steps=settings.agent.max_steps)
        self._task_log.end_task(success=False, result=final_result, total_steps=settings.agent.max_steps)
        return final_result

    # ── Step execution ────────────────────────────────────────────

    async def _execute_step(self, step: int, last_result: str) -> StepResult:
        """Execute a single step: perceive → decide → act → verify."""
        settings = get_settings()
        import time as _time

        # 1. Perceive — run screenshot + accessibility tree in parallel
        t_percept = _time.monotonic()

        async def _get_screenshot():
            return await self.screen.capture(save=False)

        async def _get_ax_tree():
            if not settings.accessibility.enabled:
                return ""
            elements = await self.accessibility.get_ui_tree()
            if elements:
                return self.accessibility.format_for_prompt(
                    elements, self.screen.width, self.screen.height
                )
            return ""

        (screenshot_b64, screenshot_img), ax_text = await asyncio.gather(
            _get_screenshot(), _get_ax_tree()
        )

        # Screen diff for verification
        diff = self.screen_diff.compare(screenshot_img)

        # OCR (only if accessibility tree is insufficient)
        ocr_text = ""
        if settings.ocr.enabled and not ax_text:
            ocr_results = await self.ocr.extract_text(screenshot_img)
            if ocr_results:
                ocr_text = self.ocr.format_for_prompt(
                    ocr_results, self.screen.width, self.screen.height
                )

        perception_ms = int((_time.monotonic() - t_percept) * 1000)

        # 2. Check if stuck
        stuck_warning = self._check_stuck(screenshot_b64)

        # 3. Decide action (run in thread to avoid blocking event loop)
        t0 = _time.monotonic()
        action = await asyncio.to_thread(
            self.executor.decide_action,
            screenshot_b64=screenshot_b64,
            task=self.short_memory.task,
            current_goal=self.short_memory.current_goal,
            last_result=last_result,
            step=step,
            max_steps=settings.agent.max_steps,
            memory_context=self.short_memory.format_for_prompt(),
            stuck_warning=stuck_warning,
            failed_targets_warning=self._format_failed_targets(),
            ax_tree_text=ax_text,
            ocr_text=ocr_text,
            screen_width=self.screen.width,
            screen_height=self.screen.height,
            mime_type=self.screen.mime_type,
        )
        llm_elapsed = _time.monotonic() - t0
        llm_ms = int(llm_elapsed * 1000)

        thought = getattr(action, "thought", "")
        act_name = action.action.value if hasattr(action.action, "value") else str(action.action)

        log.info(
            "action_decided",
            step=step,
            action=act_name,
            thought=thought[:80] if thought else "",
            llm_ms=llm_ms,
        )

        # TTS — speak the AI's reasoning, or a short action summary as fallback
        if thought:
            await tts_speak(thought)
        else:
            desc = getattr(action, "desc", "") or getattr(action, "app_name", "") or getattr(action, "query", "") or getattr(action, "text", "")
            if desc:
                await tts_speak(f"{act_name.replace('_', ' ')}: {str(desc)[:60]}")
            else:
                await tts_speak(act_name.replace("_", " "))

        # 4. Execute action
        t_exec = _time.monotonic()
        result = await self._dispatch_action(action)
        exec_ms = int((_time.monotonic() - t_exec) * 1000)

        # 5. Track
        self.short_memory.add_action(f"Step {step}: {act_name} → {result[:80]}")
        self._track_action_signature(action)

        # 6. Verify via screen diff (skip for reliable actions)
        verified = True
        verify_detail = ""
        screen_changed: bool | None = None
        change_ratio: float | None = None

        _skip_verify = (
            "wait", "save_data", "advance_plan", "replan", "done",
        )
        if act_name not in _skip_verify:
            await asyncio.sleep(0.15)
            post_b64, post_img = await self.screen.capture(save=False)
            post_diff = self.screen_diff.compare(post_img)
            screen_changed = post_diff.changed
            change_ratio = getattr(post_diff, "change_ratio", None)

            if not post_diff.changed and act_name not in ("scroll",):
                self.short_memory.add_failure(f"{act_name}: screen unchanged")
                self._consecutive_failures += 1
                verified = False
                verify_detail = "screen unchanged"
                result += " [WARNING: screen unchanged — action may have failed]"

                # Escalate
                if self._consecutive_failures >= settings.llm.escalation_threshold:
                    escalation_result = await self._escalate(
                        post_b64, f"{act_name} failed: {post_diff.description}"
                    )
                    result += f" {escalation_result}"
                    verify_detail = f"escalated: {post_diff.description}"
                    self._task_log.log_escalation(step, post_diff.description, escalation_result)
            else:
                self._consecutive_failures = 0
                verify_detail = f"screen changed ({change_ratio:.1%})" if change_ratio else "ok"
        else:
            verify_detail = "skipped (reliable action)"

        # 7. Extract action params for logging
        action_params = {}
        for field in ("x", "y", "text", "key", "keys", "direction", "amount",
                       "app_name", "query", "url", "selector", "ms", "desc",
                       "press_enter", "skill_name", "reason", "result", "command"):
            val = getattr(action, field, None)
            if val is not None:
                action_params[field] = val

        # 8. Log step to task log
        self._task_log.log_step(
            step=step,
            action_name=act_name,
            action_params=action_params,
            thought=thought,
            llm_ms=llm_ms,
            execution_result=result,
            verified=verified,
            verification_detail=verify_detail,
            screen_changed=screen_changed,
            change_ratio=change_ratio,
            stuck_warning=stuck_warning,
            perception_ms=perception_ms,
            execution_ms=exec_ms,
        )

        # 9. Handle meta-actions
        done = False
        done_result = ""

        if isinstance(action, DoneAction):
            done = True
            done_result = action.result or result

        return StepResult(
            action=action,
            result=result,
            verified=self._consecutive_failures == 0,
            done=done,
            done_result=done_result,
        )

    # ── Action dispatch ───────────────────────────────────────────

    async def _dispatch_action(self, action: AgentAction) -> str:
        """Route an action to the appropriate subsystem."""
        match action:
            # Memory actions
            case SaveDataAction():
                self.short_memory.store_data(action.key, action.value)
                return f"Saved: {action.key} = {action.value[:100]}"
            case AdvancePlanAction():
                self.short_memory.advance_plan(to=action.to)
                return f"Advanced plan → {self.short_memory.current_goal}"
            case ReplanAction():
                return await self._replan(action.reason)

            # Skill execution
            case ExecuteSkillAction():
                return await self._execute_skill(action.skill_name, action.params)

            # Done
            case DoneAction():
                return action.result or "Done"

            # All desktop actions (click, type, scroll, open_app, etc.)
            case _:
                return await self.desktop.execute(action)

    # ── Stuck detection ───────────────────────────────────────────

    def _check_stuck(self, screenshot_b64: str) -> str:
        recent = self._recent_actions
        is_stuck = False
        reason = ""

        # 3 identical actions
        if len(recent) >= 3 and len(set(recent[-3:])) == 1:
            is_stuck = True
            reason = f"Same action 3x: {recent[-1][:40]}"

        # 4 actions with ≤2 unique
        if not is_stuck and len(recent) >= 4 and len(set(recent[-4:])) <= 2:
            is_stuck = True
            reason = "Cycling between 2 actions"

        # Fuzzy click detection (all clicks within 80-unit box)
        if not is_stuck and len(recent) >= 3:
            click_coords = []
            for sig in recent[-4:]:
                parts = sig.split(":")
                if len(parts) >= 4 and parts[0] == "click":
                    try:
                        click_coords.append((int(parts[2]), int(parts[3])))
                    except ValueError:
                        pass
            if len(click_coords) >= 3:
                xs = [c[0] for c in click_coords[-3:]]
                ys = [c[1] for c in click_coords[-3:]]
                if (max(xs) - min(xs)) < 80 and (max(ys) - min(ys)) < 80:
                    is_stuck = True
                    reason = "Clicking same area repeatedly"

        # 4+ consecutive scrolls
        if not is_stuck and len(recent) >= 4:
            if all(s.split(":")[0] == "scroll" for s in recent[-4:]):
                is_stuck = True
                reason = "Excessive scrolling"

        # Cyclic detection (A-B-C-A-B-C)
        if not is_stuck and len(recent) >= 6:
            types = [s.split(":")[0] for s in recent]
            for cycle_len in (2, 3, 4):
                if len(types) >= cycle_len * 2:
                    if types[-cycle_len:] == types[-(cycle_len * 2):-cycle_len]:
                        is_stuck = True
                        reason = f"Cyclic pattern (length {cycle_len})"
                        break

        if is_stuck:
            self.short_memory.add_failure(f"Stuck: {reason}")
            # Remember failed click targets
            for sig in recent[-4:]:
                parts = sig.split(":")
                if len(parts) >= 4 and parts[0] == "click":
                    try:
                        self._failed_targets.append((int(parts[2]), int(parts[3])))
                    except ValueError:
                        pass
            self._failed_targets = self._failed_targets[-10:]

            new_plan = self.planner.create_plan(
                self.short_memory.task,
                context=f"STUCK: {reason}. Failed: {', '.join(self.short_memory.failures[-5:])}",
                screenshot_b64="",
            )
            old_done = self.short_memory.plan[: self.short_memory.current_step_idx]
            self.short_memory.set_plan(old_done + new_plan)
            self.short_memory.current_step_idx = len(old_done)
            self._recent_actions.clear()

            return (
                f"\n⚠️ AUTO-REPLANNED: {reason}. New plan:\n"
                + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(new_plan))
                + "\nTry a COMPLETELY DIFFERENT approach.\n"
            )

        return ""

    def _track_action_signature(self, action: AgentAction) -> None:
        """Build a signature string for stuck detection."""
        act = action.action.value if hasattr(action.action, "value") else str(action.action)

        if act in ("smart_type", "type_text", "paste_text"):
            text = getattr(action, "text", "")[:50]
            sig = f"{act}:{text}"
        elif act == "click":
            sig = f"{act}::{getattr(action, 'x', '')}:{getattr(action, 'y', '')}"
        else:
            sig = f"{act}:{hash(str(action)) & 0xFFFF}"

        self._recent_actions.append(sig)
        if len(self._recent_actions) > 20:
            self._recent_actions = self._recent_actions[-20:]

    def _format_failed_targets(self) -> str:
        if not self._failed_targets:
            return ""
        coords = ", ".join(f"({x},{y})" for x, y in self._failed_targets[-5:])
        return f"\n⚠️ FAILED CLICK TARGETS (avoid): {coords}\n"

    # ── Escalation & replanning ───────────────────────────────────

    async def _escalate(self, screenshot_b64: str, problem: str) -> str:
        """Escalate to planner for guidance."""
        log.info("escalating", problem=problem[:100])
        guidance = self.planner.escalate(
            screenshot_b64=screenshot_b64,
            problem=problem,
            task=self.short_memory.task,
            memory_context=self.short_memory.format_for_prompt(),
            screen_width=self.screen.width,
            screen_height=self.screen.height,
        )

        g_type = guidance.get("guidance", "advice")

        if g_type == "action" and isinstance(guidance.get("action"), dict):
            try:
                p_action = parse_action(guidance["action"])
                p_result = await self._dispatch_action(p_action)
                self._consecutive_failures = 0
                return f"[Planner guided: {p_result}]"
            except Exception as e:
                return f"[Planner action failed: {e}]"

        elif g_type == "replan":
            new_plan = guidance.get("plan", [])
            if new_plan:
                old_done = self.short_memory.plan[: self.short_memory.current_step_idx]
                self.short_memory.set_plan(old_done + new_plan)
                self.short_memory.current_step_idx = len(old_done)
                self._recent_actions.clear()
                self._consecutive_failures = 0
                return "[Planner replanned]"

        advice = guidance.get("advice", "Try different approach.")
        return f"[Planner: {advice[:200]}]"

    async def _replan(self, reason: str) -> str:
        context = f"Replan reason: {reason}"
        if self.short_memory.failures:
            context += f"\nFailed: {', '.join(self.short_memory.failures[-5:])}"

        new_plan = self.planner.create_plan(
            self.short_memory.task, context=context
        )
        old_done = self.short_memory.plan[: self.short_memory.current_step_idx]
        self.short_memory.set_plan(old_done + new_plan)
        self.short_memory.current_step_idx = len(old_done)
        self._recent_actions.clear()
        self._task_log.log_replan(self.short_memory.current_step_idx, reason, new_plan)
        return f"Replanned ({len(new_plan)} steps)"

    # ── Skill execution ───────────────────────────────────────────

    async def _execute_skill(self, name: str, params: dict) -> str:
        skill = self.skills.get(name)
        if not skill:
            return f"Skill not found: {name}"

        log.info("executing_skill", name=name, steps=len(skill.actions))
        for i, action_dict in enumerate(skill.actions):
            # Substitute params
            action_str = str(action_dict)
            for key, value in params.items():
                action_str = action_str.replace(f"${{{key}}}", str(value))

            try:
                import ast
                resolved = ast.literal_eval(action_str)
                action = parse_action(resolved)
                result = await self._dispatch_action(action)
                log.debug("skill_step", step=i + 1, result=result[:80])
            except Exception as e:
                self.skills.record_outcome(name, success=False)
                return f"Skill '{name}' failed at step {i + 1}: {e}"

        self.skills.record_outcome(name, success=True)
        return f"Skill '{name}' completed ({len(skill.actions)} steps)"

    # ── Lifecycle helpers ─────────────────────────────────────────

    def _reset(self, task: str) -> None:
        self.short_memory.reset(task)
        self.executor.reset()
        self._consecutive_failures = 0
        self._recent_actions.clear()
        self._failed_targets.clear()
        self.screen_diff.reset()

    def _on_task_complete(self, task: str, steps: int, *, success: bool) -> None:
        """Record task outcome in long-term memory."""
        self.long_memory.record_task(
            task, steps=steps, success=success, plan=self.short_memory.plan
        )
        if self.short_memory.plan:
            strategy = " → ".join(self.short_memory.plan[:5])
            task_type = " ".join(task.lower().split()[:3])
            self.long_memory.add_strategy(task_type, strategy, success=success, steps=steps)

    async def stop(self) -> None:
        """Clean shutdown."""
        pass
