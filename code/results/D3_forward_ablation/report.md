# D3: Forward Ablation — Keep-Only Each Feature Group

## Purpose

Unlike the original P1.1 (Leave-One-Group-Out), this experiment trains
the model using ONLY one feature group at a time. This reveals:
1. Whether gap_stats alone is sufficient
2. Whether any other group has standalone predictive power
3. Whether groups compensate for each other

## 1. Baseline (all 30 features)

| Horizon | Precision | Recall | FSR | Test Pos |
|---------|:---------:|:------:|:---:|:--------:|
| 50µs | 1.0000 | 1.0000 | 0.0000 | 15945/15945 |
| 100µs | 1.0000 | 1.0000 | 0.0000 | 15945/15945 |
| 250µs | 0.9787 | 0.8691 | 0.0091 | 5170/15945 |
| 500µs | 0.9642 | 0.9259 | 0.0147 | 4776/15945 |
| 1ms | 0.9634 | 0.9272 | 0.0150 | 4765/15945 |
| 5.1ms | 0.9246 | 0.9147 | 0.0258 | 4105/15945 |

## 2. Forward Ablation (Keep-Only): Precision

| Group | #Dims | 50µs | 100µs | 250µs | 500µs | 1ms | 5.1ms | Avg ΔP |
|-------|:-----:|:----:|:-----:|:-----:|:-----:|:---:|:-----:|:------:|
| gap_stats | 7 | 1.0000 | 1.0000 | 0.9787 | 0.9642 | 0.9634 | 0.9237 | -0.0002 |
| burst_stats | 5 | 1.0000 | 1.0000 | 0.9248 | 0.9131 | 0.9132 | 0.8354 | -0.0407 |
| idle_age | 1 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| path_identity | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| stream_features | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| phase_features | 2 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| resource_features | 3 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| data_quality | 4 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |
| time_features | 2 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | -0.6385 |

## 3. Forward Ablation (Keep-Only): False-Safe Rate

| Group | 50µs | 100µs | 250µs | 500µs | 1ms | 5.1ms |
|-------|:----:|:-----:|:-----:|:-----:|:---:|:-----:|
| gap_stats | 0.0000 | 0.0000 | 0.0091 | 0.0147 | 0.0150 | 0.0262 |
| burst_stats | 0.0000 | 0.0000 | 0.0291 | 0.0322 | 0.0321 | 0.0534 |
| idle_age | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| path_identity | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| stream_features | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| phase_features | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| resource_features | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| data_quality | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| time_features | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## 4. Leave-One-Group-Out (for comparison with P1.1)

| Removed Group | 250µs | 500µs | 1ms |
|---------------|:-----:|:-----:|:---:|
| gap_stats | 0.9263 | 0.9131 | 0.9128 |
| burst_stats | 0.9787 | 0.9642 | 0.9634 |
| idle_age | 0.9787 | 0.9642 | 0.9634 |
| path_identity | 0.9787 | 0.9642 | 0.9634 |
| stream_features | 0.9787 | 0.9642 | 0.9634 |
| phase_features | 0.9787 | 0.9642 | 0.9634 |
| resource_features | 0.9787 | 0.9642 | 0.9634 |
| data_quality | 0.9787 | 0.9642 | 0.9634 |
| time_features | 0.9787 | 0.9642 | 0.9634 |

## 5. Comparison: Forward (Keep-Only) vs LOO (Remove)

| Group | Forward 250µs | LOO 250µs | Forward 500µs | LOO 500µs | Forward 1ms | LOO 1ms |
|-------|:-----------:|:---------:|:-----------:|:---------:|:----------:|:-------:|
| gap_stats | 0.9787 | 0.9263 | 0.9642 | 0.9131 | 0.9634 | 0.9128 |
| burst_stats | 0.9248 | 0.9787 | 0.9131 | 0.9642 | 0.9132 | 0.9634 |
| idle_age | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| path_identity | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| stream_features | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| phase_features | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| resource_features | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| data_quality | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |
| time_features | 0.0000 | 0.9787 | 0.0000 | 0.9642 | 0.0000 | 0.9634 |

## 6. Interpretation

- **gap_stats forward > 0.9 precision**: gap_stats alone carries all predictive signal
- **Other groups forward ≈ baseline / near 0**: these groups have no standalone value
- **LOO results ≈ baseline for all except gap_stats**: confirms P1.1 — only gap_stats critical
- **Key takeaway**: For GLM-6B finetuning, gap timing statistics suffice. Other features may add value on more complex workloads.