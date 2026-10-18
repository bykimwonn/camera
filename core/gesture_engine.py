"""Deterministic, mutually exclusive single-hand gesture state machine."""
from __future__ import annotations
import math
import time
from typing import Any
import numpy as np
from utils.smoothing import EMAFilter, OneEuroFilter


class GestureEngine:
    """Recognize one deliberate gesture at a time and dispatch OS input."""
    def __init__(self, config: dict[str, Any], tracker: Any, controller: Any) -> None:
        self.cfg, self.tracker, self.io = config, tracker, controller
        self.ema = EMAFilter(float(config.get("smoothing_factor", .35)))
        self.euro = OneEuroFilter(float(config.get("one_euro_min_cutoff", 1)), float(config.get("one_euro_beta", .007)))
        self.pinched = False
        self.right_pinched = False
        self.last_click = 0.0
        self.scroll_anchor: float | None = None
        self.zoom_distance: float | None = None
        self.last_zoom = 0.0
        self.mode = "WAITING"
        self.paused = False

    @staticmethod
    def _dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a[:2] - b[:2]))

    @staticmethod
    def _extended(lm: dict[int, np.ndarray], tip: int, pip: int) -> bool:
        """Approximate extension from fingertip/PIP vertical separation."""
        return lm[tip][1] < lm[pip][1] - 0.015

    def _move_cursor(self, lm: dict[int, np.ndarray], now: float) -> None:
        raw = self.tracker.map_to_screen(lm[8])
        if self.cfg.get("one_euro_filter_enabled", True):
            point = self.euro.filter(np.array(raw, dtype=float), now)
        else:
            point = self.ema.filter(np.array(raw, dtype=float))
        self.io.move(int(point[0]), int(point[1]))

    def process(self, lm: dict[int, np.ndarray] | None, timestamp: float | None = None) -> str:
        now = timestamp if timestamp is not None else time.monotonic()
        if self.paused or lm is None:
            self.mode = "PAUSED" if self.paused else "NO HAND"
            self.scroll_anchor = None
            self.right_pinched = False
            self.io.release_left()
            self.pinched = False
            self.ema.reset(); self.euro.reset()
            return self.mode

        index = self._extended(lm, 8, 6)
        middle = self._extended(lm, 12, 10)
        ring = self._extended(lm, 16, 14)
        pinky = self._extended(lm, 20, 18)
        thumb_index = self._dist(lm[4], lm[8])
        thumb_middle = self._dist(lm[4], lm[12])
        threshold = float(self.cfg.get("click_distance_threshold", .035))
        cursor_pose = not middle and not ring and not pinky

        # Priority 1: deliberate zoom pose (three long fingers plus thumb/index pinch).
        if middle and ring and pinky and thumb_index < threshold * 1.8:
            self.io.release_left(); self.pinched = False
            self.right_pinched = False
            if self.zoom_distance is not None and now - self.last_zoom > .18:
                delta = thumb_index - self.zoom_distance
                if abs(delta) >= float(self.cfg.get("zoom_threshold_delta", .02)):
                    self.io.zoom(1 if delta > 0 else -1)
                    self.last_zoom, self.zoom_distance = now, thumb_index
            else:
                self.zoom_distance = thumb_index
            self.scroll_anchor = None
            self.mode = "ZOOMING"
            return self.mode
        self.zoom_distance = None

        # Priority 2: right click is a one-shot thumb/middle pinch with index raised.
        # A latch prevents a held pinch from producing repeated clicks.
        right_pose = index and thumb_middle < threshold
        if not right_pose:
            self.right_pinched = False
        if right_pose:
            self.io.release_left(); self.pinched = False
            self.scroll_anchor = None
            if not self.right_pinched:
                self.io.click_right()
                self.right_pinched = True
            self.mode = "RIGHT CLICK"
            return self.mode

        # Priority 3: scroll pose requires index+middle extended, the other fingers
        # curled, fingertips close, and neither thumb pinch active.
        pair_distance = self._dist(lm[8], lm[12])
        pair_limit = float(self.cfg.get("scroll_pair_distance_threshold", .10))
        no_thumb_pinch = thumb_index > threshold * 1.5 and thumb_middle > threshold * 1.5
        if index and middle and not ring and not pinky and pair_distance < pair_limit and no_thumb_pinch:
            self.io.release_left(); self.pinched = False
            center_y = float((lm[8][1] + lm[12][1]) / 2)
            if self.scroll_anchor is None:
                self.scroll_anchor = center_y
            delta = self.scroll_anchor - center_y
            deadzone = float(self.cfg.get("scroll_deadzone_y", .08))
            if abs(delta) > deadzone:
                magnitude = min(8, max(1, int(math.expm1(min(abs(delta) * 8, 3)))))
                self.io.scroll(magnitude if delta > 0 else -magnitude)
                self.scroll_anchor = center_y
            self.mode = "SCROLLING"
            return self.mode
        self.scroll_anchor = None

        # Priority 4: thumb/index pinch with other fingers curled is left press/drag.
        if cursor_pose and self.pinched:
            if thumb_index > threshold * 1.3:
                self.pinched = False
                self.io.release_left()
                self.last_click = now
            else:
                self._move_cursor(lm, now)
                self.mode = "DRAGGING"
                return self.mode
        elif cursor_pose and thumb_index < threshold and now - self.last_click >= .15:
            self.pinched = True
            self.io.press_left()
            self._move_cursor(lm, now)
            self.mode = "DRAGGING"
            return self.mode
        elif self.pinched:
            self.pinched = False
            self.io.release_left()

        # Priority 5: navigation is index alone; all other fingertips curled.
        if index and not middle and not ring and not pinky:
            self._move_cursor(lm, now)
            self.mode = "NAVIGATING"
        else:
            self.mode = "IDLE"
        return self.mode
