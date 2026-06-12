"""
Replay policies for offline trace-based scheduler evaluation.

Implements 7 policies:
  1. no_probing         — zero probes placed (baseline: zero overhead)
  2. fixed_interval     — place probe every K ms (simple baseline)
  3. random             — place probe with probability p on each gap
  4. threshold          — probe when gap bandwidth exceeds threshold
  5. ewma_only          — EWMA baseline predictor (from gap_predictor)
  6. flowgap_predictive — Full FlowGap GBDT predictor
  7. oracle             — knows all future gaps (upper bound)

All policies operate on the same gap timeline data structure.
"""

from __future__ import annotations

import sys, os, random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trace_parser"))

from scheduler_replay.schema import (
    ProbeType, ProbeConfig, ProbeOutcome,
    PROBE_LATENCY_SAME_NUMA_NS, CROSS_NUMA_FACTOR_D2H, CROSS_NUMA_FACTOR_H2D,
    POLICY_NAMES,
)
from trace_parser.intervalize import Gap, BusyInterval

# ---- Data structure for policy input ----

@dataclass
class GapSnapshot:
    """A single gap from a path timeline, used as policy decision point."""
    path_id: int
    gap: Gap
    previous_gaps: List[float]       # gap durations before this one (ns)
    previous_busy: List[BusyInterval]
    is_cross_numa: bool = False
    direction: int = 2               # D2H

    @property
    def gap_duration_ns(self) -> int:
        return self.gap.duration_ns

    @property
    def gap_start_ns(self) -> int:
        return self.gap.start_ns


@dataclass
class PolicyContext:
    """Mutable state shared across snapshots within one policy run."""
    probe_count: int = 0
    last_probe_time_ns: int = 0
    budget_remaining: int = 1000
    rng: random.Random = field(default_factory=lambda: random.Random(42))

# ---- Policy function signature ----
# Every policy returns a list of ProbeConfig for each GapSnapshot.

PolicyFunc = Callable[[GapSnapshot, PolicyContext], List[ProbeConfig]]


# ============================================================================
# Policy 1: No probing
# ============================================================================

def no_probing(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
    """Place zero probes."""
    return []


# ============================================================================
# Policy 2: Fixed interval
# ============================================================================

def make_fixed_interval(period_ns: int = 100_000_000) -> PolicyFunc:
    """Place one tiny latency probe every `period_ns`."""
    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        if ctx.last_probe_time_ns > 0 and \
           snapshot.gap_start_ns - ctx.last_probe_time_ns < period_ns:
            return []
        ctx.last_probe_time_ns = snapshot.gap_start_ns
        ctx.probe_count += 1
        return [ProbeConfig(ProbeType.TINY_LATENCY, path_id=snapshot.path_id)]
    return policy


# ============================================================================
# Policy 3: Random probing
# ============================================================================

def make_random(probability: float = 0.01) -> PolicyFunc:
    """Place a randomly chosen probe type with probability p on each gap.

    Does NOT inspect gap size — truly blind random selection.
    This is the naive baseline: when you probe without looking at traffic.
    """
    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        if ctx.rng.random() < probability:
            ctx.probe_count += 1
            # Random probe type — no gap-size inspection
            pt = ctx.rng.choice([
                ProbeType.TINY_LATENCY,
                ProbeType.NORMAL_LATENCY,
                ProbeType.BANDWIDTH,
            ])
            return [ProbeConfig(pt, path_id=snapshot.path_id)]
        return []
    return policy


# ============================================================================
# Policy 4: Threshold probing
# ============================================================================

def make_threshold(
    low_threshold_ns: int = 500_000,
    high_threshold_ns: int = 5_000_000,
) -> PolicyFunc:
    """Probe when gap exceeds bandwidth thresholds."""
    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        dur = snapshot.gap_duration_ns
        if dur >= high_threshold_ns:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.BANDWIDTH, path_id=snapshot.path_id)]
        elif dur >= low_threshold_ns:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.NORMAL_LATENCY, path_id=snapshot.path_id)]
        return []
    return policy


# ============================================================================
# Policy 5: EWMA-only probing
# ============================================================================

