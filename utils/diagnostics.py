"""Non-blocking rotating JSONL diagnostics for cursor motion and gesture quality."""
from __future__ import annotations
import json
import logging
import queue
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from typing import Any


class DroppingQueueHandler(QueueHandler):
    """Never let diagnostics disk I/O stall the real-time gesture loop."""
    def __init__(self, records: queue.Queue) -> None:
        super().__init__(records)
        self.dropped_records = 0

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.dropped_records += 1


class MotionDiagnostics:
    """Persist motion samples in a background writer; never record camera images."""
    def __init__(self, enabled: bool = True, path: Path | None = None) -> None:
        self.enabled = enabled
        self.path = path or Path.home() / ".gestureflow" / "motion.jsonl"
        self.logger = logging.getLogger("gestureflow.motion")
        self.listener: QueueListener | None = None
        self.queue_handler: DroppingQueueHandler | None = None
        if not enabled or self.logger.handlers:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            records: queue.Queue = queue.Queue(maxsize=4096)
            self.queue_handler = DroppingQueueHandler(records)
            file_handler = RotatingFileHandler(self.path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(self.queue_handler)
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False
            self.listener = QueueListener(records, file_handler, respect_handler_level=True)
            self.listener.start()
        except OSError:
            self.enabled = False
            logging.getLogger("gestureflow").exception("Could not initialize motion diagnostics")

    def record(self, event: str, **fields: Any) -> None:
        """Queue one timestamped JSON event; diagnostics never block cursor input."""
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
            logging.getLogger("gestureflow").exception("Failed queuing a motion diagnostic sample")

    def close(self) -> None:
        """Flush queued diagnostic samples and close the background writer."""
        if self.listener is not None:
            handlers = self.listener.handlers
            self.listener.stop()
            for handler in handlers:
                handler.flush()
                handler.close()
            self.listener = None
        if self.queue_handler is not None:
            self.logger.removeHandler(self.queue_handler)
            self.queue_handler.close()
            self.queue_handler = None
