"""
Feature extraction from per-path busy-idle timeline state.

Transforms a window of recent FlowEvent / BusyInterval / Gap history into
a fixed-length feature vector (~30 features) for the gap predictor.

Reference: docs/implementation_plan_v1.md Module 3 — Feature vector table.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from trace_parser.schema import FlowEvent, BusyInterval, Gap, Direction, HOST_DEVICE_ID
from trace_parser.intervalize import compute_gap_stats


# ---------------------------------------------------------------------------
# Core feature extraction
# ---------------------------------------------------------------------------

class FeatureExtractor:
    """Extract features from timeline state for a single path.

    Parameters
    ----------
    window_size : number of recent gaps/bursts to include in statistics
    min_events : minimum number of events before attempting extraction
    """

    def __init__(self, window_size: int = 50, min_events: int = 10):
        self.window_size = window_size
        self.min_events = min_events

    def extract(
        self,
        gaps: List[Gap],
        busy_intervals: List[BusyInterval],
        path_id: int,
        direction: int,
        now_ns: int,
        stream_info: Optional[Dict] = None,
        resource_info: Optional[Dict] = None,
        quality_info: Optional[Dict] = None,
    ) -> np.ndarray:
        """Extract feature vector from current timeline state.

        Returns 1D numpy array of features, or empty array if insufficient data.
        """
        if len(gaps) < self.min_events:
            return np.array([])

        features: List[float] = []

        # -------- recent gap statistics (7) --------
        gap_durations = np.array([g.duration_ns for g in gaps[-self.window_size:]])
        gap_durations = np.where(gap_durations > 0, gap_durations, 1.0)
        features.extend([
            float(np.percentile(gap_durations, 10)),
            float(np.percentile(gap_durations, 50)),
            float(np.percentile(gap_durations, 90)),
            float(np.mean(gap_durations)),
            float(np.std(gap_durations)),
            float(gap_durations[-1]),
            float(np.mean(gap_durations[-5:])) if len(gap_durations) >= 5 else float(np.mean(gap_durations)),
        ])

        # -------- recent burst statistics (5) --------
        burst_durations = np.array([
            bi.duration_ns for bi in busy_intervals[-self.window_size:]
            if bi.duration_ns > 0
        ])
        if len(burst_durations) > 0:
            total_span = (busy_intervals[-1].end_ns - busy_intervals[0].start_ns) if len(busy_intervals) >= 2 else 1
            span_s = max(total_span / 1e9, 0.001)
            burst_rate = len(burst_durations) / span_s
            features.extend([
                float(np.percentile(burst_durations, 50)),
                float(np.percentile(burst_durations, 90)),
                float(np.mean(burst_durations)),
                float(burst_rate),
                float(burst_durations[-1]),
            ])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0, 0.0])

        # -------- idle age (1) --------
        if busy_intervals:
            idle_age = max(0, now_ns - busy_intervals[-1].end_ns)
        else:
            idle_age = 0.0
        features.append(float(idle_age))

        # -------- path identity (3) --------
        features.append(float(path_id) / 65536.0)          # normalized
        features.append(float(direction))
        features.append(1.0 if direction == Direction.H2D else 0.0)  # cross_numa placeholder

        # -------- stream features (3) --------
        stream_info = stream_info or {}
        features.append(float(stream_info.get("stream_id", 0)) / 255.0)
        features.append(float(stream_info.get("pending_count", 0)))
        features.append(float(stream_info.get("time_since_last_sync", 0)) / 1e9)

        # -------- phase features (2) --------
        features.append(0.0)  # phase_id placeholder
        features.append(float(stream_info.get("sync_before_flag", 0)))

        # -------- resource features (3) --------
        resource_info = resource_info or {}
        features.append(float(resource_info.get("cpu_usage_pct", 50.0)))
        features.append(float(resource_info.get("npu_util_pct", 50.0)))
        features.append(float(resource_info.get("ebpf_event_rate", 100.0)))

        # -------- data quality (4) --------
        quality_info = quality_info or {}
        features.append(float(quality_info.get("drop_rate", 0.0)))
        features.append(float(quality_info.get("unknown_path_ratio", 0.0)))
        features.append(float(quality_info.get("async_uncertainty_ratio", 0.0)))
        features.append(float(quality_info.get("timestamp_jitter", 0.0)))

        # -------- time features (2) --------
        features.append(0.0)  # hour_of_day placeholder
        features.append(0.0)  # workload_runtime_sec placeholder

        return np.array(features, dtype=np.float32)

    def extract_many(
        self,
        gaps_list: List[List[Gap]],
        busy_list: List[List[BusyInterval]],
        path_ids: List[int],
        directions: List[int],
        now_ns: int,
    ) -> np.ndarray:
        """Batch extraction for multiple paths."""
        all_features = []
        for gaps, busy, pid, d in zip(gaps_list, busy_list, path_ids, directions):
            vec = self.extract(gaps, busy, pid, d, now_ns)
            if len(vec) > 0:
                all_features.append(vec)
        if all_features:
            return np.stack(all_features)
        return np.empty((0, self.n_features()))

    @staticmethod
    def n_features() -> int:
        return 30

    @staticmethod
    def feature_names() -> List[str]:
        return [
            "gap_p10", "gap_p50", "gap_p90", "gap_mean", "gap_std",
            "gap_last", "gap_last5_mean",
            "burst_p50", "burst_p90", "burst_mean", "burst_rate",
            "burst_last_duration",
            "idle_age_ns",
            "path_id_norm", "direction", "cross_numa_flag",
            "stream_id_norm", "stream_pending", "time_since_last_sync",
            "phase_id", "sync_before_flag",
            "cpu_usage_pct", "npu_util_pct", "ebpf_event_rate",
            "drop_rate", "unknown_path_ratio", "async_uncertainty",
            "timestamp_jitter",
            "hour_of_day", "workload_runtime",
        ]


# ---------------------------------------------------------------------------
# Label generation for multi-horizon training
# ---------------------------------------------------------------------------

def make_multi_horizon_labels(
    gaps: List[Gap],
    horizons_ns: Tuple[int, ...] = (50_000, 100_000, 250_000, 500_000,
                                     1_000_000, 2_000_000),
) -> Dict[int, np.ndarray]:
    """Convert gap durations to multi-horizon binary labels.

    For each horizon h, label y_h = 1 if gap_duration >= h, else 0.

    Returns:
        Dict[horizon_ns] -> binary label array shaped (len(gaps),)
    """
    durations = np.array([g.duration_ns for g in gaps], dtype=np.int64)
    labels: Dict[int, np.ndarray] = {}
    for h in horizons_ns:
        labels[h] = (durations >= h).astype(np.int32)
    return labels


def build_training_dataset(
    gaps_list: List[List[Gap]],
    busy_list: List[List[BusyInterval]],
    extractor: Optional[FeatureExtractor] = None,
    now_ns: int = 0,
) -> Tuple[np.ndarray, Dict[int, np.ndarray]]:
    """Build X (features) and y (multi-horizon labels) from timeline data.

    Returns:
        X: (n_samples, n_features)
        y: Dict[horizon_ns] -> (n_samples,) binary labels
    """
    if extractor is None:
        extractor = FeatureExtractor(min_events=5)

    all_X, all_labels = [], {h: [] for h in (50_000, 100_000, 250_000,
                                               500_000, 1_000_000, 2_000_000)}
    for gaps, busy in zip(gaps_list, busy_list):
        if len(gaps) < extractor.min_events:
            continue
        vec = extractor.extract(gaps, busy, 0, 1, now_ns)
        if len(vec) == 0:
            continue
        all_X.append(vec)
        for h, label_arr in make_multi_horizon_labels(gaps,
                                                       tuple(all_labels.keys())).items():
            all_labels[h].append(label_arr[-1])  # last gap = current label

    if not all_X:
        return np.empty((0, extractor.n_features())), {h: np.array([]) for h in all_labels}
    X = np.stack(all_X)
    return X, {h: np.array(v, dtype=np.int32) for h, v in all_labels.items()}
