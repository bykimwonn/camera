"""System tray lifecycle and user actions."""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt


class TrayController(QSystemTrayIcon):
    """Tray menu wiring supplied callbacks from the application."""
    def __init__(self, callbacks, parent=None) -> None:
        pix=QPixmap(32,32); pix.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pix); painter.setBrush(QColor("#32c7a5")); painter.setPen(Qt.PenStyle.NoPen); painter.drawEllipse(3,3,26,26); painter.end()
        super().__init__(QIcon(pix), parent); self.setToolTip("GestureFlow")
        menu=QMenu()
        self.toggle_action=menu.addAction("Pause Gesture Control")
        self.toggle_action.triggered.connect(callbacks["toggle"])
        self.overlay_action=menu.addAction("Hide HUD Overlay"); self.overlay_action.triggered.connect(callbacks["overlay"])
        menu.addAction("Open Settings", callbacks["settings"])
        menu.addAction("Calibrate Camera", callbacks["calibrate"])
        menu.addSeparator(); menu.addAction("Exit", callbacks["exit"])
        self.setContextMenu(menu); self.show()
