#!/usr/bin/env python3
"""P0.1 v2 — 7-policy comparison with meaningful metrics.

Metrics:
  - overhead_pct      = total probe time / total trace window
  - bw_probes         = number of bandwidth probes (128MB)
  - bw_coverage       = bw_probes / total_probes (info density)
  - avg_probe_util    = avg(probe_latency / gap_duration) — gap utilization
  - unsafe_probes     = probes whose latency exceeded gap capacity

Output: code/results/p0.1_v2_probe_coverage/
  - comparison.csv   — per-policy summary
  - comparison.txt   — human-readable table
  - per_policy/      — per-path breakdown per policy

Usage:
    cd /root/FlowGap-work/FlowGap-paper/code
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    PYTHONPATH=.:trace_parser python evaluation/run_p0.1_policy_comparison.py
"""

import csv
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "trace_parser"))

from trace_parser.parse_trace import parse_csv, group_by_path
from trace_parser.intervalize import build_timeline, Gap
from scheduler_replay.schema import (
    PROBE_LATENCY_SAME_NUMA_NS, ProbeType, POLICY_NAMES,
)
from scheduler_replay.policies import (
    GapSnapshot, PolicyContext, make_policy,
)

# ---- Config ----

OUT_DIR = ROOT / "results" / "p0.1_v2_probe_coverage"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PER_DIR = OUT_DIR / "per_policy"
PER_DIR.mkdir(exist_ok=True)

TRACE_PATH = ROOT.parent / "data" / "collected" / "pass2_raw.log"
MODEL_PATH = ROOT.parent / "models" / "gbdt_pass1.pkl"

LAT = PROBE_LATENCY_SAME_NUMA_NS

# ---- Load + build timelines ----

print("=" * 60)
print("P0.1 v2 — 7-Policy Comparison (Coverage + Overhead)")
print(f"  Trace: {TRACE_PATH}")
print(f"  Model: {'found' if MODEL_PATH.exists() else 'missing'}")
print("=" * 60)

t0 = time.time()
events = parse_csv(str(TRACE_PATH))
print(f"\nLoaded {len(events)} events in {time.time()-t0:.1f}s")

print("Building timelines...")
t1 = time.time()
by_path = group_by_path(events)
all_gaps: List[Tuple[int, Gap]] = []
for path_key, path_events in by_path.items():
    pid = hash(path_key) & 0xFFFF
    busy, gaps = build_timeline(path_events, 50_000, 100_000, pid)
    for g in gaps:
        all_gaps.append((pid, g))
all_gaps.sort(key=lambda x: x[1].start_ns)
print(f"  {len(by_path)} paths, {len(all_gaps)} gaps in {time.time()-t1:.1f}s")

# Total trace window (ns) for overhead calculation
trace_window_ns = all_gaps[-1][1].end_ns - all_gaps[0][1].start_ns
print(f"  Trace window: {trace_window_ns / 1e9:.0f}s")

# ---- Evaluate each policy ----

rows: List[Dict] = []

for policy_name in POLICY_NAMES:
    print(f"\n  {policy_name:>22s}...", end=" ", flush=True)

    t2 = time.time()
    ctx = PolicyContext()
    per_path_prev: Dict[int, List[float]] = defaultdict(list)

    # Build policy
    kwargs = {}
    if policy_name == "flowgap_predictive" and MODEL_PATH.exists():
        kwargs["predictor_model_path"] = str(MODEL_PATH)
    policy_fn = make_policy(policy_name, **kwargs)

    # Counters
    total_probes = 0
    bw_probes = 0
    normal_probes = 0
    tiny_probes = 0
    unsafe_probes = 0
    total_overhead_ns = 0
    utilization_sum = 0.0
    skipped = 0

    # Per-path
    per_path: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "bw": 0, "normal": 0, "tiny": 0, "unsafe": 0}
    )

    for pid, gap in all_gaps:
        dur_ns = gap.duration_ns

        # Snapshot
        prev = per_path_prev.get(pid, [])
        snap = GapSnapshot(
            path_id=pid,
            gap=gap,
            previous_gaps=list(prev),
            previous_busy=[],
        )

        decisions = policy_fn(snap, ctx)
        if not decisions:
            skipped += 1
            continue

        for probe in decisions:
            probe_lat = LAT.get(probe.probe_type, 50_000)
            fits = dur_ns >= probe_lat

            total_probes += 1
            total_overhead_ns += probe_lat
            if dur_ns > 0:
                utilization_sum += probe_lat / dur_ns
            if not fits:
                unsafe_probes += 1

            pt = probe.probe_type
            if pt == ProbeType.BANDWIDTH:
                bw_probes += 1
                per_path[pid]["bw"] += 1
            elif pt == ProbeType.NORMAL_LATENCY:
                normal_probes += 1
                per_path[pid]["normal"] += 1
            elif pt == ProbeType.TINY_LATENCY:
                tiny_probes += 1
                per_path[pid]["tiny"] += 1

            per_path[pid]["total"] += 1
            if not fits:
                per_path[pid]["unsafe"] += 1

        # Update per-path gap history
        per_path_prev[pid].append(float(dur_ns))
        per_path_prev[pid] = per_path_prev[pid][-50:]

    dt = time.time() - t2

    # Compute metrics
    overhead_pct = total_overhead_ns / max(1, trace_window_ns) * 100
    unsafe_rate = unsafe_probes / max(1, total_probes) * 100
    bw_ratio = bw_probes / max(1, total_probes) * 100
    avg_util = utilization_sum / max(1, total_probes) * 100
    paths_with_probes = sum(1 for v in per_path.values() if v["total"] > 0)

    row = {
        "policy": policy_name,
        "total_probes": total_probes,
        "bw_probes": bw_probes,
        "normal_probes": normal_probes,
        "tiny_probes": tiny_probes,
        "bw_ratio_pct": round(bw_ratio, 1),
        "overhead_pct": round(overhead_pct, 4),
        "avg_gap_util_pct": round(avg_util, 1),
        "unsafe_probes": unsafe_probes,
        "unsafe_rate_pct": round(unsafe_rate, 1),
        "paths_covered": paths_with_probes,
        "dt_s": round(dt, 1),
    }
    rows.append(row)

    print(f"total={total_probes:6d}  bw={bw_ratio:5.1f}%  "
          f"overhead={overhead_pct:.4f}%  unsafe={unsafe_rate:.1f}%  "
          f"paths={paths_with_probes}  dt={dt:.1f}s")

    # Save per-policy per-path detail
    with open(PER_DIR / f"{policy_name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path_id", "total", "bw", "normal", "tiny", "unsafe"])
        for p, d in sorted(per_path.items()):
            w.writerow([p, d["total"], d["bw"], d["normal"], d["tiny"], d["unsafe"]])


