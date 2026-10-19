"""Main BT CURSOR control panel."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QVBoxLayout, QWidget,
)
from utils.resources import resource_path


class BTMainWindow(QMainWindow):
    """Visible launcher and mode/settings panel for the cursor app."""

    def __init__(self, config, callbacks) -> None:
        super().__init__()
        self.callbacks = callbacks
        self.setWindowTitle("BT CURSOR")
        self.setWindowIcon(QIcon(str(resource_path("assets/bt_cursor.png"))))
        self.setMinimumSize(700, 560)
        self.resize(820, 640)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #091321; color: #eaf2fb; font-family: 'Segoe UI'; }
            QFrame#card { background: #111f33; border: 1px solid #263a55; border-radius: 16px; }
            QLabel#brand { color: #f4f8ff; font-size: 25px; font-weight: 800; }
            QLabel#subtitle { color: #91a5bd; font-size: 12px; }
            QLabel#section { color: #ecf4ff; font-size: 16px; font-weight: 700; }
            QLabel#body { color: #aabbd0; font-size: 13px; }
            QLabel#camera { color: #32d6b1; font-size: 12px; font-weight: 700; }
            QPushButton#mode { background: #172941; color: #deebf9; border: 1px solid #2b415f;
                border-radius: 12px; padding: 16px; text-align: left; font-size: 15px; font-weight: 700; }
            QPushButton#mode:hover { border-color: #35d4b3; }
            QPushButton#mode:checked { background: #123c45; border: 2px solid #35d4b3; color: #f2fffc; }
            QPushButton#primary { background: #2ad2ad; color: #071720; border: 0; border-radius: 10px;
                padding: 11px 18px; font-weight: 800; }
            QPushButton#primary:hover { background: #58e5c2; }
            QPushButton#secondary { background: #1a2b43; color: #e7f0fb; border: 1px solid #314762;
                border-radius: 10px; padding: 10px 16px; font-weight: 600; }
            QPushButton#secondary:hover { border-color: #35d4b3; }
        """)

        root = QWidget(); layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(18)

        header = QHBoxLayout()
        brand_block = QVBoxLayout(); brand_block.setSpacing(2)
        brand = QLabel("BT CURSOR"); brand.setObjectName("brand")
        subtitle = QLabel("Hands-free control for your Windows PC"); subtitle.setObjectName("subtitle")
        brand_block.addWidget(brand); brand_block.addWidget(subtitle)
        header.addLayout(brand_block); header.addStretch(1)
        self.camera_status = QLabel("● Connecting to camera…"); self.camera_status.setObjectName("camera")
        header.addWidget(self.camera_status, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        mode_card = QFrame(); mode_card.setObjectName("card")
        mode_layout = QVBoxLayout(mode_card); mode_layout.setContentsMargins(20, 18, 20, 20); mode_layout.setSpacing(13)
        section = QLabel("Choose how you want to control the cursor"); section.setObjectName("section")
        mode_layout.addWidget(section)
        mode_row = QHBoxLayout(); mode_row.setSpacing(12)
        self.hand_button = QPushButton("HAND GESTURES\nMove, click, drag, scroll and zoom");
        self.head_button = QPushButton("HEAD CURSOR\nMove your head; dwell to click and scroll")
        for button in (self.hand_button, self.head_button):
            button.setObjectName("mode"); button.setCheckable(True); button.setMinimumHeight(92)
            mode_row.addWidget(button, 1)
        self.mode_group = QButtonGroup(self); self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.hand_button); self.mode_group.addButton(self.head_button)
        self.hand_button.clicked.connect(lambda: self.callbacks["set_mode"]("Hand"))
        self.head_button.clicked.connect(lambda: self.callbacks["set_mode"]("Head"))
        mode_layout.addLayout(mode_row)
        layout.addWidget(mode_card)

        details = QFrame(); details.setObjectName("card")
        details_layout = QVBoxLayout(details); details_layout.setContentsMargins(20, 17, 20, 17); details_layout.setSpacing(8)
        detail_title = QLabel("How it works"); detail_title.setObjectName("section")
        self.mode_help = QLabel(""); self.mode_help.setObjectName("body"); self.mode_help.setWordWrap(True)
        details_layout.addWidget(detail_title); details_layout.addWidget(self.mode_help)
        layout.addWidget(details, 1)

        controls = QHBoxLayout(); controls.setSpacing(10)
        self.pause_button = QPushButton("Pause controls"); self.pause_button.setObjectName("secondary")
        self.pause_button.clicked.connect(self.callbacks["toggle"])
        settings_button = QPushButton("Settings"); settings_button.setObjectName("secondary")
        settings_button.clicked.connect(self.callbacks["settings"])
        self.hud_button = QPushButton("Show camera HUD"); self.hud_button.setObjectName("secondary")
        self.hud_button.clicked.connect(self.callbacks["overlay"])
        self.exit_button = QPushButton("Exit"); self.exit_button.setObjectName("secondary")
        self.exit_button.clicked.connect(self.callbacks["exit"])
        controls.addWidget(self.pause_button); controls.addStretch(1)
        controls.addWidget(settings_button); controls.addWidget(self.hud_button); controls.addWidget(self.exit_button)
        layout.addLayout(controls)
        footer = QLabel("Emergency pause: Ctrl + Shift + Esc     •     Head mode uses local face landmarks only")
        footer.setObjectName("subtitle"); footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        self.setCentralWidget(root)
        self.set_mode(config.get("control_mode", "Hand"), config)
        self.set_paused(False)
        self.set_hud(bool(config.get("show_overlay", False)))

    def set_mode(self, mode: str, config=None) -> None:
        head = mode == "Head"
        self.head_button.setChecked(head)
        self.hand_button.setChecked(not head)
        dwell = float((config or {}).get("head_dwell_seconds", 1.0))
        if head:
            self.mode_help.setText(
                f"Move your head to guide the pointer. Hold still for {dwell:g} seconds to perform the selected click. "
                "Hold the pointer near the top or bottom edge to scroll up or down. Move away after a click to re-arm. "
                "Choose left, right, or double-click in Settings."
            )
        else:
            self.mode_help.setText(
                "Use the hand poses shown in Settings to move, click, drag, scroll, and zoom. "
                "Hand controls remain independent from Head Cursor mode."
            )

    def set_camera_status(self, connected: bool, message: str) -> None:
        self.camera_status.setText(("● " if connected else "● ") + message)
        self.camera_status.setStyleSheet("color: #32d6b1;" if connected else "color: #ffbd69;")

    def set_paused(self, paused: bool) -> None:
        self.pause_button.setText("Resume controls" if paused else "Pause controls")

    def set_hud(self, visible: bool) -> None:
        self.hud_button.setText("Hide camera HUD" if visible else "Show camera HUD")
