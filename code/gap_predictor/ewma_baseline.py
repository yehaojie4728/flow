"""
Phase-aware EWMA / quantile baseline predictor.

Tier 0 model. Used for:
  - Cold start (insufficient training samples)
  - Fallback (drift detected)
  - Baseline comparison in RQ2 experiments

Reference: docs/implementation_plan_v1.md Module 3 — Tier 0.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from gap_predictor.schema import HORIZONS_NS


class EWMABaseline:
    """Exponentially-weighted moving average of recent gap durations.

    Predicts S(h) = fraction of recent gaps >= h.

    Parameters
    ----------
    window_size : number of recent gaps to retain per path
    alpha : EWMA smoothing factor (0 < alpha <= 1). Larger = more weight on recent.
    min_samples : minimum gaps required before predicting (else return 0.0)
    """

    def __init__(
        self,
        window_size: int = 100,
        alpha: float = 0.1,
        min_samples: int = 10,
    ):
        self.window_size = window_size
        self.alpha = alpha
        self.min_samples = min_samples
        self._gap_histories: Dict[int, Deque[float]] = {}  # path_id → deque of gap durations (ns)
        self._ewma_values: Dict[int, float] = {}

    def update(self, path_id: int, gap_duration_ns: float):
        """Add a new observed gap duration."""
        if path_id not in self._gap_histories:
            self._gap_histories[path_id] = deque(maxlen=self.window_size)
            self._ewma_values[path_id] = gap_duration_ns
        else:
            self._ewma_values[path_id] = (
                self.alpha * gap_duration_ns
                + (1 - self.alpha) * self._ewma_values[path_id]
            )
        self._gap_histories[path_id].append(gap_duration_ns)

    def predict(self, path_id: int, horizons: Tuple[int, ...] = HORIZONS_NS) -> Dict[int, float]:
        """Predict S(h) for each horizon using recent gap distribution.

        S(h) = fraction of gaps in window that are >= h.
        """
        if path_id not in self._gap_histories:
            return {h: 0.0 for h in horizons}

        gaps = list(self._gap_histories[path_id])
        if len(gaps) < self.min_samples:
            return {h: 0.0 for h in horizons}

        gaps_arr = np.array(gaps)
        return {
            h: float(np.mean(gaps_arr >= h))
            for h in horizons
        }

    def predict_quantile(self, path_id: int, quantile: float = 0.1) -> float:
        """Return the quantile of recent gap durations (lower bound estimate)."""
        if path_id not in self._gap_histories:
            return 0.0
        gaps = list(self._gap_histories[path_id])
        if len(gaps) < max(self.min_samples, 1):
            return 0.0
        return float(np.percentile(gaps, quantile * 100))

    def mean_gap(self, path_id: int) -> float:
        """Exponential-weighted mean gap for path."""
        return self._ewma_values.get(path_id, 0.0)

    def n_samples(self, path_id: int) -> int:
        """Number of gaps observed for this path."""
        return len(self._gap_histories.get(path_id, []))

    def is_ready(self, path_id: int) -> bool:
        return self.n_samples(path_id) >= self.min_samples

    def reset_path(self, path_id: int):
        self._gap_histories.pop(path_id, None)
        self._ewma_values.pop(path_id, None)

    def reset_all(self):
        self._gap_histories.clear()
        self._ewma_values.clear()


class QuantileBaseline(EWMABaseline):
    """Non-parametric quantile baseline: predict S(h) from historical gap quantiles.

    More conservative than EWMA — uses the minimum of the EWMA estimate
    and the p10 quantile to produce conservative gap bounds.
    """

    def predict(self, path_id: int, horizons: Tuple[int, ...] = HORIZONS_NS) -> Dict[int, float]:
        base = super().predict(path_id, horizons)
        p10 = self.predict_quantile(path_id, 0.1)
        # Conservative adjustment: if p10 is very small, reduce confidence
        for h in horizons:
            if p10 < h:
                base[h] *= 0.5  # penalty for short gaps
        return base
