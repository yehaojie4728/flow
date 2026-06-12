"""
Scheduler replay evaluation metrics.

Computes:
  - overlap_ratio: fraction of probe time that overlaps with busy intervals
  - safe_probing_ratio: fraction of probes placed without overlap
  - harmful_probe_count: number of probes with any overlap
  - probing_overhead: fraction of total time spent probing
  - probes_per_second: achieved probe rate
  - per_path breakdowns

Reference: docs/implementation_plan_v1.md Module 5.
"""

from __future__ import annotations

import sys, os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_replay.schema import (
    ProbeOutcome, RunMetrics, ProbeType, ProbeConfig,
    PROBE_LATENCY_SAME_NUMA_NS,
)


def compute_summary(outcomes: List[ProbeOutcome], policy_name: str = "") -> RunMetrics:
    """Compute RunMetrics from a list of probe outcomes."""
    executed = [p for p in outcomes if not p.cancelled]
    safe = [p for p in executed if p.safe]
    unsafe = [p for p in executed if not p.safe]

    total_probe_ns = sum(
        p.ended_time_ns - p.started_time_ns for p in executed
    )
    total_overlap_ns = sum(p.busy_overlap_ns for p in executed)

    per_path: Dict[int, dict] = defaultdict(
        lambda: {"total": 0, "executed": 0, "safe": 0, "unsafe": 0}
    )
    for p in outcomes:
        pid = p.probe.path_id
        per_path[pid]["total"] += 1
        if not p.cancelled:
            per_path[pid]["executed"] += 1
            if p.safe:
                per_path[pid]["safe"] += 1
            else:
                per_path[pid]["unsafe"] += 1

    return RunMetrics(
        policy=policy_name,
        total_probes_scheduled=len(outcomes),
        total_probes_executed=len(executed),
        safe_probes=len(safe),
        unsafe_probes=len(unsafe),
        cancelled_probes=len([p for p in outcomes if p.cancelled]),
        downgraded_probes=len([p for p in executed if p.downgraded]),
        probe_overlap_ratio=round(
            total_overlap_ns / max(1, total_probe_ns), 4
        ),
        safe_probing_ratio=round(len(safe) / max(1, len(executed)), 4),
        harmful_probe_count=len(unsafe),
        total_probing_ns=total_probe_ns,
        per_path_metrics=dict(per_path),
    )


def compare_results(results: Dict[str, RunMetrics]) -> Dict[str, dict]:
    """Create a comparison table across policies."""
    rows = {}
    baseline = results.get("no_probing", None)
    for name, m in results.items():
        rows[name] = {
            "executed": m.total_probes_executed,
            "safe_pct": round(m.safe_probing_ratio * 100, 1),
            "overlap_pct": round(m.probe_overlap_ratio * 100, 1),
            "harmful": m.harmful_probe_count,
            "overhead_pct": m.probing_overhead_pct,
            "downgraded": m.downgraded_probes,
        }
    return rows


def metrics_table(results: Dict[str, RunMetrics]) -> str:
    """Pretty-print comparison table."""
    comp = compare_results(results)
    lines = [
        f"{'Policy':<24s} {'Probes':>7s} {'Safe%':>7s} {'Overlap%':>9s} "
        f"{'Harm':>6s} {'Ovhd%':>7s}",
        "-" * 70,
    ]
    for name in ["no_probing", "fixed_interval", "random", "threshold",
                 "ewma_only", "flowgap_predictive", "oracle"]:
        if name not in comp:
            continue
        c = comp[name]
        lines.append(
            f"{name:<24s} {c['executed']:7d} {c['safe_pct']:6.1f}% "
            f"{c['overlap_pct']:8.1f}% {c['harmful']:6d} {c['overhead_pct']:6.1f}%"
        )
    return "\n".join(lines)


def probing_overhead(
    total_probing_ns: int, total_time_ns: int,
) -> float:
    """Fraction of time spent probing."""
    if total_time_ns <= 0:
        return 0.0
    return round(total_probing_ns / total_time_ns * 100, 3)


def probe_rate_per_second(
    probe_count: int, total_time_ns: int,
) -> float:
    """Probes per second."""
    if total_time_ns <= 0:
        return 0.0
    return round(probe_count / (total_time_ns / 1e9), 2)


def per_probe_type_breakdown(
    outcomes: List[ProbeOutcome],
) -> Dict[int, int]:
    """Count probes by type."""
    counts: Dict[int, int] = defaultdict(int)
    for p in outcomes:
        if not p.cancelled:
            counts[p.probe.probe_type] += 1
    return dict(counts)


def calculate_gap_coverage(
    outcomes: List[ProbeOutcome],
    safe_outcomes: List[ProbeOutcome],
    total_gaps: int,
) -> Dict[str, float]:
    """Gap coverage metrics."""
    safe_gaps_used = len(set(p.gap_during_probe_ns for p in safe_outcomes))
    return {
        "total_gaps": total_gaps,
        "gaps_probed": len(outcomes),
        "gaps_safe_probed": safe_gaps_used,
        "coverage_pct": round(safe_gaps_used / max(1, total_gaps) * 100, 1),
        "utilization_pct": round(len(outcomes) / max(1, total_gaps) * 100, 1),
    }
