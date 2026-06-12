#!/usr/bin/env python3
"""
Fast parquet generation — vectorized sliding windows, sampled.
Only top 8 paths, stride 10. ~3K rows per pass.
"""
import json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
PROC_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
PROC_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "code" / "trace_parser"))

from trace_parser.parse_trace import parse_csv, group_by_path
from trace_parser.intervalize import build_timeline

HORIZONS_NS = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000)
MAX_PATHS = 8
SAMPLE_STRIDE = 10
WIN = 50

FEATURE_NAMES = [
    "gap_p10", "gap_p50", "gap_p90", "gap_mean", "gap_std",
    "gap_last", "gap_last5_mean",
    "burst_p50", "burst_p90", "burst_mean", "burst_rate", "burst_last_dur",
    "idle_age_ns",
    "path_id_norm", "direction_code", "cross_numa_flag",
    "stream_id_norm", "stream_pending", "time_since_last_sync",
    "phase_id", "sync_before_flag",
    "cpu_usage_pct", "npu_util_pct", "ebpf_event_rate",
    "drop_rate", "unknown_path_ratio", "async_uncertainty", "timestamp_jitter",
    "hour_of_day", "workload_runtime",
]


def build_pass(pass_name, csv_path):
    print(f"\n{'='*50}\n{pass_name}\n{'='*50}", flush=True)
    t0 = time.time()

    events = parse_csv(str(csv_path))
    print(f"  {len(events)} events, {time.time()-t0:.1f}s", flush=True)
    groups = group_by_path(events)
    print(f"  {len(groups)} paths", flush=True)

    all_rows = []

    for pk, evs in sorted(groups.items(), key=lambda x: -len(x[1]))[:MAX_PATHS]:
        path_id = hash(pk) & 0xFFFF
        busy, gaps = build_timeline(evs, 50_000, 100_000, path_id)
        n = len(gaps)
        if n < WIN:
            continue

        # Pre-compute gap + burst arrays
        gap_arr = np.array([g.duration_ns for g in gaps], dtype=np.float64)
        burst_arr = np.array([b.duration_ns for b in busy if b.duration_ns > 0], dtype=np.float64)

        for i in range(WIN, n, SAMPLE_STRIDE):
            win_gaps = gap_arr[max(0, i - WIN):i]
            # Gap features
            gp = {
                "p10": float(np.percentile(win_gaps, 10)),
                "p50": float(np.percentile(win_gaps, 50)),
                "p90": float(np.percentile(win_gaps, 90)),
                "mean": float(np.mean(win_gaps)),
                "std": float(np.std(win_gaps)) if len(win_gaps) > 1 else 0.0,
                "last": float(win_gaps[-1]),
                "last5": float(np.mean(win_gaps[-5:])) if len(win_gaps) >= 5 else float(np.mean(win_gaps)),
            }
            # Burst features
            n_bi = min(i, len(burst_arr))
            win_bursts = burst_arr[max(0, n_bi - WIN):n_bi]
            if len(win_bursts) > 0:
                bp = {
                    "p50": float(np.percentile(win_bursts, 50)),
                    "p90": float(np.percentile(win_bursts, 90)),
                    "mean": float(np.mean(win_bursts)),
                    "last": float(win_bursts[-1]),
                }
            else:
                bp = {"p50": 0.0, "p90": 0.0, "mean": 0.0, "last": 0.0}

            idle = float(max(0, gaps[i].start_ns - (busy[min(i, len(busy)-1)].end_ns if i < len(busy) else gaps[i-1].start_ns))) if i > 0 else 0.0

            row = {
                "pass": pass_name, "path_id": path_id, "gap_idx": i,
                "gap_start_ns": gaps[i].start_ns, "gap_duration_ns": gaps[i].duration_ns,
                "direction": 2,
                "f_gap_p10": gp["p10"], "f_gap_p50": gp["p50"],
                "f_gap_p90": gp["p90"], "f_gap_mean": gp["mean"],
                "f_gap_std": gp["std"], "f_gap_last": gp["last"],
                "f_gap_last5_mean": gp["last5"],
                "f_burst_p50": bp["p50"], "f_burst_p90": bp["p90"],
                "f_burst_mean": bp["mean"], "f_burst_rate": 0.0,
                "f_burst_last_duration": bp["last"],
                "f_idle_age_ns": idle,
                "f_path_id_norm": float(path_id) / 65536,
                "f_direction_code": 2.0, "f_cross_numa_flag": 0.0,
                "f_stream_id_norm": 0.0, "f_stream_pending": 0.0,
                "f_time_since_last_sync": 0.0,
                "f_phase_id": 0.0, "f_sync_before_flag": 0.0,
                "f_cpu_usage_pct": 50.0, "f_npu_util_pct": 50.0,
                "f_ebpf_event_rate": float(len(gaps) / max(0.001, (gaps[-1].end_ns - gaps[0].start_ns) / 1e9)),
                "f_drop_rate": 0.0, "f_unknown_path_ratio": 0.0,
                "f_async_uncertainty": 0.0, "f_timestamp_jitter": 0.0,
                "f_hour_of_day": 0.0, "f_workload_runtime": 0.0,
            }
            all_rows.append(row)

        print(f"  Path {path_id}: {len(evs)} ev, {n} gaps, from {n//SAMPLE_STRIDE} rows", flush=True)

    df = pd.DataFrame(all_rows)
    print(f"  Total: {len(df)} rows ({time.time()-t0:.1f}s)", flush=True)
    return df


def main():
    df1 = build_pass("pass1", ROOT / "data/raw/trace_pass1_raw.csv")
    df2 = build_pass("pass2", ROOT / "data/raw/trace_pass2_raw.csv")

    df1.to_parquet(str(PROC_DIR / "burst_gap_events.parquet"), index=False)
    df2.to_parquet(str(PROC_DIR / "burst_gap_events_pass2.parquet"), index=False)
    df_all = pd.concat([df1, df2], ignore_index=True)
    df_all.to_parquet(str(PROC_DIR / "burst_gap_events_all.parquet"), index=False)

    print(f"\nDone. Pass1: {len(df1)}, Pass2: {len(df2)}, Total: {len(df_all)}")
    for pct in [10, 50, 90, 99]:
        v = np.percentile(df_all["gap_duration_ns"], pct)
        print(f"  Gap p{pct}: {v/1e3:.0f}µs")


if __name__ == "__main__":
    main()
