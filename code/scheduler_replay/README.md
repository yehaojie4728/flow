# Scheduler Replay

Offline trace-based evaluation of FlowGap probe placement policies.

## Quick start

```bash
cd /root/FlowGap-work/FlowGap-paper/code

# Run tests
PYTHONPATH=.:trace_parser python scheduler_replay/test_replay.py

# Run all 7 policies on real trace data
PYTHONPATH=.:trace_parser python -c "
from trace_parser.parse_trace import parse_csv, group_by_path
from trace_parser.intervalize import build_timeline
from scheduler_replay.replay import compare_policies

# Load Pass1 trace (170K events), build timelines for top 4 paths
events = parse_csv('../data/raw/trace_pass1_raw.csv')
groups = group_by_path(events)
top4 = sorted(groups.items(), key=lambda x: -len(x[1]))[:4]
timelines = {}
for pk, evs in top4:
    busy, gaps = build_timeline(evs, 50_000, 100_000, 1)
    timelines[hash(pk) & 0xFFFF] = (busy, gaps)

results = compare_policies(timelines)
print('Done.')
"
```

## Files

| File | Purpose |
|---|---|
| `schema.py` | Probe latencies from **real Ascend 910B** benchmarks, ProbeOutcome, RunMetrics |
| `policies.py` | 7 replay policies (factory pattern) |
| `replay.py` | Chronological gap replay engine |
| `metrics.py` | Overlap ratio, safe probing ratio, harmful probe count |
| `test_replay.py` | 32 unit tests |

## Policies

| # | Policy | Description |
|---|---|---|
| 1 | `no_probing` | Zero probes — baseline overhead |
| 2 | `fixed_interval` | Tiny latency probe every K ms |
| 3 | `random` | Probe each gap with probability p |
| 4 | `threshold` | Probe when gap exceeds bandwidth threshold |
| 5 | `ewma_only` | EWMA-based gap prediction (Tier 0 from gap_predictor) |
| 6 | `flowgap_predictive` | Full GBDT predictor (Tier 1 from gap_predictor) |
| 7 | `oracle` | Knows all future gaps — upper bound |

## Probe latencies (real Ascend 910B)

Measured on the actual hardware via HostDiagV2's `memcpy_benchmark`:

| Probe | Size | Iterations | Same-NUMA | Cross-NUMA D2H | Cross-NUMA H2D |
|---|---|---|---|---|---|
| Tiny latency | 4 KB | 1 | **50 µs** | 62 µs | 115 µs |
| Normal latency | 4 KB | 10 | **500 µs** | 620 µs | 1155 µs |
| Bandwidth | 128 MB | 1 | **5.1 ms** | 6.3 ms | 11.8 ms |
| Confirmation | 4 KB | 5 | **250 µs** | 310 µs | 578 µs |

Bandwidth measured at 25.1 GB/s (same NUMA) / 20.3 GB/s (cross NUMA D2H).
