"""Compact always-on-top, mouse-transparent camera HUD."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout


class HudOverlay(QWidget):
    """Displays annotated RGB camera frames and current gesture state."""
    def __init__(self, position=(20, 20), size=(320, 240)) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*size); self.move(*position)
        self.image = QLabel(); self.state = QLabel("WAITING")
        self.state.setStyleSheet("color:white;background:rgba(10,18,30,190);padding:5px;font-weight:bold")
        self.image.setStyleSheet("background:rgba(0,0,0,150)")
        layout = QVBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.addWidget(self.state); layout.addWidget(self.image)

    def update_frame(self, rgb, mode: str) -> None:
        h, w, channels = rgb.shape
        image = QImage(rgb.data, w, h, channels*w, QImage.Format.Format_RGB888).copy()
        self.image.setPixmap(QPixmap.fromImage(image).scaled(self.width()-8, self.height()-38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.state.setText(f"MODE: {mode}")
