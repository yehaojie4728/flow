#!/usr/bin/env python3
"""
Train FlowGap gap predictor on real Ascend 910B traces.

Pipeline:
  1. Parse raw Pass1/Pass2 CSVs → FlowEvent[]
  2. Group by path, build busy-idle timelines
  3. Extract features + multi-horizon labels
  4. Save burst_gap_events.parquet
  5. Train on Pass 1 (cold-start analysis + GBDT)
  6. Evaluate on Pass 2
  7. Produce RQ1 metrics → results/rq1_predictability.md

Usage:
    cd /root/FlowGap-work/FlowGap-paper/code
    PYTHONPATH=.:trace_parser python gap_predictor/train_predictor.py
"""

import json, os, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"
RESULTS_DIR = ROOT / "results"
PROC_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "code"))
sys.path.insert(0, str(ROOT / "code" / "trace_parser"))

from trace_parser.parse_trace import parse_csv, group_by_path
from trace_parser.intervalize import (
    build_timeline, compute_gap_stats, compute_safe_window_availability,
)
from trace_parser.schema import FlowEvent, BusyInterval, Gap, Direction

from gap_predictor.features import (
    FeatureExtractor, make_multi_horizon_labels, build_training_dataset,
)
from gap_predictor.schema import HORIZONS_NS
from gap_predictor.ewma_baseline import EWMABaseline, QuantileBaseline
from gap_predictor.survival_model import (
    MultiHorizonSurvivalPredictor, time_series_split_validate, aggregate_cv_results,
)
from gap_predictor.calibrator import CalibrationTable, ConfidenceComposer
from gap_predictor.predictor import GapPredictor


# ============================================================================
# Step 1: Parse and build timelines
# ============================================================================

def build_timelines(csv_path: str) -> Dict[int, Tuple[List[BusyInterval], List[Gap]]]:
    """Parse CSV, group by path, build per-path busy-idle timelines."""
    print(f"  Parsing {csv_path}...")
    events = parse_csv(str(csv_path))
    print(f"    {len(events)} events loaded")

    groups = group_by_path(events)
    print(f"    {len(groups)} unique paths")

    timelines = {}
    min_probe = 50_000  # ns
    safety_margin = 100_000

    for pk, evs in groups.items():
        path_id = hash(pk) & 0xFFFF
        busy, gaps = build_timeline(evs, min_probe, safety_margin, path_id)
        if len(gaps) >= 5:  # need minimum gaps for training
            timelines[path_id] = (busy, gaps)

    print(f"    {len(timelines)} paths with >=5 gaps")
    return timelines


# ============================================================================
# Step 2: Extract features + labels, save parquet
# ============================================================================

def timelines_to_parquet(
    timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]],
    output_path: str,
    pass_label: str = "pass1",
):
    """Extract features and labels, save as parquet."""
    extractor = FeatureExtractor(window_size=50, min_events=5)
    all_rows = []

    for path_id, (busy, gaps) in timelines.items():
        # Walk through gaps chronologically, extracting features from prior context
        for i, gap in enumerate(gaps):
            if i < extractor.min_events:
                continue

            prior_gaps = gaps[:i]
            prior_busy = busy[:max(1, i)]

            features = extractor.extract(
                prior_gaps, prior_busy,
                path_id=path_id,
                direction=Direction.D2H if gap.link_bitmap & 2 else Direction.H2D,
                now_ns=gap.start_ns,
            )
            if len(features) == 0:
                continue

            row = {
                "pass": pass_label,
                "path_id": path_id,
                "gap_idx": i,
                "gap_start_ns": gap.start_ns,
                "gap_end_ns": gap.end_ns,
                "gap_duration_ns": gap.duration_ns,
                "direction": gap.link_bitmap & 2 == 2,
            }
            for j, name in enumerate(extractor.feature_names()):
                row[f"f_{name}"] = float(features[j])
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    df.to_parquet(output_path, index=False)
    print(f"  Saved {len(df)} rows → {output_path}")
    return df


# ============================================================================
# Step 3: Train and evaluate
# ============================================================================

