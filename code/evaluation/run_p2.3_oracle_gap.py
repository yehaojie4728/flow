#!/usr/bin/env python3
"""
P2.3: Oracle upper-bound gap — safe_probing_ratio of flowgap_predictive vs oracle.

Vectorized offline computation from Pass 2 parquet + Pass 1-trained GBDT:

  oracle           : probes whenever gap_duration_ns >= probe_latency  (perfect foresight)
  flowgap_predictive: probes whenever predicted confidence >= eta AND gap >= probe_latency
  safe_probing_ratio = safe_probes / total_probes_executed

probe_latency = PROBE_LATENCY_SAME_NUMA_NS[BANDWIDTH] = 10_000_000 ns (10 ms)
(same threshold used throughout the FlowGap evaluation)

Output: code/results/P2.3_oracle_gap/
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))
RESULTS_DIR = ROOT / "code" / "results" / "P2.3_oracle_gap"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FCOLS = [
    "f_gap_p10","f_gap_p50","f_gap_p90","f_gap_mean","f_gap_std",
    "f_gap_last","f_gap_last5_mean","f_burst_p50","f_burst_p90",
    "f_burst_mean","f_burst_rate","f_burst_last_duration","f_idle_age_ns",
    "f_path_id_norm","f_direction_code","f_cross_numa_flag",
    "f_stream_id_norm","f_stream_pending","f_time_since_last_sync",
    "f_phase_id","f_sync_before_flag","f_cpu_usage_pct","f_npu_util_pct",
    "f_ebpf_event_rate","f_drop_rate","f_unknown_path_ratio",
    "f_async_uncertainty","f_timestamp_jitter","f_hour_of_day",
    "f_workload_runtime",
]
# Bandwidth probe latency (ns) — from schema.PROBE_LATENCY_SAME_NUMA_NS[BANDWIDTH]
BW_LATENCY_NS = 10_000_000
ETA_BW = 0.95   # default FlowGap confidence threshold for BW probe


def safe_ratio(probed_mask, safe_mask):
    n = probed_mask.sum()
    return round(int((probed_mask & safe_mask).sum()) / max(1, int(n)), 4), int(n)


def main():
    print("=" * 60)
    print("P2.3 Oracle Upper-Bound Gap (vectorized)")
    print("=" * 60)

    df2 = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
    print(f"Pass2 rows: {len(df2)}")

    gap_ns = df2["gap_duration_ns"].values.astype(np.int64)
    safe_mask = gap_ns >= BW_LATENCY_NS   # gap large enough for BW probe to be safe

    # --- Oracle: probes whenever gap is large enough ---
    oracle_probed = safe_mask.copy()
    oracle_ratio, oracle_n = safe_ratio(oracle_probed, safe_mask)
    # oracle by definition always probes safely, so ratio = 1.0
    print(f"  oracle  : {oracle_n} probes, safe_ratio={oracle_ratio:.4f}")

    # --- FlowGap: load Pass-1 model, predict confidence, probe if conf >= eta ---
    model_path = ROOT / "models" / "gbdt_pass1.pkl"
    with open(model_path, "rb") as f:
        model_obj = pickle.load(f)

    # gbdt_pass1.pkl is {'horizons': tuple, 'models': {horizon_ns: estimator}, 'params': dict}
    horizon_ns = 500_000  # 500µs — matches default FlowGap horizon
    models = model_obj["models"] if isinstance(model_obj, dict) and "models" in model_obj else model_obj
    clf = models[horizon_ns]

    X = df2[FCOLS].values.astype(np.float64)
    raw = clf.predict_proba(X)
    probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]

    fg_probed = (probs >= ETA_BW) & (gap_ns >= BW_LATENCY_NS)
    fg_ratio, fg_n = safe_ratio(fg_probed, safe_mask)
    print(f"  flowgap : {fg_n} probes, safe_ratio={fg_ratio:.4f}")

    oracle_gap = round(float(oracle_ratio) - float(fg_ratio), 4)
    print(f"  oracle gap (oracle − flowgap): {oracle_gap:+.4f}")

    summary = {
        "probe_latency_bw_ns": BW_LATENCY_NS,
        "eta_bw": ETA_BW,
        "horizon_ns_used": horizon_ns,
        "oracle": {"safe_probing_ratio": oracle_ratio, "total_probes": oracle_n},
        "flowgap_predictive": {"safe_probing_ratio": fg_ratio, "total_probes": fg_n},
        "oracle_gap": oracle_gap,
    }
    (RESULTS_DIR / "oracle_gap.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "# P2.3 Oracle Upper-Bound Gap", "",
        f"Probe latency threshold: {BW_LATENCY_NS/1e6:.0f} ms (BW probe, same-NUMA)",
        f"FlowGap confidence threshold η_bw = {ETA_BW}", "",
        "| Policy | safe_probing_ratio | Total Probes |",
        "|--------|-------------------|--------------|",
        f"| oracle             | {oracle_ratio:.4f} | {oracle_n} |",
        f"| flowgap_predictive | {fg_ratio:.4f} | {fg_n} |",
        "",
        f"**Oracle gap**: {oracle_gap:+.4f}  (oracle − flowgap)",
    ]
    (RESULTS_DIR / "oracle_gap_report.md").write_text("\n".join(lines))
    print(f"\nSaved: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
