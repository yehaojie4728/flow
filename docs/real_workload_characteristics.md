# Real Workload Characteristics — GLM-6B Finetuning on Ascend 910B

Generated from: `/root/FlowGap-work/reference_repo/runs/raw/aclrtMemcpy_numa_raw.log`
Copied to: `data/raw/aclrtMemcpy_numa_raw.log`

---

## Source

| Field | Value |
|---|---|
| Workload | ChatGLM-6B finetuning (MindFormers, MindSpore) |
| Platform | 8× Ascend 910B, Kunpeng 920 (192 cores, 756 GB) |
| CANN version | 8.5.0 |
| Collection method | eBPF uprobe on `aclrtMemcpy` (HostDiagV2 `trace_memcpy_numa.py`) |
| Duration | 6077s (1.7 hours) |
| Collection date | 2026-04-29 |

## Summary statistics

| Metric | Value |
|---|---|
| Total events | 1054 (1 header row + 1054 data rows) |
| Unique PIDs | 11 |
| Unique TIDs | 17 |
| Direction | 100% H2D (Host → Device) |
| Memcpy sizes | 24.5 – 1040 MB |
| Bandwidth | 0.6 – 23.0 GB/s |
| Latency | 1.9 ms – 1.7 s |
| Unique paths | 11 (NUMA × NPU pairs) |

## Path-level breakdown

| Path | Events | Total MB | Direction | Gap p50 | Gap p90 | Role |
|---|---|---|---|---|---|---|
| NUMA 0 → NPU 2 | 840 | 107,250 | H2D | 1.1 ms | 133.4 ms | **Dominant data loader** |
| NUMA 0 → NPU 1 | 29 | 4,151 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 3 → NPU 6 | 29 | 4,151 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 1 → NPU 0 | 29 | 4,151 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 3 → NPU 7 | 29 | 4,151 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 2 → NPU 4 | 28 | 3,112 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 0 → NPU 5 | 28 | 3,112 | H2D | 0.4 ms | 0.5 ms | Worker |
| NUMA 1 → NPU 3 | 28 | 3,112 | H2D | 0.3 ms | 0.4 ms | Worker |
| NUMA 2 → NPU 2 | 10 | 945 | H2D | 0.4 ms | 36.0 ms | Occasional |
| NUMA 1 → Device ? | 2 | 256 | H2D | 3028 ms | 3028 ms | Unknown device |
| NUMA 1 → NPU 2 | 2 | 388 | H2D | 0.5 ms | 0.5 ms | Occasional |

## Key observations for FlowGap

### 1. Burst-gap structure confirmed

The dominant path (NUMA 0 → NPU 2) has 840 events merged into only **22 busy intervals** after probe-aware intervalization (threshold=150µs). This means most inter-event gaps are < 150µs — they form dense bursts. Between bursts there are **22 gaps** with p50=1.1ms and p90=133.4ms.

This confirms the core FlowGap hypothesis: Ascend memcpy traffic is bursty with structured gaps that can be predicted.

### 2. Safe-window availability

For the dominant data-loader path (22 gaps):
- **Tiny latency probe (50µs)**: 22/22 safe (100%)
- **Normal latency probe (500µs)**: majority safe
- **Bandwidth probe (5ms)**: only the largest gaps (~133ms)

The p90 gap of 133ms is ample for even a large bandwidth probe (128MB, ~5-12ms).

### 3. path-level prediction is essential

Worker paths have only 28-29 events each over 1.7 hours — very sparse. A per-path predictor must handle both dense (840 events in 22 bursts) and sparse (28 events in 20+ bursts) paths.

### 4. Device tracking gaps exist

2 events have `Device ?` (unknown NPU). This is ~0.2% of total events. The parser correctly flags these with `QF_UNKNOWN_DEVICE`.

### 5. All traffic is H2D

This workload (finetuning) has only H2D memcpy. This is expected: data is loaded from host memory into NPU HBM. D2H and D2D would appear in different workload types (checkpoint save, model export, multi-NPU communication).

## Implications for synthetic trace design

The synthetic generator should produce:

1. **One dominant path** (80% of events) with dense bursts and long compute gaps (~100ms)
2. **Multiple worker paths** (2-3% each) with sparse, evenly-distributed events
3. **Iteration-aligned structure**: burst (data loading) → compute gap → burst
4. **Realistic BW ranges**: local NUMA 8-23 GB/s, cross-NUMA 0.6-10 GB/s
5. **Per-path variety**: some paths should have large gaps (p90 > 100ms), others small (p90 < 1ms)

The new `generate_realistic_trace.py` models this with configurable parameters.

## Comparison: synthetic vs real

| Metric | Real (GLM-6B) | Synthetic (v2, glm mode) |
|---|---|---|
| Events | 1054 | 273 (50 iterations) |
| Duration | 6077s | 33s |
| Paths | 11 | 8 |
| Dominant path events | 840 (80%) | 232 (85%) |
| Dominant gap p90 | 133.4 ms | 320.7 ms |
| Secondary gap p50 | 0.3-0.5 ms | 1.1-6.8 s (too sparse) |

**Gap:** The synthetic trace is still too compressed. Secondary paths are too sparse because the 50-iteration window is too short relative to the compute gaps. For predictor testing, increase iterations to 500+ for better secondary path coverage.
