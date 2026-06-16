#!/usr/bin/env python3
"""
P1.1 Feature Ablation Study for FlowGap

测试策略：Leave-One-Group-Out
- 每次去掉一组特征，评估预测精度的降幅
- 对比全特征基线
"""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
PROC_DIR = ROOT / "data" / "processed"
RESULTS_DIR = ROOT / "code" / "results" / "P1.1"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 特征分组定义（索引从 0 开始）
FEATURE_GROUPS = {
    "gap_stats": list(range(0, 7)),        # gap_p10 ~ gap_last5_mean
    "burst_stats": list(range(7, 12)),     # burst_p50 ~ burst_last_duration
    "idle_age": [12],                      # idle_age_ns
    "path_identity": list(range(13, 16)),  # path_id_norm, direction, cross_numa_flag
    "stream_features": list(range(16, 19)),# stream_id_norm, stream_pending, time_since_last_sync
    "phase_features": list(range(19, 21)), # phase_id, sync_before_flag
    "resource_features": list(range(21, 24)), # cpu_usage_pct, npu_util_pct, ebpf_event_rate
    "data_quality": list(range(24, 28)),   # drop_rate ~ timestamp_jitter
    "time_features": list(range(28, 30)),  # hour_of_day, workload_runtime
}

HORIZONS = [250_000, 500_000, 1_000_000]  # 重点关注 250µs, 500µs, 1ms
H_LABELS = {250_000: "250µs", 500_000: "500µs", 1_000_000: "1ms"}

GBDT_PARAMS = dict(
    n_estimators=30,
    max_depth=2,
    learning_rate=0.1,
    subsample=0.8,
    random_state=42,
    verbose=0
)

def compute_metrics(probs, labels):
    """计算评估指标"""
    preds = (probs >= 0.5).astype(np.int32)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fsr = fp / (fp + (len(labels) - tp - fp)) if (len(labels) - tp - fp) > 0 else 0.0
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "fsr": round(fsr, 4),
    }

def train_and_eval(X_train, y_train, X_test, y_test, feature_mask=None):
    """训练并评估模型，可选特征mask"""
    if feature_mask is not None:
        X_train = X_train[:, feature_mask]
        X_test = X_test[:, feature_mask]
    
    if y_train.std() < 1e-9:
        # 所有标签相同，返回均值预测
        probs = np.full(len(y_test), float(y_train.mean()))
    else:
        clf = GradientBoostingClassifier(**GBDT_PARAMS)
        clf.fit(X_train, y_train)
        raw = clf.predict_proba(X_test)
        probs = raw[:, 1] if raw.shape[1] == 2 else raw[:, 0]
    
    return compute_metrics(probs, y_test)

print("Loading data...", flush=True)
df_train = pd.read_parquet(str(PROC_DIR / "burst_gap_events.parquet"))
df_test = pd.read_parquet(str(PROC_DIR / "burst_gap_events_pass2.parquet"))

# 特征列
FCOLS = [f"f_gap_p10", f"f_gap_p50", f"f_gap_p90", f"f_gap_mean", f"f_gap_std",
         f"f_gap_last", f"f_gap_last5_mean", f"f_burst_p50", f"f_burst_p90",
         f"f_burst_mean", f"f_burst_rate", f"f_burst_last_duration", f"f_idle_age_ns",
         f"f_path_id_norm", f"f_direction_code", f"f_cross_numa_flag",
         f"f_stream_id_norm", f"f_stream_pending", f"f_time_since_last_sync",
         f"f_phase_id", f"f_sync_before_flag", f"f_cpu_usage_pct", f"f_npu_util_pct",
         f"f_ebpf_event_rate", f"f_drop_rate", f"f_unknown_path_ratio",
         f"f_async_uncertainty", f"f_timestamp_jitter", f"f_hour_of_day",
         f"f_workload_runtime"]

X_train_full = df_train[FCOLS].values.astype(np.float64)
X_test = df_test[FCOLS].values.astype(np.float64)
gap_train_full = df_train["gap_duration_ns"].values
gap_test = df_test["gap_duration_ns"].values

print(f"Train: {len(X_train_full)}, Test: {len(X_test)}", flush=True)

# 下采样训练集（每3个取1个，加速训练）
subsample_idx = slice(None, None, 3)
X_train = X_train_full[subsample_idx]
gap_train = gap_train_full[subsample_idx]
print(f"Subsampled train: {len(X_train)}", flush=True)

