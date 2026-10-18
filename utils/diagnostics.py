"""Compact rotating JSONL diagnostics for cursor motion and gesture quality."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class MotionDiagnostics:
    """Persist motion samples locally without recording camera images or hand data."""
    def __init__(self, enabled: bool = True, path: Path | None = None) -> None:
        self.enabled = enabled
        self.path = path or Path.home() / ".gestureflow" / "motion.jsonl"
        self.logger = logging.getLogger("gestureflow.motion")
        if not enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.logger.handlers:
                handler = RotatingFileHandler(self.path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(message)s"))
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
                self.logger.propagate = False
        except OSError:
            self.enabled = False
            logging.getLogger("gestureflow").exception("Could not initialize motion diagnostics")

    def record(self, event: str, **fields: Any) -> None:
        """Write one timestamped JSON event; diagnostics failures never affect control."""
        if not self.enabled:
            return
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            **fields,
        }
        try:
            self.logger.info(json.dumps(record, separators=(",", ":"), default=str))
        except Exception:
            logging.getLogger("gestureflow").exception("Failed writing a motion diagnostic sample")
