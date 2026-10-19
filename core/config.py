"""Validated, atomic JSON configuration persistence."""
from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    # On the reported PC, device 0 resolves to the phone camera; prefer laptop webcam index 1.
    "camera_id": 1, "camera_fps": 15, "camera_width": 320, "camera_height": 240, "smoothing_factor": 0.35,
    "one_euro_filter_enabled": True, "one_euro_min_cutoff": 0.7, "one_euro_beta": 0.015,
    "cursor_deadband_px": 10.0,
    "click_distance_threshold": 0.045, "click_release_hysteresis": 1.35,
    "left_drag_hold_ms": 450, "double_click_interval_ms": 300,
    "scroll_sensitivity": 120, "scroll_deadzone_y": 0.025, "zoom_threshold_delta": 0.012,
    "active_hand": "Right", "invert_cursor_x": True, "scroll_pair_distance_threshold": 0.10, "show_overlay": False,
    "overlay_position": [20, 20], "overlay_size": [320, 240], "fail_safe_corner": True,
    "min_detection_confidence": 0.65, "min_tracking_confidence": 0.65, "low_light_enhancement": True,
    "camera_margin": 0.20, "motion_diagnostics": True,
    "control_mode": "Hand", "eye_calibration": None, "eye_deadband_px": 18.0,
    "config_version": 2, "enabled": True,
}


class ConfigManager:
    """Loads defaults, tolerates corrupt files, and atomically persists updates."""
    def __init__(self, path: Path | None = None) -> None:
        default_path = (Path.home() / ".gestureflow" / "config.json" if getattr(sys, "frozen", False)
                        else Path(__file__).resolve().parents[1] / "config.json")
        self.path = path or default_path
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    # Apply one-time defaults migration without overriding later user choices.
                    try:
                        old_version = int(loaded.get("config_version", 0))
                    except (TypeError, ValueError):
                        old_version = 0
                    if old_version < 2:
                        if loaded.get("cursor_deadband_px") == 6.0:
                            loaded["cursor_deadband_px"] = DEFAULTS["cursor_deadband_px"]
                        if loaded.get("show_overlay") is True:
                            loaded["show_overlay"] = False
                        loaded["config_version"] = 2
                    if old_version < 3:
                        # Move off device 0 (reported as the phone camera) and lower CPU load.
                        if loaded.get("camera_id", 0) == 0:
                            loaded["camera_id"] = DEFAULTS["camera_id"]
                        if loaded.get("camera_fps", 30) == 30:
                            loaded["camera_fps"] = DEFAULTS["camera_fps"]
                        if loaded.get("camera_width", 640) == 640:
                            loaded["camera_width"] = DEFAULTS["camera_width"]
                        if loaded.get("camera_height", 480) == 480:
                            loaded["camera_height"] = DEFAULTS["camera_height"]
                        loaded["config_version"] = 3
                    self.data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, json.JSONDecodeError) as exc:
            logging.getLogger("gestureflow").exception("Config read failed; defaults used: %s", exc)
        return self.data

    def save(self, updates: dict[str, Any] | None = None) -> None:
        if updates:
            self.data.update({k: v for k, v in updates.items() if k in DEFAULTS})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            logging.getLogger("gestureflow").exception("Could not save configuration")
            raise