results = []

# === 基线：全特征 ===
print("\n=== Baseline: All Features ===", flush=True)
for h in HORIZONS:
    y_train = (gap_train >= h).astype(np.int32)
    y_test = (gap_test >= h).astype(np.int32)
    
    metrics = train_and_eval(X_train, y_train, X_test, y_test)
    metrics["horizon"] = H_LABELS[h]
    metrics["horizon_ns"] = h
    metrics["ablation"] = "baseline"
    metrics["removed_group"] = "none"
    
    results.append(metrics)
    print(f"  {H_LABELS[h]}: precision={metrics['precision']:.4f}, fsr={metrics['fsr']:.4f}", flush=True)

# === 消融实验：逐个去除特征组 ===
print("\n=== Ablation: Leave-One-Group-Out ===", flush=True)
for group_name, group_indices in FEATURE_GROUPS.items():
    print(f"\n--- Removing {group_name} ({len(group_indices)} features) ---", flush=True)
    
    # 构建mask：保留除了当前组之外的所有特征
    all_indices = set(range(30))
    keep_indices = sorted(all_indices - set(group_indices))
    
    for h in HORIZONS:
        y_train = (gap_train >= h).astype(np.int32)
        y_test = (gap_test >= h).astype(np.int32)
        
        metrics = train_and_eval(X_train, y_train, X_test, y_test, feature_mask=keep_indices)
        metrics["horizon"] = H_LABELS[h]
        metrics["horizon_ns"] = h
        metrics["ablation"] = "leave_one_group_out"
        metrics["removed_group"] = group_name
        metrics["n_features_used"] = len(keep_indices)
        
        results.append(metrics)
        print(f"  {H_LABELS[h]}: precision={metrics['precision']:.4f} (Δ={metrics['precision'] - [r for r in results if r['horizon_ns']==h and r['ablation']=='baseline'][0]['precision']:.4f})", flush=True)

# === 保存结果 ===
output_json = RESULTS_DIR / "ablation_study.json"
with open(output_json, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n✓ Saved: {output_json}", flush=True)

# === 生成报告 ===
report_lines = [
    "# P1.1 Feature Ablation Study",
    "",
    "**Method**: Leave-One-Group-Out ablation with GBDT predictor",
    "",
    "**Data**: GLM-6B Pass1 (train) → Pass2 (test)",
    "",
    "## Baseline Performance (All 30 Features)",
    "",
    "| Horizon | Precision | Recall | FSR |",
    "|---------|-----------|--------|-----|",
]

baseline_results = [r for r in results if r["ablation"] == "baseline"]
for r in sorted(baseline_results, key=lambda x: x["horizon_ns"]):
    report_lines.append(f"| {r['horizon']} | {r['precision']:.4f} | {r['recall']:.4f} | {r['fsr']:.4f} |")

report_lines.extend([
    "",
    "## Ablation Results (Precision Drop when Removing Each Group)",
    "",
    "| Removed Group | 250µs | 500µs | 1ms | Avg Δ |",
    "|---------------|-------|-------|-----|-------|",
])

for group_name in FEATURE_GROUPS.keys():
    group_results = [r for r in results if r["removed_group"] == group_name]
    if not group_results:
        continue
    
    deltas = []
    row = [group_name]
    for h_ns in HORIZONS:
        baseline_prec = [r["precision"] for r in baseline_results if r["horizon_ns"] == h_ns][0]
        ablated_prec = [r["precision"] for r in group_results if r["horizon_ns"] == h_ns][0]
        delta = baseline_prec - ablated_prec
        deltas.append(delta)
        row.append(f"{ablated_prec:.4f} ({delta:+.4f})")
    
    avg_delta = np.mean(deltas)
    row.append(f"{avg_delta:+.4f}")
    report_lines.append("| " + " | ".join(row) + " |")

report_lines.extend([
    "",
    "**Interpretation**:",
    "- Positive Δ: removing this group hurts precision (important features)",
    "- Negative Δ: removing this group improves precision (noisy features)",
    "- Near-zero Δ: group has minimal impact",
])

output_md = RESULTS_DIR / "ablation_study.md"
with open(output_md, "w") as f:
    f.write("\n".join(report_lines))
print(f"✓ Report: {output_md}", flush=True)
print("\nDone.")