def prepare_xy(
    timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]],
) -> Tuple[np.ndarray, Dict[int, np.ndarray], np.ndarray]:
    """Build X, y_dict, actual_gaps from timelines."""
    extractor = FeatureExtractor(window_size=50, min_events=5)
    all_X = []
    all_gap_durations = []

    # Collect all feature vectors and corresponding gaps
    for path_id, (busy, gaps) in timelines.items():
        for i, gap in enumerate(gaps):
            if i < extractor.min_events:
                continue
            features = extractor.extract(
                gaps[:i], busy[:max(1, i)],
                path_id=path_id, direction=1,
                now_ns=gap.start_ns,
            )
            if len(features) == 0:
                continue
            all_X.append(features)
            all_gap_durations.append(gap.duration_ns)

    if not all_X:
        return np.empty((0, extractor.n_features())), {}, np.array([])

    X = np.stack(all_X)
    gap_arr = np.array(all_gap_durations, dtype=np.int64)

    # Multi-horizon labels
    y_dict = {}
    for h in HORIZONS_NS:
        y_dict[h] = (gap_arr >= h).astype(np.int32)

    return X, y_dict, gap_arr


def train_and_eval(
    pass1_timelines: dict,
    pass2_timelines: dict,
) -> dict:
    """Train GBDT on Pass 1, evaluate on Pass 2. Also evaluate EWMA baseline."""
    results = {}

    # ---- Prepare training / test data ----
    X_train, y_train_dict, gaps_train = prepare_xy(pass1_timelines)
    X_test, y_test_dict, gaps_test = prepare_xy(pass2_timelines)

    print(f"  Training: {X_train.shape[0]} samples, {X_train.shape[1]} features")
    print(f"  Test:     {X_test.shape[0]} samples")

    if X_train.shape[0] < 50:
        print("  WARNING: Insufficient training data. Using EWMA-only baseline.")
        results["status"] = "EWMA only (insufficient data)"
        return results

    # ---- EWMA baseline (train on Pass 1, evaluate on Pass 2) ----
    ewma = EWMABaseline(window_size=100, alpha=0.1, min_samples=10)
    for g in gaps_train:
        ewma.update(0, float(g))
    ewma_preds = {h: ewma.predict(0, (h,)).get(h, 0.5) for h in HORIZONS_NS}

    ewma_metrics = {}
    for h in HORIZONS_NS:
        if h not in y_test_dict or len(y_test_dict[h]) == 0:
            continue
        labels = y_test_dict[h]
        probs = np.full(len(labels), ewma_preds.get(h, 0.5))
        preds = (probs >= 0.5).astype(np.int32)
        tp = int(np.sum((preds == 1) & (labels == 1)))
        fp = int(np.sum((preds == 1) & (labels == 0)))
        fn = int(np.sum((preds == 0) & (labels == 1)))
        tn = int(np.sum((preds == 0) & (labels == 0)))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        brier = float(np.mean((probs - labels.astype(float)) ** 2))

        ewma_metrics[h] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "false_safe_rate": round(fpr, 4),
            "brier_score": round(brier, 4),
            "n_samples": len(labels),
        }

    print("\n  EWMA baseline:")
    for h, m in sorted(ewma_metrics.items()):
        print(f"    h={h//1000:5d}us  prec={m['precision']:.3f}  recall={m['recall']:.3f}  FSR={m['false_safe_rate']:.3f}  Brier={m['brier_score']:.4f}")

    results["ewma_baseline"] = ewma_metrics

    # ---- GBDT predictor: train on Pass 1, evaluate on Pass 2 ----
    print("\n  Training GBDT survival predictor...")
    t0 = time.time()

    predictor = GapPredictor(model_dir=str(ROOT / "models"))
    predictor.train(pass1_timelines)

    train_time = time.time() - t0

    # Test on Pass 2
    t0 = time.time()
    gbdt_metrics_raw = predictor.evaluate(pass2_timelines)
    infer_time = time.time() - t0

    print(f"\n  GBDT predictor (train={train_time:.1f}s, eval={infer_time:.1f}s):")
    for h, m in sorted(gbdt_metrics_raw.items()):
        print(f"    h={h//1000:5d}us  prec={m['precision']:.3f}  recall={m['recall']:.3f}  FSR={m['false_safe_rate']:.3f}  Brier={m['brier_score']:.4f}  n={m['n_samples']}")

    results["gbdt_predictor"] = gbdt_metrics_raw
    results["training_time_sec"] = round(train_time, 1)
    results["inference_time_sec"] = round(infer_time, 1)

    # ---- Cold-start analysis (how many events needed to converge) ----
    cs_results = []
    for events_pct in [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]:
        n_events = max(50, int(X_train.shape[0] * events_pct))
        X_sub = X_train[:n_events]
        y_sub = {h: y_train_dict[h][:n_events] for h in y_train_dict}

        try:
            m = MultiHorizonSurvivalPredictor()
            m.fit(X_sub, y_sub)
            # Evaluate on full test
            metrics_for_pct = {}
            for h in HORIZONS_NS:
                if h not in y_test_dict or len(y_test_dict[h]) == 0:
                    continue
                if h not in m._models:
                    continue
                try:
                    probs = m.predict_proba(X_test, h)
                except Exception:
                    probs = np.full(len(y_test_dict[h]), 0.5)
                labels = y_test_dict[h]
                preds = (probs >= 0.5).astype(np.int32)
                tp = int(np.sum((preds == 1) & (labels == 1)))
                fp = int(np.sum((preds == 1) & (labels == 0)))
                fn = int(np.sum((preds == 0) & (labels == 1)))
                tn = int(np.sum((preds == 0) & (labels == 0)))
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
                metrics_for_pct[h] = {"precision": round(prec, 4), "false_safe_rate": round(fpr, 4)}
            cs_results.append({
                "training_fraction": events_pct,
                "training_samples": n_events,
                "per_horizon": metrics_for_pct,
            })
        except Exception as e:
            cs_results.append({"training_fraction": events_pct, "training_samples": n_events, "error": str(e)})

    results["cold_start"] = cs_results

    return results


