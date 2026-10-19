"""Dwell-to-left-click state machine for head-position cursor control."""
from __future__ import annotations

import math
from typing import Optional


class DwellClicker:
    """Click once after the cursor remains near a point; re-arm after moving away."""

    def __init__(self, dwell_seconds: float = 1.0, radius_px: float = 32.0,
                 rearm_distance_px: float = 72.0) -> None:
        self.dwell_seconds = max(.25, float(dwell_seconds))
        self.radius_px = max(4.0, float(radius_px))
        self.rearm_distance_px = max(self.radius_px, float(rearm_distance_px))
        self._anchor: Optional[tuple[float, float]] = None
        self._started: Optional[float] = None
        self._clicked_at: Optional[tuple[float, float]] = None

    def update(self, point: tuple[float, float], now: float) -> tuple[bool, float, str]:
        """Return (click_now, progress_0_to_1, status)."""
        x, y = map(float, point)
        if self._clicked_at is not None:
            moved = math.hypot(x - self._clicked_at[0], y - self._clicked_at[1])
            if moved < self.rearm_distance_px:
                return False, 1.0, "CLICKED — move head to re-arm"
            self._clicked_at = None
            self._anchor = (x, y)
            self._started = now

        if self._anchor is None or self._started is None:
            self._anchor = (x, y)
            self._started = now
            return False, 0.0, f"DWELL 0/{self.dwell_seconds:.1f}s"

        moved = math.hypot(x - self._anchor[0], y - self._anchor[1])
        if moved > self.radius_px:
            self._anchor = (x, y)
            self._started = now
            return False, 0.0, f"DWELL 0/{self.dwell_seconds:.1f}s"

        progress = max(0.0, min(1.0, (now - self._started) / self.dwell_seconds))
        if progress >= 1.0:
            self._clicked_at = (x, y)
            self._anchor = None
            self._started = None
            return True, 1.0, "LEFT CLICK — move head to re-arm"
        return False, progress, f"DWELL {now - self._started:.1f}/{self.dwell_seconds:.1f}s"

    def face_lost(self) -> None:
        """Cancel an in-progress dwell if the head leaves the camera."""
        self._anchor = None
        self._started = None
