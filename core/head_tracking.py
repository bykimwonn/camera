"""Local face-landmark extraction for head-position cursor control."""
from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np


class HeadPositionTracker:
    """Use the face bounding-box center as a coarse, calibration-free cursor input.

    MediaPipe landmarks are processed locally only to locate the current face/head. No
    face templates, identity labels, or images are retained.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        import mediapipe as mp
        from utils.mediapipe_compat import load_solutions

        self.solutions = load_solutions(mp)
        self.mesh = self.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=float(config.get("min_detection_confidence", .65)),
            min_tracking_confidence=float(config.get("min_tracking_confidence", .65)),
        )
        import pyautogui
        self.screen_w, self.screen_h = map(int, pyautogui.size())
        self.margin = float(config.get("camera_margin", .20))
        self.logger = logging.getLogger("gestureflow.head")

    def process(self, rgb: np.ndarray) -> tuple[np.ndarray | None, np.ndarray]:
        """Return normalized face-center coordinates and an optional debug frame."""
        try:
            rgb.flags.writeable = False
            result = self.mesh.process(rgb)
            rgb.flags.writeable = True
            annotated = rgb.copy()
            if not result.multi_face_landmarks:
                return None, annotated

            points = result.multi_face_landmarks[0].landmark
            h, w = annotated.shape[:2]
            xs = np.asarray([p.x for p in points], dtype=float)
            ys = np.asarray([p.y for p in points], dtype=float)
            x0, x1 = float(xs.min()), float(xs.max())
            y0, y1 = float(ys.min()), float(ys.max())
            if x1 <= x0 or y1 <= y0:
                return None, annotated

            center = np.asarray([(x0 + x1) / 2, (y0 + y1) / 2], dtype=float)
            cv2.rectangle(annotated, (int(x0 * w), int(y0 * h)),
                          (int(x1 * w), int(y1 * h)), (56, 225, 178), 2)
            cv2.circle(annotated, (int(center[0] * w), int(center[1] * h)),
                       5, (0, 255, 255), -1)
            return center, annotated
        except Exception:
            self.logger.exception("Head landmark processing failed")
            try:
                rgb.flags.writeable = True
            except Exception:
                pass
            return None, rgb

    def map_to_screen(self, point: np.ndarray) -> tuple[int, int]:
        """Map head position within the camera frame to screen coordinates."""
        lo = max(0.0, min(.45, self.margin))
        hi = 1.0 - lo
        x = np.interp(float(point[0]), [lo, hi], [0, self.screen_w - 1])
        y = np.interp(float(point[1]), [lo, hi], [0, self.screen_h - 1])
        return int(np.clip(x, 0, self.screen_w - 1)), int(np.clip(y, 0, self.screen_h - 1))

    def close(self) -> None:
        self.mesh.close()