# ============================================================================
# Step 4: Generate RQ1 report
# ============================================================================

def generate_report(results: dict, output_path: str):
    """Generate Markdown RQ1 report."""
    lines = []
    lines.append("# RQ1: FlowGap Traffic Predictability")
    lines.append("")
    lines.append(f"**Generated** by `code/gap_predictor/train_predictor.py`  ")
    lines.append(f"**Data**: GLM-6B finetuning, 8× Ascend 910B, 341,934 total events  ")
    lines.append("")

    # EWMA baseline
    if "ewma_baseline" in results:
        lines.append("## EWMA Baseline (Pass 1 → Pass 2)")
        lines.append("")
        lines.append("| Horizon | Precision | Recall | False-Safe Rate | Brier Score | Samples |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for h, m in sorted(results["ewma_baseline"].items()):
            lines.append(f"| {h//1000}µs | {m['precision']:.4f} | {m['recall']:.4f} | {m['false_safe_rate']:.4f} | {m['brier_score']:.4f} | {m['n_samples']} |")
        lines.append("")

    # GBDT predictor
    if "gbdt_predictor" in results:
        train_t = results.get("training_time_sec", 0)
        infer_t = results.get("inference_time_sec", 0)
        lines.append(f"## GBDT Predictor (Pass 1 → Pass 2)  ")
        lines.append(f"_Train: {train_t:.1f}s, Inference: {infer_t:.1f}s_")
        lines.append("")
        lines.append("| Horizon | Precision | Recall | False-Safe Rate | Brier Score | Samples |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for h, m in sorted(results["gbdt_predictor"].items()):
            lines.append(f"| {h//1000}µs | {m['precision']:.4f} | {m['recall']:.4f} | {m['false_safe_rate']:.4f} | {m['brier_score']:.4f} | {m['n_samples']} |")
        lines.append("")

        # Improvement over EWMA
        lines.append("### GBDT vs EWMA Improvement")
        lines.append("")
        lines.append("| Horizon | Δ Precision | Δ Recall | Δ False-Safe Rate | Δ Brier |")
        lines.append("|---|---:|---:|---:|---:|")
        for h, m in sorted(results["gbdt_predictor"].items()):
            if h in results.get("ewma_baseline", {}):
                e = results["ewma_baseline"][h]
                d_p = m["precision"] - e["precision"]
                d_r = m["recall"] - e["recall"]
                d_f = m["false_safe_rate"] - e["false_safe_rate"]
                d_b = m["brier_score"] - e["brier_score"]
                lines.append(f"| {h//1000}µs | {d_p:+.4f} | {d_r:+.4f} | {d_f:+.4f} | {d_b:+.4f} |")
        lines.append("")

    # Cold start analysis
    if "cold_start" in results:
        lines.append("## Cold-Start Analysis")
        lines.append("")
        lines.append("| Training % | Samples | 50µs Precision | 50µs FSR | 500µs Precision | 500µs FSR |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for cs in results["cold_start"]:
            if "error" in cs:
                continue
            pct = cs["training_fraction"]
            n = cs["training_samples"]
            p50 = cs["per_horizon"].get(50_000, {})
            p500 = cs["per_horizon"].get(500_000, {})
            lines.append(
                f"| {pct*100:.0f}% | {n} | "
                f"{p50.get('precision', 0):.4f} | {p50.get('false_safe_rate', 0):.4f} | "
                f"{p500.get('precision', 0):.4f} | {p500.get('false_safe_rate', 0):.4f} |"
            )
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    key_h = 50_000  # tiny latency probe
    gbdt = results.get("gbdt_predictor", {}).get(key_h, {})
    ewma = results.get("ewma_baseline", {}).get(key_h, {})
    lines.append(f"- **GBDT Tiny-latency precision**: {gbdt.get('precision', 0):.4f}")
    lines.append(f"- **GBDT Tiny-latency false-safe rate**: {gbdt.get('false_safe_rate', 0):.4f}")
    lines.append(f"- **EWMA Tiny-latency precision**: {ewma.get('precision', 0):.4f}")
    lines.append(f"- **GBDT improvement over EWMA (precision)**: {gbdt.get('precision', 0) - ewma.get('precision', 0):+.4f}")
    lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport saved: {output_path}")


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("FlowGap Gap Predictor Training Pipeline")
    print("=" * 60)

    # ---- Step 1: Build timelines ----
    print("\n[Step 1] Building per-path timelines...")
    pass1_timelines = build_timelines(str(RAW_DIR / "trace_pass1_raw.csv"))
    pass2_timelines = build_timelines(str(RAW_DIR / "trace_pass2_raw.csv"))

    # ---- Step 2: Extract features + save parquet ----
    print("\n[Step 2] Extracting features and saving parquet...")
    df1 = timelines_to_parquet(
        pass1_timelines,
        str(PROC_DIR / "burst_gap_events.parquet"),
        "pass1",
    )
    df2 = timelines_to_parquet(
        pass2_timelines,
        str(PROC_DIR / "burst_gap_events_pass2.parquet"),
        "pass2",
    )
    # Combine
    df_all = pd.concat([df1, df2], ignore_index=True)
    df_all.to_parquet(str(PROC_DIR / "burst_gap_events_all.parquet"), index=False)
    print(f"  Combined: {len(df_all)} rows → {PROC_DIR / 'burst_gap_events_all.parquet'}")

    # ---- Step 3: Visualize gap distribution ----
    print("\n[Step 3] Gap distribution summary...")
    for label, df in [("Pass 1", df1), ("Pass 2", df2)]:
        print(f"\n  {label} gap durations:")
        for pct in [10, 50, 90, 99]:
            val = np.percentile(df["gap_duration_ns"], pct)
            print(f"    p{pct}: {val/1e3:.0f}µs ({val/1e6:.1f}ms)")

    # ---- Step 4: Train and evaluate ----
    print("\n[Step 4] Training and evaluating predictor...")
    results = train_and_eval(pass1_timelines, pass2_timelines)

    # Save results JSON
    results_path = RESULTS_DIR / "rq1_predictability.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved: {results_path}")

    # ---- Step 5: Generate report ----
    print("\n[Step 5] Generating RQ1 report...")
    generate_report(results, str(RESULTS_DIR / "rq1_predictability.md"))

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print(f"  Parquet: {PROC_DIR / 'burst_gap_events.parquet'}")
    print(f"  Report:  {RESULTS_DIR / 'rq1_predictability.md'}")
    print(f"  JSON:    {RESULTS_DIR / 'rq1_predictability.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
