"""
Drift detection for gap-prediction workloads.

Monitors feature distribution changes over time. If the current
feature distribution diverges from the historical baseline,
triggers a fallback to EWMA-only prediction.

Reference: docs/implementation_plan_v1.md Module 3.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np


class DriftDetector:
    """Rolling-statistics drift detector.

    Maintains a sliding reference window of recent feature vectors.
    Compares current feature means against reference distribution.

    Parameters
    ----------
    window_size : number of recent feature vectors to track
    threshold : drift score above which to trigger fallback
    feature_mask : optional list of feature indices to monitor (None = all)
    """

    def __init__(
        self,
        window_size: int = 200,
        threshold: float = 0.3,
        feature_mask: Optional[List[int]] = None,
    ):
        self.window_size = window_size
        self.threshold = threshold
        self.feature_mask = feature_mask
        self._history: Deque[np.ndarray] = deque(maxlen=window_size)
        self._ref_mean: Optional[np.ndarray] = None
        self._ref_std: Optional[np.ndarray] = None
        self._warmup = max(30, window_size // 4)

    def update(self, features: np.ndarray):
        """Add a new feature vector to the reference window."""
        f = features.copy()
        if self.feature_mask is not None:
            f = f[self.feature_mask]
        self._history.append(f)

        if len(self._history) >= self._warmup:
            arr = np.stack(list(self._history))
            self._ref_mean = np.mean(arr, axis=0)
            self._ref_std = np.std(arr, axis=0)
            self._ref_std = np.where(self._ref_std < 1e-6, 1.0, self._ref_std)

    def score(self, current_features: np.ndarray) -> float:
        """Compute drift score for current feature vector.

        0.0 = no drift, 1.0 = complete divergence.

        Uses normalized Euclidean distance from reference distribution mean.
        """
        if self._ref_mean is None or self._ref_std is None:
            return 0.0

        f = current_features.copy()
        if self.feature_mask is not None:
            f = f[self.feature_mask]

        # Mahalanobis-like distance (per-dimension L1 deviation)
        z_scores = np.abs((f - self._ref_mean) / self._ref_std)
        score = float(np.mean(np.clip(z_scores / 3.0, 0.0, 1.0)))
        return score

    def is_drifted(self, current_features: np.ndarray) -> bool:
        """True if drift score exceeds threshold."""
        return self.score(current_features) > self.threshold

    def n_samples(self) -> int:
        return len(self._history)

    def is_ready(self) -> bool:
        return self.n_samples() >= self._warmup

    def reset(self):
        self._history.clear()
        self._ref_mean = None
        self._ref_std = None


class RollingStats:
    """Simple rolling mean/std tracker for gap/burst statistics.

    Used as feature-level drift detection (not full-distribution).
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._values: Deque[float] = deque(maxlen=window_size)

    def update(self, value: float):
        self._values.append(value)

    def mean(self) -> float:
        if not self._values:
            return 0.0
        return float(np.mean(list(self._values)))

    def std(self) -> float:
        if len(self._values) < 2:
            return 0.0
        return float(np.std(list(self._values), ddof=1))

    def relative_change(self, current: float) -> float:
        """Fractional change from rolling mean."""
        mu = self.mean()
        if mu < 1.0:
            return 0.0
        return abs(current - mu) / mu

    def reset(self):
        self._values.clear()


def detect_phase_shift(
    gap_history: List[float],
    window_size: int = 50,
    threshold: float = 0.3,
) -> bool:
    """Lightweight recent-vs-historical gap comparison.

    True if recent gaps differ significantly from long-term average.
    """
    if len(gap_history) < window_size * 2:
        return False
    long_term = np.mean(gap_history[:-window_size])
    recent = np.mean(gap_history[-window_size:])
    if long_term < 1.0:
        return False
    return abs(recent - long_term) / long_term > threshold
