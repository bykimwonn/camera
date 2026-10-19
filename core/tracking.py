"""MediaPipe landmark extraction and aspect-aware screen coordinate mapping."""
from __future__ import annotations
import logging
import time
from typing import Any
import cv2
import numpy as np
import pyautogui


class HandTracker:
    """Wrap MediaPipe Hands; methods execute on the GUI/processing thread."""
    def __init__(self, config: dict[str, Any]) -> None:
        import mediapipe as mp
        from utils.mediapipe_compat import load_solutions
        self.mp = mp
        self.solutions = load_solutions(mp)
        self.hands = self.solutions.hands.Hands(static_image_mode=False, max_num_hands=1,
            model_complexity=0, min_detection_confidence=float(config.get("min_detection_confidence", .75)),
            min_tracking_confidence=float(config.get("min_tracking_confidence", .75)))
        self.drawer = self.solutions.drawing_utils
        self.screen_w, self.screen_h = pyautogui.size()
        self.margin = float(config.get("camera_margin", .15))
        self.invert_cursor_x = bool(config.get("invert_cursor_x", True))
        self.low_light_enhancement = bool(config.get("low_light_enhancement", True))
        self._low_light_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.logger = logging.getLogger("gestureflow.tracking")

    def _enhance_dim_frame(self, rgb: np.ndarray) -> np.ndarray:
        """Apply mild CLAHE to luminance only when the frame is actually dim."""
        if not self.low_light_enhancement:
            return rgb
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        if float(np.mean(gray)) >= 95.0:
            return rgb
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        lab[:, :, 0] = self._low_light_clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    def process(self, rgb: np.ndarray) -> tuple[dict[int, np.ndarray] | None, np.ndarray]:
        try:
            rgb = self._enhance_dim_frame(rgb)
            rgb.flags.writeable = False
            result = self.hands.process(rgb)
            rgb.flags.writeable = True
            landmarks = None
            if result.multi_hand_landmarks:
                hand = result.multi_hand_landmarks[0]
                landmarks = {i: np.array([p.x, p.y, p.z], dtype=float) for i, p in enumerate(hand.landmark)}
                self.drawer.draw_landmarks(rgb, hand, self.solutions.hands.HAND_CONNECTIONS)
            return landmarks, rgb
        except Exception:
            self.logger.exception("Landmark processing failed")
            return None, rgb

    def map_to_screen(self, point: np.ndarray) -> tuple[int, int]:
        """Map normalized camera coordinates into padded screen bounds."""
        x0, x1 = self.margin, 1 - self.margin
        y0, y1 = self.margin, 1 - self.margin
        camera_x = 1.0 - float(point[0]) if self.invert_cursor_x else float(point[0])
        x = float(np.interp(camera_x, [x0, x1], [0, self.screen_w - 1]))
        y = float(np.interp(point[1], [y0, y1], [0, self.screen_h - 1]))
        return int(np.clip(x, 0, self.screen_w - 1)), int(np.clip(y, 0, self.screen_h - 1))

    def close(self) -> None:
        self.hands.close()
