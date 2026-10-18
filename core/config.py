"""Validated, atomic JSON configuration persistence."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "camera_id": 0, "camera_fps": 30, "camera_width": 640, "camera_height": 480, "smoothing_factor": 0.35,
    "one_euro_filter_enabled": True, "one_euro_min_cutoff": 0.7, "one_euro_beta": 0.015,
    "cursor_deadband_px": 10.0,
    "click_distance_threshold": 0.045, "click_release_hysteresis": 1.35,
    "left_drag_hold_ms": 450, "double_click_interval_ms": 300,
    "scroll_sensitivity": 120, "scroll_deadzone_y": 0.025, "zoom_threshold_delta": 0.012,
    "active_hand": "Right", "invert_cursor_x": True, "scroll_pair_distance_threshold": 0.10, "show_overlay": True, "overlay_position": [20, 20],
    "overlay_size": [320, 240], "fail_safe_corner": True,
    "min_detection_confidence": 0.75, "min_tracking_confidence": 0.75,
    "camera_margin": 0.20, "motion_diagnostics": True, "enabled": True,
}


class ConfigManager:
    """Loads defaults, tolerates corrupt files, and atomically persists updates."""
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[1] / "config.json"
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    # The previous shipped default (6 px) still allowed visible cursor
                    # tremor on high-DPI laptop screens; migrate only that untouched default.
                    if loaded.get("cursor_deadband_px") == 6.0:
                        loaded["cursor_deadband_px"] = DEFAULTS["cursor_deadband_px"]
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
