#!/usr/bin/env python3
"""
Train GBDT survival predictor on Pass 1 parquet, save to disk.

Output: models/gbdt_pass1.pkl — loadable by GapPredictor.load() or
         MultiHorizonSurvivalPredictor.load().

Usage:
    cd /root/FlowGap-work/FlowGap-paper/code
    PYTHONPATH=.:trace_parser python gap_predictor/train_and_save.py
"""
import os, sys, time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "code"))

from gap_predictor.survival_model import MultiHorizonSurvivalPredictor
from gap_predictor.schema import HORIZONS_NS



def main():
    parquet_path = ROOT / "data" / "processed" / "burst_gap_events.parquet"
    if not parquet_path.exists():
        print(f"Parquet not found: {parquet_path}")
        print("Run gap_predictor/build_parquet.py first.")
        sys.exit(1)

    print(f"Loading: {parquet_path}")
    df = pd.read_parquet(str(parquet_path))
    print(f"  {len(df)} rows")

    # Feature columns (must match build_parquet.py)
    feature_cols = [c for c in df.columns if c.startswith("f_")]
    X = df[feature_cols].values.astype(np.float64)
    gap_ns = df["gap_duration_ns"].values.astype(np.int64)

    print(f"  X shape: {X.shape}, features: {len(feature_cols)}")

    # Build y_dict = per-horizon binary labels
    y_dict = {}
    for h in HORIZONS_NS:
        y_dict[h] = (gap_ns >= h).astype(np.int32)
        # Debug: how many positive samples
        n_pos = int(y_dict[h].sum())
        print(f"  horizon {h // 1000:5d}µs: {n_pos}/{len(y_dict[h])} safe ({n_pos / max(1, len(y_dict[h])) * 100:.1f}%)")

    # Train
    print("\nTraining MultiHorizonSurvivalPredictor...")
    t0 = time.time()

    model = MultiHorizonSurvivalPredictor(
        horizons_ns=HORIZONS_NS,
        gbdt_params={
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "random_state": 42,
        },
    )
    model.fit(X, y_dict)

    train_time = time.time() - t0
    print(f"  Trained {len(model._models)} models in {train_time:.1f}s")

    # Save
    save_path = MODEL_DIR / "gbdt_pass1.pkl"
    model.save(str(save_path))
    print(f"  Saved to: {save_path} ({save_path.stat().st_size // 1024} KB)")

    # Verify load
    print("\nVerifying load...")
    loaded = MultiHorizonSurvivalPredictor.load(str(save_path))
    assert loaded._fitted
    # Quick predict check
    p = loaded.predict_proba(X[:10], 50_000)
    print(f"  Sample predictions (50µs horizon): {np.round(p, 3).tolist()}")
    print("  Load OK")

    print(f"\nDone. Model ready at {save_path}")


if __name__ == "__main__":
    main()
