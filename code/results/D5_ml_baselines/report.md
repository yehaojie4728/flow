# D5: ML Baseline Comparison

Compares EWMA, LogisticRegression, and GBDT across all 6 horizons.

## Result Table

| Horizon | Model | Precision | Recall | FSR | Brier |
|---------|-------|:---------:|:------:|:---:|:-----:|
| 250µs | EWMA | 0.3242 | 1.0000 | 1.0000 | 0.6758 |
| 250µs |   LR | 0.9285 | 0.7362 | 0.0272 | 0.0949 |
| 250µs | GBDT | 0.9722 | 0.9010 | 0.0123 | 0.0340 |
| 500µs (NORMAL) | EWMA | 0.2995 | 1.0000 | 1.0000 | 0.7005 |
| 500µs (NORMAL) |   LR | 0.8788 | 0.7301 | 0.0431 | 0.0879 |
| 500µs (NORMAL) | GBDT | 0.9647 | 0.9608 | 0.0150 | 0.0172 |
| 1ms | EWMA | 0.2988 | 1.0000 | 1.0000 | 0.7012 |
| 1ms |   LR | 0.8779 | 0.7316 | 0.0434 | 0.0874 |
| 1ms | GBDT | 0.9660 | 0.9614 | 0.0144 | 0.0160 |
| 5.1ms (BW) | EWMA | 0.2574 | 1.0000 | 1.0000 | 0.7426 |
| 5.1ms (BW) |   LR | 0.7765 | 0.7179 | 0.0716 | 0.0949 |
| 5.1ms (BW) | GBDT | 0.9636 | 0.9425 | 0.0123 | 0.0177 |

## Delta vs GBDT (Precision)

| Horizon | EWMA ΔP | LR ΔP | LR P ≈ GBDT? |
|---------|:-------:|:-----:|:-----------:|
| 250µs | -0.6480 | -0.0437 | No |
| 500µs (NORMAL) | -0.6652 | -0.0859 | No |
| 1ms | -0.6672 | -0.0881 | No |
| 5.1ms (BW) | -0.7062 | -0.1871 | No |

## Interpretation

- If LR ≈ GBDT: the problem is linearly separable given gap_stats → GBDT not strictly needed
- If GBDT >> LR: burst-gap patterns have nonlinear structure worth modeling
- If EWMA >> LR & GBDT at TINY horizon: trivial prediction (nearly all gaps qualify)