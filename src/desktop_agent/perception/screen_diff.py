"""Screen diff engine — detect what changed between consecutive screenshots.

Used for instant action verification: if nothing changed, the action likely failed.
If a specific region changed, we can focus verification on that area.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from desktop_agent.log import get_logger

log = get_logger(__name__)


@dataclass
class DiffResult:
    """Result of comparing two screenshots."""

    changed: bool
    change_percentage: float  # 0.0 – 1.0
    changed_regions: list[tuple[int, int, int, int]]  # (x, y, w, h) bounding boxes
    description: str


class ScreenDiff:
    """Compare consecutive screenshots to detect changes."""

    def __init__(self, threshold: float = 0.01) -> None:
        self._threshold = threshold  # minimum change % to consider "changed"
        self._previous: np.ndarray | None = None

    def compare(self, current: Image.Image) -> DiffResult:
        """Compare current screenshot against the previous one.

        Returns a DiffResult describing what changed.
        """
        current_arr = np.array(current.convert("RGB"), dtype=np.float32)

        if self._previous is None:
            self._previous = current_arr
            return DiffResult(
                changed=True,
                change_percentage=1.0,
                changed_regions=[],
                description="First screenshot — no comparison available.",
            )

        # Ensure same dimensions
        if self._previous.shape != current_arr.shape:
            self._previous = current_arr
            return DiffResult(
                changed=True,
                change_percentage=1.0,
                changed_regions=[],
                description="Screen resolution changed.",
            )

        # Per-pixel difference
        diff = np.abs(current_arr - self._previous)
        pixel_diff = diff.mean(axis=2)  # average across RGB channels

        # Threshold: pixel is "changed" if diff > 15 (out of 255)
        changed_mask = pixel_diff > 15.0
        change_pct = changed_mask.mean()

        # Find bounding boxes of changed regions
        regions = self._find_regions(changed_mask)

        self._previous = current_arr

        if change_pct < self._threshold:
            return DiffResult(
                changed=False,
                change_percentage=change_pct,
                changed_regions=[],
                description=f"Screen essentially unchanged ({change_pct:.1%} diff).",
            )

        if change_pct > 0.8:
            desc = "Major screen change (likely app switch or new window)."
        elif change_pct > 0.3:
            desc = f"Significant change ({change_pct:.0%} of screen)."
        elif change_pct > 0.05:
            desc = f"Moderate change in {len(regions)} region(s)."
        else:
            desc = f"Minor change ({change_pct:.1%}) in {len(regions)} region(s)."

        return DiffResult(
            changed=True,
            change_percentage=change_pct,
            changed_regions=regions,
            description=desc,
        )

    def _find_regions(
        self, mask: np.ndarray, min_size: int = 20
    ) -> list[tuple[int, int, int, int]]:
        """Find bounding boxes of contiguous changed regions."""
        try:
            from skimage.measure import label, regionprops
        except ImportError:
            # Fallback: return single bounding box if any change
            if mask.any():
                ys, xs = np.where(mask)
                return [(int(xs.min()), int(ys.min()), int(xs.ptp()), int(ys.ptp()))]
            return []

        labeled = label(mask.astype(np.uint8))
        regions = []
        for prop in regionprops(labeled):
            if prop.area < min_size:
                continue
            y1, x1, y2, x2 = prop.bbox
            regions.append((x1, y1, x2 - x1, y2 - y1))

        # Merge overlapping regions and return top 10
        return regions[:10]

    def reset(self) -> None:
        """Clear the previous screenshot."""
        self._previous = None
