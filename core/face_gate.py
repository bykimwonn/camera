"""On-device face enrollment and matching gate for gesture input."""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path
from typing import Any
import cv2
import numpy as np


class FaceGate:
    """Require the locally enrolled face and exactly one visible face in frame.

    Source frames and enrollment crops remain in memory. Only an OpenCV LBPH model
    is saved under the user's .gestureflow directory. This is a convenience gate,
    not a replacement for Windows sign-in or high-assurance authentication.
    """
    SAMPLE_COUNT = 24
    SAMPLE_INTERVAL = 0.18
    REQUIRED_MATCHES = 3

    def __init__(self, threshold: float = 75.0, profile_path: Path | None = None) -> None:
        self.path = profile_path or Path.home() / ".gestureflow" / "face_profile.yml"
        self.threshold = float(np.clip(threshold, 35.0, 120.0))
        self.logger = logging.getLogger("gestureflow.face")
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(str(cascade_path))
        self.available = (not self.detector.empty() and hasattr(cv2, "face")
                          and hasattr(cv2.face, "LBPHFaceRecognizer_create"))
        self.recognizer: Any | None = None
        self.enrolling = False
        self.samples: list[np.ndarray] = []
        self.last_sample_at = 0.0
        self.authorized = False
        self.match_streak = 0
        self.miss_streak = 0
        self.status = "No face profile; enroll in Settings"
        if not self.available:
            self.status = "Face module unavailable; install opencv-contrib-python"
            self.logger.error(self.status)
        else:
            self._load()

    def _create_recognizer(self):
        return cv2.face.LBPHFaceRecognizer_create(1, 8, 8, 8, self.threshold)

    @property
    def has_profile(self) -> bool:
        return self.recognizer is not None

    def _gray(self, rgb: np.ndarray) -> np.ndarray:
        gray = rgb if rgb.ndim == 2 else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        # Helps dim/uneven lighting and IR grayscale, but cannot invent light in a dark room.
        return self.clahe.apply(gray)

    def _detect(self, rgb: np.ndarray) -> tuple[np.ndarray | None, list[tuple[int, int, int, int]]]:
        gray = self._gray(rgb)
        h, w = gray.shape[:2]
        min_face = max(64, min(w, h) // 7)
        found = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                               flags=cv2.CASCADE_SCALE_IMAGE,
                                               minSize=(min_face, min_face))
        boxes = [(int(x), int(y), int(x + fw), int(y + fh)) for x, y, fw, fh in found]
        if len(boxes) != 1:
            return None, boxes
        x0, y0, x1, y1 = boxes[0]
        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            return None, boxes
        return cv2.resize(crop, (160, 160), interpolation=cv2.INTER_AREA), boxes

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            recognizer = self._create_recognizer()
            recognizer.read(str(self.path))
            self.recognizer = recognizer
            self.status = "Face profile loaded"
        except Exception:
            self.logger.exception("Could not read local face profile")
            self.status = "Face profile invalid; enroll again in Settings"

    def set_threshold(self, value: float) -> None:
        self.threshold = float(np.clip(value, 35.0, 120.0))
        if self.recognizer is not None:
            self.recognizer.setThreshold(self.threshold)

    def begin_enrollment(self) -> bool:
        if not self.available:
            self.status = "Face enrollment unavailable; check OpenCV installation"
            return False
        self.samples.clear()
        self.last_sample_at = 0.0
        self.authorized = False
        self.match_streak = self.miss_streak = 0
        self.enrolling = True
        self.status = f"Enrollment: 0/{self.SAMPLE_COUNT}; face the camera"
        return True

    def cancel_enrollment(self) -> None:
        self.enrolling = False
        self.samples.clear()
        self.status = "Enrollment cancelled"

    def _finish_enrollment(self) -> None:
        try:
            model = self._create_recognizer()
            model.train(self.samples, np.ones(len(self.samples), dtype=np.int32))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_name("face_profile.tmp.yml")
            model.write(str(temp_path))
            os.replace(temp_path, self.path)
            self.recognizer = model
            self.samples.clear()
            self.enrolling = False
            self.authorized = False
            self.match_streak = self.miss_streak = 0
            self.status = "Enrollment saved locally; verifying"
            self.logger.info("Saved local face model; source samples discarded")
        except Exception as exc:
            self.logger.exception("Face enrollment failed: %s", exc)
            self.samples.clear()
            self.enrolling = False
            self.status = "Enrollment failed; see application log"

    def update(self, rgb: np.ndarray, required: bool = True) -> tuple[bool, str, list[tuple[int, int, int, int]]]:
        """Inspect one frame and return (authorized, status, face boxes)."""
        if not self.available:
            return not required, self.status, []
        if not required and not self.enrolling:
            return True, "Face gate disabled", []
        try:
            crop, boxes = self._detect(rgb)
        except Exception:
            self.logger.exception("Face detection failed")
            self.authorized = False
            return not required, "Face detection error", []

        if self.enrolling:
            if len(boxes) > 1:
                self.status = "Enrollment: only one person in view"
            elif crop is None:
                self.status = f"Enrollment: {len(self.samples)}/{self.SAMPLE_COUNT}; face not found"
            elif time.monotonic() - self.last_sample_at >= self.SAMPLE_INTERVAL:
                self.samples.append(crop.copy())
                self.last_sample_at = time.monotonic()
                self.status = (f"Enrollment: {len(self.samples)}/{self.SAMPLE_COUNT}; look forward, "
                               "then turn slightly left/right")
                if len(self.samples) >= self.SAMPLE_COUNT:
                    self._finish_enrollment()
            return False, self.status, boxes

        if not required:
            return True, "Face gate disabled", boxes
        if self.recognizer is None:
            return False, "Locked: enroll your face in Settings", boxes
        if len(boxes) > 1:
            self.authorized = False
            self.match_streak = self.miss_streak = 0
            return False, "Locked: multiple faces", boxes
        if crop is None:
            self.miss_streak += 1
            self.match_streak = 0
            if self.miss_streak >= 3:
                self.authorized = False
            self.status = "Face temporarily lost" if self.authorized else "Locked: face not detected"
            return self.authorized, self.status, boxes

        try:
            label, distance = self.recognizer.predict(crop)
            matched = label == 1 and float(distance) <= self.threshold
        except Exception:
            self.logger.exception("Face matching failed")
            self.authorized = False
            return False, "Locked: face match error", boxes
        if matched:
            self.miss_streak = 0
            self.match_streak += 1
            self.authorized = self.match_streak >= self.REQUIRED_MATCHES
            self.status = "Face verified" if self.authorized else "Verifying face..."
        else:
            self.authorized = False
            self.match_streak = 0
            self.miss_streak += 1
            self.status = "Locked: face mismatch"
        return self.authorized, self.status, boxes
