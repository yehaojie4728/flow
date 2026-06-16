"""
Offline trace replay engine with virtual time.

Replays per-path gap timelines through a configurable policy
and produces RunMetrics — no live Ascend hardware needed.
"""

from __future__ import annotations

import sys, os, time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trace_parser"))

from scheduler_replay.schema import (
    ProbeType, ProbeConfig, ProbeOutcome, RunMetrics,
    PROBE_LATENCY_SAME_NUMA_NS, CROSS_NUMA_FACTOR_D2H,
    POLICY_NAMES, ReplayConfig,
)
from scheduler_replay.policies import (
    GapSnapshot, PolicyContext, PolicyFunc,
    make_policy, no_probing,
)
from trace_parser.intervalize import Gap, BusyInterval


def replay_trace(
    timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]],
    policy_name: str,
    config: Optional[ReplayConfig] = None,
) -> RunMetrics:
    """Replay a trace through a policy and return aggregate metrics.

    Parameters
    ----------
    timelines : per-path busy-idle timelines from trace_parser
    policy_name : one of POLICY_NAMES
    config : replay configuration (defaults used if None)

    Returns
    -------
    RunMetrics with aggregate statistics
    """
    if config is None:
        config = ReplayConfig(policy=policy_name)

    policy_fn = make_policy(policy_name,
                            period_ns=config.fixed_period_ms * 1_000_000,
                            probability=config.random_probability,
                            predictor_model_path=config.predictor_model_path)

    ctx = PolicyContext()

    # Collect all gap snapshots across paths, sorted chronologically
    all_snapshots: List[GapSnapshot] = []
    for path_id, (busy, gaps) in timelines.items():
        gap_durs: List[float] = []
        for i, gap in enumerate(gaps):
            snap = GapSnapshot(
                path_id=path_id,
                gap=gap,
                previous_gaps=list(gap_durs),
                previous_busy=busy[max(0, i - 64):max(1, i)],
            )
            all_snapshots.append(snap)
            gap_durs.append(float(gap.duration_ns))

    # Sort by gap start time (chronological)
    all_snapshots.sort(key=lambda s: s.gap_start_ns)

    # --- Replay ---
    probe_outcomes: List[ProbeOutcome] = []
    active_probes: List[ProbeOutcome] = []

    total_gap_ns = 0
    total_busy_ns = sum(
        bi.duration_ns for busy_list, _ in timelines.values()
        for bi in busy_list
    )
    busy_intervals_all = sorted(
        (bi for _, (busy, _) in timelines.items() for bi in busy),
        key=lambda bi: bi.start_ns,
    )

    for snap in all_snapshots:
        dur = snap.gap_duration_ns
        total_gap_ns += dur

        # Budget check
        if ctx.probe_count >= config.probe_budget_per_second * 100:
            continue

        # Clean completed probes
        active_probes = [p for p in active_probes
                         if p.ended_time_ns > snap.gap_start_ns or not p.ended_time_ns]

        # Get policy decisions for this gap
        decisions = policy_fn(snap, ctx)

        for probe in decisions:
            # Check: is this gap large enough for the probe?
            probe_lat = probe.expected_latency_ns
            if dur < probe_lat:
                # Downgrade or skip
                if probe.probe_type == ProbeType.BANDWIDTH and dur >= PROBE_LATENCY_SAME_NUMA_NS[ProbeType.NORMAL_LATENCY]:
                    probe.probe_type = ProbeType.NORMAL_LATENCY
                    probe_lat = probe.expected_latency_ns
                elif dur < PROBE_LATENCY_SAME_NUMA_NS[ProbeType.TINY_LATENCY]:
                    continue

            if dur < probe_lat:
                continue

            # Check for overlap with any active probe on this path
            active_on_path = [p for p in active_probes
                              if p.probe.path_id == probe.path_id]
            if len(active_on_path) >= config.max_concurrent_probes:
                continue

            # Place probe
            start_t = snap.gap.start_ns + 1000  # small offset
            end_t = start_t + probe_lat

            # Check: does probe fit in gap?
            overlap_busy = 0
            safe = True
            for bi in busy_intervals_all:
                if bi.end_ns <= start_t:
                    continue
                if bi.start_ns >= end_t:
                    break
                # Overlap detected
                ov = min(end_t, bi.end_ns) - max(start_t, bi.start_ns)
                if ov > 0:
                    overlap_busy += ov
                    safe = False

            outcome = ProbeOutcome(
                probe=probe,
                scheduled_time_ns=snap.gap_start_ns,
                started_time_ns=start_t,
                ended_time_ns=end_t,
                safe=safe,
                gap_during_probe_ns=dur,
                busy_overlap_ns=overlap_busy,
                reason="fits" if safe else f"overlap {overlap_busy}ns",
            )
            probe_outcomes.append(outcome)
            active_probes.append(outcome)

    # ---- Compute metrics ----
    total_time_ns = (all_snapshots[-1].gap.end_ns - all_snapshots[0].gap.start_ns) \
        if all_snapshots else 1

    executed = [p for p in probe_outcomes if not p.cancelled]
    safe = [p for p in executed if p.safe]
    unsafe = [p for p in executed if not p.safe]

    total_probing_ns = sum(p.ended_time_ns - p.started_time_ns for p in executed)

    # Per-path breakout
    per_path: Dict[int, dict] = {}
    for pid in sorted(set(p.probe.path_id for p in probe_outcomes)):
        pp = [p for p in probe_outcomes if p.probe.path_id == pid]
        pe = [p for p in pp if not p.cancelled]
        per_path[pid] = {
            "total": len(pp),
            "executed": len(pe),
            "safe": len([p for p in pe if p.safe]),
        }

    return RunMetrics(
        policy=policy_name,
        total_probes_scheduled=len(probe_outcomes),
        total_probes_executed=len(executed),
        safe_probes=len(safe),
        unsafe_probes=len(unsafe),
        cancelled_probes=len([p for p in probe_outcomes if p.cancelled]),
        downgraded_probes=len([p for p in executed if p.downgraded]),
        probe_overlap_ratio=round(
            (sum(p.busy_overlap_ns for p in unsafe) / max(1, total_probing_ns)), 4
        ),
        safe_probing_ratio=round(len(safe) / max(1, len(executed)), 4),
        harmful_probe_count=len(unsafe),
        total_gap_ns=total_gap_ns,
        total_busy_ns=total_busy_ns,
        total_probing_ns=total_probing_ns,
        probing_overhead_pct=round(total_probing_ns / max(1, total_time_ns) * 100, 2),
        per_path_metrics=per_path,
    )


def compare_policies(
    timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]],
    policies: Optional[List[str]] = None,
    config: Optional[ReplayConfig] = None,
) -> Dict[str, RunMetrics]:
    """Run all policies against the same timelines and compare.

    Returns Dict[policy_name] → RunMetrics.
    """
    if policies is None:
        policies = list(POLICY_NAMES)
    results: Dict[str, RunMetrics] = {}
    for name in policies:
        print(f"  Running {name:>22s}...", end=" ", flush=True)
        t0 = time.time()
        if config is not None:
            config.policy = name
        results[name] = replay_trace(timelines, name, config)
        dt = time.time() - t0
        m = results[name]
        print(f"{m.total_probes_executed:5d} probes, "
              f"{m.safe_probing_ratio*100:5.1f}% safe, "
              f"{dt:.2f}s")
    return results
