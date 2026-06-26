#!/usr/bin/env python3
"""
D5: ML baseline comparison — LogisticRegression vs GBDT.

If gap_stats dominates (LOO + forward ablation both show it), a simple
linear model (LR) should approach GBDT performance. This validates or
refutes the claim that GBDT's complexity is necessary.

Output: code/results/D5_ml_baselines/
"""

import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
RESULTS_DIR = ROOT / "code" / "results" / "D5_ml_baselines"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = {
    "250µs": 250_000,
    "500µs (NORMAL)": 500_000,
    "1ms": 1_000_000,
    "5.1ms (BW)": 5_100_000,
}

GBDT_PARAMS = dict(n_estimators=50, max_depth=4, learning_rate=0.1,
                   subsample=0.8, random_state=42)
LR_PARAMS = dict(max_iter=1000, random_state=42, C=1.0, solver='lbfgs')


def compute_metrics(probs, labels):
    preds = (probs >= 0.5).astype(np.int32)
    tp = int((preds & labels).sum())
    fp = int((preds & (1 - labels)).sum())
    fn = int(((1 - preds) & labels).sum())
    tn = int(((1 - preds) & (1 - labels)).sum())
    return {
        "precision": round(tp / (tp + fp), 4) if tp + fp else 0.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 0.0,
        "fsr": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "brier": round(np.mean((probs - labels) ** 2), 4),
    }


print("=" * 60)
print("D5: ML Baseline — LogisticRegression vs GBDT")
print("=" * 60)

df_train = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events.parquet"))
df_test = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
print(f"Train: {len(df_train)}, Test: {len(df_test)}")

FCOLS = [c for c in df_train.columns if c.startswith("f_")]
X_train = df_train[FCOLS].values.astype(np.float64)
X_test = df_test[FCOLS].values.astype(np.float64)
gap_train = df_train["gap_duration_ns"].values.astype(np.int64)
gap_test = df_test["gap_duration_ns"].values.astype(np.int64)

# EWMA baseline
def ewma_predict(gap_vals, threshold):
    if len(gap_vals) == 0:
        return np.zeros(len(gap_test))
    mean = np.mean(gap_vals)
    return np.full(len(gap_test), float(mean >= threshold))

print("\nTraining EWMA...")
ewma_results = {}
for h_label, h_ns in HORIZONS.items():
    y_te = (gap_test >= h_ns).astype(np.int32)
    probs = ewma_predict(gap_train, h_ns)
    ewma_results[h_label] = compute_metrics(probs, y_te)

print("Training GBDT...")
gbdt_results = {}
for h_label, h_ns in HORIZONS.items():
    y_tr = (gap_train >= h_ns).astype(np.int32)
    y_te = (gap_test >= h_ns).astype(np.int32)
    clf = GradientBoostingClassifier(**GBDT_PARAMS)
    clf.fit(X_train, y_tr)
    probs = clf.predict_proba(X_test)[:, 1]
    gbdt_results[h_label] = compute_metrics(probs, y_te)

print("Training LogisticRegression...")
lr_results = {}
for h_label, h_ns in HORIZONS.items():
    y_tr = (gap_train >= h_ns).astype(np.int32)
    y_te = (gap_test >= h_ns).astype(np.int32)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(**LR_PARAMS))
    pipe.fit(X_train, y_tr)
    probs = pipe.predict_proba(X_test)[:, 1]
    lr_results[h_label] = compute_metrics(probs, y_te)

# Write report
lines = ["# D5: ML Baseline Comparison", "",
         "Compares EWMA, LogisticRegression, and GBDT across all 6 horizons.", "",
         "## Result Table", "",
         "| Horizon | Model | Precision | Recall | FSR | Brier |",
         "|---------|-------|:---------:|:------:|:---:|:-----:|"]
for h_label in HORIZONS:
    for model_name, res in [("EWMA", ewma_results), ("LR", lr_results), ("GBDT", gbdt_results)]:
        r = res[h_label]
        lines.append(f"| {h_label} | {model_name:>4s} | {r['precision']:.4f} | {r['recall']:.4f} | {r['fsr']:.4f} | {r['brier']:.4f} |")

# Delta summary
lines += ["", "## Delta vs GBDT (Precision)", "",
          "| Horizon | EWMA ΔP | LR ΔP | LR P ≈ GBDT? |",
          "|---------|:-------:|:-----:|:-----------:|"]
for h_label in HORIZONS:
    e_d = ewma_results[h_label]['precision'] - gbdt_results[h_label]['precision']
    l_d = lr_results[h_label]['precision'] - gbdt_results[h_label]['precision']
    close = "Yes" if abs(l_d) < 0.01 else ("~Yes" if abs(l_d) < 0.02 else "No")
    lines.append(f"| {h_label} | {e_d:+.4f} | {l_d:+.4f} | {close} |")

lines += ["", "## Interpretation", "",
          "- If LR ≈ GBDT: the problem is linearly separable given gap_stats → GBDT not strictly needed",
          "- If GBDT >> LR: burst-gap patterns have nonlinear structure worth modeling",
          "- If EWMA >> LR & GBDT at TINY horizon: trivial prediction (nearly all gaps qualify)"]

(RESULTS_DIR / "report.md").write_text("\n".join(lines))
print(f"\nSaved: {RESULTS_DIR / 'report.md'}")
print("Done.")
