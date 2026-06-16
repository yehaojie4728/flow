#!/usr/bin/env python3
"""
P2.2: Online drift analysis — does prediction quality degrade over time?

Train GBDT on Pass 1, predict on Pass 2. Split Pass 2 chronologically into
deciles and report precision / FSR per decile. Explicitly compare the first
80% vs the last 20% of Pass 2 to quantify temporal drift.

Output: code/results/P2.2_drift/
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))
RESULTS_DIR = ROOT / "code" / "results" / "P2.2_drift"
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
HORIZONS = {"250µs": 250_000, "500µs": 500_000, "1ms": 1_000_000}
GBDT_PARAMS = dict(n_estimators=50, max_depth=4, learning_rate=0.1,
                   subsample=0.8, random_state=42)


def metrics(probs, labels):
    preds = (probs >= 0.5).astype(int)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    tn = int(((1 - preds) & (1 - labels)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    fsr = fp / (fp + tn) if fp + tn else 0.0
    return round(precision, 4), round(fsr, 4)


def main():
    print("=" * 60)
    print("P2.2 Online Drift Analysis (train Pass1 -> test Pass2 over time)")
    print("=" * 60)

    df1 = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events.parquet"))
    df2 = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
    print(f"Pass1 train: {len(df1)}  Pass2 test: {len(df2)}")

    X_train = df1[FCOLS].values.astype(np.float64)
    gap_train = df1["gap_duration_ns"].values.astype(np.int64)
    X_test = df2[FCOLS].values.astype(np.float64)
    gap_test = df2["gap_duration_ns"].values.astype(np.int64)

    n = len(df2)
    decile_edges = [int(n * i / 10) for i in range(11)]
    split_80 = int(n * 0.8)

    decile_records = []
    split_records = []

    for h_label, h_ns in HORIZONS.items():
        y_train = (gap_train >= h_ns).astype(np.int32)
        y_test = (gap_test >= h_ns).astype(np.int32)

        if y_train.std() < 1e-9:
            probs = np.full(len(y_test), float(y_train.mean()))
        else:
            clf = GradientBoostingClassifier(**GBDT_PARAMS)
            clf.fit(X_train, y_train)
            raw = clf.predict_proba(X_test)
            probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]

        print(f"\n  Horizon {h_label}")
        # Per-decile
        for d in range(10):
            lo, hi = decile_edges[d], decile_edges[d + 1]
            if hi <= lo:
                continue
            prec, fsr = metrics(probs[lo:hi], y_test[lo:hi])
            decile_records.append({"horizon": h_label, "decile": d + 1,
                                   "precision": prec, "fsr": fsr,
                                   "n": int(hi - lo)})
            print(f"    decile {d+1:>2}: precision={prec:.4f} FSR={fsr:.4f}")

        # First 80% vs last 20%
        p_early, f_early = metrics(probs[:split_80], y_test[:split_80])
        p_late, f_late = metrics(probs[split_80:], y_test[split_80:])
        split_records.append({"horizon": h_label,
                              "precision_first80": p_early, "fsr_first80": f_early,
                              "precision_last20": p_late, "fsr_last20": f_late,
                              "precision_drift": round(p_late - p_early, 4),
                              "fsr_drift": round(f_late - f_early, 4)})
        print(f"    first80%: prec={p_early:.4f} FSR={f_early:.4f} | "
              f"last20%: prec={p_late:.4f} FSR={f_late:.4f} | "
              f"Δprec={p_late - p_early:+.4f}")

    pd.DataFrame(decile_records).to_csv(RESULTS_DIR / "drift_deciles.csv", index=False)
    pd.DataFrame(split_records).to_csv(RESULTS_DIR / "drift_split.csv", index=False)

    lines = ["# P2.2 Online Drift Analysis", "",
             "Train on Pass 1, predict Pass 2. Pass 2 ordered chronologically.", "",
             "## First 80% vs Last 20%", "",
             "| Horizon | Prec (first80) | Prec (last20) | ΔPrec | FSR (first80) | FSR (last20) | ΔFSR |",
             "|---------|---------------|---------------|-------|---------------|--------------|------|"]
    for r in split_records:
        lines.append(f"| {r['horizon']} | {r['precision_first80']:.4f} | "
                     f"{r['precision_last20']:.4f} | {r['precision_drift']:+.4f} | "
                     f"{r['fsr_first80']:.4f} | {r['fsr_last20']:.4f} | {r['fsr_drift']:+.4f} |")
    lines += ["", "## Per-decile precision", ""]
    for h_label in HORIZONS:
        lines += [f"### {h_label}", "", "| Decile | Precision | FSR |", "|--------|-----------|-----|"]
        for r in decile_records:
            if r["horizon"] == h_label:
                lines.append(f"| {r['decile']} | {r['precision']:.4f} | {r['fsr']:.4f} |")
        lines.append("")

    (RESULTS_DIR / "drift_report.md").write_text("\n".join(lines))
    print(f"\nSaved: {RESULTS_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