# ---- Print comparison table ----

sep = "-" * 95
print(f"\n{sep}")
header = (f"{'Policy':<24s} {'Probes':>7s} {'BW%':>6s} "
          f"{'Overhead%':>10s} {'Unsafe%':>8s} {'Paths':>6s} {'Time(s)':>8s}")
print(header)
print(sep)
for r in rows:
    print(f"{r['policy']:<24s} {r['total_probes']:7d} "
          f"{r['bw_ratio_pct']:5.1f}% "
          f"{r['overhead_pct']:9.4f}% {r['unsafe_rate_pct']:7.1f}% "
          f"{r['paths_covered']:6d} {r['dt_s']:8.1f}")

# Key comparisons
print(f"\nKey findings:")

# Best BW coverage among non-oracle, non-trivial
real_policies = [r for r in rows if r["policy"] not in ("no_probing", "oracle")]
best_bw = max(real_policies, key=lambda r: r["bw_ratio_pct"])
best_unsafe = min([r for r in real_policies if r["total_probes"] > 100],
                  key=lambda r: r["unsafe_rate_pct"])

print(f"  Best BW coverage:    {best_bw['policy']} ({best_bw['bw_ratio_pct']:.1f}%)")
print(f"  Lowest unsafe rate:  {best_unsafe['policy']} ({best_unsafe['unsafe_rate_pct']:.1f}%)")

# flowgap vs ewma vs threshold
for name in ("flowgap_predictive", "ewma_only", "threshold"):
    r = [x for x in rows if x["policy"] == name]
    if r:
        r = r[0]
        print(f"  {name}: bw={r['bw_ratio_pct']:.1f}%  "
              f"overhead={r['overhead_pct']:.4f}%  unsafe={r['unsafe_rate_pct']:.1f}%")

# ---- Save CSV + TXT ----

csv_path = OUT_DIR / "comparison.csv"
cols = ["policy", "total_probes", "bw_probes", "normal_probes", "tiny_probes",
        "bw_ratio_pct", "overhead_pct", "avg_gap_util_pct",
        "unsafe_probes", "unsafe_rate_pct", "paths_covered", "dt_s"]
with open(csv_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

txt_path = OUT_DIR / "comparison.txt"
with open(txt_path, "w") as f:
    f.write(f"P0.1 v2 — 7-Policy Comparison on Pass 2 Trace\n")
    f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"Events: {len(events)}, Paths: {len(by_path)}, Gaps: {len(all_gaps)}\n")
    f.write(f"Trace window: {trace_window_ns / 1e9:.0f}s\n\n")
    f.write(header + "\n")
    f.write(sep + "\n")
    for r in rows:
        f.write(f"{r['policy']:<24s} {r['total_probes']:7d} "
                f"{r['bw_ratio_pct']:5.1f}% "
                f"{r['overhead_pct']:9.4f}% {r['unsafe_rate_pct']:7.1f}% "
                f"{r['paths_covered']:6d}\n")
    f.write(f"\nKey: BW% = fraction of probes that are bandwidth probes (128 MB)\n")
    f.write(f"      Overhead% = total probe time / trace window\n")
    f.write(f"      Unsafe% = probes whose latency exceeded gap capacity\n")

print(f"\nSaved: {csv_path}")
print(f"Saved: {txt_path}")
print(f"Per-policy data: {PER_DIR}/")
print(f"Old v1 results preserved in: {ROOT / 'results' / 'p0.1_v1_simple_metric'}/")