def make_ewma(alpha: float = 0.1, safety_margin_ns: int = 200_000) -> PolicyFunc:
    """EWMA-based: predict gap from recent history, probe if predicted safe.

    This is the Tier-0 baseline from gap_predictor — uses simple
    exponential-moving-average of recent gap durations.
    """
    ewma_values: Dict[int, float] = {}
    gap_histories: Dict[int, List[float]] = {}

    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        pid = snapshot.path_id
        dur = float(snapshot.gap_duration_ns)

        # Update EWMA
        if pid not in gap_histories:
            gap_histories[pid] = []
            ewma_values[pid] = dur
        else:
            ewma_values[pid] = alpha * dur + (1 - alpha) * ewma_values[pid]
        gap_histories[pid].append(dur)
        gap_histories[pid] = gap_histories[pid][-100:]

        if len(gap_histories[pid]) < 10:
            return []

        # Predict: assume gap >= ewma_mean
        predicted_gap = max(ewma_values[pid],
                            np.percentile(gap_histories[pid], 10))

        # Decide probe type
        latencies = PROBE_LATENCY_SAME_NUMA_NS
        if predicted_gap - safety_margin_ns >= latencies[ProbeType.BANDWIDTH]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.BANDWIDTH, path_id=pid)]
        elif predicted_gap - safety_margin_ns >= latencies[ProbeType.NORMAL_LATENCY]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.NORMAL_LATENCY, path_id=pid)]
        elif predicted_gap - safety_margin_ns >= latencies[ProbeType.TINY_LATENCY]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.TINY_LATENCY, path_id=pid)]
        return []
    return policy


# ============================================================================
# Policy 6: FlowGap predictive probing
# ============================================================================

def make_flowgap(predictor_model_path: str = "") -> PolicyFunc:
    """Full FlowGap GBDT predictor — loads trained model and evaluates.

    Loads a MultiHorizonSurvivalPredictor from a pickle file (trained by
    gap_predictor/train_and_save.py).  Features are computed inline
    using the same statistics as build_parquet.py.

    Falls back to EWMA if model not available.
    """
    # Lazy imports — only when policy is constructed
    try:
        from gap_predictor.survival_model import MultiHorizonSurvivalPredictor
        from gap_predictor.schema import ETA_TINY_LATENCY, ETA_NORMAL_LATENCY, ETA_BANDWIDTH
        HAS_PREDICTOR = True
    except ImportError:
        HAS_PREDICTOR = False

    # Per-path state
    path_gap_durs: Dict[int, List[float]] = {}   # recent gap durations (ns)
    path_burst_durs: Dict[int, List[float]] = {}  # recent burst durations (ns)
    ewma_fallback = make_ewma() if HAS_PREDICTOR else None
    survival_model = None
    WIN = 50

    if HAS_PREDICTOR and predictor_model_path and os.path.exists(predictor_model_path):
        try:
            survival_model = MultiHorizonSurvivalPredictor.load(predictor_model_path)
        except Exception:
            survival_model = None

    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        nonlocal survival_model, path_gap_durs, path_burst_durs
        pid = snapshot.path_id
        dur = float(snapshot.gap_duration_ns)

        # Accumulate
        if pid not in path_gap_durs:
            path_gap_durs[pid] = []
            path_burst_durs[pid] = []
        path_gap_durs[pid].append(dur)
        path_gap_durs[pid] = path_gap_durs[pid][-WIN:]  # keep window

        # Track burst durations from recent busy intervals
        for bi in snapshot.previous_busy[-WIN:]:
            if bi.duration_ns > 0:
                path_burst_durs[pid].append(float(bi.duration_ns))
        path_burst_durs[pid] = path_burst_durs[pid][-WIN:]

        if len(path_gap_durs[pid]) < 10:
            return []

        if survival_model is not None:
            try:
                # Compute the same 30 features as build_parquet.py
                feats = _compute_30_features(
                    path_gap_durs[pid],
                    path_burst_durs[pid],
                    pid,
                    snapshot,
                )
                if len(feats) == 0:
                    return []

                probs = survival_model.predict_proba(
                    feats.reshape(1, -1), 500_000
                )
                conf = float(probs[0])

                # Map confidence to probe type
                latencies = PROBE_LATENCY_SAME_NUMA_NS
                if conf >= 0.95 and dur >= latencies[ProbeType.BANDWIDTH]:
                    ctx.probe_count += 1
                    return [ProbeConfig(ProbeType.BANDWIDTH, path_id=pid)]
                elif conf >= 0.90 and dur >= latencies[ProbeType.NORMAL_LATENCY]:
                    ctx.probe_count += 1
                    return [ProbeConfig(ProbeType.NORMAL_LATENCY, path_id=pid)]
                elif dur >= latencies[ProbeType.TINY_LATENCY]:
                    ctx.probe_count += 1
                    return [ProbeConfig(ProbeType.TINY_LATENCY, path_id=pid)]
            except Exception:
                pass

        # Fall back to EWMA
        if ewma_fallback is not None:
            return ewma_fallback(snapshot, ctx)
        return []

    return policy


