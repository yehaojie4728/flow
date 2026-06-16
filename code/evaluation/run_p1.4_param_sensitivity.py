#!/usr/bin/env python3
"""P1.4 Parameter Sensitivity: sweep eta_bw threshold on FlowGap predictor."""
import csv, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path(__file__).resolve().parent.parent
PROC_DIR = ROOT.parent / "data" / "processed"
RESULTS_DIR = ROOT / "results" / "P1.4_param_sensitivity"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

LAT_BW, LAT_NORMAL, LAT_TINY = 5_000_000, 100_000, 50_000

FCOLS = ["f_gap_p10","f_gap_p50","f_gap_p90","f_gap_mean","f_gap_std",
         "f_gap_last","f_gap_last5_mean","f_burst_p50","f_burst_p90",
         "f_burst_mean","f_burst_rate","f_burst_last_duration","f_idle_age_ns",
         "f_path_id_norm","f_direction_code","f_cross_numa_flag",
         "f_stream_id_norm","f_stream_pending","f_time_since_last_sync",
         "f_phase_id","f_sync_before_flag","f_cpu_usage_pct","f_npu_util_pct",
         "f_ebpf_event_rate","f_drop_rate","f_unknown_path_ratio",
         "f_async_uncertainty","f_timestamp_jitter","f_hour_of_day","f_workload_runtime"]

print("Loading data...", flush=True)
df1 = pd.read_parquet(str(PROC_DIR / "burst_gap_events.parquet"))
df2 = pd.read_parquet(str(PROC_DIR / "burst_gap_events_pass2.parquet"))
X1 = df1[FCOLS].values.astype(np.float64)[::3]
gap1 = df1["gap_duration_ns"].values[::3]
X2 = df2[FCOLS].values.astype(np.float64)
gap2 = df2["gap_duration_ns"].values
print(f"  Train: {len(X1)}, Test: {len(X2)}", flush=True)

# Train GBDT at 500µs horizon
y1 = (gap1 >= 500_000).astype(np.int32)
clf = GradientBoostingClassifier(n_estimators=30, max_depth=2, learning_rate=0.1,
                                  subsample=0.8, random_state=42)
clf.fit(X1, y1)
raw = clf.predict_proba(X2)
probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]
lbl = (gap2 >= 500_000)
print(f"  GBDT trained. Positive rate: {lbl.mean():.3f}", flush=True)

# Sweep eta_bw
ETA_VALUES = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.99]
print("\n=== Sweep eta_bw ===", flush=True)
results = []
for eta_bw in ETA_VALUES:
    eta_normal = max(0.50, eta_bw - 0.05)
    probe_lat = np.where(probs >= eta_bw, LAT_BW,
                np.where(probs >= eta_normal, LAT_NORMAL, LAT_TINY))
    fits = gap2 >= probe_lat
    bw_mask = probs >= eta_bw
    tp = int((bw_mask & lbl).sum())
    fp = int((bw_mask & ~lbl).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    r = {
        "eta_bw": eta_bw,
        "eta_normal": round(eta_normal, 2),
        "bw_probes": int(bw_mask.sum()),
        "precision_500us": round(precision, 4),
        "safe_ratio": round(float(fits.sum()) / len(fits), 4),
        "unsafe_count": int((~fits).sum()),
    }
    results.append(r)
    print(f"  η={eta_bw:.2f}: bw_probes={r['bw_probes']:5d}  precision={r['precision_500us']:.4f}  safe_ratio={r['safe_ratio']:.4f}", flush=True)

# Save
with open(RESULTS_DIR / "param_sensitivity.json", "w") as f:
    json.dump(results, f, indent=2)
with open(RESULTS_DIR / "eta_sweep.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader(); w.writerows(results)

lines = [
    "# P1.4 Parameter Sensitivity: Confidence Threshold η",
    "", "**Data**: Pass1 (train) → Pass2 (test) | GBDT horizon=500µs", "",
    "| η_bw | η_normal | BW Probes | Precision@500µs | Safe Ratio |",
    "|------|----------|-----------|-----------------|------------|",
]
for r in results:
    lines.append(f"| {r['eta_bw']:.2f} | {r['eta_normal']:.2f} | {r['bw_probes']} | {r['precision_500us']:.4f} | {r['safe_ratio']:.4f} |")
lines += ["", "Higher η → fewer BW probes but higher precision; safe_ratio stable as small probes always fit."]

with open(RESULTS_DIR / "param_sensitivity.md", "w") as f:
    f.write("\n".join(lines))

print(f"\nSaved: {RESULTS_DIR}/")
print("Done.")
