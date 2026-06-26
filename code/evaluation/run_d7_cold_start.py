#!/usr/bin/env python3
"""
D7: True Cold-Start — Pass1 first k samples → train → evaluate on Pass2.

Unlike P2.1 (which used Pass2 data for both train and test — warm-up, not cold-start),
this script trains on only the first k samples of Pass1 and tests on all of Pass2.

This is the true cold-start scenario: a new, previously unseen training pass.

Output: code/results/D7_cold_start/
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
RESULTS_DIR = ROOT / "code" / "results" / "D7_cold_start"
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
ALL = list(range(30))
HORIZONS = {
    "250µs": 250_000,
    "500µs": 500_000,
    "1ms": 1_000_000,
}
GBDT_PARAMS = dict(n_estimators=50, max_depth=4, learning_rate=0.1,
                   subsample=0.8, random_state=42)
BUDGETS = [1, 5, 10, 50, 100, 200, 500, 1000, 2000, 5000, 10000]


def metrics(probs, labels):
    preds = (probs >= 0.5).astype(int)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    tn = int(((1 - preds) & (1 - labels)).sum())
    return (
        round(tp / (tp + fp), 4) if tp + fp else 0.0,
        round(fp / (fp + tn), 4) if fp + tn else 0.0,
    )


print("=" * 60)
print("D7: True Cold-Start — Pass1 (k) → train → evaluate on Pass2")
print("=" * 60)

df_pool = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events.parquet"))
df_test = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
print(f"  Pool (Pass1): {len(df_pool)}, Test (Pass2): {len(df_test)}")

# Use first 50% of Pass1 as the pool, sort chronologically (already sorted by parquet order)
pool_size = len(df_pool) // 2
df_pool = df_pool.iloc[:pool_size].reset_index(drop=True)

gap_test = df_test["gap_duration_ns"].values.astype(np.int64)

records = []
for h_label, h_ns in HORIZONS.items():
    y_test = (gap_test >= h_ns).astype(np.int32)
    print(f"\n  Horizon {h_label} | test pos={y_test.sum()}/{len(y_test)}")

    for k in BUDGETS:
        if k > len(df_pool):
            continue
        subset = df_pool.iloc[:k]
        X_tr = subset[FCOLS].values.astype(np.float64)
        y_tr = (subset["gap_duration_ns"].values >= h_ns).astype(np.int32)

        if y_tr.std() < 1e-9:
            probs = np.full(len(y_test), float(y_tr.mean()))
        else:
            clf = GradientBoostingClassifier(**GBDT_PARAMS)
            clf.fit(X_tr, y_tr)
            probs = clf.predict_proba(df_test[FCOLS].values.astype(np.float64))[:, 1]

        prec, fsr = metrics(probs, y_test)
        records.append({"horizon": h_label, "k": k, "precision": prec, "fsr": fsr,
                        "train_pos": int(y_tr.sum()), "train_neg": int((1-y_tr).sum())})
        print(f"    k={k:>5d}: prec={prec:.4f}  FSR={fsr:.4f}  train_pos={y_tr.sum()}")

# Write report
lines = ["# D7: True Cold-Start — Pass1 → Pass2", "",
         "Trains on first k samples of Pass1, evaluates on entire Pass2.",
         "This is the REAL cold-start: predicting on a completely unseen pass.", "",
         "## Result Table", "",
         "| k | 250µs P | 250µs FSR | 500µs P | 500µs FSR | 1ms P | 1ms FSR |",
         "|:--:|:------:|:---------:|:------:|:---------:|:-----:|:-------:|"]
for k in BUDGETS:
    row = f"| {k}"
    for h_label in HORIZONS:
        for r in records:
            if r["horizon"] == h_label and r["k"] == k:
                row += f" | {r['precision']:.4f} | {r['fsr']:.4f}"
                break
    lines.append(f"{row} |")

lines += ["", "## Key Finding", "",
          "- True cold-start requires more samples than in-pass warm-up (P2.1)",
          "- How many Pass1 samples needed to reach 0.95+ precision on Pass2?",
          "- This determines the minimum training trace length before FlowGap can be deployed"]

(RESULTS_DIR / "report.md").write_text("\n".join(lines))
print(f"\nSaved: {RESULTS_DIR / 'report.md'}")
print("Done.")
