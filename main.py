"""GestureFlow Windows desktop entry point."""
from __future__ import annotations
import sys, logging, time
from collections import deque
import numpy as np
from pynput import keyboard, mouse
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from core.config import ConfigManager
from core.capture import CameraWorker
from core.tracking import HandTracker
from core.gesture_engine import GestureEngine
from core.head_tracking import HeadPositionTracker
from core.dwell_clicker import DwellClicker
from core.input_controller import InputController
from utils.smoothing import OneEuroFilter
from gui.overlay import HudOverlay
from gui.settings_dialog import SettingsDialog
from gui.tray import TrayController
from utils.logger import configure_logging
from utils.resources import resource_path


class EmergencySignals(QObject):
    """Marshal pynput callbacks safely onto the Qt main thread."""
    pause_requested = pyqtSignal()


class GestureFlowApp:
    """Owns worker, tracker, gesture engine, overlay and tray lifetimes."""
    def __init__(self, app: QApplication) -> None:
        self.app=app; self.log=configure_logging(); self.manager=ConfigManager(); self.cfg=self.manager.data
        self.tracker=HandTracker(self.cfg); self.controller=InputController(self.cfg.get("fail_safe_corner",True))
        self.engine=GestureEngine(self.cfg,self.tracker,self.controller)
        self.head_tracker: HeadPositionTracker | None = None
        self.head_filter: OneEuroFilter | None = None
        self.head_cursor_position: np.ndarray | None = None
        self.head_last_sample_time: float | None = None
        self.head_feature_history: deque[np.ndarray] = deque(maxlen=3)
        self.head_error: str | None = None
        self.dwell_clicker = DwellClicker(float(self.cfg.get("head_dwell_seconds", 1.0)))
        self.overlay=HudOverlay(self.cfg["overlay_position"],self.cfg["overlay_size"])
        if self.cfg.get("show_overlay",True): self.overlay.show()
        self.camera=None
        self.frame_timer = QTimer()
        self.frame_timer.setInterval(50)  # Cap inference to 20 FPS; capture still drops stale frames.
        self.frame_timer.timeout.connect(self.process_latest_frame)
        self.frame_timer.start()
        self.tray=TrayController({"toggle":self.toggle,"set_mode":self.set_control_mode,"overlay":self.toggle_overlay,"settings":self.settings,"calibrate":self.calibrate,"exit":self.shutdown})
        self.tray.set_control_mode(self.cfg.get("control_mode", "Hand"))
        self.tray.overlay_action.setText("Hide HUD Overlay" if self.overlay.isVisible() else "Show HUD Overlay")
        self.emergency=EmergencySignals(); self.emergency.pause_requested.connect(self.toggle)
        self._hotkey=keyboard.GlobalHotKeys({'<ctrl>+<shift>+<esc>': self.emergency.pause_requested.emit})
        self._hotkey.start()
        self._corner_active=False
        self._mouse_listener=mouse.Listener(on_move=self._watch_corner)
        self._mouse_listener.start()
        app.aboutToQuit.connect(self.shutdown); self.start_camera()

    def _watch_corner(self, x: int, y: int) -> None:
        """Emergency pause when the pointer reaches top-left; require leaving to re-arm."""
        if not self.cfg.get("fail_safe_corner", True):
            return
        at_corner = x <= 1 and y <= 1
        if at_corner and not self._corner_active:
            self._corner_active = True
            self.emergency.pause_requested.emit()
        elif not at_corner:
            self._corner_active = False

    def start_camera(self) -> None:
        if self.camera:
            self.camera.stop()
        self.camera=CameraWorker(int(self.cfg["camera_id"]),int(self.cfg["camera_fps"]),int(self.cfg["camera_width"]),int(self.cfg["camera_height"]))
        self.camera.camera_status.connect(self.on_status); self.camera.start()

    def process_latest_frame(self) -> None:
        """Consume only the newest camera frame; never queue an unbounded frame backlog."""
        camera = self.camera
        if camera is None or not camera.isRunning():
            return
        frame = camera.take_latest_frame()
        if frame is not None:
            self.on_frame(frame)

    def on_status(self, ok: bool, message: str) -> None:
        self.engine.motion_diagnostics.record("camera_status", connected=ok, message=message)
        self.tray.showMessage("GestureFlow",message,QSystemTrayIcon.MessageIcon.Information if ok else QSystemTrayIcon.MessageIcon.Warning,3000)

    def _ensure_head_tracker(self) -> bool:
        if self.head_tracker is not None:
            if self.head_filter is None:
                self.head_filter = OneEuroFilter(float(self.cfg.get("one_euro_min_cutoff", .7)),
                                                 float(self.cfg.get("one_euro_beta", .015)))
            return True
        if self.head_error is not None:
            return False
        try:
            self.head_tracker = HeadPositionTracker(self.cfg)
            self.head_filter = OneEuroFilter(float(self.cfg.get("one_euro_min_cutoff", .7)),
                                             float(self.cfg.get("one_euro_beta", .015)))
            self.head_error = None
            return True
        except Exception as exc:
            self.head_error = str(exc)
            logging.getLogger("gestureflow.head").exception("Could not initialize head cursor mode")
            return False

    def _move_head_cursor(self, point: tuple[int, int]) -> str:
        if self.head_filter is None:
            self.dwell_clicker.face_lost()
            return "HEAD FILTER UNAVAILABLE"
        now = time.monotonic()
        filtered = self.head_filter.filter(np.asarray(point, dtype=float), now)
        if not np.all(np.isfinite(filtered)):
            self.dwell_clicker.face_lost()
            return "HEAD POSITION INVALID"
        if self.head_cursor_position is None:
            try:
                self.head_cursor_position = np.asarray(self.controller.mouse.position, dtype=float)
            except Exception:
                self.head_cursor_position = filtered.copy()
        previous = self.head_cursor_position.copy()
        dt = float(np.clip(now - self.head_last_sample_time, 1 / 60, .25)) if self.head_last_sample_time is not None else 1 / 15
        self.head_last_sample_time = now
        movement = filtered - previous
        distance = float(np.linalg.norm(movement))
        max_step = max(1.0, float(self.cfg.get("head_max_speed_px_s", 900.0)) * dt)
        if distance > max_step and distance > 0:
            candidate = previous + movement * (max_step / distance)
        else:
            candidate = filtered
        delta = float(np.linalg.norm(candidate - previous))
        deadband = float(self.cfg.get("head_deadband_px", 8.0))
        if delta >= deadband or (distance > max_step and delta > 1.0):
            self.head_cursor_position = candidate.copy()
            self.controller.move(int(round(candidate[0])), int(round(candidate[1])))
        dwell_seconds = float(np.clip(self.cfg.get("head_dwell_seconds", 1.0), .5, 3.0))
        self.dwell_clicker.dwell_seconds = dwell_seconds
        clicked, progress, dwell_status = self.dwell_clicker.update(
            tuple(map(float, self.head_cursor_position)), now)
        if clicked:
            self.controller.click_left()
            self.tray.showMessage("GestureFlow", "Head dwell: left click", QSystemTrayIcon.MessageIcon.Information, 900)
        self.engine.motion_diagnostics.record(
            "head_cursor_sample", mapped_px=list(point),
            filtered_px=[round(float(v), 2) for v in filtered],
            cursor_px=[round(float(v), 2) for v in self.head_cursor_position],
            delta_px=round(delta, 2), max_step_px=round(max_step, 2),
            dwell_progress=round(progress, 3), clicked=clicked,
        )
        return dwell_status

    def on_frame(self, rgb: np.ndarray) -> None:
        started = time.perf_counter()
        hand_detected = False
        head_detected = False
        annotated = rgb
        if self.engine.paused:
            self.engine.process(None)
            self.dwell_clicker.face_lost()
            mode = "PAUSED"
        elif self.cfg.get("control_mode", "Hand") == "Head":
            if not self._ensure_head_tracker():
                self.engine.process(None)
                mode = "HEAD MODE ERROR"
            else:
                head, annotated = self.head_tracker.process(rgb)
                head_detected = head is not None
                if head is None:
                    self.head_feature_history.clear()
                    self.head_last_sample_time = None
                    if self.head_filter is not None:
                        self.head_filter.reset()
                    self.dwell_clicker.face_lost()
                    self.engine.process(None)
                    mode = "NO HEAD"
                else:
                    self.head_feature_history.append(head)
                    stable_head = np.median(np.stack(self.head_feature_history), axis=0)
                    point = self.head_tracker.map_to_screen(stable_head)
                    self.engine.process(None)
                    mode = self._move_head_cursor(point)
        else:
            landmarks, annotated = self.tracker.process(rgb)
            hand_detected = landmarks is not None
            mode = self.engine.process(landmarks)
        self.engine.motion_diagnostics.record(
            "frame", mode=mode, control_mode=self.cfg.get("control_mode", "Hand"),
            hand_detected=hand_detected, head_detected=head_detected,
            frame_size=[int(rgb.shape[1]), int(rgb.shape[0])],
            processing_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        if self.overlay.isVisible(): self.overlay.update_frame(annotated, mode)

    def set_control_mode(self, mode: str) -> None:
        """Switch exclusively between hand gestures and head-position dwell control."""
        if mode not in {"Hand", "Head"}:
            return
        self.cfg["control_mode"] = mode
        self.manager.save({"control_mode": mode})
        self.controller.release_left()
        self.head_cursor_position = None
        self.head_last_sample_time = None
        self.head_feature_history.clear()
        self.dwell_clicker.face_lost()
        self.head_filter = None
        if mode == "Head":
            self.head_error = None
            if not self._ensure_head_tracker():
                self.tray.showMessage("GestureFlow", f"Head mode unavailable: {self.head_error}", QSystemTrayIcon.MessageIcon.Warning, 5000)
                self.cfg["control_mode"] = "Hand"
                self.manager.save({"control_mode": "Hand"})
                mode = "Hand"
        elif self.head_tracker is not None:
            self.head_tracker.close()
            self.head_tracker = None
        self.tray.set_control_mode(mode)

    def toggle(self) -> None:
        self.engine.paused = not self.engine.paused
        self.tray.toggle_action.setText("Resume Gesture Control" if self.engine.paused else "Pause Gesture Control")
        if self.engine.paused:
            self.controller.release_left()
            self.dwell_clicker.face_lost()
            self.head_feature_history.clear()
            self.head_last_sample_time = None
            if self.head_filter is not None:
                self.head_filter.reset()
        self.tray.showMessage("GestureFlow", "Tracking paused" if self.engine.paused else "Tracking active")

    def toggle_overlay(self) -> None:
        self.overlay.setVisible(not self.overlay.isVisible())
        self.tray.overlay_action.setText("Hide HUD Overlay" if self.overlay.isVisible() else "Show HUD Overlay")

    def settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self.manager)
        if dialog.exec():
            old_tracker = self.tracker
            try:
                self.cfg = self.manager.data
                self.tracker = HandTracker(self.cfg)
                diagnostics = self.engine.motion_diagnostics
                self.engine = GestureEngine(self.cfg, self.tracker, self.controller)
                self.engine.motion_diagnostics = diagnostics
                old_tracker.close()
                if (self.camera.camera_id != self.cfg["camera_id"] or
                        self.camera.fps != self.cfg["camera_fps"]):
                    self.start_camera()
                self.overlay.setVisible(self.cfg["show_overlay"])
                self.tray.set_control_mode(self.cfg.get("control_mode", "Hand"))
                self.dwell_clicker = DwellClicker(float(self.cfg.get("head_dwell_seconds", 1.0)))
                if self.cfg.get("control_mode", "Hand") == "Head":
                    if self.head_tracker is not None:
                        self.head_tracker.close()
                        self.head_tracker = None
                    self.head_filter = None
                    self.head_cursor_position = None
                    self.head_last_sample_time = None
                    self.head_feature_history.clear()
                    self.head_error = None
                    if not self._ensure_head_tracker():
                        QMessageBox.warning(None, "Head cursor unavailable", self.head_error or "Unable to start head tracking")
                elif self.head_tracker is not None:
                    self.head_tracker.close()
                    self.head_tracker = None
                    self.head_filter = None
                    self.head_cursor_position = None
                    self.head_last_sample_time = None
                    self.head_feature_history.clear()
            except Exception as exc:
                logging.getLogger("gestureflow").exception("Settings update failed: %s", exc)
                QMessageBox.warning(None, "Settings update failed", str(exc))

    def calibrate(self) -> None:
        self.tracker.margin=max(.05,min(.3,self.tracker.margin))
        self.tray.showMessage("GestureFlow",f"Calibration ready. Current camera margin: {self.tracker.margin:.0%}")

    def shutdown(self) -> None:
        if getattr(self, "frame_timer", None): self.frame_timer.stop()
        if getattr(self,"camera",None): self.camera.stop(); self.camera=None
        if getattr(self,"_hotkey",None): self._hotkey.stop()
        if getattr(self,"_mouse_listener",None): self._mouse_listener.stop()
        if getattr(self,"controller",None): self.controller.close()
        if getattr(self,"tracker",None): self.tracker.close()
        if getattr(self, "head_tracker", None): self.head_tracker.close()
        if getattr(self,"engine",None): self.engine.motion_diagnostics.close()
        if getattr(self,"tray",None): self.tray.hide()
        if getattr(self,"app",None): self.app.quit()


def main() -> int:
    app=QApplication(sys.argv); app.setApplicationName("GestureFlow"); app.setWindowIcon(QIcon(str(resource_path("assets/gestureflow.png")))); app.setQuitOnLastWindowClosed(False)
    try: runtime=GestureFlowApp(app)
    except Exception as exc:
        logging.getLogger("gestureflow").exception("Startup failed")
        QMessageBox.critical(None,"GestureFlow startup error",f"Unable to initialize GestureFlow:\n{exc}")
        return 1
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
