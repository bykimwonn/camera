"""MediaPipe landmark extraction and aspect-aware screen coordinate mapping."""
from __future__ import annotations
import logging
import time
from typing import Any
import numpy as np
import pyautogui


class HandTracker:
    """Wrap MediaPipe Hands; methods execute on the GUI/processing thread."""
    def __init__(self, config: dict[str, Any]) -> None:
        import mediapipe as mp
        if not hasattr(mp, "solutions"):
            raise RuntimeError(
                f"MediaPipe {getattr(mp, '__version__', 'unknown')} lacks the legacy solutions API. "
                "Install the supported version with: python -m pip install mediapipe==0.10.21"
            )
        self.mp = mp
        self.hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1,
            model_complexity=0, min_detection_confidence=float(config.get("min_detection_confidence", .75)),
            min_tracking_confidence=float(config.get("min_tracking_confidence", .75)))
        self.drawer = mp.solutions.drawing_utils
        self.screen_w, self.screen_h = pyautogui.size()
        self.margin = float(config.get("camera_margin", .15))
        self.logger = logging.getLogger("gestureflow.tracking")

    def process(self, rgb: np.ndarray) -> tuple[dict[int, np.ndarray] | None, np.ndarray]:
        try:
            rgb.flags.writeable = False
            result = self.hands.process(rgb)
            rgb.flags.writeable = True
            landmarks = None
            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                landmarks = {i: np.array([p.x, p.y, p.z], dtype=float) for i, p in enumerate(hand.landmark)}
                self.drawer.draw_landmarks(rgb, hand, self.mp.solutions.hands.HAND_CONNECTIONS)
            return landmarks, rgb
        except Exception:
            self.logger.exception("Landmark processing failed")
            return None, rgb

    def map_to_screen(self, point: np.ndarray) -> tuple[int, int]:
        """Map normalized camera coordinates into padded screen bounds."""
        x0, x1 = self.margin, 1 - self.margin
        y0, y1 = self.margin, 1 - self.margin
        x = float(np.interp(point[0], [x0, x1], [0, self.screen_w - 1]))
        y = float(np.interp(point[1], [y0, y1], [0, self.screen_h - 1]))
        return int(np.clip(x, 0, self.screen_w - 1)), int(np.clip(y, 0, self.screen_h - 1))

    def close(self) -> None:
        self.hands.close()
