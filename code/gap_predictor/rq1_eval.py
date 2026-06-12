#!/usr/bin/env python3
"""RQ1 eval — aggressively optimized for sandbox runtime limits."""
import json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
PROC_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000)
H_LABELS = {10_000: "10µs", 25_000: "25µs", 50_000: "50µs", 100_000: "100µs",
            250_000: "250µs", 500_000: "500µs", 1_000_000: "1ms", 2_000_000: "2ms"}

FCOLS = [f"f_gap_p10","f_gap_p50","f_gap_p90","f_gap_mean","f_gap_std",
    "f_gap_last","f_gap_last5_mean","f_burst_p50","f_burst_p90",
    "f_burst_mean","f_burst_rate","f_burst_last_duration","f_idle_age_ns",
    "f_path_id_norm","f_direction_code","f_cross_numa_flag",
    "f_stream_id_norm","f_stream_pending","f_time_since_last_sync",
    "f_phase_id","f_sync_before_flag","f_cpu_usage_pct","f_npu_util_pct",
    "f_ebpf_event_rate","f_drop_rate","f_unknown_path_ratio",
    "f_async_uncertainty","f_timestamp_jitter","f_hour_of_day",
    "f_workload_runtime"]

GBDT_PARAMS = dict(n_estimators=30, max_depth=2, learning_rate=0.1,
                   subsample=0.8, random_state=42, verbose=0)


