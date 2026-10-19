"""Resolve MediaPipe's legacy Solutions API across package exports."""
from __future__ import annotations

import importlib
from types import ModuleType


def load_solutions(mediapipe: ModuleType) -> ModuleType:
    """Return MediaPipe Solutions, even when the top-level alias is not exported."""
    solutions = getattr(mediapipe, "solutions", None)
    if solutions is not None:
        return solutions
    try:
        return importlib.import_module("mediapipe.python.solutions")
    except ImportError as exc:
        version = getattr(mediapipe, "__version__", "unknown")
        location = getattr(mediapipe, "__file__", "unknown")
        raise RuntimeError(
            f"MediaPipe {version} at {location} does not provide its legacy Solutions API. "
            "Activate GestureFlow's .venv and run: "
            "python -m pip install --force-reinstall mediapipe==0.10.21"
        ) from exc
