"""Resolve assets in source runs and PyInstaller bundles."""
from __future__ import annotations
import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """Return an absolute resource path for development or frozen execution."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / relative_path