def mets(probs, labels):
    preds = (probs >= 0.5).astype(np.int32)
    tp = int((preds & labels).sum())
    fp = int((preds & (1-labels)).sum())
    fn = int(((1-preds) & labels).sum())
    tn = int(((1-preds) & (1-labels)).sum())
    n = len(labels)
    return {
        "precision": round(tp/(tp+fp),4) if tp+fp>0 else 0,
        "recall": round(tp/(tp+fn),4) if tp+fn>0 else 0,
        "false_safe_rate": round(fp/(fp+tn),4) if fp+tn>0 else 0,
        "brier_score": round(float(((probs-labels)**2).mean()),4),
        "n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


print("Loading data...", flush=True)
df1 = pd.read_parquet(str(PROC_DIR / "burst_gap_events.parquet"))
df2 = pd.read_parquet(str(PROC_DIR / "burst_gap_events_pass2.parquet"))
print(f"Train: {len(df1)}, Test: {len(df2)}", flush=True)

gap1 = df1["gap_duration_ns"].values.astype(np.int64)
gap2 = df2["gap_duration_ns"].values.astype(np.int64)
X1 = df1[FCOLS].values.astype(np.float64)
X2 = df2[FCOLS].values.astype(np.float64)

print(f"Gap range train: {gap1.min()/1e3:.0f}µs–{gap1.max()/1e6:.1f}ms", flush=True)
print(f"Gap range test:  {gap2.min()/1e3:.0f}µs–{gap2.max()/1e6:.1f}ms", flush=True)

# Try sampling fewer data points for GBDT (take every 3rd point)
sub = slice(None, None, 3)
X1s, gap1s = X1[sub], gap1[sub]
print(f"Subsampled train: {len(X1s)} for GBDT", flush=True)

# ===== EWMA =====
print("\n--- EWMA ---", flush=True)
ewma_out = []
for h in HORIZONS:
    p = (gap1 >= h).mean()
    probs = np.full(len(gap2), p)
    lbl = (gap2 >= h).astype(np.int32)
    m = mets(probs, lbl)
    m["horizon_ns"] = h; m["horizon_label"] = H_LABELS[h]
    ewma_out.append(m)
    print(f"  {H_LABELS[h]:>6s}: prec={m['precision']:.3f} FSR={m['false_safe_rate']:.3f}", flush=True)

# ===== GBDT =====
print("\n--- GBDT ---", flush=True)
gbdt_out = []
for h in HORIZONS:
    y1s = (gap1s >= h).astype(np.int32)
    lbl2 = (gap2 >= h).astype(np.int32)
    if y1s.std() < 1e-9:
        probs = np.full(len(gap2), float(y1s.mean()))
    else:
        t0 = time.time()
        clf = GradientBoostingClassifier(**GBDT_PARAMS)
        clf.fit(X1s, y1s)
        raw = clf.predict_proba(X2)
        probs = raw[:,1] if raw.shape[1]==2 else raw[:,0]
        dt = time.time() - t0
        print(f"  {H_LABELS[h]:>6s}: fit={dt:.1f}s", flush=True)
    m = mets(probs, lbl2)
    m["horizon_ns"] = h; m["horizon_label"] = H_LABELS[h]
    gbdt_out.append(m)
    print(f"  {H_LABELS[h]:>6s}: prec={m['precision']:.3f} FSR={m['false_safe_rate']:.3f} Brier={m['brier_score']:.4f}", flush=True)

# ===== Cold start =====
print("\n--- Cold Start (50µs) ---", flush=True)
cs_out = []
for frac in [0.02, 0.05, 0.1, 0.3, 0.5, 1.0]:
    n = max(30, int(len(X1s)*frac))
    ys = (gap1s[:n] >= 50_000).astype(np.int32)
    lbl2 = (gap2 >= 50_000).astype(np.int32)
    if ys.std() < 1e-9:
        probs = np.full(len(gap2), float(ys.mean()))
    else:
        clf = GradientBoostingClassifier(**GBDT_PARAMS)
        clf.fit(X1s[:n], ys)
        raw = clf.predict_proba(X2)
        probs = raw[:,1] if raw.shape[1]==2 else raw[:,0]
    m = mets(probs, lbl2)
    cs_out.append({"frac": frac, "n": n, "precision50": m["precision"], "fsr50": m["false_safe_rate"]})
    print(f"  {frac*100:.0f}% ({n}): prec={m['precision']:.3f} FSR={m['false_safe_rate']:.3f}", flush=True)

# ===== Save =====
result = {"ewma": ewma_out, "gbdt": gbdt_out, "cold_start": cs_out}
with open(RESULTS_DIR / "rq1_predictability.json", "w") as f:
    json.dump(result, f, indent=2)
print(f"\nJSON: {RESULTS_DIR}/rq1_predictability.json", flush=True)

# ===== Report =====
r = ["# RQ1: FlowGap Traffic Predictability", "",
     "**Data**: GLM-6B finetuning, 8× Ascend 910B | Train: Pass1 | Test: Pass2", "",
     "**Method**: Per-horizon GBDT (30 trees, depth=2) with EWMA baseline.", "",
     "## EWMA Baseline", "",
     "| Horizon | Precision | Recall | FSR | Brier |", "|---|---:|---:|---:|---:|"]
for m in ewma_out:
    r.append(f"| {m['horizon_label']} | {m['precision']:.4f} | {m['recall']:.4f} | {m['false_safe_rate']:.4f} | {m['brier_score']:.4f} |")
r += ["", "## GBDT Predictor", "",
      "| Horizon | Precision | Recall | FSR | Brier |", "|---|---:|---:|---:|---:|"]
for m in gbdt_out:
    r.append(f"| {m['horizon_label']} | {m['precision']:.4f} | {m['recall']:.4f} | {m['false_safe_rate']:.4f} | {m['brier_score']:.4f} |")
r += ["", "## Cold Start (50µs horizon)", "",
      "| Data % | Samples | Precision | FSR |", "|---|---:|---:|---:|"]
for c in cs_out:
    r.append(f"| {c['frac']*100:.0f}% | {c['n']} | {c['precision50']:.4f} | {c['fsr50']:.4f} |")

with open(RESULTS_DIR / "rq1_predictability.md", "w") as f:
    f.write("\n".join(r))
print(f"Report: {RESULTS_DIR}/rq1_predictability.md")
print("Done.")
