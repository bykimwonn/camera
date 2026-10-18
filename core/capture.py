"""Asynchronous camera reader. Frames are immutable RGB arrays emitted to Qt."""
from __future__ import annotations
import logging
import time
import cv2
from PyQt6.QtCore import QThread, pyqtSignal


class CameraWorker(QThread):
    """Capture thread with bounded retry/backoff and cooperative shutdown."""
    frame_ready = pyqtSignal(object)
    camera_status = pyqtSignal(bool, str)

    def __init__(self, camera_id: int = 0, fps: int = 30, width: int = 640, height: int = 480) -> None:
        super().__init__()
        self.camera_id, self.fps = camera_id, max(1, fps)
        self.width, self.height = max(320, width), max(240, height)
        self._running = True
        self.logger = logging.getLogger("gestureflow.capture")

    def stop(self) -> None:
        self._running = False
        self.wait(2500)

    def run(self) -> None:
        cap = None
        failures = 0
        while self._running:
            try:
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    # DirectShow avoids slow backend probing and is reliable on Windows.
                    cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY)
                    cap.set(cv2.CAP_PROP_FPS, self.fps)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        failures += 1
                        self.camera_status.emit(False, f"Camera {self.camera_id} unavailable; retry {failures}")
                        self.msleep(min(5000, 500 * failures))
                        cap.release()
                        cap = None
                        continue
                    failures = 0
                    self.camera_status.emit(True, "Camera connected")
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    self.camera_status.emit(False, "Camera frame unavailable")
                    cap.release()
                    cap = None
                    self.msleep(min(3000, 250 * failures))
                    continue
                self.frame_ready.emit(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            except Exception as exc:
                self.logger.exception("Camera capture error: %s", exc)
                self.camera_status.emit(False, str(exc))
                self.msleep(1000)
        if cap is not None:
            cap.release()
