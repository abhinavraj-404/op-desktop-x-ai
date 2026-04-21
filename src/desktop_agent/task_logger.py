"""Detailed JSON task logger — records every aspect of task execution.

Writes one JSONL (JSON Lines) file per task with full details:
task, plan, each step's thought process, action params, timing,
verification results, and final outcome.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)

_LOG_DIR = Path("data/logs/tasks")


class TaskLogger:
    """Logs comprehensive task execution details to a JSONL file."""

    def __init__(self) -> None:
        self._log_dir = _LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._file: Path | None = None
        self._task_id: str = ""
        self._task_start: float = 0.0
        self._step_records: list[dict] = []

    def start_task(self, task: str) -> None:
        """Begin logging a new task."""
        now = datetime.now(timezone.utc)
        self._task_id = now.strftime("%Y%m%d_%H%M%S")
        self._task_start = time.monotonic()
        self._step_records = []

        # One file per task: data/logs/tasks/20260420_115027.jsonl
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in task[:40]).strip()
        self._file = self._log_dir / f"{self._task_id}_{safe_name.replace(' ', '_')}.jsonl"

        self._write({
            "event": "task_started",
            "timestamp": now.isoformat(),
            "task": task,
            "task_id": self._task_id,
        })

    def log_plan(self, plan: list[str]) -> None:
        """Record the generated plan."""
        self._write({
            "event": "plan_created",
            "timestamp": self._now(),
            "elapsed_s": self._elapsed(),
            "plan": plan,
            "step_count": len(plan),
        })

    def log_step(
        self,
        *,
        step: int,
        action_name: str,
        action_params: dict,
        thought: str,
        llm_ms: int,
        execution_result: str,
        verified: bool,
        verification_detail: str = "",
        screen_changed: bool | None = None,
        change_ratio: float | None = None,
        stuck_warning: str = "",
        perception_ms: int = 0,
        execution_ms: int = 0,
    ) -> None:
        """Record full details of a single step."""
        record = {
            "event": "step_executed",
            "timestamp": self._now(),
            "elapsed_s": self._elapsed(),
            "step": step,
            "action": action_name,
            "params": action_params,
            "thought": thought,
            "timing": {
                "llm_decision_ms": llm_ms,
                "perception_ms": perception_ms,
                "execution_ms": execution_ms,
                "total_step_ms": perception_ms + llm_ms + execution_ms,
            },
            "result": execution_result[:500],
            "verification": {
                "verified": verified,
                "detail": verification_detail,
                "screen_changed": screen_changed,
                "change_ratio": change_ratio,
            },
            "stuck_warning": stuck_warning or None,
        }
        self._step_records.append(record)
        self._write(record)

    def log_escalation(self, step: int, reason: str, result: str) -> None:
        """Record an escalation event."""
        self._write({
            "event": "escalation",
            "timestamp": self._now(),
            "elapsed_s": self._elapsed(),
            "step": step,
            "reason": reason,
            "result": result[:500],
        })

    def log_replan(self, step: int, reason: str, new_plan: list[str] | None = None) -> None:
        """Record a replan event."""
        self._write({
            "event": "replan",
            "timestamp": self._now(),
            "elapsed_s": self._elapsed(),
            "step": step,
            "reason": reason,
            "new_plan": new_plan,
        })

    def end_task(self, *, success: bool, result: str, total_steps: int) -> None:
        """Finalize the task log with summary."""
        total_time = self._elapsed()
        avg_step_ms = int(total_time * 1000 / max(total_steps, 1))

        # Compute aggregate stats
        llm_times = [s["timing"]["llm_decision_ms"] for s in self._step_records]
        actions_used = [s["action"] for s in self._step_records]
        failed_steps = [s["step"] for s in self._step_records if not s["verification"]["verified"]]

        self._write({
            "event": "task_completed",
            "timestamp": self._now(),
            "task_id": self._task_id,
            "success": success,
            "result": result[:1000],
            "total_steps": total_steps,
            "total_time_s": round(total_time, 2),
            "avg_step_ms": avg_step_ms,
            "summary": {
                "actions_used": actions_used,
                "unique_actions": list(set(actions_used)),
                "failed_steps": failed_steps,
                "total_llm_time_ms": sum(llm_times) if llm_times else 0,
                "avg_llm_ms": int(sum(llm_times) / len(llm_times)) if llm_times else 0,
                "max_llm_ms": max(llm_times) if llm_times else 0,
            },
        })

        log.info(
            "task_log_saved",
            file=str(self._file),
            steps=total_steps,
            time_s=round(total_time, 2),
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _write(self, record: dict) -> None:
        if not self._file:
            return
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            log.debug("task_log_write_failed", error=str(e))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _elapsed(self) -> float:
        return round(time.monotonic() - self._task_start, 3)
