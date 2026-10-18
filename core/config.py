"""Validated, atomic JSON configuration persistence."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "camera_id": 0, "camera_fps": 30, "camera_width": 640, "camera_height": 480, "smoothing_factor": 0.35,
    "one_euro_filter_enabled": True, "one_euro_min_cutoff": 1.0, "one_euro_beta": 0.007,
    "click_distance_threshold": 0.035, "double_click_interval_ms": 300,
    "scroll_sensitivity": 120, "scroll_deadzone_y": 0.08, "zoom_threshold_delta": 0.02,
    "active_hand": "Right", "show_overlay": True, "overlay_position": [20, 20],
    "overlay_size": [320, 240], "fail_safe_corner": True,
    "min_detection_confidence": 0.75, "min_tracking_confidence": 0.75,
    "camera_margin": 0.15, "enabled": True,
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
