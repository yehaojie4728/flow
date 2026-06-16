# P1.4 Parameter Sensitivity: Confidence Threshold η

**Data**: Pass1 (train) → Pass2 (test) | GBDT horizon=500µs

| η_bw | η_normal | BW Probes | Precision@500µs | Safe Ratio |
|------|----------|-----------|-----------------|------------|
| 0.50 | 0.50 | 4633 | 0.9545 | 0.9455 |
| 0.60 | 0.55 | 4573 | 0.9582 | 0.9468 |
| 0.70 | 0.65 | 4047 | 0.9983 | 0.9668 |
| 0.80 | 0.75 | 3853 | 0.9995 | 0.9681 |
| 0.85 | 0.80 | 3846 | 0.9995 | 0.9681 |
| 0.90 | 0.85 | 3846 | 0.9995 | 0.9681 |
| 0.95 | 0.90 | 0 | 1.0000 | 1.0000 |
| 0.99 | 0.94 | 0 | 1.0000 | 1.0000 |

Higher η → fewer BW probes but higher precision; safe_ratio stable as small probes always fit.