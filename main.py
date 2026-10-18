"""GestureFlow Windows desktop entry point."""
from __future__ import annotations
import sys, logging
import numpy as np
from pynput import keyboard, mouse
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from core.config import ConfigManager
from core.capture import CameraWorker
from core.tracking import HandTracker
from core.gesture_engine import GestureEngine
from core.input_controller import InputController
from gui.overlay import HudOverlay
from gui.settings_dialog import SettingsDialog
from gui.tray import TrayController
from utils.logger import configure_logging


class EmergencySignals(QObject):
    """Marshal pynput callbacks safely onto the Qt main thread."""
    pause_requested = pyqtSignal()


class GestureFlowApp:
    """Owns worker, tracker, gesture engine, overlay and tray lifetimes."""
    def __init__(self, app: QApplication) -> None:
        self.app=app; self.log=configure_logging(); self.manager=ConfigManager(); self.cfg=self.manager.data
        self.tracker=HandTracker(self.cfg); self.controller=InputController(self.cfg.get("fail_safe_corner",True))
        self.engine=GestureEngine(self.cfg,self.tracker,self.controller)
        self.overlay=HudOverlay(self.cfg["overlay_position"],self.cfg["overlay_size"])
        if self.cfg.get("show_overlay",True): self.overlay.show()
        self.camera=None
        self.frame_timer = QTimer()
        self.frame_timer.setInterval(40)  # Process at most 25 frames/s on laptop CPUs.
        self.frame_timer.timeout.connect(self.process_latest_frame)
        self.frame_timer.start()
        self.tray=TrayController({"toggle":self.toggle,"overlay":self.toggle_overlay,"settings":self.settings,"calibrate":self.calibrate,"exit":self.shutdown})
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
        self.tray.showMessage("GestureFlow",message,QSystemTrayIcon.MessageIcon.Information if ok else QSystemTrayIcon.MessageIcon.Warning,3000)

    def on_frame(self, rgb: np.ndarray) -> None:
        landmarks, annotated=self.tracker.process(rgb)
        mode=self.engine.process(landmarks)
        if self.overlay.isVisible(): self.overlay.update_frame(annotated,mode)

    def toggle(self) -> None:
        self.engine.paused=not self.engine.paused
        self.tray.toggle_action.setText("Resume Gesture Control" if self.engine.paused else "Pause Gesture Control")
        if self.engine.paused: self.controller.release_left()
        self.tray.showMessage("GestureFlow", "Tracking paused" if self.engine.paused else "Tracking active")

    def toggle_overlay(self) -> None:
        self.overlay.setVisible(not self.overlay.isVisible())
        self.tray.overlay_action.setText("Hide HUD Overlay" if self.overlay.isVisible() else "Show HUD Overlay")

    def settings(self) -> None:
        dialog=SettingsDialog(self.cfg,self.manager)
        if dialog.exec():
            self.cfg=self.manager.data
            self.tracker.invert_cursor_x = bool(self.cfg.get("invert_cursor_x", True))
            self.tracker.margin = float(self.cfg.get("camera_margin", .20))
            self.engine=GestureEngine(self.cfg,self.tracker,self.controller)
            if self.camera.camera_id != self.cfg["camera_id"] or self.camera.fps != self.cfg["camera_fps"]: self.start_camera()
            self.overlay.setVisible(self.cfg["show_overlay"])

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
        if getattr(self,"tray",None): self.tray.hide()
        if getattr(self,"app",None): self.app.quit()


def main() -> int:
    app=QApplication(sys.argv); app.setApplicationName("GestureFlow"); app.setQuitOnLastWindowClosed(False)
    try: runtime=GestureFlowApp(app)
    except Exception as exc:
        logging.getLogger("gestureflow").exception("Startup failed")
        QMessageBox.critical(None,"GestureFlow startup error",f"Unable to initialize GestureFlow:\n{exc}")
        return 1
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
