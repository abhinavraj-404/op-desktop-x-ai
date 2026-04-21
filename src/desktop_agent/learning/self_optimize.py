"""Self-optimizer — analyses past task performance to improve prompts and strategies.

Periodically reviews completed tasks, identifies failure patterns,
and proposes adjustments to prompts and retry strategies.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from desktop_agent.memory.long_term import LongTermMemory
from desktop_agent.memory.skill_store import SkillLibrary
from desktop_agent.log import get_logger

log = get_logger(__name__)


@dataclass
class OptimizationInsight:
    category: str  # "failure_pattern" | "strategy" | "prompt_tweak"
    description: str
    confidence: float
    suggested_action: str
    evidence: list[str] = field(default_factory=list)


class SelfOptimizer:
    """Analyses task history and proposes improvements."""

    def __init__(self, long_memory: LongTermMemory, skills: SkillLibrary) -> None:
        self._memory = long_memory
        self._skills = skills
        self._insights: list[OptimizationInsight] = []

    def analyse_recent_performance(self, n_tasks: int = 20) -> list[OptimizationInsight]:
        """Analyse recent tasks and identify optimization opportunities."""
        insights: list[OptimizationInsight] = []

        # Check skill reliability
        for skill in self._skills.list_all():
            if skill.times_used >= 3 and skill.reliability < 0.5:
                insights.append(OptimizationInsight(
                    category="strategy",
                    description=f"Skill '{skill.name}' has low reliability ({skill.reliability:.0%})",
                    confidence=0.8,
                    suggested_action=f"Review and update skill '{skill.name}' or remove it",
                    evidence=[
                        f"Used {skill.times_used} times",
                        f"Success rate: {skill.reliability:.0%}",
                    ],
                ))

        # Check for common failure patterns in memory
        failures = self._memory.query("failed actions common patterns", n_results=10)
        if failures:
            click_failures = [f for f in failures if "click" in f.lower()]
            if len(click_failures) >= 3:
                insights.append(OptimizationInsight(
                    category="failure_pattern",
                    description="Frequent click failures detected",
                    confidence=0.7,
                    suggested_action="Increase use of accessibility tree for element targeting",
                    evidence=click_failures[:3],
                ))

            type_failures = [f for f in failures if "type" in f.lower() or "text" in f.lower()]
            if len(type_failures) >= 3:
                insights.append(OptimizationInsight(
                    category="failure_pattern",
                    description="Frequent typing failures detected",
                    confidence=0.7,
                    suggested_action="Default to paste_text over type_text for reliability",
                    evidence=type_failures[:3],
                ))

        self._insights = insights
        log.info("optimization_analysis", insights=len(insights))
        return insights

    def get_prompt_adjustments(self) -> list[str]:
        """Return prompt adjustment suggestions based on insights."""
        adjustments = []
        for insight in self._insights:
            if insight.confidence >= 0.6:
                adjustments.append(
                    f"[{insight.category}] {insight.suggested_action} "
                    f"(confidence: {insight.confidence:.0%})"
                )
        return adjustments
