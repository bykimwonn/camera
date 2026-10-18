"""Deterministic, debounced single-hand gesture state machine."""
from __future__ import annotations
import math
import time
from typing import Any
import numpy as np
from utils.smoothing import EMAFilter, OneEuroFilter


class GestureEngine:
    """Recognizes deliberate gestures and dispatches through InputController."""
    def __init__(self, config: dict[str, Any], tracker: Any, controller: Any) -> None:
        self.cfg, self.tracker, self.io = config, tracker, controller
        self.ema = EMAFilter(float(config.get("smoothing_factor", .35)))
        self.euro = OneEuroFilter(float(config.get("one_euro_min_cutoff", 1)), float(config.get("one_euro_beta", .007)))
        self.pinched = False
        self.last_click = 0.0
        self.last_right = 0.0
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
        # Image y grows downward; robustly distinguish extended from curled fingers.
        return lm[tip][1] < lm[pip][1] - 0.015

    def process(self, lm: dict[int, np.ndarray] | None, timestamp: float | None = None) -> str:
        now = timestamp or time.monotonic()
        if self.paused or lm is None:
            self.mode = "PAUSED" if self.paused else "NO HAND"
            self.scroll_anchor = None
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

        # Zoom mode: three extended fingers and thumb-index pinch; distance changes drive zoom.
        if middle and ring and pinky and thumb_index < threshold * 1.8:
            if self.pinched: self.io.release_left()
            self.pinched = False
            if self.zoom_distance is not None and now - self.last_zoom > .18:
                delta = thumb_index - self.zoom_distance
                if abs(delta) >= float(self.cfg.get("zoom_threshold_delta", .02)):
                    self.io.zoom(1 if delta > 0 else -1)
                    self.last_zoom, self.zoom_distance = now, thumb_index
            else: self.zoom_distance = thumb_index
            self.mode = "ZOOMING"
            return self.mode
        self.zoom_distance = None

        # Scroll gesture has priority over cursor navigation.
        if index and middle and self._dist(lm[8], lm[12]) < .12:
            self.io.release_left(); self.pinched = False
            if self.scroll_anchor is None: self.scroll_anchor = float((lm[8][1] + lm[12][1]) / 2)
            delta = self.scroll_anchor - float((lm[8][1] + lm[12][1]) / 2)
            deadzone = float(self.cfg.get("scroll_deadzone_y", .08))
            if abs(delta) > deadzone:
                magnitude = min(8, max(1, int(math.expm1(min(abs(delta) * 8, 3)))))
                self.io.scroll(magnitude if delta > 0 else -magnitude)
                self.scroll_anchor = float((lm[8][1] + lm[12][1]) / 2)
            self.mode = "SCROLLING"
            return self.mode
        self.scroll_anchor = None

        # Right-click pinch is a one-shot event while index remains raised.
        if index and thumb_middle < threshold and now - self.last_right > .35:
            self.io.release_left(); self.pinched = False
            self.io.click_right(); self.last_right = now
            self.mode = "RIGHT CLICK"
            return self.mode

        # Left pinch uses hysteresis, holding button throughout a drag.
        if self.pinched:
            if thumb_index > threshold * 1.3:
                self.pinched = False; self.io.release_left()
                self.last_click = now
        elif thumb_index < threshold and now - self.last_click >= .15:
            self.pinched = True; self.io.press_left()
        if self.pinched:
            self.mode = "DRAGGING"
            return self.mode

        if index and not middle and not ring and not pinky:
            raw = self.tracker.map_to_screen(lm[8])
            if self.cfg.get("one_euro_filter_enabled", True):
                point = self.euro.filter(np.array(raw, dtype=float), now)
            else:
                point = self.ema.filter(np.array(raw, dtype=float))
            self.io.move(int(point[0]), int(point[1]))
            self.mode = "NAVIGATING"
        else:
            self.mode = "IDLE"
        return self.mode
