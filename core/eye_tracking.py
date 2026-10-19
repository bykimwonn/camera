"""Local MediaPipe iris tracking and nine-point gaze calibration."""
from __future__ import annotations
import logging
import time
from typing import Any
import cv2
import numpy as np


class EyeGazeTracker:
    """Estimate screen gaze from iris landmarks; calibration is required per user/screen."""
    GRID = (0.08, 0.50, 0.92)
    SETTLE_SECONDS = 0.55
    SAMPLES_PER_TARGET = 12

    def __init__(self, config: dict[str, Any]) -> None:
        import mediapipe as mp
        from utils.mediapipe_compat import load_solutions
        self.mp = mp
        self.solutions = load_solutions(mp)
        self.mesh = self.solutions.face_mesh.FaceMesh(
            static_image_mode=False, max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=float(config.get("min_detection_confidence", .65)),
            min_tracking_confidence=float(config.get("min_tracking_confidence", .65)),
        )
        import pyautogui
        self.screen_w, self.screen_h = map(int, pyautogui.size())
        self.logger = logging.getLogger("gestureflow.eye")
        self.coefficients: np.ndarray | None = self._load_coefficients(config.get("eye_calibration"))
        self.calibrating = False
        self.calibration_success = False
        self.calibration_status = "Ready to calibrate"
        self._targets_ui: list[tuple[float, float]] = []
        self._targets_output: list[tuple[float, float]] = []
        self._target_index = 0
        self._target_started = 0.0
        self._target_samples: list[np.ndarray] = []
        self._features: list[np.ndarray] = []
        self._target_points: list[np.ndarray] = []
        self.latest_feature: np.ndarray | None = None

    @staticmethod
    def _load_coefficients(value: Any) -> np.ndarray | None:
        try:
            coeff = np.asarray(value, dtype=float)
            if coeff.shape == (5, 2) and np.all(np.isfinite(coeff)):
                return coeff
        except (TypeError, ValueError):
            pass
        return None

    @property
    def calibrated(self) -> bool:
        return self.coefficients is not None

    @property
    def calibration_target(self) -> tuple[int, int] | None:
        if not self.calibrating or self._target_index >= len(self._targets_ui):
            return None
        return tuple(map(int, self._targets_ui[self._target_index]))

    @property
    def calibration_progress(self) -> tuple[int, int]:
        return self._target_index + 1, len(self._targets_ui)

    @staticmethod
    def _xy(landmarks, index: int) -> np.ndarray:
        p = landmarks[index]
        return np.array([p.x, p.y], dtype=float)

    @classmethod
    def _eye_ratio(cls, landmarks, iris_ids: range, corner_a: int, corner_b: int,
                   upper_lid: int, lower_lid: int) -> tuple[float, float] | None:
        iris = np.mean([cls._xy(landmarks, i) for i in iris_ids], axis=0)
        a, b = cls._xy(landmarks, corner_a), cls._xy(landmarks, corner_b)
        top, bottom = cls._xy(landmarks, upper_lid), cls._xy(landmarks, lower_lid)
        dx, dy = b[0] - a[0], bottom[1] - top[1]
        if abs(dx) < 1e-4 or abs(dy) < 1e-4:
            return None
        return float((iris[0] - a[0]) / dx), float((iris[1] - top[1]) / dy)

    def process(self, rgb: np.ndarray) -> tuple[np.ndarray | None, np.ndarray]:
        """Return four normalized iris-relative-to-eye features and annotated frame."""
        try:
            rgb.flags.writeable = False
            result = self.mesh.process(rgb)
            rgb.flags.writeable = True
            annotated = rgb.copy()
            self.latest_feature = None
            if not result.multi_face_landmarks:
                return None, annotated
            points = result.multi_face_landmarks[0].landmark
            left = self._eye_ratio(points, range(468, 473), 33, 133, 159, 145)
            right = self._eye_ratio(points, range(473, 478), 362, 263, 386, 374)
            if left is None or right is None:
                return None, annotated
            feature = np.asarray([left[0], right[0], left[1], right[1]], dtype=float)
            if not np.all(np.isfinite(feature)):
                return None, annotated
            self.latest_feature = feature
            h, w = annotated.shape[:2]
            for idx in (468, 473):
                p = points[idx]
                cv2.circle(annotated, (int(p.x * w), int(p.y * h)), 3, (0, 255, 255), -1)
            return feature, annotated
        except Exception:
            self.logger.exception("Eye landmark processing failed")
            try:
                rgb.flags.writeable = True
            except Exception:
                pass
            return None, rgb

    def begin_calibration(self, screen_origin: tuple[int, int] = (0, 0),
                          view_size: tuple[int, int] | None = None) -> None:
        ox, oy = screen_origin
        view_w, view_h = view_size or (self.screen_w, self.screen_h)
        self._targets_ui = [(ox + int(view_w * x), oy + int(view_h * y))
                            for y in self.GRID for x in self.GRID]
        self._targets_output = [(int(self.screen_w * x), int(self.screen_h * y))
                                for y in self.GRID for x in self.GRID]
        self._target_index = 0
        self._target_started = time.monotonic()
        self._target_samples = []
        self._features = []
        self._target_points = []
        self.calibrating = True
        self.calibration_success = False
        self.calibration_status = "Follow the dot with your eyes; keep your head still"

    def cancel_calibration(self) -> None:
        self.calibrating = False
        self.calibration_success = False
        self._target_samples.clear()
        self.calibration_status = "Calibration cancelled"

    def sample_calibration(self, feature: np.ndarray | None) -> None:
        """Collect stable gaze samples for the current visual target."""
        if not self.calibrating:
            return
        if feature is None:
            self.calibration_status = "Keep your face and both eyes visible"
            return
        if time.monotonic() - self._target_started < self.SETTLE_SECONDS:
            self.calibration_status = f"Look at target {self._target_index + 1}/{len(self._targets_ui)} and hold still"
            return
        self._target_samples.append(np.asarray(feature, dtype=float).copy())
        self.calibration_status = f"Calibrating {self._target_index + 1}/{len(self._targets_ui)} ({len(self._target_samples)}/{self.SAMPLES_PER_TARGET})"
        if len(self._target_samples) < self.SAMPLES_PER_TARGET:
            return
        self._features.append(np.median(np.stack(self._target_samples), axis=0))
        self._target_points.append(np.asarray(self._targets_output[self._target_index], dtype=float))
        self._target_index += 1
        self._target_samples = []
        self._target_started = time.monotonic()
        if self._target_index < len(self._targets_ui):
            return
        design = np.column_stack([np.asarray(self._features), np.ones(len(self._features))])
        targets = np.asarray(self._target_points)
        coefficients, _, _, _ = np.linalg.lstsq(design, targets, rcond=None)
        error = np.linalg.norm(design @ coefficients - targets, axis=1)
        rms = float(np.sqrt(np.mean(error ** 2)))
        self.calibrating = False
        if not np.all(np.isfinite(coefficients)) or rms > max(self.screen_w, self.screen_h) * .18:
            self.calibration_status = f"Calibration too noisy ({rms:.0f}px); improve lighting and repeat"
            self.calibration_success = False
            return
        self.coefficients = coefficients
        self.calibration_success = True
        self.calibration_status = f"Calibration complete (average error {rms:.0f}px)"

    def gaze_to_screen(self, feature: np.ndarray) -> tuple[int, int] | None:
        if self.coefficients is None:
            return None
        vector = np.append(np.asarray(feature, dtype=float), 1.0)
        point = vector @ self.coefficients
        if not np.all(np.isfinite(point)):
            return None
        return (int(np.clip(point[0], 0, self.screen_w - 1)),
                int(np.clip(point[1], 0, self.screen_h - 1)))

    def calibration_data(self) -> list[list[float]] | None:
        return self.coefficients.tolist() if self.coefficients is not None else None

    def close(self) -> None:
        self.mesh.close()
