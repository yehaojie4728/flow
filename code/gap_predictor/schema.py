"""
SafeWindow schema, horizon definitions, and confidence constants for the gap predictor.

Reference: docs/trace_schema.md §4, docs/implementation_plan_v1.md Module 3.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import enum

# ---------------------------------------------------------------------------
# Horizon set (nanoseconds) — the h in S(h | x_t)
# ---------------------------------------------------------------------------

HORIZONS_NS = (
    10_000,       # 10 µs
    25_000,       # 25 µs
    50_000,       # 50 µs  (tiny latency probe)
    100_000,      # 100 µs
    250_000,      # 250 µs
    500_000,      # 500 µs (normal latency probe)
    1_000_000,    # 1 ms
    2_000_000,    # 2 ms
)

HORIZON_LABELS = {
    10_000:    "10us",
    25_000:    "25us",
    50_000:    "50us",
    100_000:   "100us",
    250_000:   "250us",
    500_000:   "500us",
    1_000_000: "1ms",
    2_000_000: "2ms",
}

# ---------------------------------------------------------------------------
# Confidence thresholds → probe type mapping
# ---------------------------------------------------------------------------

ETA_BANDWIDTH      = 0.98
ETA_NORMAL_LATENCY = 0.95
ETA_TINY_LATENCY   = 0.90
# below 0.90 → no probe allowed

# ---------------------------------------------------------------------------
# Probe type codes
# ---------------------------------------------------------------------------

class ProbeType(enum.IntEnum):
    NONE           = 0
    TINY_LATENCY   = 1   # 4 KB × 1, ~50 µs
    NORMAL_LATENCY = 2   # 4 KB × 10, ~500 µs
    BANDWIDTH      = 3   # 128 MB, ~5-10 ms
    CONFIRMATION   = 4   # 4 KB × 5, ~250 µs


def confidence_to_probe_type(conf: float) -> int:
    """Map calibrated confidence to probe type."""
    if conf >= ETA_BANDWIDTH:
        return ProbeType.BANDWIDTH
    if conf >= ETA_NORMAL_LATENCY:
        return ProbeType.NORMAL_LATENCY
    if conf >= ETA_TINY_LATENCY:
        return ProbeType.TINY_LATENCY
    return ProbeType.NONE


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------

class ReasonCode(enum.IntEnum):
    SAFE              = 0
    LOW_CONFIDENCE    = 1
    GAP_TOO_SHORT     = 2
    NO_DATA           = 3
    DRIFT_DETECTED    = 4
    LOW_DATA_QUALITY  = 5
    COOLDOWN          = 6


# ---------------------------------------------------------------------------
# SafeWindow dataclass
# ---------------------------------------------------------------------------

@dataclass
class SafeWindow:
    """Predicted safe window for a path."""
    path_id: int
    link_bitmap: int = 0
    t_publish: int = 0             # monotonic ns when computed
    t_valid_from: int = 0          # monotonic ns from which prediction valid
    g_lower_bound: int = 0         # predicted conservative gap lower bound (ns)
    p_safe: float = 0.0            # raw predicted safe probability S(h | x_t)
    confidence: float = 0.0        # calibrated confidence C_final
    horizon_ns: int = 0            # horizon h this prediction is valid for
    allowed_probe_type: int = 0    # ProbeType
    max_probe_size: int = 0        # max bytes for probe at this confidence
    reason_code: int = ReasonCode.SAFE

    @classmethod
    def unsafe(cls, path_id: int, reason: int) -> "SafeWindow":
        return cls(path_id=path_id, reason_code=reason)

    @property
    def is_safe(self) -> bool:
        return self.reason_code == ReasonCode.SAFE

    @property
    def probe_type_label(self) -> str:
        return ProbeType(self.allowed_probe_type).name


# ---------------------------------------------------------------------------
# Prediction record (for offline evaluation)
# ---------------------------------------------------------------------------

@dataclass
class PredictionRecord:
    """Single prediction record for evaluation."""
    path_id: int
    horizon_ns: int
    p_safe_raw: float
    p_safe_calibrated: float
    actual_gap_ns: int
    actual_safe: bool           # True if actual gap >= horizon
    g_lower_bound: int = 0
    lower_bound_holds: bool = True
    timestamp_ns: int = 0
    features: Optional[Dict] = None


@dataclass
class EvaluationResult:
    """Per-horizon evaluation metrics."""
    horizon_ns: int
    precision: float = 0.0
    recall: float = 0.0
    false_safe_rate: float = 0.0
    brier_score: float = 0.0
    expected_calibration_error: float = 0.0
    lower_bound_coverage: float = 0.0
    n_samples: int = 0
    n_safe: int = 0
    n_predicted_safe: int = 0


# ---------------------------------------------------------------------------
# Feature names
# ---------------------------------------------------------------------------

FEATURE_GROUP_LABELS = {
    "recent_gap_stats":     ["gap_p10", "gap_p50", "gap_p90", "gap_mean",
                             "gap_std", "gap_last", "gap_last5_mean"],
    "recent_burst_stats":   ["burst_p50", "burst_p90", "burst_mean",
                             "burst_rate", "burst_last_duration"],
    "idle_age":             ["time_since_last_busy"],
    "path_identity":        ["path_id", "direction", "cross_numa_flag"],
    "stream_features":      ["stream_id", "stream_pending_count",
                             "time_since_last_sync"],
    "phase_features":       ["phase_id", "sync_before_flag"],
    "resource_features":    ["cpu_usage_pct", "npu_util_pct", "ebpf_event_rate"],
    "data_quality":         ["drop_rate", "unknown_path_ratio",
                             "async_uncertainty_ratio", "timestamp_jitter"],
    "time_features":        ["hour_of_day", "workload_runtime_sec"],
}
