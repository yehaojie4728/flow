# Probe Scheduler — Online Monitoring

Lightweight real-time NPU telemetry during live MindSpore training.

## Architecture

```
Terminal 1: bash run_distribute.sh   →  GLM-6B training  (8× NPU)
Terminal 1: eBPF tracer (background)  →  trace CSV  (tail -f)
Terminal 2: online_loop.py            →  read trace → predict → execute probes
```

## Quick start

### Step 1: Start training + eBPF tracer

```bash
cd /root/FlowGap-work/FlowGap-paper
nohup bash scripts/collect_glm6b_pass2.sh > logs/pass2_latest.log 2>&1 &
```

### Step 2: Start online probe loop (separate terminal)

```bash
cd /root/FlowGap-work/FlowGap-paper/code
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37

# Dry run first — verify policy decisions without touching NPU
PYTHONPATH=.:trace_parser python probe_scheduler/online_loop.py \
    --trace-log ../data/collected/pass2_raw.log \
    --probe-policy threshold \
    --dry-run

# Live run (needs training on NPU)
PYTHONPATH=.:trace_parser python probe_scheduler/online_loop.py \
    --trace-log ../data/collected/pass2_raw.log \
    --probe-policy flowgap_predictive \
    --budget-per-sec 5
```

### Step 3: Run executor tests (no training needed, but NPU must be free)

```bash
cd /root/FlowGap-work/FlowGap-paper/code
source /root/anaconda3/etc/profile.d/conda.sh
conda activate mindspore_py37
FLOWGAP_TEST_NPU=1 PYTHONPATH=.:trace_parser \
    python probe_scheduler/test_probe_executor.py
```

## Files

| File | Purpose |
|---|---|
| `probe_executor.py` | AscendCL ctypes wrapper — real memcpy probes on NPU |
| `online_loop.py` | Main event loop: tail trace → predict → execute |
| `test_probe_executor.py` | Tests (binding only in sandbox, full with NPU) |

## Probe executor

Uses ctypes to call `libascendcl.so` directly — no C++ compilation needed.

Uses a **separate AscendCL stream** from MindSpore training to avoid HCCL interference.

| Probe | Size | Iterations | Expected latency (same NUMA) |
|---|---|---|---|
| Tiny latency | 4 KB | 1 | ~50 µs |
| Normal latency | 4 KB | 10 | ~500 µs |
| Bandwidth | 128 MB | 1 | ~5 ms |

## Safety isolation

1. **Separate AscendCL stream**: Probe executor creates its own `aclrtCreateStream()`, never touches the training stream. HCCL communication is unaffected.
2. **Separate device context**: Probe executor calls `aclInit("flowgap_probe")`, MindSpore uses its own context. No shared state.
3. **Persistent buffers**: Host and device buffers allocated once at startup, reused across probes — no malloc overhead during probing.
4. **Budget enforcement**: `--budget-per-sec` limits probe rate to avoid saturating memory bandwidth.

## Policies (from scheduler_replay)

The online loop uses the same 7 policies from `scheduler_replay/policies.py`:

| Policy | Description |
|---|---|
| `no_probing` | Zero probes |
| `fixed_interval` | One probe every K ms |
| `random` | Random probe on each gap |
| `threshold` | Probe when gap exceeds bandwidth threshold |
| `ewma_only` | EWMA-based prediction (Tier 0) |
| `flowgap_predictive` | Full GBDT predictor (Tier 1) |
| `oracle` | Knows all future gaps |

## Dry run mode

`--dry-run` logs decisions without calling AscendCL. Safe to run anytime:

```
[DRY] Path 28068: TINY_LATENCY in gap 197µs
[DRY] Path 12338: BANDWIDTH in gap 18231µs
[SKIP] Path 34364: Gap 120µs < probe 5000µs
```
