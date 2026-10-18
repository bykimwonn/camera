"""GestureFlow control, tracking, and local face-security settings."""
from __future__ import annotations
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)


class SettingsDialog(QDialog):
    """Edit settings, tune detection, and enroll a local face profile."""
    def __init__(self, config, manager, face_gate=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GestureFlow Settings")
        self.resize(540, 610)
        self.cfg, self.manager, self.face_gate = config, manager, face_gate

        tabs = QTabWidget()
        control = QWidget(); form = QFormLayout(control)
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
        rows = [("Camera device", self.camera), ("Camera FPS", self.fps), ("Scroll sensitivity", self.sensitivity),
                ("EMA smoothing", self.smoothing), ("Pinch threshold", self.pinch), ("One Euro filter", self.one_euro),
                ("Filter cutoff (lower = steadier/slower)", self.min_cutoff), ("Filter response (higher = less lag)", self.beta),
                ("Show floating HUD", self.overlay), ("Invert horizontal cursor", self.invert_x),
                ("Cursor reach (higher = less hand travel)", self.camera_margin), ("Jitter deadband (higher = steadier)", self.jitter)]
        for label, widget in rows: form.addRow(label, widget)
        tabs.addTab(control, "Control")

        tracking = QWidget(); tracking_form = QFormLayout(tracking)
        self.detection_confidence = self._confidence(config.get("min_detection_confidence", .75))
        self.tracking_confidence = self._confidence(config.get("min_tracking_confidence", .65))
        self.detection_confidence.setValue(config.get("min_detection_confidence", .65))
        self.low_light = QCheckBox("Enhance dim RGB/IR frames automatically")
        self.low_light.setChecked(config.get("low_light_enhancement", True))
        tracking_form.addRow("Hand detection confidence", self.detection_confidence)
        tracking_form.addRow("Hand tracking confidence", self.tracking_confidence)
        tracking_form.addRow(self.low_light)
        tracking_note = QLabel("If tracking drops in dim light, improve visible lighting or select an IR camera exposed to OpenCV. Low-light enhancement helps, but cannot recover detail in complete darkness.")
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

        access = QWidget(); access_form = QFormLayout(access)
        self.face_required = QCheckBox("Require my enrolled face before gesture input")
        self.face_required.setChecked(bool(config.get("face_verification_enabled", True)))
        self.face_threshold = QDoubleSpinBox(); self.face_threshold.setRange(35, 120); self.face_threshold.setSingleStep(5)
        self.face_threshold.setValue(config.get("face_match_threshold", 75.0))
        self.enroll_button = QPushButton("Enroll / replace face profile")
        self.face_status = QLabel(self.face_gate.status if self.face_gate else "Face verification unavailable")
        self.face_status.setWordWrap(True)
        privacy = QLabel("Face matching runs locally. Only an OpenCV face model is saved in your user profile; camera frames and enrollment samples are not uploaded. This is a convenience gate, not a replacement for Windows sign-in.")
        privacy.setWordWrap(True)
        access_form.addRow(self.face_required)
        access_form.addRow("Match threshold (higher is more tolerant)", self.face_threshold)
        access_form.addRow(self.enroll_button)
        access_form.addRow("Enrollment status", self.face_status)
        access_form.addRow(privacy)
        tabs.addTab(access, "Face access")
        self.enroll_button.setEnabled(bool(self.face_gate and self.face_gate.available))
        self.enroll_button.clicked.connect(self._toggle_enrollment)
        self.face_timer = QTimer(self); self.face_timer.setInterval(250); self.face_timer.timeout.connect(self._refresh_face_status)
        self.face_timer.start()

        self.status = QLabel("Camera and confidence changes restart tracking after saving.")
        self.status.setWordWrap(True)
        save = QPushButton("Save settings"); save.clicked.connect(self.save)
        layout = QVBoxLayout(self); layout.addWidget(tabs); layout.addWidget(self.status); layout.addWidget(save)

    @staticmethod
    def _confidence(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(); spin.setRange(.3, .95); spin.setSingleStep(.05); spin.setDecimals(2); spin.setValue(value)
        return spin

    def _toggle_enrollment(self) -> None:
        if not self.face_gate:
            return
        if self.face_gate.enrolling:
            self.face_gate.cancel_enrollment()
            self.enroll_button.setText("Enroll / replace face profile")
        elif self.face_gate.begin_enrollment():
            self.enroll_button.setText("Cancel enrollment")
        self._refresh_face_status()

    def _refresh_face_status(self) -> None:
        if self.face_gate:
            self.face_status.setText(self.face_gate.status)
            if self.face_gate.has_profile and not self.face_gate.enrolling:
                self.enroll_button.setText("Enroll / replace face profile")

    def save(self) -> None:
        updates = {
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
            "face_verification_enabled": self.face_required.isChecked(),
            "face_match_threshold": self.face_threshold.value(),
        }
        self.manager.save(updates)
        if self.face_gate:
            self.face_gate.set_threshold(self.face_threshold.value())
        self.accept()

    def closeEvent(self, event) -> None:
        if self.face_gate and self.face_gate.enrolling:
            self.face_gate.cancel_enrollment()
        self.face_timer.stop()
        super().closeEvent(event)
