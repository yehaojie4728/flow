# P1.1 Feature Ablation Study

**Method**: Leave-One-Group-Out ablation with GBDT predictor

**Data**: GLM-6B Pass1 (train) → Pass2 (test)

## Baseline Performance (All 30 Features)

| Horizon | Precision | Recall | FSR |
|---------|-----------|--------|-----|
| 250µs | 0.9715 | 0.8704 | 0.0115 |
| 500µs | 0.9545 | 0.9259 | 0.0183 |
| 1ms | 0.9536 | 0.9272 | 0.0187 |

## Ablation Results (Precision Drop when Removing Each Group)

| Removed Group | 250µs | 500µs | 1ms | Avg Δ |
|---------------|-------|-------|-----|-------|
| gap_stats | 0.9288 (+0.0427) | 0.9157 (+0.0388) | 0.9157 (+0.0379) | +0.0398 |
| burst_stats | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| idle_age | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| path_identity | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| stream_features | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| phase_features | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| resource_features | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| data_quality | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |
| time_features | 0.9715 (+0.0000) | 0.9545 (+0.0000) | 0.9536 (+0.0000) | +0.0000 |

**Interpretation**:
- Positive Δ: removing this group hurts precision (important features)
- Negative Δ: removing this group improves precision (noisy features)
- Near-zero Δ: group has minimal impact