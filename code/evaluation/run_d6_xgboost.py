#!/usr/bin/env python3
"""
D6: XGBoost baseline — engineering-optimal GBDT implementation.

Compares GBDT (scikit-learn) vs XGBoost (industry standard) for gap prediction.
If XGBoost significantly outperforms GBDT, it suggests room for engineering
improvement. If similar, scikit-learn GBDT is sufficient.

Output: code/results/D6_xgboost/
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/root/FlowGap-work/FlowGap-paper")
RESULTS_DIR = ROOT / "code" / "results" / "D6_xgboost"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HORIZONS = {
    "250µs": 250_000,
    "500µs (NORMAL)": 500_000,
    "1ms": 1_000_000,
    "5.1ms (BW)": 5_100_000,
}


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
print("D6: XGBoost Baseline Comparison")
print("=" * 60)

df_train = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events.parquet"))
df_test = pd.read_parquet(str(ROOT / "data/processed/burst_gap_events_pass2.parquet"))
print(f"Train: {len(df_train)}, Test: {len(df_test)}")

FCOLS = [c for c in df_train.columns if c.startswith("f_")]
X_train = df_train[FCOLS].values.astype(np.float64)
X_test = df_test[FCOLS].values.astype(np.float64)
gap_train = df_train["gap_duration_ns"].values.astype(np.int64)
gap_test = df_test["gap_duration_ns"].values.astype(np.int64)

# GBDT (same as P0.2)
from sklearn.ensemble import GradientBoostingClassifier
gbdt_results = {}
for h_label, h_ns in HORIZONS.items():
    y_tr = (gap_train >= h_ns).astype(np.int32)
    y_te = (gap_test >= h_ns).astype(np.int32)
    clf = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1,
                                     subsample=0.8, random_state=42)
    clf.fit(X_train, y_tr)
    probs = clf.predict_proba(X_test)[:, 1]
    gbdt_results[h_label] = compute_metrics(probs, y_te)

# XGBoost
try:
    import xgboost as xgb
    xgb_results = {}
    for h_label, h_ns in HORIZONS.items():
        y_tr = (gap_train >= h_ns).astype(np.int32)
        y_te = (gap_test >= h_ns).astype(np.int32)
        clf = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1,
                                subsample=0.8, random_state=42,
                                eval_metric='logloss', verbosity=0)
        clf.fit(X_train, y_tr)
        probs = clf.predict_proba(X_test)[:, 1]
        xgb_results[h_label] = compute_metrics(probs, y_te)
    xgb_available = True
except ImportError:
    xgb_available = False
    xgb_results = {}

lines = ["# D6: XGBoost Baseline Comparison", ""]

if xgb_available:
    lines += ["## Result Table", "",
              "| Horizon | Model | Precision | Recall | FSR | Brier |",
              "|---------|-------|:---------:|:------:|:---:|:-----:|"]
    for h_label in HORIZONS:
        for model_name, res in [("GBDT", gbdt_results), ("XGBoost", xgb_results)]:
            r = res.get(h_label)
            if r:
                lines.append(f"| {h_label} | {model_name:>7s} | {r['precision']:.4f} | {r['recall']:.4f} | {r['fsr']:.4f} | {r['brier']:.4f} |")

    lines += ["", "## Delta (XGBoost − GBDT)", "",
              "| Horizon | Δ Precision | Δ Recall | Δ FSR | Δ Brier |",
              "|---------|:----------:|:--------:|:-----:|:-------:|"]
    for h_label in HORIZONS:
        g = gbdt_results[h_label]
        x = xgb_results[h_label]
        lines.append(f"| {h_label} | {x['precision']-g['precision']:+.4f} | {x['recall']-g['recall']:+.4f} | {x['fsr']-g['fsr']:+.4f} | {x['brier']-g['brier']:+.4f} |")
    lines += ["", "## Interpretation", "",
              "- If XGBoost ≈ GBDT: scikit-learn GBDT is sufficient, no need for specialized libraries",
              "- If XGBoost >> GBDT: could use XGBoost in production for marginal gains"]
else:
    lines += ["XGBoost not installed. Install with: `pip install xgboost`", ""]

(RESULTS_DIR / "report.md").write_text("\n".join(lines))
print(f"\nSaved: {RESULTS_DIR / 'report.md'}")
print("Done.")
