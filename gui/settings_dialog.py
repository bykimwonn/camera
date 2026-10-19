"""BT CURSOR camera, mode, and gesture preferences."""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QLabel,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)


class SettingsDialog(QDialog):
    """Edit camera, cursor, low-light, and gesture settings."""
    def __init__(self, config, manager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BT CURSOR Settings")
        self.resize(540, 580)
        self.cfg, self.manager = config, manager

        tabs = QTabWidget()
        control = QWidget(); form = QFormLayout(control)
        self.control_mode = QComboBox()
        self.control_mode.addItem("Hand gestures", "Hand")
        self.control_mode.addItem("Head cursor + dwell click/scroll", "Head")
        mode_index = self.control_mode.findData(config.get("control_mode", "Hand"))
        self.control_mode.setCurrentIndex(max(0, mode_index))
        form.addRow("Cursor control mode", self.control_mode)
        self.camera = QSpinBox(); self.camera.setRange(0, 20); self.camera.setValue(config["camera_id"])
        self.fps = QSpinBox(); self.fps.setRange(10, 60); self.fps.setValue(config["camera_fps"])
        self.sensitivity = QSpinBox(); self.sensitivity.setRange(20, 400); self.sensitivity.setValue(config["scroll_sensitivity"])
        self.smoothing = QDoubleSpinBox(); self.smoothing.setRange(.05, 1); self.smoothing.setSingleStep(.05); self.smoothing.setValue(config["smoothing_factor"])
        self.pinch = QDoubleSpinBox(); self.pinch.setRange(.01, .12); self.pinch.setSingleStep(.005); self.pinch.setValue(config["click_distance_threshold"])
        self.one_euro = QCheckBox(); self.one_euro.setChecked(config["one_euro_filter_enabled"])
        self.overlay = QCheckBox(); self.overlay.setChecked(config["show_overlay"])
        self.invert_x = QCheckBox(); self.invert_x.setChecked(config.get("invert_cursor_x", True))
        self.camera_margin = QDoubleSpinBox(); self.camera_margin.setRange(.05, .35); self.camera_margin.setSingleStep(.025); self.camera_margin.setValue(config.get("camera_margin", .20))
        self.jitter = QDoubleSpinBox(); self.jitter.setRange(0, 20); self.jitter.setSingleStep(1); self.jitter.setSuffix(" px"); self.jitter.setValue(config.get("cursor_deadband_px", 10.0))
        self.min_cutoff = QDoubleSpinBox(); self.min_cutoff.setRange(.2, 3.0); self.min_cutoff.setSingleStep(.1); self.min_cutoff.setValue(config.get("one_euro_min_cutoff", .7))
        self.beta = QDoubleSpinBox(); self.beta.setRange(0, .1); self.beta.setSingleStep(.005); self.beta.setValue(config.get("one_euro_beta", .015))
        rows = [("Camera device index (shared by Hand and Head)", self.camera), ("Camera FPS", self.fps), ("Scroll sensitivity", self.sensitivity),
                ("EMA smoothing", self.smoothing), ("Pinch threshold", self.pinch), ("One Euro filter", self.one_euro),
                ("Filter cutoff (lower = steadier/slower)", self.min_cutoff), ("Filter response (higher = less lag)", self.beta),
                ("Show floating HUD", self.overlay), ("Invert horizontal cursor", self.invert_x),
                ("Cursor reach (higher = less head/hand travel)", self.camera_margin), ("Jitter deadband (higher = steadier)", self.jitter)]
        for label, widget in rows: form.addRow(label, widget)
        tabs.addTab(control, "Control")

        tracking = QWidget(); tracking_form = QFormLayout(tracking)
        self.detection_confidence = self._confidence(config.get("min_detection_confidence", .65))
        self.tracking_confidence = self._confidence(config.get("min_tracking_confidence", .65))
        self.low_light = QCheckBox("Enhance dim RGB/IR frames automatically")
        self.low_light.setChecked(config.get("low_light_enhancement", True))
        tracking_form.addRow("Hand detection confidence", self.detection_confidence)
        tracking_form.addRow("Hand tracking confidence", self.tracking_confidence)
        tracking_form.addRow(self.low_light)
        self.head_dwell = QDoubleSpinBox(); self.head_dwell.setRange(.5, 3.0); self.head_dwell.setSingleStep(.25); self.head_dwell.setSuffix(" s")
        self.head_dwell.setValue(config.get("head_dwell_seconds", 1.0))
        tracking_form.addRow("Hold head steady to click", self.head_dwell)
        self.head_click_action = QComboBox()
        self.head_click_action.addItem("Left click", "left")
        self.head_click_action.addItem("Right click", "right")
        self.head_click_action.addItem("Double-click", "double")
        action_index = self.head_click_action.findData(config.get("head_click_action", "left"))
        self.head_click_action.setCurrentIndex(max(0, action_index))
        tracking_form.addRow("Head dwell action", self.head_click_action)
        tracking_note = QLabel("Head mode moves the cursor with your face/head position. Hold still for the dwell time to perform the selected click. Hold near the top or bottom screen edge to scroll; move away after a click to re-arm. The optional HUD outlines the tracked face and shows action status. It uses local face landmarks only and does not identify you. Hand mode remains separate and retains its gesture controls.")
        tracking_note.setWordWrap(True); tracking_form.addRow(tracking_note)
        tabs.addTab(tracking, "Tracking")

        advanced = QWidget(); advanced_form = QFormLayout(advanced)
        self.deadzone = QDoubleSpinBox(); self.deadzone.setRange(.01, .3); self.deadzone.setSingleStep(.01); self.deadzone.setValue(config["scroll_deadzone_y"])
        self.zoom = QDoubleSpinBox(); self.zoom.setRange(.005, .1); self.zoom.setSingleStep(.005); self.zoom.setValue(config["zoom_threshold_delta"])
        self.scroll_pair = QDoubleSpinBox(); self.scroll_pair.setRange(.04, .20); self.scroll_pair.setSingleStep(.01); self.scroll_pair.setValue(config.get("scroll_pair_distance_threshold", .10))
        self.drag_hold = QSpinBox(); self.drag_hold.setRange(200, 1000); self.drag_hold.setSingleStep(50); self.drag_hold.setValue(config.get("left_drag_hold_ms", 450))
        advanced_form.addRow("Scroll deadzone", self.deadzone)
        advanced_form.addRow("Scroll finger spacing", self.scroll_pair)
        advanced_form.addRow("Hold pinch this long to drag (ms)", self.drag_hold)
        advanced_form.addRow("Zoom delta", self.zoom)
        tabs.addTab(advanced, "Gestures")

        self.status = QLabel("Settings are saved locally. Camera and confidence changes restart tracking after saving.")
        self.status.setWordWrap(True)
        save = QPushButton("Save settings"); save.clicked.connect(self.save)
        layout = QVBoxLayout(self); layout.addWidget(tabs); layout.addWidget(self.status); layout.addWidget(save)

    @staticmethod
    def _confidence(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(); spin.setRange(.3, .95); spin.setSingleStep(.05); spin.setDecimals(2); spin.setValue(value)
        return spin

    def save(self) -> None:
        updates = {
            "control_mode": self.control_mode.currentData(),
            "head_dwell_seconds": self.head_dwell.value(),
            "head_click_action": self.head_click_action.currentData(),
            "camera_id": self.camera.value(), "camera_fps": self.fps.value(),
            "scroll_sensitivity": self.sensitivity.value(), "smoothing_factor": self.smoothing.value(),
            "click_distance_threshold": self.pinch.value(), "one_euro_filter_enabled": self.one_euro.isChecked(),
            "one_euro_min_cutoff": self.min_cutoff.value(), "one_euro_beta": self.beta.value(),
            "show_overlay": self.overlay.isChecked(), "invert_cursor_x": self.invert_x.isChecked(),
            "camera_margin": self.camera_margin.value(), "cursor_deadband_px": self.jitter.value(),
            "min_detection_confidence": self.detection_confidence.value(),
            "min_tracking_confidence": self.tracking_confidence.value(),
            "low_light_enhancement": self.low_light.isChecked(),
            "left_drag_hold_ms": self.drag_hold.value(), "scroll_deadzone_y": self.deadzone.value(),
            "scroll_pair_distance_threshold": self.scroll_pair.value(), "zoom_threshold_delta": self.zoom.value(),
        }
        self.manager.save(updates)
        self.accept()
