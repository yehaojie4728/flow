# D7: True Cold-Start — Pass1 → Pass2

Trains on first k samples of Pass1, evaluates on entire Pass2.
This is the REAL cold-start: predicting on a completely unseen pass.

## Result Table

| k | 250µs P | 250µs FSR | 500µs P | 500µs FSR | 1ms P | 1ms FSR |
|:--:|:------:|:---------:|:------:|:---------:|:-----:|:-------:|
| 1 | 0.3242 | 1.0000 | 0.2995 | 1.0000 | 0.2988 | 1.0000 |
| 5 | 0.3242 | 1.0000 | 0.2995 | 1.0000 | 0.2988 | 1.0000 |
| 10 | 0.7488 | 0.1051 | 0.7184 | 0.1136 | 0.7184 | 0.1135 |
| 50 | 0.7039 | 0.1687 | 0.6737 | 0.1793 | 0.6736 | 0.1792 |
| 100 | 0.5904 | 0.2423 | 0.5661 | 0.2476 | 0.5661 | 0.2474 |
| 200 | 0.8747 | 0.0561 | 0.9664 | 0.0129 | 0.9664 | 0.0129 |
| 500 | 0.8889 | 0.0535 | 0.9161 | 0.0366 | 0.9153 | 0.0369 |
| 1000 | 0.9218 | 0.0368 | 0.9241 | 0.0337 | 0.9233 | 0.0340 |
| 2000 | 0.8915 | 0.0532 | 0.8896 | 0.0511 | 0.8888 | 0.0514 |
| 5000 | 0.9780 | 0.0097 | 0.9738 | 0.0110 | 0.9738 | 0.0110 |
| 10000 |

## Key Finding

- True cold-start requires more samples than in-pass warm-up (P2.1)
- How many Pass1 samples needed to reach 0.95+ precision on Pass2?
- This determines the minimum training trace length before FlowGap can be deployed