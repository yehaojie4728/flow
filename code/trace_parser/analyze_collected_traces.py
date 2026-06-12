#!/usr/bin/env python3
"""
Analyze FlowGap collected traces (pass1 + pass2) through the trace parser.
Produces per-path busy-idle timelines, gap statistics, safe-window availability.

Output: results/pass1_analysis.json, results/pass2_analysis.json,
        results/combined_report.md
"""

import csv, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_trace import parse_csv, group_by_path
from intervalize import (
    build_timeline, compute_gap_stats, compute_safe_window_availability,
    export_agg_csv, export_gap_csv,
)
from schema import QualityFlag

RESULTS_DIR = "/root/FlowGap-work/FlowGap-paper/results"
DATA_DIR = "/root/FlowGap-work/FlowGap-paper/data/raw"
os.makedirs(RESULTS_DIR, exist_ok=True)

PROBE_DURATIONS = [50_000, 500_000, 5_000_000, 10_000_000]
SAFETY_MARGIN = 100_000
MIN_PROBE = 50_000


def analyze_pass(name: str, csv_path: str) -> dict:
    print(f"\n{'='*60}\nAnalyzing {name}: {csv_path}\n{'='*60}")
    events = parse_csv(csv_path)
    n_total = len(events)
    is_synth = sum(1 for e in events if e.is_synthetic)
    is_real = n_total - is_synth
    print(f"Events: {n_total} total, {is_real} real, {is_synth} synthetic")

    sizes = [e.size_mb for e in events]
    bws = [e.bw_gbps for e in events if e.bw_gbps > 0]
    lats = [e.latency_us for e in events]
    dur_s = (events[-1].ts_exit_ns - events[0].ts_enter_ns) / 1e9 if events else 0
    dirs = {}
    for e in events:
        dirs[e.direction_label] = dirs.get(e.direction_label, 0) + 1

    summary = {
        "total_events": n_total, "real": is_real, "synthetic": is_synth,
        "duration_seconds": round(dur_s, 1), "directions": dirs,
        "size_mb": {"min": round(min(sizes), 1), "max": round(max(sizes), 1)},
        "bw_gbps": {"min": round(min(bws), 1) if bws else 0, "max": round(max(bws), 1) if bws else 0},
        "latency_us": {"min": round(min(lats), 1), "max": round(max(lats), 1)},
    }
    print(f"Duration: {dur_s:.0f}s, dirs: {dirs}")

    # Per-path analysis
    groups = group_by_path(events)
    paths_data = []

    for pk, evs in sorted(groups.items(), key=lambda x: -len(x[1])):
        path_id = hash(pk) & 0xFFFF
        busy, gaps = build_timeline(evs, MIN_PROBE, SAFETY_MARGIN, path_id)
        gstats = compute_gap_stats(gaps)
        avail = compute_safe_window_availability(gaps, PROBE_DURATIONS, SAFETY_MARGIN)
        total_mb = sum(e.size_mb for e in evs)
        dir_label = evs[0].direction_label

        paths_data.append({
            "path_key": str(pk), "path_id": path_id,
            "events": len(evs), "total_mb": round(total_mb, 1),
            "direction": dir_label,
            "busy_intervals": len(busy), "gaps": gstats["count"],
            "gap_p50_us": round(gstats["p50_ns"] / 1000, 1),
            "gap_p90_us": round(gstats["p90_ns"] / 1000, 1),
            "gap_min_us": round(gstats["min_ns"] / 1000, 1),
            "gap_max_us": round(gstats["max_ns"] / 1000, 1),
            "safe_tiny_latency_pct": round(avail[50_000][2] * 100, 1),
            "safe_normal_latency_pct": round(avail[500_000][2] * 100, 1),
            "safe_bandwidth_pct": round(avail[5_000_000][2] * 100, 1),
            "safe_large_bandwidth_pct": round(avail[10_000_000][2] * 100, 1),
        })
        print(f"  {dir_label}: {len(evs)} ev, {total_mb:.0f}MB, "
              f"{gstats['count']} gaps, p50={gstats['p50_ns']/1e3:.0f}us, "
              f"tiny={avail[50000][2]*100:.0f}%, bw={avail[5000000][2]*100:.0f}%")

    return {"summary": summary, "paths": sorted(paths_data, key=lambda x: -x["events"])}


# Run
pass1 = analyze_pass("pass1", os.path.join(DATA_DIR, "trace_pass1_raw.csv"))
pass2 = analyze_pass("pass2", os.path.join(DATA_DIR, "trace_pass2_raw.csv"))

# JSON
with open(os.path.join(RESULTS_DIR, "trace_analysis.json"), "w") as f:
    json.dump({"pass1": pass1, "pass2": pass2}, f, indent=2, default=str)

# Markdown report
with open(os.path.join(RESULTS_DIR, "combined_report.md"), "w") as f:
    f.write("# FlowGap Trace Analysis — Combined Report\n\n")
    f.write(f"**Generated** by `code/trace_parser/analyze_collected_traces.py`  \n")
    f.write(f"**Data source**: GLM-6B finetuning on 8× Ascend 910B  \n\n")

    for name, data in [("Pass 1 (Training Set)", pass1), ("Pass 2 (Validation Set)", pass2)]:
        s = data["summary"]
        f.write(f"## {name}\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Events | {s['total_events']} |\n")
        f.write(f"| Real | {s['real']} |\n")
        f.write(f"| Duration | {s['duration_seconds']:.0f} s |\n")
        f.write(f"| Directions | {s['directions']} |\n")
        f.write(f"| Size | {s['size_mb']['min']:.0f}–{s['size_mb']['max']:.0f} MB |\n")
        f.write(f"| BW | {s['bw_gbps']['min']:.1f}–{s['bw_gbps']['max']:.1f} GB/s |\n")
        f.write(f"| Latency | {s['latency_us']['min']:.0f}–{s['latency_us']['max']:.0f} µs |\n\n")

        f.write(f"### Per-Path Gap Statistics\n\n")
        f.write(f"| Direction | Events | Total MB | Gaps | Busy Int. | Gap p50 | Gap p90 | Tiny-safe | BW-safe |\n")
        f.write(f"|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for p in data["paths"][:15]:
            f.write(f"| {p['direction']} | {p['events']} | {p['total_mb']:.0f} | "
                    f"{p['gaps']} | {p['busy_intervals']} | "
                    f"{p['gap_p50_us']:.0f}µs | {p['gap_p90_us']:.0f}µs | "
                    f"{p['safe_tiny_latency_pct']:.0f}% | {p['safe_bandwidth_pct']:.0f}% |\n")
        f.write("\n")

print(f"\nResults: {RESULTS_DIR}/")
print("Done.")
