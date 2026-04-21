"""Task scheduler — cron-style and one-shot scheduled task execution.

Supports:
- One-shot delayed tasks
- Recurring tasks (cron-like intervals)
- Priority-based queue
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Coroutine, Any

from desktop_agent.log import get_logger

log = get_logger(__name__)


class TaskPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class ScheduledTask:
    id: str
    name: str
    task_description: str  # Natural language task for the agent
    run_at: float  # Unix timestamp for next run
    interval: float | None = None  # Seconds between runs (None = one-shot)
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = field(default_factory=time.time)
    last_run: float | None = None
    run_count: int = 0
    enabled: bool = True


class Scheduler:
    """Manages scheduled tasks and fires them when due."""

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_task: Callable[[ScheduledTask], Coroutine[Any, Any, None]] | None = None

    def on_task_due(self, callback: Callable[[ScheduledTask], Coroutine[Any, Any, None]]) -> None:
        """Register async callback for when a task is due."""
        self._on_task = callback

    def schedule(
        self,
        name: str,
        task_description: str,
        *,
        delay_seconds: float = 0,
        interval_seconds: float | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """Schedule a new task. Returns task ID."""
        task_id = str(uuid.uuid4())[:8]
        task = ScheduledTask(
            id=task_id,
            name=name,
            task_description=task_description,
            run_at=time.time() + delay_seconds,
            interval=interval_seconds,
            priority=priority,
        )
        self._tasks[task_id] = task
        log.info("task_scheduled", id=task_id, name=name, delay=delay_seconds)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            log.info("task_cancelled", id=task_id)
            return True
        return False

    def list_tasks(self) -> list[ScheduledTask]:
        """List all scheduled tasks, sorted by next run time."""
        return sorted(self._tasks.values(), key=lambda t: t.run_at)

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("scheduler_started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("scheduler_stopped")

    async def _loop(self) -> None:
        while self._running:
            now = time.time()
            due_tasks = [
                t for t in self._tasks.values()
                if t.enabled and t.run_at <= now
            ]
            # Sort by priority (highest first)
            due_tasks.sort(key=lambda t: t.priority.value, reverse=True)

            for task in due_tasks:
                if self._on_task:
                    try:
                        log.info("task_firing", id=task.id, name=task.name)
                        await self._on_task(task)
                        task.last_run = now
                        task.run_count += 1

                        if task.interval:
                            task.run_at = now + task.interval
                        else:
                            del self._tasks[task.id]
                    except Exception as e:
                        log.error("task_execution_failed", id=task.id, error=str(e))

            await asyncio.sleep(1)
