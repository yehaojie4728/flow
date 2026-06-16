# P1.3 eBPF Tracer Overhead Analysis

**Method**: GLM-6B training, mpstat system sampling + pidstat tracer sampling
**Config**: warmup=180s, sample=300s, interval=2s, ncpu=192

## System CPU Utilization (busy% = 100 - idle)

| Phase | Samples | Mean busy% | Median | Stdev | Min | Max |
|-------|---------|-----------|--------|-------|-----|-----|
| A (baseline, no tracer) | 150 | 1.0726 | 0.97 | 0.6965 | 0.51 | 4.89 |
| B (with eBPF tracer)    | 150 | 2.24 | 1.045 | 3.6419 | 0.56 | 35.98 |

**System CPU overhead**: +1.1674 percentage points (2.24% - 1.0726%)

## Tracer Process CPU (pidstat, %CPU relative to single core)

| Samples | Mean | Median | Stdev | Min | Max |
|---------|------|--------|-------|-----|-----|
| 150 | 0.3867 | 0.0 | 3.3694 | 0.0 | 33.0 |

**Tracer process whole-system CPU**: 0.002% (= 0.3867% / 192 cores)

## Interpretation

- The eBPF tracer adds **+1.1674 pp** to system CPU busy ratio during training.
- The tracer user-space process itself consumes **0.002%** of total machine CPU.
