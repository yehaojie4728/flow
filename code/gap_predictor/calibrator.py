"""
Confidence calibration for safe-window predictions.

Converts raw model probabilities into calibrated confidence scores
via empirical binning (reliability-diagram approach).

Composes multiple confidence components:
    C_final = min(C_model, C_calib, C_data, C_drift)

Reference: docs/implementation_plan_v1.md Module 3.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from gap_predictor.schema import ETA_TINY_LATENCY, ETA_NORMAL_LATENCY, ETA_BANDWIDTH, HORIZONS_NS


class CalibrationTable:
    """Empirical bin-based calibration using reliability diagram bins.

    After observing (predicted_prob, actual_label) pairs, maps
    raw probabilities to calibrated confidences.
    """

    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self._bin_edges: Optional[np.ndarray] = None
        self._bin_accuracies: Optional[np.ndarray] = None  # fraction of positive labels per bin
        self._bin_counts: Optional[np.ndarray] = None
        self._fitted = False

    def update(self, probs: List[float], labels: List[int]):
        """Cumulative update with new (prob, label) pairs."""
        if not probs:
            return
        probs = np.array(probs)
        labels = np.array(labels)
        edges = np.linspace(0, 1, self.n_bins + 1)
        acc = np.zeros(self.n_bins)
        cnt = np.zeros(self.n_bins, dtype=np.int64)

        for i in range(self.n_bins):
            mask = (probs >= edges[i]) & (probs < edges[i + 1])
            cnt[i] = np.sum(mask)
            if cnt[i] > 0:
                acc[i] = np.mean(labels[mask])

        self._bin_edges = edges
        self._bin_accuracies = acc
        self._bin_counts = cnt
        self._fitted = True

    def calibrate(self, raw_prob: float) -> float:
        """Calibrate a single probability.

        Returns the empirical accuracy of the bin this probability falls into.
        If bin has too few samples, return raw_prob (no calibration).
        """
        if not self._fitted or self._bin_accuracies is None:
            return raw_prob
        if raw_prob < 0 or raw_prob > 1:
            return max(0.0, min(1.0, raw_prob))

        for i in range(self.n_bins):
            if self._bin_edges is not None and \
                    raw_prob >= self._bin_edges[i] and raw_prob < self._bin_edges[i + 1]:
                if self._bin_counts[i] < 5:
                    return raw_prob  # too few samples
                return float(self._bin_accuracies[i])
        return raw_prob

    def calibrate_array(self, probs: np.ndarray) -> np.ndarray:
        return np.array([self.calibrate(float(p)) for p in probs])

    def expected_calibration_error(self) -> float:
        """Compute ECE = weighted sum of |acc(bin) - mean_prob(bin)|."""
        if not self._fitted:
            return 1.0
        # Simplified: ECE from observed counts
        if self._bin_counts is None or self._bin_accuracies is None:
            return 1.0
        total = max(1, int(np.sum(self._bin_counts)))
        # We don't store per-bin mean_prob, so use bin center as estimate
        centers = (self._bin_edges[:-1] + self._bin_edges[1:]) / 2 if self._bin_edges is not None else np.zeros(10)
        ece = 0.0
        for i in range(self.n_bins):
            if self._bin_counts[i] > 0:
                ece += self._bin_counts[i] * abs(self._bin_accuracies[i] - centers[i]) / total
        return float(ece)

    def plot_table(self) -> List[Dict]:
        """Return calibration data as list of dicts (for logging/reporting)."""
        if not self._fitted:
            return []
        rows = []
        for i in range(self.n_bins):
            rows.append({
                "bin": i,
                "lower": round(float(self._bin_edges[i]), 2) if self._bin_edges is not None else 0.0,
                "upper": round(float(self._bin_edges[i + 1]), 2) if self._bin_edges is not None else 0.0,
                "accuracy": round(float(self._bin_accuracies[i]), 4) if self._bin_accuracies is not None else 0.0,
                "count": int(self._bin_counts[i]) if self._bin_counts is not None else 0,
            })
        return rows


class ConfidenceComposer:
    """Compose multiple confidence components into C_final.

    C_final = min(C_model, C_calib, C_data, C_drift)
    """

    def compose(
        self,
        c_model: float,      # raw model probability
        c_calib: float,      # calibrated probability (from CalibrationTable)
        c_data: float = 1.0, # data quality confidence
        c_drift: float = 1.0,# drift confidence (1.0 - drift_score)
    ) -> float:
        return min(c_model, c_calib, c_data, c_drift)

    @staticmethod
    def data_quality_confidence(
        drop_rate: float = 0.0,
        unknown_path_ratio: float = 0.0,
        async_uncertainty_ratio: float = 0.0,
    ) -> float:
        """Compute C_data from quality metrics.

        Linear penalty from quality flags.
        """
        q = 1.0
        q -= min(0.3, drop_rate * 3)          # drop_rate > 10% → -0.3
        q -= min(0.2, unknown_path_ratio * 2)  # unknown_path > 10% → -0.2
        q -= min(0.5, async_uncertainty_ratio) # async uncertainty
        return max(0.0, q)

    @staticmethod
    def drift_confidence(drift_score: float) -> float:
        """C_drift = 1.0 - drift_score, clamped to [0.1, 1.0]."""
        return max(0.1, min(1.0, 1.0 - drift_score))
