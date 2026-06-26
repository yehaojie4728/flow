# D1: Obs 4 — Motivation Comparison

**Trace**: Pass 2, busiest D2H path ((4, 4294967295, <Direction.D2H: 2>, 255, 7), 21406 events)
**Window**: 50ms, densest region (busy fraction: 86.4%)
**Method**: Interval-overlap check for fixed_interval; per-gap GBDT prediction for FlowGap

## Results

| Strategy | Total Probes | Unsafe | Unsafe% |
|----------|:-----------:|:------:|:-------:|
| fixed_interval (1ms) | 49 | 46 | 93.9% |
| fixed_interval (5ms) | 9 | 7 | 77.8% |
| flowgap_predictive | 0 | 0 | 0.0% |

## Interpretation

- FlowGap correctly identified insufficient history to predict — it chose silence over unsafe probing. Fixed-interval blindly placed probes with 77.8% unsafe rate.

## Note

This experiment uses a 50ms window from the single busiest D2H path.
The comprehensive 7-policy comparison (§5.5 P0.1) covers all 60 paths
over the full 6007s trace with coverage metrics (BW%, Overhead%, Unsafe%).