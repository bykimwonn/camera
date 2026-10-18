"""Tabbed GestureFlow preferences dialog."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, QSlider,
    QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton, QComboBox, QHBoxLayout, QLabel)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """Edit validated runtime preferences; persist on Save."""
    def __init__(self, config, manager, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("GestureFlow Settings"); self.resize(430, 360)
        self.cfg, self.manager = config, manager
        tabs = QTabWidget(); general = QWidget(); form = QFormLayout(general)
        self.camera = QSpinBox(); self.camera.setRange(0, 20); self.camera.setValue(config["camera_id"])
        self.fps = QSpinBox(); self.fps.setRange(10, 60); self.fps.setValue(config["camera_fps"])
        self.sensitivity = QSpinBox(); self.sensitivity.setRange(20, 400); self.sensitivity.setValue(config["scroll_sensitivity"])
        self.smoothing = QDoubleSpinBox(); self.smoothing.setRange(.05, 1); self.smoothing.setSingleStep(.05); self.smoothing.setValue(config["smoothing_factor"])
        self.pinch = QDoubleSpinBox(); self.pinch.setRange(.01, .12); self.pinch.setSingleStep(.005); self.pinch.setValue(config["click_distance_threshold"])
        self.one_euro = QCheckBox(); self.one_euro.setChecked(config["one_euro_filter_enabled"])
        self.overlay = QCheckBox(); self.overlay.setChecked(config["show_overlay"])
        self.invert_x = QCheckBox(); self.invert_x.setChecked(config.get("invert_cursor_x", True))
        for label, widget in [("Camera device", self.camera),("Camera FPS",self.fps),("Scroll sensitivity",self.sensitivity),("EMA smoothing",self.smoothing),("Pinch threshold",self.pinch),("Use One Euro filter",self.one_euro),("Show HUD",self.overlay),("Invert horizontal cursor",self.invert_x)]: form.addRow(label,widget)
        tabs.addTab(general,"Control")
        advanced = QWidget(); af = QFormLayout(advanced)
        self.deadzone = QDoubleSpinBox(); self.deadzone.setRange(.01,.3); self.deadzone.setSingleStep(.01); self.deadzone.setValue(config["scroll_deadzone_y"])
        self.zoom = QDoubleSpinBox(); self.zoom.setRange(.005,.1); self.zoom.setSingleStep(.005); self.zoom.setValue(config["zoom_threshold_delta"])
        self.scroll_pair = QDoubleSpinBox(); self.scroll_pair.setRange(.04,.20); self.scroll_pair.setSingleStep(.01); self.scroll_pair.setValue(config.get("scroll_pair_distance_threshold", .10))
        af.addRow("Scroll deadzone",self.deadzone); af.addRow("Scroll finger spacing",self.scroll_pair); af.addRow("Zoom delta",self.zoom); tabs.addTab(advanced,"Gestures")
        self.status = QLabel("Changes apply when saved; camera changes restart capture.")
        save = QPushButton("Save settings"); save.clicked.connect(self.save)
        layout=QVBoxLayout(self); layout.addWidget(tabs); layout.addWidget(self.status); layout.addWidget(save)

    def save(self) -> None:
        self.manager.save({"camera_id":self.camera.value(),"camera_fps":self.fps.value(),"scroll_sensitivity":self.sensitivity.value(),"smoothing_factor":self.smoothing.value(),"click_distance_threshold":self.pinch.value(),"one_euro_filter_enabled":self.one_euro.isChecked(),"show_overlay":self.overlay.isChecked(),"invert_cursor_x":self.invert_x.isChecked(),"scroll_deadzone_y":self.deadzone.value(),"scroll_pair_distance_threshold":self.scroll_pair.value(),"zoom_threshold_delta":self.zoom.value()})
        self.accept()
