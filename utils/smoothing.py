"""Low-latency position filters."""
from __future__ import annotations
import math
from typing import Optional
import numpy as np


class EMAFilter:
    """Exponential moving-average filter for N-dimensional positions."""
    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha = float(np.clip(alpha, 0.01, 1.0))
        self.value: Optional[np.ndarray] = None

    def reset(self) -> None:
        self.value = None

    def filter(self, value: np.ndarray) -> np.ndarray:
        point = np.asarray(value, dtype=float)
        self.value = point.copy() if self.value is None else self.alpha * point + (1 - self.alpha) * self.value
        return self.value.copy()


class OneEuroFilter:
    """Adaptive low-pass filter (Casiez et al.) for arbitrary vector values."""
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, derivative_cutoff: float = 1.0) -> None:
        self.min_cutoff = max(0.001, min_cutoff)
        self.beta = max(0.0, beta)
        self.derivative_cutoff = max(0.001, derivative_cutoff)
        self._last_t: Optional[float] = None
        self._last_x: Optional[np.ndarray] = None
        self._dx = np.zeros(2)

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def reset(self) -> None:
        self._last_t = None
        self._last_x = None
        self._dx = np.zeros(2)

    def filter(self, value: np.ndarray, timestamp: float) -> np.ndarray:
        x = np.asarray(value, dtype=float)
        if self._last_x is None or self._last_t is None:
            self._last_x, self._last_t = x.copy(), timestamp
            self._dx = np.zeros_like(x)
            return x.copy()
        dt = float(np.clip(timestamp - self._last_t, 1e-4, 0.25))
        derivative = (x - self._last_x) / dt
        ad = self._alpha(self.derivative_cutoff, dt)
        self._dx = ad * derivative + (1 - ad) * self._dx
        cutoff = self.min_cutoff + self.beta * np.abs(self._dx)
        filtered = self._alpha(float(np.mean(cutoff)), dt) * x + (1 - self._alpha(float(np.mean(cutoff)), dt)) * self._last_x
        self._last_x, self._last_t = filtered.copy(), timestamp
        return filtered