# ============================================================================
# Policy 7: Oracle gap-aware probing
# ============================================================================

def make_oracle() -> PolicyFunc:
    """Oracle: knows all future gaps. Places probes only when guaranteed safe.

    This is an upper bound — no predictor can outperform oracle.
    """
    def policy(snapshot: GapSnapshot, ctx: PolicyContext) -> List[ProbeConfig]:
        dur = snapshot.gap_duration_ns
        latencies = PROBE_LATENCY_SAME_NUMA_NS
        # Oracle: probe exact type the gap can accommodate
        if dur >= latencies[ProbeType.BANDWIDTH]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.BANDWIDTH, path_id=snapshot.path_id)]
        elif dur >= latencies[ProbeType.NORMAL_LATENCY]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.NORMAL_LATENCY, path_id=snapshot.path_id)]
        elif dur >= latencies[ProbeType.TINY_LATENCY]:
            ctx.probe_count += 1
            return [ProbeConfig(ProbeType.TINY_LATENCY, path_id=snapshot.path_id)]
        return []
    return policy


# ============================================================================
# Feature computation (inline — matches build_parquet.py 30-feature layout)
# ============================================================================

def _compute_30_features(
    gap_durs: List[float],
    burst_durs: List[float],
    path_id: int,
    snapshot: GapSnapshot,
) -> np.ndarray:
    """Compute exactly the same 30 features as build_parquet.py.

    Features must match the column order in burst_gap_events.parquet.
    """
    arr = np.array(gap_durs, dtype=np.float64)
    if len(arr) < 5:
        return np.array([])

    b_arr = np.array(burst_durs, dtype=np.float64) if burst_durs else np.array([0.0])

    # Gap stats
    gp10 = float(np.percentile(arr, 10))
    gp50 = float(np.percentile(arr, 50))
    gp90 = float(np.percentile(arr, 90))
    gp_mean = float(np.mean(arr))
    gp_std = float(np.std(arr))
    gp_last = float(arr[-1])
    gp_last5 = float(np.mean(arr[-5:])) if len(arr) >= 5 else gp_mean

    # Burst stats
    bp50 = float(np.percentile(b_arr, 50))
    bp90 = float(np.percentile(b_arr, 90))
    bp_mean = float(np.mean(b_arr))
    bp_last = float(b_arr[-1])
    bp_rate = 0.0

    # Idle age
    if snapshot.previous_busy and len(snapshot.previous_busy) > 0:
        idle_age = float(max(0, snapshot.gap_start_ns - snapshot.previous_busy[-1].end_ns))
    else:
        idle_age = 0.0

    return np.array([
        gp10, gp50, gp90, gp_mean, gp_std,
        gp_last, gp_last5,
        bp50, bp90, bp_mean, bp_rate, bp_last,
        idle_age,
        float(path_id) / 65536,
        2.0,  # direction_code (D2H)
        0.0,  # cross_numa_flag
        0.0, 0.0, 0.0,  # stream placeholders
        0.0, 0.0,  # phase
        50.0, 50.0,  # cpu/npu util
        float(len(gap_durs)),
        0.0, 0.0, 0.0, 0.0,  # drop/unknown/async/jitter
        0.0, 0.0,  # hour/runtime
    ], dtype=np.float64)


# ============================================================================
# Policy factory
# ============================================================================


def make_policy(name: str, **kwargs) -> PolicyFunc:
    """Factory: create a policy function by name."""
    if name == "no_probing":
        return no_probing
    elif name == "fixed_interval":
        period_ns = kwargs.get("period_ns", kwargs.get("fixed_period_ms", 100) * 1_000_000)
        return make_fixed_interval(period_ns)
    elif name == "random":
        p = kwargs.get("probability", kwargs.get("random_probability", 0.01))
        return make_random(p)
    elif name == "threshold":
        lo = kwargs.get("low_threshold_ns", kwargs.get("threshold_mbps_low", 0.0))
        hi = kwargs.get("high_threshold_ns", kwargs.get("threshold_mbps_high", 500_000))
        return make_threshold(int(lo), int(hi))
    elif name == "ewma_only":
        alpha = kwargs.get("alpha", 0.1)
        return make_ewma(alpha)
    elif name == "flowgap_predictive":
        path = kwargs.get("predictor_model_path", "")
        return make_flowgap(path)
    elif name == "oracle":
        return make_oracle()
    else:
        raise ValueError(f"Unknown policy: {name}. Known: {POLICY_NAMES}")
