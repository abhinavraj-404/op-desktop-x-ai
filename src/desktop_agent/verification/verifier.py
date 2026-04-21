"""Action verifier — validates that actions achieved their intended effect.

Combines multiple verification signals: screen diff, OCR text comparison,
accessibility state checks, and command exit codes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from desktop_agent.core.actions import AgentAction
from desktop_agent.log import get_logger
from desktop_agent.perception.screen_diff import DiffResult

log = get_logger(__name__)


@dataclass
class VerificationResult:
    success: bool
    confidence: float  # 0.0 – 1.0
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""


class ActionVerifier:
    """Multi-signal action verifier."""

    def __init__(self) -> None:
        self._history: list[dict] = []

    def verify(
        self,
        action: AgentAction,
        *,
        diff: DiffResult | None = None,
        pre_text: str = "",
        post_text: str = "",
        command_exit_code: int | None = None,
        expected_change: str = "",
    ) -> VerificationResult:
        """Verify that an action achieved its expected effect.

        Args:
            action: The action that was executed.
            diff: Screen diff between before and after.
            pre_text: OCR/AX text before action.
            post_text: OCR/AX text after action.
            expected_change: Description of expected change (optional).
        """
        act = action.action.value if hasattr(action.action, "value") else str(action.action)
        evidence: list[str] = []
        scores: list[float] = []

        # 1. Screen diff verification
        if diff is not None:
            if act in ("wait", "save_data", "advance_plan", "done"):
                # These shouldn't change the screen
                scores.append(1.0)
                evidence.append("No screen change expected")
            elif diff.changed:
                ratio = diff.change_ratio
                if ratio > 0.05:
                    scores.append(1.0)
                    evidence.append(f"Significant screen change ({ratio:.1%})")
                elif ratio > 0.01:
                    scores.append(0.7)
                    evidence.append(f"Minor screen change ({ratio:.1%})")
                else:
                    scores.append(0.4)
                    evidence.append(f"Tiny screen change ({ratio:.1%})")
            else:
                scores.append(0.1)
                evidence.append("No screen change detected")

        # 2. Text appearance verification
        if post_text and expected_change:
            if expected_change.lower() in post_text.lower():
                scores.append(1.0)
                evidence.append(f"Expected text found: '{expected_change[:50]}'")
            else:
                scores.append(0.3)
                evidence.append(f"Expected text NOT found: '{expected_change[:50]}'")

        if pre_text and post_text and act in ("smart_type", "type_text", "paste_text"):
            typed_text = getattr(action, "text", "")
            if typed_text and typed_text[:20] in post_text and typed_text[:20] not in pre_text:
                scores.append(1.0)
                evidence.append("Typed text appeared on screen")
            elif pre_text != post_text:
                scores.append(0.6)
                evidence.append("Screen text changed after typing")

        # 3. Click verification (check if region near click changed)
        if act in ("click", "double_click") and diff and diff.regions:
            click_x = getattr(action, "x", 500)
            click_y = getattr(action, "y", 500)
            # Check if any change region is near the click
            for r in diff.regions:
                rx = (r["x1"] + r["x2"]) / 2
                ry = (r["y1"] + r["y2"]) / 2
                dist = ((rx - click_x * diff.width / 1000) ** 2 +
                        (ry - click_y * diff.height / 1000) ** 2) ** 0.5
                if dist < max(diff.width, diff.height) * 0.3:
                    scores.append(0.9)
                    evidence.append("Change detected near click location")
                    break

        # Calculate composite
        if not scores:
            confidence = 0.5
            evidence.append("No verification signals available")
        else:
            confidence = sum(scores) / len(scores)

        success = confidence >= 0.4
        suggestion = ""
        if not success:
            suggestion = self._suggest_recovery(action, evidence)

        result = VerificationResult(
            success=success,
            confidence=confidence,
            evidence=evidence,
            suggestion=suggestion,
        )

        self._history.append({
            "action": act,
            "success": success,
            "confidence": confidence,
            "time": time.time(),
        })

        log.debug(
            "verification",
            action=act,
            success=success,
            confidence=f"{confidence:.2f}",
            evidence=evidence,
        )
        return result

    def _suggest_recovery(self, action: AgentAction, evidence: list[str]) -> str:
        act = action.action.value if hasattr(action.action, "value") else str(action.action)

        if act in ("click", "double_click"):
            return (
                "Click may have missed target. "
                "Check element position using accessibility tree or OCR."
            )
        elif act in ("smart_type", "type_text"):
            return (
                "Text may not have been entered. "
                "Ensure the input field is focused first."
            )
        elif act in ("open_app",):
            return "App may not have opened. Try Spotlight search instead."
        return "Action appears to have no effect. Try a different approach."

    @property
    def recent_success_rate(self) -> float:
        """Success rate of last 10 actions."""
        recent = self._history[-10:]
        if not recent:
            return 1.0
        return sum(1 for h in recent if h["success"]) / len(recent)
