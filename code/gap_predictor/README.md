# FlowGap Gap Predictor

Multi-horizon safe-window predictor for Ascend memcpy traffic. Core module of FlowGap (Module 3).

## Quick start

```bash
cd code

# Run unit tests
PYTHONPATH=.:trace_parser python gap_predictor/test_gap_predictor.py

# Train a predictor from parsed trace data
PYTHONPATH=.:trace_parser python -c "
from gap_predictor.predictor import GapPredictor
from gap_predictor.features import FeatureExtractor
# ... load timelines from trace_parser output ...
predictor = GapPredictor(model_dir='../models')
predictor.train(timelines)
"
```

## Files

| File | Purpose |
|---|---|
| `schema.py` | SafeWindow dataclass, horizon definitions, confidence thresholds |
| `features.py` | Feature extraction from per-path timelines (~30 features) |
| `ewma_baseline.py` | Tier 0: EWMA/quantile baseline (cold start, fallback) |
| `survival_model.py` | Tier 1: multi-horizon GBDT survival predictor |
| `lower_bound.py` | Gap lower-bound estimation via quantile regression |
| `calibrator.py` | Empirical calibration table + confidence composition |
| `drift_detector.py` | Rolling-statistics drift detection |
| `predictor.py` | Main orchestrator: feature → predict → calibrate → publish |
| `test_gap_predictor.py` | Unit tests (36 tests) |

## Architecture

```
BusyInterval[] + Gap[]
        │
        ▼
  features.py  ──  FeatureExtractor → np.ndarray (30 features)
        │
        ├──▶ ewma_baseline.py  (Tier 0, cold start)
        │
        └──▶ survival_model.py (Tier 1, trained)
                    │
                    ▼
              calibrator.py  ──  CalibrationTable + ConfidenceComposer
                    │
                    ▼
              predictor.py   ──  SafeWindow[]
```

## Model tiers

| Tier | Model | When used | Features needed |
|---|---|---|---|
| 0 | EWMA / Quantile baseline | Cold start, drift detected | gap history only |
| 1 | Multi-horizon GBDT | Sufficient training samples | Full 30-feature vector |

## Predictor interface

```python
from gap_predictor.predictor import GapPredictor

p = GapPredictor(model_dir="./models")

# Training
p.train(timelines)  # Dict[path_id] → (busy_intervals, gaps)

# Prediction
windows = p.predict(path_id, gaps, busy_intervals, now_ns=time.time_ns())
for sw in windows:
    print(f"Horizon {sw.horizon_ns}ns: p_safe={sw.p_safe:.3f}, "
          f"confidence={sw.confidence:.3f}, probe={sw.probe_type_label}")

# Evaluation
results = p.evaluate(held_out_timelines)
```

## Horizon set

```
10µs   25µs   50µs   100µs   250µs   500µs   1ms   2ms
 ← tiny latency →  ← normal latency →  ← bandwidth →
```

## Confidence thresholds

| Confidence | Probe type |
|---|---|
| ≥ 0.98 | Bandwidth (128 MB) |
| ≥ 0.95 | Normal latency (4 KB × 10) |
| ≥ 0.90 | Tiny latency (4 KB × 1) |
| < 0.90 | No probe |

## Dependencies

- `numpy` (required)
- `scikit-learn` (required for survival_model — install `pip install scikit-learn`)
- `pytest` (optional, for running tests)

## Design documentation

See `../../docs/gap_predictor_design.md` for detailed design rationale.
