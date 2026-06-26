# D2: Drift Gap Distribution — first 80% vs last 20% of Pass2

## Purpose

Explain why P2.2 reports "last 20% has higher precision than first 80%".
If gaps are systematically larger in later segments, higher precision is
a data artifact — not model improvement.

**Split point**: 12756 / 15945  (at 80% chronological ordering)
**Early samples**: 12756  |  **Late samples**: 3189

## Gap Duration Distribution

| Statistic | First 80% | Last 20% | Δ |
|-----------|:---------:|:--------:|:--:|
| p10 | 167.0 µs | 163.3 µs | -3.7 µs |
| p25 | 175.6 µs | 169.3 µs | -6.3 µs |
| p50 (median) | 207.7 µs | 188.6 µs | -19.1 µs |
| p75 | 4103.2 µs | 10518.4 µs | +6415.2 µs |
| p90 | 18028.9 µs | 18094.6 µs | +65.6 µs |
| mean | 44912.7 µs | 367968.6 µs | +323056.0 µs |
| std | 3096759.5 µs | 10699630.5 µs | +7602871.0 µs |
| min | 150.3 µs | 151.2 µs | +0.9 µs |
| max | 340828631.6 µs | 350034781.0 µs | +9206149.3 µs |

## Per-Horizon Safe Fraction (gap ≥ threshold)

| Horizon | First 80% Safe% | Last 20% Safe% | Δ |
|---------|:---------------:|:--------------:|:--:|
| 50µs | 100.0% | 100.0% | +0.0 pp |
| 100µs | 100.0% | 100.0% | +0.0 pp |
| 250µs | 31.8% | 34.8% | +2.9 pp |
| 500µs | 28.9% | 34.0% | +5.1 pp |
| 1.0ms | 28.9% | 34.0% | +5.1 pp |
| 5.1ms | 24.7% | 29.9% | +5.2 pp |
| 10.0ms | 17.4% | 25.2% | +7.9 pp |

## Per-Path Safe Fraction (500µs horizon)

| Path | First 80% Safe% | Last 20% Safe% | Δ | N (early/late) |
|------|:---------------:|:--------------:|:--:|:--------------:|
| 39862 | 28.4% | 36.7% | +8.2 pp | 675/1262 |

## Interpretation

Gap distribution appears to shift. Note that "improvement" does not indicate the model learns over time — it is a passive property of the data.