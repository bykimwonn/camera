"""Deterministic, mutually exclusive single-hand gesture state machine."""
from __future__ import annotations
import math
import time
from typing import Any
import numpy as np
from utils.smoothing import EMAFilter, OneEuroFilter


class GestureEngine:
    """Recognize deliberate poses; left taps and drags use separate timing paths."""
    def __init__(self, config: dict[str, Any], tracker: Any, controller: Any) -> None:
        self.cfg, self.tracker, self.io = config, tracker, controller
        self.ema = EMAFilter(float(config.get("smoothing_factor", .35)))
        self.euro = OneEuroFilter(float(config.get("one_euro_min_cutoff", .7)), float(config.get("one_euro_beta", .015)))
        self.cursor_deadband_px = max(0.0, float(config.get("cursor_deadband_px", 4.0)))
        self.cursor_position: np.ndarray | None = None
        self.left_pinching = False
        self.left_dragging = False
        self.left_pinch_started: float | None = None
        self.right_pinched = False
        self.scroll_anchor: float | None = None
        self.zoom_active = False
        self.zoom_distance: float | None = None
        self.last_zoom = 0.0
        self.mode = "WAITING"
        self.paused = False

    @staticmethod
    def _dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a[:2] - b[:2]))

    @staticmethod
    def _extended(lm: dict[int, np.ndarray], tip: int, pip: int) -> bool:
        """Estimate extension from tip/PIP y positions in normalized image space."""
        return lm[tip][1] < lm[pip][1] - 0.015

    def _move_cursor(self, lm: dict[int, np.ndarray], now: float) -> None:
        raw = self.tracker.map_to_screen(lm[8])
        if self.cfg.get("one_euro_filter_enabled", True):
            point = self.euro.filter(np.array(raw, dtype=float), now)
        else:
            point = self.ema.filter(np.array(raw, dtype=float))
        if not np.all(np.isfinite(point)):
            return
        if self.cursor_position is not None:
            delta = point - self.cursor_position
            if float(np.linalg.norm(delta)) < self.cursor_deadband_px:
                return
        self.cursor_position = np.asarray(point, dtype=float).copy()
        self.io.move(int(round(point[0])), int(round(point[1])))

    def _cancel_left_pinch(self) -> None:
        if self.left_dragging:
            self.io.release_left()
        self.left_pinching = self.left_dragging = False
        self.left_pinch_started = None

    def process(self, lm: dict[int, np.ndarray] | None, timestamp: float | None = None) -> str:
        now = timestamp if timestamp is not None else time.monotonic()
        if self.paused or lm is None:
            self.mode = "PAUSED" if self.paused else "NO HAND"
            self.scroll_anchor = None
            self.right_pinched = self.zoom_active = False
            self._cancel_left_pinch()
            self.ema.reset(); self.euro.reset()
            return self.mode

        index = self._extended(lm, 8, 6)
        middle = self._extended(lm, 12, 10)
        ring = self._extended(lm, 16, 14)
        pinky = self._extended(lm, 20, 18)
        thumb_index = self._dist(lm[4], lm[8])
        thumb_middle = self._dist(lm[4], lm[12])
        threshold = float(self.cfg.get("click_distance_threshold", .045))
        release_threshold = threshold * float(self.cfg.get("click_release_hysteresis", 1.35))
        cursor_pose = not middle and not ring and not pinky

        # 1) Zoom: three non-index fingers stay extended. A thumb/index pinch arms
        # the mode; subsequent expansion/contraction produces discrete zoom steps.
        zoom_fingers = middle and ring and pinky
        if not self.zoom_active and zoom_fingers and thumb_index < threshold * 1.8:
            self.zoom_active = True
            self.zoom_distance = thumb_index
        if self.zoom_active:
            if not zoom_fingers:
                self.zoom_active = False
                self.zoom_distance = None
            else:
                self._cancel_left_pinch()
                self.right_pinched = False
                self.scroll_anchor = None
                if self.zoom_distance is not None and now - self.last_zoom >= .22:
                    delta = thumb_index - self.zoom_distance
                    step = float(self.cfg.get("zoom_threshold_delta", .012))
                    if abs(delta) >= step:
                        self.io.zoom(1 if delta > 0 else -1)
                        self.last_zoom = now
                        self.zoom_distance = thumb_index
                self.mode = "ZOOMING"
                return self.mode

        # 2) Right click is one event per thumb/middle pinch, with index raised.
        right_pose = index and thumb_middle < threshold
        if not right_pose:
            self.right_pinched = False
        if right_pose:
            self._cancel_left_pinch()
            self.scroll_anchor = None
            if not self.right_pinched:
                self.io.click_right()
                self.right_pinched = True
            self.mode = "RIGHT CLICK"
            return self.mode

        # 3) Scroll with index+middle up, close together, other fingers curled,
        # and no thumb pinch. Small hand travel yields a controlled scroll step.
        pair_distance = self._dist(lm[8], lm[12])
        pair_limit = float(self.cfg.get("scroll_pair_distance_threshold", .10))
        no_thumb_pinch = thumb_index > threshold * 1.5 and thumb_middle > threshold * 1.5
        if index and middle and not ring and not pinky and pair_distance < pair_limit and no_thumb_pinch:
            self._cancel_left_pinch()
            center_y = float((lm[8][1] + lm[12][1]) / 2)
            if self.scroll_anchor is None:
                self.scroll_anchor = center_y
            delta = self.scroll_anchor - center_y
            deadzone = float(self.cfg.get("scroll_deadzone_y", .025))
            if abs(delta) >= deadzone:
                sensitivity = float(self.cfg.get("scroll_sensitivity", 120))
                magnitude = max(1, min(10, int(round(abs(delta) * sensitivity))))
                self.io.scroll(magnitude if delta > 0 else -magnitude)
                self.scroll_anchor = center_y
            self.mode = "SCROLLING"
            return self.mode
        self.scroll_anchor = None

        # 4) Thumb/index pinch is a pending tap. Release before the hold delay to
        # click; hold past the delay to begin a drag. This avoids accidental drags.
        if self.left_pinching:
            if not cursor_pose or thumb_index > release_threshold:
                if self.left_dragging:
                    self.io.release_left()
                elif cursor_pose and thumb_index > release_threshold:
                    self.io.click_left()
                self.left_pinching = self.left_dragging = False
                self.left_pinch_started = None
            elif not self.left_dragging:
                hold_ms = float(self.cfg.get("left_drag_hold_ms", 450))
                if self.left_pinch_started is not None and (now - self.left_pinch_started) * 1000 >= hold_ms:
                    self.io.press_left()
                    self.left_dragging = True
            if self.left_pinching:
                if self.left_dragging:
                    self._move_cursor(lm, now)
                    self.mode = "DRAGGING"
                else:
                    self.mode = "CLICK READY"
                return self.mode

        if cursor_pose and thumb_index < threshold:
            self.left_pinching = True
            self.left_dragging = False
            self.left_pinch_started = now
            self.mode = "CLICK READY"
            return self.mode

        # 5) Move with index alone. Screen mapping is calibrated and smoothed.
        if index and not middle and not ring and not pinky:
            self._move_cursor(lm, now)
            self.mode = "NAVIGATING"
        else:
            self.mode = "IDLE"
        return self.mode
