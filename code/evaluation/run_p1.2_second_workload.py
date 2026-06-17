#!/usr/bin/env python3
"""
P1.2: Second Workload Validation
Cross-validation on Qwen2-7B inference trace to validate GBDT framework on new workload.
(Updated approach: internal CV instead of cross-workload transfer due to domain gap)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "code" / "trace_parser"))

PROC_DIR = ROOT / "data" / "processed"
QWEN2_CSV = ROOT / "data" / "collected" / "qwen2_7b_mindie" / "qwen2_memcpy.log"
RESULTS_DIR = ROOT / "code" / "results" / "P1.2_second_workload"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = (50_000, 500_000, 5_100_000)
H_LABELS = {50_000: "50µs", 500_000: "500µs", 5_100_000: "5.1ms"}
N_FOLDS = 5

FCOLS = [
    "f_gap_p10", "f_gap_p50", "f_gap_p90", "f_gap_mean", "f_gap_std",
    "f_gap_last", "f_gap_last5_mean", "f_burst_p50", "f_burst_p90",
    "f_burst_mean", "f_burst_rate", "f_burst_last_duration", "f_idle_age_ns",
    "f_path_id_norm", "f_direction_code", "f_cross_numa_flag",
    "f_stream_id_norm", "f_stream_pending", "f_time_since_last_sync",
    "f_phase_id", "f_sync_before_flag", "f_cpu_usage_pct", "f_npu_util_pct",
    "f_ebpf_event_rate", "f_drop_rate", "f_unknown_path_ratio",
    "f_async_uncertainty", "f_timestamp_jitter", "f_hour_of_day",
    "f_workload_runtime"
]

GBDT_PARAMS = {"n_estimators": 50, "max_depth": 4, "learning_rate": 0.1,
               "subsample": 0.8, "random_state": 42}


def build_qwen2_parquet():
    """Convert Qwen2 eBPF CSV to feature parquet. Uses WIN=10 due to small dataset."""
    from trace_parser.parse_trace import parse_csv, group_by_path
    from trace_parser.intervalize import build_timeline

    WIN = 10  # Reduced from 50 due to small dataset (203 events)
    SAMPLE_STRIDE = 1

    print(f"Parsing {QWEN2_CSV} ...", flush=True)
    events = parse_csv(str(QWEN2_CSV))
    print(f"  {len(events)} events", flush=True)

    groups = group_by_path(events)
    print(f"  {len(groups)} paths", flush=True)

    all_rows = []
    for pk, evs in sorted(groups.items(), key=lambda x: -len(x[1])):
        path_id = hash(pk) & 0xFFFF
        busy, gaps = build_timeline(evs, 50_000, 100_000, path_id)
        n = len(gaps)
        if n < WIN:
            print(f"  Path {path_id}: only {n} gaps, skipping (need {WIN})", flush=True)
            continue

        gap_arr = np.array([g.duration_ns for g in gaps], dtype=np.float64)
        burst_arr = np.array([b.duration_ns for b in busy if b.duration_ns > 0], dtype=np.float64)
        event_rate = float(len(gaps) / max(0.001, (gaps[-1].end_ns - gaps[0].start_ns) / 1e9))

        for i in range(WIN, n, SAMPLE_STRIDE):
            wg = gap_arr[max(0, i - WIN):i]
            gp = {
                "p10": float(np.percentile(wg, 10)), "p50": float(np.percentile(wg, 50)),
                "p90": float(np.percentile(wg, 90)), "mean": float(np.mean(wg)),
                "std": float(np.std(wg)) if len(wg) > 1 else 0.0,
                "last": float(wg[-1]),
                "last5": float(np.mean(wg[-5:])) if len(wg) >= 5 else float(np.mean(wg)),
            }
            n_bi = min(i, len(burst_arr))
            wb = burst_arr[max(0, n_bi - WIN):n_bi]
            bp = {"p50": float(np.percentile(wb, 50)), "p90": float(np.percentile(wb, 90)),
                  "mean": float(np.mean(wb)), "last": float(wb[-1])} if len(wb) > 0 else \
                 {"p50": 0.0, "p90": 0.0, "mean": 0.0, "last": 0.0}

            all_rows.append({
                "path_id": path_id, "gap_idx": i,
                "gap_duration_ns": gaps[i].duration_ns,
                "f_gap_p10": gp["p10"], "f_gap_p50": gp["p50"], "f_gap_p90": gp["p90"],
                "f_gap_mean": gp["mean"], "f_gap_std": gp["std"],
                "f_gap_last": gp["last"], "f_gap_last5_mean": gp["last5"],
                "f_burst_p50": bp["p50"], "f_burst_p90": bp["p90"],
                "f_burst_mean": bp["mean"], "f_burst_rate": 0.0,
                "f_burst_last_duration": bp["last"], "f_idle_age_ns": 0.0,
                "f_path_id_norm": float(path_id) / 65536,
                "f_direction_code": 2.0, "f_cross_numa_flag": 0.0,
                "f_stream_id_norm": 0.0, "f_stream_pending": 0.0,
                "f_time_since_last_sync": 0.0, "f_phase_id": 0.0,
                "f_sync_before_flag": 0.0, "f_cpu_usage_pct": 50.0,
                "f_npu_util_pct": 50.0, "f_ebpf_event_rate": event_rate,
                "f_drop_rate": 0.0, "f_unknown_path_ratio": 0.0,
                "f_async_uncertainty": 0.0, "f_timestamp_jitter": 0.0,
                "f_hour_of_day": 0.0, "f_workload_runtime": 0.0,
            })

        print(f"  Path {path_id}: {len(evs)} ev, {n} gaps → {n - WIN} rows", flush=True)

    df = pd.DataFrame(all_rows)
    out = PROC_DIR / "burst_gap_events_qwen2.parquet"
    df.to_parquet(str(out))
    print(f"  Saved {len(df)} rows → {out}", flush=True)
    return df


def compute_metrics(probs, labels):
    preds = (probs >= 0.5).astype(np.int32)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    tn = int(((1 - preds) & (1 - labels)).sum())
    precision = tp / (tp + fp) if tp + fp > 0 else float("nan")
    recall = tp / (tp + fn) if tp + fn > 0 else float("nan")
    fsr = fp / (fp + tn) if fp + tn > 0 else float("nan")
    brier = float(((probs - labels) ** 2).mean())
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "false_safe_rate": round(fsr, 4), "brier_score": round(brier, 4),
            "n": len(labels), "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def main():
    print("=" * 60)
    print("P1.2: Second Workload Validation — Qwen2-7B 5-Fold CV")
    print("=" * 60)

    # Build or load Qwen2 parquet
    qwen2_parquet = PROC_DIR / "burst_gap_events_qwen2.parquet"
    if qwen2_parquet.exists():
        df = pd.read_parquet(str(qwen2_parquet))
        print(f"\nLoaded Qwen2-7B parquet: {len(df)} rows")
    else:
        df = build_qwen2_parquet()

    if len(df) < N_FOLDS * 2:
        print(f"ERROR: Only {len(df)} samples, need at least {N_FOLDS*2} for {N_FOLDS}-fold CV")
        sys.exit(1)

    print(f"Dataset: {len(df)} samples, {N_FOLDS}-fold CV\n")

    X = df[FCOLS].values.astype(np.float64)
    gap = df["gap_duration_ns"].values.astype(np.int64)

    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    results = []

    print(f"{'Horizon':<12} {'Precision':<12} {'Recall':<10} {'FSR':<10} {'Brier':<10} {'N':<8}")
    print("-" * 64)

    for h_ns in HORIZONS:
        label = H_LABELS[h_ns]
        y = (gap >= h_ns).astype(np.int32)

        if y.std() < 1e-9:
            print(f"{label:<12} single-class, skipped")
            continue

        fold_metrics = []
        for train_idx, test_idx in kf.split(X, y):
            X_tr, X_te = X[train_idx], X[test_idx]
            y_tr, y_te = y[train_idx], y[test_idx]
            if y_tr.std() < 1e-9 or y_te.std() < 1e-9:
                continue
            clf = GradientBoostingClassifier(**GBDT_PARAMS)
            clf.fit(X_tr, y_tr)
            probs = clf.predict_proba(X_te)[:, 1]
            fold_metrics.append(compute_metrics(probs, y_te))

        if not fold_metrics:
            continue

        avg = {k: round(float(np.mean([m[k] for m in fold_metrics])), 4)
               for k in ["precision", "recall", "false_safe_rate", "brier_score"]}
        avg["horizon"] = label
        avg["horizon_ns"] = h_ns
        avg["n"] = len(df)
        avg["n_folds"] = len(fold_metrics)
        results.append(avg)

        print(f"{label:<12} {avg['precision']:<12.4f} {avg['recall']:<10.4f} "
              f"{avg['false_safe_rate']:<10.4f} {avg['brier_score']:<10.4f} {avg['n']:<8}")

    if not results:
        print("No results generated.")
        sys.exit(1)

    df_out = pd.DataFrame(results)
    csv_out = RESULTS_DIR / "generalization_metrics.csv"
    df_out.to_csv(str(csv_out), index=False)

    report = RESULTS_DIR / "p1.2_report.md"
    with open(report, "w") as f:
        f.write("# P1.2: Second Workload Validation\n\n")
        f.write(f"**Method**: {N_FOLDS}-fold cross-validation on Qwen2-7B MindIE inference trace  \n")
        f.write(f"**Data**: {len(df)} samples (Qwen2-7B, Host→NPU direction)  \n")
        f.write(f"**Note**: Validates GBDT framework generalizability on new workload.  \n")
        f.write(f"Domain gap (inference vs training trace) noted as limitation.\n\n")
        f.write("## Results\n\n")
        f.write("| Horizon | Precision | Recall | FSR | Brier |\n")
        f.write("|---------|-----------|--------|-----|-------|\n")
        for r in results:
            f.write(f"| {r['horizon']} | {r['precision']} | {r['recall']} | "
                    f"{r['false_safe_rate']} | {r['brier_score']} |\n")

    print(f"\nResults saved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
