"""System tray lifecycle and user actions."""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt
from utils.resources import resource_path


class TrayController(QSystemTrayIcon):
    """Tray menu wiring supplied callbacks from the application."""
    def __init__(self, callbacks, parent=None) -> None:
        icon = QIcon(str(resource_path("assets/bt_cursor.png")))
        if icon.isNull():
            pix = QPixmap(32, 32); pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix); painter.setBrush(QColor("#32c7a5")); painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(3, 3, 26, 26); painter.end()
            icon = QIcon(pix)
        super().__init__(icon, parent); self.setToolTip("BT CURSOR")
        menu=QMenu()
        menu.addAction("Open BT CURSOR", callbacks["show_window"])
        self.toggle_action=menu.addAction("Pause Cursor Control")
        self.toggle_action.triggered.connect(callbacks["toggle"])
        mode_menu = menu.addMenu("Cursor Control Mode")
        self.hand_mode_action = mode_menu.addAction("Hand gestures")
        self.hand_mode_action.setCheckable(True)
        self.head_mode_action = mode_menu.addAction("Head cursor + dwell click/scroll")
        self.head_mode_action.setCheckable(True)
        self.hand_mode_action.triggered.connect(lambda checked=False: callbacks["set_mode"]("Hand"))
        self.head_mode_action.triggered.connect(lambda checked=False: callbacks["set_mode"]("Head"))
        self.overlay_action=menu.addAction("Show Camera HUD"); self.overlay_action.triggered.connect(callbacks["overlay"])
        menu.addAction("Settings", callbacks["settings"])
        menu.addAction("Calibrate Camera", callbacks["calibrate"])
        menu.addSeparator(); menu.addAction("Exit", callbacks["exit"])
        self.setContextMenu(menu); self.show()

    def set_control_mode(self, mode: str) -> None:
        """Reflect the active mutually exclusive hand/head mode in the tray menu."""
        self.hand_mode_action.setChecked(mode != "Head")
        self.head_mode_action.setChecked(mode == "Head")
