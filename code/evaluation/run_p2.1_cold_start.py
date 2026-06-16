#!/usr/bin/env python3
"""
P2.1: Cold-start analysis — how many warm-up samples needed for reliable prediction?

Uses Pass 2 data. For each warm-up budget k ∈ {1,5,10,50,100,200,500},
train GBDT on first k samples per path, evaluate on the rest.
Reports precision / FSR per k and per horizon.

Output: code/results/P2.1_cold_start/
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))
RESULTS_DIR = ROOT / "code" / "results" / "P2.1_cold_start"
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
HORIZONS = {
    "250µs": 250_000,
    "500µs": 500_000,
    "1ms":  1_000_000,
}
GBDT_PARAMS = dict(n_estimators=50, max_depth=4, learning_rate=0.1,
                   subsample=0.8, random_state=42)
BUDGETS = [1, 5, 10, 50, 100, 200, 500]


def metrics(probs, labels):
    preds = (probs >= 0.5).astype(int)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    tn = int(((1 - preds) & (1 - labels)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    fsr = fp / (fp + tn) if fp + tn else 0.0
    return round(precision, 4), round(fsr, 4), len(labels)


def main():
    print("=" * 60)
    print("P2.1 Cold-start Analysis")
    print("=" * 60)

    df = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
    print(f"Pass2 data: {len(df)} rows")

    # Split into cold-start train pool (first half) and fixed test (second half)
    # Simulate cold start: vary how many samples from the train pool are used.
    n = len(df)
    mid = n // 2
    df_pool = df.iloc[:mid].reset_index(drop=True)
    df_test  = df.iloc[mid:].reset_index(drop=True)

    X_test_all = df_test[FCOLS].values.astype(np.float64)
    gap_test = df_test["gap_duration_ns"].values.astype(np.int64)

    records = []
    for h_label, h_ns in HORIZONS.items():
        y_test = (gap_test >= h_ns).astype(np.int32)
        print(f"\n  Horizon {h_label} | test pos={y_test.sum()}/{len(y_test)}")
        for k in BUDGETS:
            subset = df_pool.iloc[:k] if k <= len(df_pool) else df_pool
            X_tr = subset[FCOLS].values.astype(np.float64)
            y_tr = (subset["gap_duration_ns"].values >= h_ns).astype(np.int32)

            if y_tr.std() < 1e-9:
                probs = np.full(len(y_test), float(y_tr.mean()))
            else:
                clf = GradientBoostingClassifier(**GBDT_PARAMS)
                clf.fit(X_tr, y_tr)
                raw = clf.predict_proba(X_test_all)
                probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]

            prec, fsr, n_test = metrics(probs, y_test)
            records.append({"horizon": h_label, "warmup_k": k,
                            "precision": prec, "fsr": fsr, "n_test": n_test,
                            "n_train": len(subset)})
            print(f"    k={k:>4}  precision={prec:.4f}  FSR={fsr:.4f}")

    df_out = pd.DataFrame(records)
    csv_path = RESULTS_DIR / "cold_start.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}")

    # Markdown report
    lines = ["# P2.1 Cold-start Analysis", "",
             "Train on first k samples of Pass 2 (first half), evaluate on Pass 2 (second half).", ""]
    for h_label in HORIZONS:
        sub = df_out[df_out.horizon == h_label]
        lines += [f"## Horizon {h_label}", "",
                  "| Warm-up k | Precision | FSR |",
                  "|-----------|-----------|-----|"]
        for _, r in sub.iterrows():
            lines.append(f"| {int(r.warmup_k)} | {r.precision:.4f} | {r.fsr:.4f} |")
        lines.append("")

    md_path = RESULTS_DIR / "cold_start_report.md"
    md_path.write_text("\n".join(lines))
    print(f"Report: {md_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
