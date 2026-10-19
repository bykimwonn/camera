"""GestureFlow Windows desktop entry point."""
from __future__ import annotations
import sys, logging, time
import numpy as np
from pynput import keyboard, mouse
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QSystemTrayIcon
from core.config import ConfigManager
from core.capture import CameraWorker
from core.tracking import HandTracker
from core.gesture_engine import GestureEngine
from core.eye_tracking import EyeGazeTracker
from core.input_controller import InputController
from gui.eye_calibration import EyeCalibrationDialog
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
        self.eye_tracker: EyeGazeTracker | None = None
        self.eye_filter: OneEuroFilter | None = None
        self.eye_cursor_position: np.ndarray | None = None
        self.eye_error: str | None = None
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
        if self.cfg.get("control_mode", "Hand") == "Eye" and not self.cfg.get("eye_calibration"):
            QTimer.singleShot(1000, lambda: self.tray.showMessage(
                "GestureFlow", "Eye mode is selected but not calibrated. Open Settings → Tracking.",
                QSystemTrayIcon.MessageIcon.Warning, 5000))

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

    def _ensure_eye_tracker(self) -> bool:
        if self.eye_tracker is not None:
            return True
        if self.eye_error is not None:
            return False
        try:
            self.eye_tracker = EyeGazeTracker(self.cfg)
            self.eye_filter = OneEuroFilter(float(self.cfg.get("one_euro_min_cutoff", .7)),
                                            float(self.cfg.get("one_euro_beta", .015)))
            self.eye_error = None
            return True
        except Exception as exc:
            self.eye_error = str(exc)
            logging.getLogger("gestureflow.eye").exception("Could not initialize eye gaze mode")
            return False

    def _move_eye_cursor(self, point: tuple[int, int]) -> None:
        if self.eye_filter is None:
            return
        filtered = self.eye_filter.filter(np.asarray(point, dtype=float), time.monotonic())
        if not np.all(np.isfinite(filtered)):
            return
        previous = self.eye_cursor_position.copy() if self.eye_cursor_position is not None else None
        delta = float(np.linalg.norm(filtered - previous)) if previous is not None else None
        deadband = float(self.cfg.get("eye_deadband_px", 18.0))
        sent = previous is None or delta >= deadband
        self.engine.motion_diagnostics.record(
            "eye_cursor_sample", mapped_px=list(point),
            filtered_px=[round(float(v), 2) for v in filtered],
            delta_px=round(delta, 2) if delta is not None else None,
            deadband_px=deadband, sent_to_os=sent,
        )
        if sent:
            self.eye_cursor_position = filtered.copy()
            self.controller.move(int(round(filtered[0])), int(round(filtered[1])))

    def on_frame(self, rgb: np.ndarray) -> None:
        started = time.perf_counter()
        hand_detected = False
        eye_detected = False
        annotated = rgb
        if self.eye_tracker is not None and self.eye_tracker.calibrating:
            feature, annotated = self.eye_tracker.process(rgb)
            self.eye_tracker.sample_calibration(feature)
            eye_detected = feature is not None
            self.engine.process(None)
            mode = "EYE CALIBRATING"
        elif self.engine.paused:
            self.engine.process(None)
            mode = "PAUSED"
        elif self.cfg.get("control_mode", "Hand") == "Eye":
            if not self._ensure_eye_tracker():
                self.engine.process(None)
                mode = "EYE MODE ERROR"
            else:
                feature, annotated = self.eye_tracker.process(rgb)
                eye_detected = feature is not None
                if not self.eye_tracker.calibrated:
                    self.engine.process(None)
                    mode = "EYE CALIBRATION REQUIRED"
                elif feature is None:
                    self.engine.process(None)
                    mode = "NO EYES"
                else:
                    point = self.eye_tracker.gaze_to_screen(feature)
                    if point is not None:
                        self._move_eye_cursor(point)
                        mode = "EYE GAZE"
                    else:
                        self.engine.process(None)
                        mode = "NO GAZE"
        else:
            landmarks, annotated = self.tracker.process(rgb)
            hand_detected = landmarks is not None
            mode = self.engine.process(landmarks)
        self.engine.motion_diagnostics.record(
            "frame", mode=mode, control_mode=self.cfg.get("control_mode", "Hand"),
            hand_detected=hand_detected, eye_detected=eye_detected,
            frame_size=[int(rgb.shape[1]), int(rgb.shape[0])],
            processing_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        if self.overlay.isVisible(): self.overlay.update_frame(annotated, mode)

    def set_control_mode(self, mode: str) -> None:
        """Switch exclusively between hand gestures and calibrated eye cursor."""
        if mode not in {"Hand", "Eye"}:
            return
        self.cfg["control_mode"] = mode
        self.manager.save({"control_mode": mode})
        self.controller.release_left()
        self.eye_cursor_position = None
        self.eye_filter = None
        if mode == "Eye":
            self.eye_error = None
            if not self._ensure_eye_tracker():
                self.tray.showMessage("GestureFlow", f"Eye mode unavailable: {self.eye_error}", QSystemTrayIcon.MessageIcon.Warning, 5000)
                self.cfg["control_mode"] = "Hand"
                self.manager.save({"control_mode": "Hand"})
                mode = "Hand"
            elif not self.eye_tracker.calibrated:
                self.tray.showMessage("GestureFlow", "Eye mode selected. Calibrate it in Settings → Tracking.", QSystemTrayIcon.MessageIcon.Warning, 5000)
        elif self.eye_tracker is not None and not self.eye_tracker.calibrating:
            self.eye_tracker.close()
            self.eye_tracker = None
        self.tray.set_control_mode(mode)

    def toggle(self) -> None:
        self.engine.paused=not self.engine.paused
        self.tray.toggle_action.setText("Resume Gesture Control" if self.engine.paused else "Pause Gesture Control")
        if self.engine.paused: self.controller.release_left()
        self.tray.showMessage("GestureFlow", "Tracking paused" if self.engine.paused else "Tracking active")

    def toggle_overlay(self) -> None:
        self.overlay.setVisible(not self.overlay.isVisible())
        self.tray.overlay_action.setText("Hide HUD Overlay" if self.overlay.isVisible() else "Show HUD Overlay")

    def calibrate_eye(self) -> bool:
        self.eye_error = None
        if not self._ensure_eye_tracker():
            QMessageBox.warning(None, "Eye gaze unavailable", self.eye_error or "Unable to start eye tracker")
            return False
        if self.camera is None or not self.camera.isRunning():
            QMessageBox.warning(None, "Camera unavailable", "Connect a camera before eye calibration.")
            return False
        was_paused = self.engine.paused
        self.engine.paused = True
        try:
            dialog = EyeCalibrationDialog(self.eye_tracker)
            if dialog.exec() == QDialog.DialogCode.Accepted and self.eye_tracker.calibration_success:
                self.manager.save({"eye_calibration": self.eye_tracker.calibration_data()})
                self.cfg = self.manager.data
                self.eye_filter = OneEuroFilter(float(self.cfg.get("one_euro_min_cutoff", .7)),
                                                float(self.cfg.get("one_euro_beta", .015)))
                self.eye_cursor_position = None
                self.tray.showMessage("GestureFlow", self.eye_tracker.calibration_status, QSystemTrayIcon.MessageIcon.Information, 4000)
                return True
            self.tray.showMessage("GestureFlow", self.eye_tracker.calibration_status, QSystemTrayIcon.MessageIcon.Warning, 4000)
            return False
        except Exception as exc:
            logging.getLogger("gestureflow.eye").exception("Eye calibration failed")
            QMessageBox.warning(None, "Eye calibration failed", str(exc))
            return False
        finally:
            self.engine.paused = was_paused

    def settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self.manager, on_calibrate_eye=self.calibrate_eye)
        if dialog.exec():
            old_tracker = self.tracker
            try:
                self.cfg = self.manager.data
                self.tracker = HandTracker(self.cfg)
                diagnostics = self.engine.motion_diagnostics
                self.engine = GestureEngine(self.cfg, self.tracker, self.controller)
                self.engine.motion_diagnostics = diagnostics
                old_tracker.close()
                if self.camera.camera_id != self.cfg["camera_id"] or self.camera.fps != self.cfg["camera_fps"]:
                    self.start_camera()
                self.overlay.setVisible(self.cfg["show_overlay"])
                self.tray.set_control_mode(self.cfg.get("control_mode", "Hand"))
                if self.cfg.get("control_mode", "Hand") == "Eye":
                    self.eye_error = None
                    if not self._ensure_eye_tracker():
                        QMessageBox.warning(None, "Eye gaze unavailable", self.eye_error or "Unable to start eye tracker")
                    elif not self.eye_tracker.calibrated:
                        self.tray.showMessage("GestureFlow", "Eye mode needs calibration: Settings → Tracking → Calibrate Eye Gaze", QSystemTrayIcon.MessageIcon.Warning, 5000)
                elif self.eye_tracker is not None and not self.eye_tracker.calibrating:
                    self.eye_tracker.close()
                    self.eye_tracker = None
                    self.eye_filter = None
                    self.eye_cursor_position = None
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
        if getattr(self, "eye_tracker", None): self.eye_tracker.close()
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
