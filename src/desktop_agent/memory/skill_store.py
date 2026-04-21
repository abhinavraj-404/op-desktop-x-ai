"""Skill library — reusable action sequences (macros) that the agent learns.

When a task is completed successfully, the action sequence can be stored
as a named skill.  When a similar task appears later, the agent can replay
the skill with parameter substitution instead of re-reasoning from scratch.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


class Skill:
    """A named, replayable sequence of actions."""

    def __init__(
        self,
        name: str,
        description: str,
        actions: list[dict],
        *,
        params: list[str] | None = None,
        success_count: int = 0,
        fail_count: int = 0,
    ) -> None:
        self.name = name
        self.description = description
        self.actions = actions
        self.params = params or []
        self.success_count = success_count
        self.fail_count = fail_count
        self.created_at = time.time()

    @property
    def reliability(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.5

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "actions": self.actions,
            "params": self.params,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        skill = cls(
            name=data["name"],
            description=data["description"],
            actions=data["actions"],
            params=data.get("params", []),
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
        )
        skill.created_at = data.get("created_at", time.time())
        return skill


class SkillLibrary:
    """Persistent skill storage with search and replay."""

    def __init__(self) -> None:
        settings = get_settings()
        self._path = Path(settings.memory.skill_library_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self._path.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                skill = Skill.from_dict(data)
                self._skills[skill.name] = skill
            except Exception as e:
                log.warning("skill_load_failed", file=str(f), error=str(e))

    def _save_skill(self, skill: Skill) -> None:
        path = self._path / f"{skill.name}.json"
        path.write_text(json.dumps(skill.to_dict(), indent=2))

    def register(
        self,
        name: str,
        description: str,
        actions: list[dict],
        *,
        params: list[str] | None = None,
    ) -> Skill:
        """Register a new skill or update an existing one."""
        if name in self._skills:
            existing = self._skills[name]
            existing.actions = actions
            existing.description = description
            if params:
                existing.params = params
            self._save_skill(existing)
            log.info("skill_updated", name=name)
            return existing

        skill = Skill(name=name, description=description, actions=actions, params=params)
        self._skills[name] = skill
        self._save_skill(skill)
        log.info("skill_registered", name=name, steps=len(actions))
        return skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def search(self, query: str, n: int = 5) -> list[Skill]:
        """Simple keyword search over skill names and descriptions."""
        query_lower = query.lower()
        scored: list[tuple[float, Skill]] = []

        for skill in self._skills.values():
            text = f"{skill.name} {skill.description}".lower()
            # Count keyword overlap
            words = query_lower.split()
            score = sum(1 for w in words if w in text)
            if score > 0:
                scored.append((score * skill.reliability, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:n]]

    def record_outcome(self, name: str, *, success: bool) -> None:
        """Record whether a skill execution succeeded or failed."""
        skill = self._skills.get(name)
        if skill:
            if success:
                skill.success_count += 1
            else:
                skill.fail_count += 1
            self._save_skill(skill)

    def list_all(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.reliability, reverse=True)

    def format_for_prompt(self, query: str) -> str:
        """Format relevant skills for injection into the LLM prompt."""
        relevant = self.search(query, n=3)
        if not relevant:
            return ""

        lines = ["## Available Skills (reusable macros)"]
        for s in relevant:
            lines.append(
                f"  - **{s.name}**: {s.description} "
                f"({len(s.actions)} steps, {s.reliability:.0%} reliable)"
            )
            if s.params:
                lines.append(f"    params: {', '.join(s.params)}")
        return "\n".join(lines)
