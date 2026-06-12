"""
Gap lower-bound estimation via quantile regression.

Provides a conservative estimate of the minimum expected gap duration
for a given path. Used by the predictor to set g_lower_bound in SafeWindow.

Reference: docs/implementation_plan_v1.md Module 3.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional, Tuple

import numpy as np

from gap_predictor.schema import HORIZONS_NS


class LowerBoundEstimator:
    """Estimate lower bound of gap duration.

    Methods:
      - quantile: p5 / p10 of recent gap history
      - conformal: (basic conformal prediction — placeholder)

    Parameters
    ----------
    quantile : quantile for lower bound (0.01–0.25 typical)
    window_size : number of recent gaps to track
    min_samples : minimum gaps before returning estimate
    """

    def __init__(
        self,
        quantile: float = 0.05,
        window_size: int = 100,
        min_samples: int = 20,
    ):
        if not 0 < quantile < 1:
            raise ValueError("quantile must be in (0, 1)")
        self.quantile = quantile
        self.window_size = window_size
        self.min_samples = min_samples
        self._histories: Dict[int, Deque[float]] = {}

    def update(self, path_id: int, gap_duration_ns: float):
        if path_id not in self._histories:
            self._histories[path_id] = deque(maxlen=self.window_size)
        self._histories[path_id].append(gap_duration_ns)

    def estimate(self, path_id: int) -> float:
        """Return lower bound gap estimate (ns).

        Returns 0 if insufficient data.
        """
        if path_id not in self._histories:
            return 0.0
        gaps = list(self._histories[path_id])
        if len(gaps) < self.min_samples:
            return 0.0
        return float(np.percentile(gaps, self.quantile * 100))

    def estimate_all(self, path_ids: list) -> Dict[int, float]:
        return {pid: self.estimate(pid) for pid in path_ids}

    def n_samples(self, path_id: int) -> int:
        return len(self._histories.get(path_id, []))

    def reset(self):
        self._histories.clear()


def estimate_lower_bound_simple(gaps: list, quantile: float = 0.05) -> float:
    """Stateless helper: lower bound from a flat list of gap durations."""
    if len(gaps) < 10:
        return 0.0
    return float(np.percentile(gaps, quantile * 100))
