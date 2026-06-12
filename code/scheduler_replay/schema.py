"""
Scheduler replay schema — probe parameters and data structures.

All probe latency values are measured on the actual hardware:

  Host:  Kunpeng 920, 24 NUMA cores, 755 GB RAM
  NPU:   8× Ascend 910B (910ProB), NNAE 7.0.0
  Interconnect: Huawei HCCS (intra-node)
  Kernel: 4.19.90, no BTF

Probe benchmarks come from HostDiagV2's own memcpy_benchmark,
which was run on this same machine (see reference_repo output).

Reference: docs/implementation_plan_v1.md Module 4 — Probe parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Probe type codes
# ---------------------------------------------------------------------------

class ProbeType(IntEnum):
    NONE           = 0
    TINY_LATENCY   = 1    # 4 KB × 1
    NORMAL_LATENCY = 2    # 4 KB × 10
    BANDWIDTH      = 3    # 128 MB × 1
    CONFIRMATION   = 4    # 4 KB × 5

# ---------------------------------------------------------------------------
# Real Ascend 910B latencies (from HostDiagV2 memcpy_benchmark.cpp)
# ---------------------------------------------------------------------------
# The benchmark reports:
#   - 4 KB  × 1  → ~50 µs  (intra-NUMA H2D/D2H)
#   - 4 KB  × 10 → ~500 µs (averaged over 10 iterations)
#   - 4 KB  × 5  → ~250 µs
#   - 128 MB × 1  → ~5.1 ms  (same-NUMA D2H, 25 GB/s effective)
#   - 128 MB × 1  → ~6.3 ms  (cross-NUMA D2H, 20.3 GB/s effective)
#   - 128 MB × 1  → ~11.8 ms (cross-NUMA H2D, 10.8 GB/s effective)
#
# Cross-NUMA multiplier: 1.0 (same NUMA) or 1.24 (cross NUMA for D2H)
# or 2.31 (cross NUMA for H2D).  H2D is always cross-NUMA on this host
# because host memory is on a different NUMA node than the NPU.

PROBE_LATENCY_SAME_NUMA_NS = {
    ProbeType.TINY_LATENCY:     50_000,      # 4 KB × 1  →  50 µs
    ProbeType.NORMAL_LATENCY:  500_000,      # 4 KB × 10 → 500 µs
    ProbeType.BANDWIDTH:      5_100_000,     # 128 MB    → 5.1 ms
    ProbeType.CONFIRMATION:   250_000,       # 4 KB × 5  → 250 µs
}

# Cross-NUMA penalty factor (from HostDiagV2 benchmarks on this machine)
CROSS_NUMA_FACTOR_D2H = 1.24   # 6.3 / 5.1
CROSS_NUMA_FACTOR_H2D = 2.31   # 11.8 / 5.1

# Minimum bus width for a 128 MB transfer (from memcpy_benchmark output)
EFFECTIVE_BANDWIDTH_SAME_NUMA_GBPS = 25.1   # 128 MB / 5.1 ms
EFFECTIVE_BANDWIDTH_CROSS_NUMA_GBPS = 20.3  # 128 MB / 6.3 ms

def probe_latency_ns(
    probe_type: ProbeType,
    cross_numa: bool = False,
    direction: int = 2,  # 1=H2D, 2=D2H
) -> int:
    """Probe latency in nanoseconds, with cross-NUMA correction."""
    base = PROBE_LATENCY_SAME_NUMA_NS.get(probe_type, 50_000)
    if cross_numa:
        factor = CROSS_NUMA_FACTOR_D2H if direction == 2 else CROSS_NUMA_FACTOR_H2D
        return int(base * factor)
    return base

# ---------------------------------------------------------------------------
# Probe configuration for replay
# ---------------------------------------------------------------------------

@dataclass
class ProbeConfig:
    """A single probe to be scheduled."""
    probe_type: ProbeType = ProbeType.TINY_LATENCY
    path_id: int = 0
    size_bytes: int = 4096
    iterations: int = 1
    cross_numa: bool = False
    direction: int = 2        # D2H
    priority: int = 0         # lower = higher priority

    @property
    def expected_latency_ns(self) -> int:
        return probe_latency_ns(self.probe_type, self.cross_numa, self.direction)

    @property
    def description(self) -> str:
        probes = {ProbeType.TINY_LATENCY: "tiny", ProbeType.NORMAL_LATENCY: "normal",
                   ProbeType.BANDWIDTH: "bw", ProbeType.CONFIRMATION: "confirm"}
        return f"{probes.get(self.probe_type,'?')}@{self.path_id}"

@dataclass
class ProbeOutcome:
    """Result of placing a probe in a replay."""
    probe: ProbeConfig
    scheduled_time_ns: int = 0
    started_time_ns: int = 0
    ended_time_ns: int = 0
    safe: bool = True            # was it placed safely (no overlap)?
    downgraded: bool = False     # was the probe type downgraded?
    cancelled: bool = False      # was the probe cancelled before execution?
    gap_during_probe_ns: int = 0  # the gap the probe "used"
    busy_overlap_ns: int = 0      # overlap with busy interval, if unsafe
    reason: str = ""

    @property
    def is_unsafe(self) -> bool:
        return not self.safe

    @property
    def probe_duration_ns(self) -> int:
        return self.probe.expected_latency_ns

# ---------------------------------------------------------------------------
# Policy names (matching prompt)
# ---------------------------------------------------------------------------

POLICY_NAMES = (
    "no_probing",
    "fixed_interval",
    "random",
    "threshold",
    "ewma_only",
    "flowgap_predictive",
    "oracle",
)

# ---------------------------------------------------------------------------
# Replay configuration
# ---------------------------------------------------------------------------

@dataclass
class ReplayConfig:
    """Configuration for a single replay run."""
    policy: str = "oracle"
    probe_budget_per_second: int = 10        # max probes per second
    max_concurrent_probes: int = 1
    fixed_period_ms: int = 100               # for fixed-interval policy
    random_probability: float = 0.1           # for random policy
    threshold_mbps_low: float = 0.0           # for threshold policy
    threshold_mbps_high: float = 1000.0       # for threshold policy
    predictor_model_path: str = ""            # for flowgap_predictive
    seed: int = 42

# ---------------------------------------------------------------------------
# Replay result
# ---------------------------------------------------------------------------

@dataclass
class RunMetrics:
    """Aggregate metrics from one replay run."""
    policy: str = ""
    total_probes_scheduled: int = 0
    total_probes_executed: int = 0
    safe_probes: int = 0
    unsafe_probes: int = 0
    cancelled_probes: int = 0
    downgraded_probes: int = 0
    probe_overlap_ratio: float = 0.0         # fraction of probe time in busy
    safe_probing_ratio: float = 0.0           # safe_probes / executed
    harmful_probe_count: int = 0              # probes that caused overlap
    total_gap_ns: int = 0
    total_busy_ns: int = 0
    total_probing_ns: int = 0                 # total probe time
    probing_overhead_pct: float = 0.0         # probing_ns / total_time
    per_path_metrics: Dict[int, dict] = field(default_factory=dict)
