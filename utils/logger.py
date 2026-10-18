"""Application logging configuration."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> logging.Logger:
    """Set up console and rotating user-local file logging."""
    log_dir = Path.home() / ".gestureflow"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("gestureflow")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        file_handler = RotatingFileHandler(log_dir / "gestureflow.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8")
        file_handler.setFormatter(formatter)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console)
    return logger
