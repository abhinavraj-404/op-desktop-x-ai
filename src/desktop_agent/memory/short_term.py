"""Short-term (per-task) working memory with structured plan tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop_agent.config import get_settings


@dataclass
class ShortTermMemory:
    """Per-task working memory. Tracks plan, collected data, and progress."""

    task: str = ""
    plan: list[str] = field(default_factory=list)
    current_step_idx: int = 0
    collected_data: dict[str, str] = field(default_factory=dict)
    action_history: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def reset(self, task: str) -> None:
        self.task = task
        self.plan = []
        self.current_step_idx = 0
        self.collected_data = {}
        self.action_history = []
        self.failures = []

    def set_plan(self, plan: list[str]) -> None:
        self.plan = plan
        self.current_step_idx = 0

    def advance_plan(self, *, to: int | None = None) -> None:
        if to is not None:
            target = max(0, min(to - 1, len(self.plan) - 1))
            self.current_step_idx = max(self.current_step_idx + 1, target)
        elif self.current_step_idx < len(self.plan) - 1:
            self.current_step_idx += 1

    @property
    def current_goal(self) -> str:
        if self.plan and self.current_step_idx < len(self.plan):
            return self.plan[self.current_step_idx]
        return self.task

    @property
    def progress_pct(self) -> float:
        if not self.plan:
            return 0.0
        return self.current_step_idx / len(self.plan)

    def store_data(self, key: str, value: str) -> None:
        self.collected_data[key] = value

    def add_action(self, summary: str) -> None:
        settings = get_settings()
        self.action_history.append(summary)
        # Trim to configured max
        max_actions = settings.memory.max_short_term_actions
        if len(self.action_history) > max_actions:
            self.action_history = self.action_history[-max_actions:]

    def add_failure(self, what: str) -> None:
        self.failures.append(what)
        if len(self.failures) > 20:
            self.failures = self.failures[-20:]

    def format_for_prompt(self) -> str:
        """Render as compact text for injection into the LLM context."""
        parts: list[str] = []

        if self.plan:
            plan_lines = []
            for i, step in enumerate(self.plan):
                if i < self.current_step_idx:
                    marker = "✓"
                elif i == self.current_step_idx:
                    marker = "→"
                else:
                    marker = " "
                plan_lines.append(f"  {marker} {i + 1}. {step}")
            parts.append("## Plan\n" + "\n".join(plan_lines))

        if self.collected_data:
            lines = [f"  - {k}: {v}" for k, v in self.collected_data.items()]
            parts.append("## Collected Data\n" + "\n".join(lines))

        if self.failures:
            parts.append(
                "## Failed Approaches (don't repeat)\n"
                + "\n".join(f"  - {f}" for f in self.failures[-5:])
            )

        if self.action_history:
            recent = self.action_history[-8:]
            parts.append("## Recent Actions\n" + "\n".join(f"  - {a}" for a in recent))

        return "\n\n".join(parts)
