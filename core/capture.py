"""Asynchronous camera reader. Frames are immutable RGB arrays emitted to Qt."""
from __future__ import annotations
import logging
import threading
import cv2
from PyQt6.QtCore import QThread, pyqtSignal


class CameraWorker(QThread):
    """Capture thread with bounded retry/backoff and cooperative shutdown."""
    camera_status = pyqtSignal(bool, str)

    def __init__(self, camera_id: int = 0, fps: int = 30, width: int = 640, height: int = 480) -> None:
        super().__init__()
        self.camera_id, self.fps = camera_id, max(1, fps)
        self.width, self.height = max(320, width), max(240, height)
        self._running = True
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self.logger = logging.getLogger("gestureflow.capture")

    def take_latest_frame(self):
        """Return and clear the newest frame; stale frames are intentionally dropped."""
        with self._frame_lock:
            frame = self._latest_frame
            self._latest_frame = None
            return frame

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
                    source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self.camera_status.emit(True, f"Camera connected ({source_w}x{source_h})")
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    self.camera_status.emit(False, "Camera frame unavailable")
                    cap.release()
                    cap = None
                    self.msleep(min(3000, 250 * failures))
                    continue
                # Some Windows camera drivers ignore requested dimensions. Cap pixels here
                # anyway so inference load remains predictable on laptop CPUs.
                source_h, source_w = frame.shape[:2]
                scale = min(1.0, self.width / source_w, self.height / source_h)
                if scale < 1.0:
                    target = (max(1, int(source_w * scale)), max(1, int(source_h * scale)))
                    frame = cv2.resize(frame, target, interpolation=cv2.INTER_AREA)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self._frame_lock:
                    # A one-frame mailbox prevents queued Qt signals from growing without bound.
                    self._latest_frame = rgb
            except Exception as exc:
                self.logger.exception("Camera capture error: %s", exc)
                self.camera_status.emit(False, str(exc))
                self.msleep(1000)
        if cap is not None:
            cap.release()
