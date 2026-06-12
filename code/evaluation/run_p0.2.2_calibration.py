#!/usr/bin/env python3
"""
P0.2.2: Calibration evaluation — ECE + Brier + Reliability diagram

Output: results/p0.2.2_calibration/
  - calibration_metrics.csv
  - reliability_curve_data.csv
  - calibration_report.txt
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
sys.path.insert(0, str(ROOT / "code"))

PROC_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "code" / "results" / "p0.2.2_calibration"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = (50_000, 500_000, 5_100_000)
H_LABELS = {50_000: "50µs(TINY)", 500_000: "500µs(NORMAL)", 5_100_000: "5.1ms(BW)"}

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

GBDT_PARAMS = {
    "n_estimators": 50,
    "max_depth": 4,
    "learning_rate": 0.1,
    "subsample": 0.8,
    "random_state": 42,
    "verbose": 0
}


def compute_ece(probs, labels, n_bins=10):
    """Compute Expected Calibration Error."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_lowers = bin_boundaries[:-1]
    bin_uppers = bin_boundaries[1:]
    
    ece = 0.0
    bin_data = []
    
    for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
        in_bin = (probs > bin_lower) & (probs <= bin_upper)
        prop_in_bin = in_bin.mean()
        
        if prop_in_bin > 0:
            accuracy_in_bin = labels[in_bin].mean()
            avg_confidence_in_bin = probs[in_bin].mean()
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
            
            bin_data.append({
                "bin_lower": bin_lower,
                "bin_upper": bin_upper,
                "confidence": avg_confidence_in_bin,
                "accuracy": accuracy_in_bin,
                "count": int(in_bin.sum()),
                "proportion": prop_in_bin
            })
        else:
            bin_data.append({
                "bin_lower": bin_lower,
                "bin_upper": bin_upper,
                "confidence": (bin_lower + bin_upper) / 2,
                "accuracy": 0.0,
                "count": 0,
                "proportion": 0.0
            })
    
    return ece, bin_data


def compute_brier_score(probs, labels):
    """Compute Brier score."""
    return float(((probs - labels) ** 2).mean())


def main():
    print("=" * 60)
    print("P0.2.2: Calibration Evaluation")
    print("=" * 60)

    p1 = PROC_DIR / "burst_gap_events.parquet"
    p2 = PROC_DIR / "burst_gap_events_pass2.parquet"

    print(f"\nLoading training data: {p1.name}")
    df1 = pd.read_parquet(str(p1))
    print(f"  {len(df1)} rows")

    print(f"\nLoading test data: {p2.name}")
    df2 = pd.read_parquet(str(p2))
    print(f"  {len(df2)} rows")

    X_train = df1[FCOLS].values.astype(np.float64)
    gap_train = df1["gap_duration_ns"].values.astype(np.int64)

    X_test = df2[FCOLS].values.astype(np.float64)
    gap_test = df2["gap_duration_ns"].values.astype(np.int64)

    calibration_metrics = []
    all_reliability_data = []

    print(f"\n{'Horizon':<15} {'ECE':<12} {'Brier':<12} {'Avg Conf':<12} {'Avg Acc':<12}")
    print("-" * 65)

    for h_ns in HORIZONS:
        h_label = H_LABELS[h_ns]

        y_train = (gap_train >= h_ns).astype(np.int32)
        y_test = (gap_test >= h_ns).astype(np.int32)

        if y_train.std() < 1e-9:
            probs = np.full(len(y_test), float(y_train.mean()))
        else:
            clf = GradientBoostingClassifier(**GBDT_PARAMS)
            clf.fit(X_train, y_train)
            raw = clf.predict_proba(X_test)
            probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]

        ece, bin_data = compute_ece(probs, y_test, n_bins=10)
        brier = compute_brier_score(probs, y_test)
        avg_confidence = float(probs.mean())
        avg_accuracy = float(y_test.mean())

        calibration_metrics.append({
            "horizon_ns": h_ns,
            "horizon_label": h_label,
            "ece": round(ece, 4),
            "brier_score": round(brier, 4),
            "avg_confidence": round(avg_confidence, 4),
            "avg_accuracy": round(avg_accuracy, 4)
        })

        for bin_info in bin_data:
            bin_info["horizon_ns"] = h_ns
            bin_info["horizon_label"] = h_label
            all_reliability_data.append(bin_info)

        print(f"{h_label:<15} {ece:<12.4f} {brier:<12.4f} {avg_confidence:<12.4f} {avg_accuracy:<12.4f}")

    csv_path = RESULTS_DIR / "calibration_metrics.csv"
    pd.DataFrame(calibration_metrics).to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}")

    curve_path = RESULTS_DIR / "reliability_curve_data.csv"
    pd.DataFrame(all_reliability_data).to_csv(curve_path, index=False)
    print(f"Saved: {curve_path}")

    lines = [
        "# P0.2.2: Calibration Evaluation",
        "",
        "**Objective**: Evaluate the reliability of GBDT probability predictions.",
        "",
        "**Training**: Pass 1 | **Test**: Pass 2",
        "",
        "## Calibration Metrics",
        "",
        "| Horizon | ECE | Brier Score | Avg Confidence | Avg Accuracy |",
        "|---------|-----|-------------|----------------|--------------|",
    ]

    for m in calibration_metrics:
        lines.append(
            f"| {m['horizon_label']} | {m['ece']:.4f} | {m['brier_score']:.4f} | "
            f"{m['avg_confidence']:.4f} | {m['avg_accuracy']:.4f} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "- **ECE**: 预测概率与实际准确率的平均偏差 (越低越好,<0.05 为良好校准)",
        "- **Brier Score**: 概率预测的均方误差 (越低越好)",
        "- **Avg Confidence**: 模型预测的平均概率",
        "- **Avg Accuracy**: 实际正样本的比例",
        "",
        "**理想状态**: Avg Confidence ≈ Avg Accuracy",
    ])

    report_path = RESULTS_DIR / "calibration_report.txt"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved: {report_path}")

    print("\n" + "=" * 60)
    print("P0.2.2 Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
