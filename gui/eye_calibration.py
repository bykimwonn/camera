"""Fullscreen gaze calibration overlay."""
from __future__ import annotations
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import QApplication, QDialog


class EyeCalibrationDialog(QDialog):
    """Show nine targets while the camera samples eye direction."""
    def __init__(self, tracker, parent=None) -> None:
        super().__init__(parent)
        self.tracker = tracker
        self.screen = QApplication.primaryScreen().geometry()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setGeometry(self.screen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.tracker.begin_calibration((self.screen.x(), self.screen.y()),
                                       (self.screen.width(), self.screen.height()))
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _poll(self) -> None:
        self.update()
        if not self.tracker.calibrating:
            self.timer.stop()
            self.accept() if self.tracker.calibration_success else self.reject()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 14, 26, 238))
        painter.setPen(QColor("white"))
        font = QFont("Segoe UI", 18); painter.setFont(font)
        painter.drawText(40, 50, "Follow the dot with your eyes. Keep your head still.")
        painter.setPen(QColor("#b8c7d9"))
        painter.drawText(40, 84, self.tracker.calibration_status)
        target = self.tracker.calibration_target
        if target is not None:
            x, y = target[0] - self.screen.x(), target[1] - self.screen.y()
            painter.setPen(QPen(QColor("#0b1220"), 3))
            painter.setBrush(QColor("#38e1b2"))
            painter.drawEllipse(x - 17, y - 17, 34, 34)
            painter.setBrush(QColor("white")); painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x - 5, y - 5, 10, 10)
        painter.setPen(QColor("#b8c7d9")); painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(40, self.height() - 35, "Press Esc to cancel calibration")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.tracker.cancel_calibration()
            self.reject()
        else:
            super().keyPressEvent(event)
