# FlowGap Trace Parser

Parses raw CSV trace files into normalized, per-path busy-idle timelines with probe-aware interval merging.

**Validated against real GLM-6B finetuning trace (1054 events, 1.7h, 11 paths).**

## Quick start

```bash
cd code

# Generate a realistic synthetic trace (GLM-6B finetuning style)
python trace_parser/generate_realistic_trace.py --mode glm --iterations 200

# Or use the simple 3-path generator for unit tests
python trace_parser/generate_synthetic_trace.py data/processed/trace_synthetic_burst1ms.csv

# Parse a real HostDiagV2 trace
python -c "from trace_parser.parse_trace import parse_csv; e=parse_csv('../data/raw/aclrtMemcpy_numa_raw.log'); print(len(e), 'events')"

# Analyze any trace (synthetic or real)
python trace_parser/generate_realistic_trace.py --mode analyze --input ../data/raw/aclrtMemcpy_numa_raw.log

# Build busy-idle timelines (per-path mode)
python trace_parser/intervalize.py ../data/raw/aclrtMemcpy_numa_raw.log --per-path

# Run unit tests
PYTHONPATH=trace_parser python trace_parser/test_trace_parser.py
```

## Files

| File | Purpose |
|---|---|
| `schema.py` | Data structures: `FlowEvent`, `BusyInterval`, `Gap`, enums, validation |
| `parse_trace.py` | CSV parser supporting HostDiagV2 (11-column) and FlowGap (21-column) formats |
| `intervalize.py` | Probe-aware intervalization: micro-gap merging, gap extraction, overlap detection, statistics |
| `generate_synthetic_trace.py` | Simple 3-path synthetic trace generator (unit test quality) |
| `generate_realistic_trace.py` | Realistic multi-path generator modeling GLM-6B finetuning workloads |
| `test_trace_parser.py` | Unit tests (38 tests, all pass) |

## Input formats

### HostDiagV2 legacy (from `external/reference_repo/`)

```csv
PID,TID,Source,Destination,Size_MB,Latency_us,Bandwidth_GBps,Start_ns,End_ns,WallStart_ns,WallEnd_ns
```

Source/Destination are strings like `Host(NUMA 0)` or `NPU 2`. Direction is inferred.

### FlowGap extended

```csv
pid,tid,src_dev,dst_dev,src_numa,dst_numa,size_mb,latency_us,bw_gbps,start_ns,end_ns,wall_start_ns,wall_end_ns,direction,async_flag,api_type,stream_id,path_id,link_bitmap,quality_flags
```

All fields numeric. Format auto-detected by header inspection.

## Key concepts

### Probe-aware intervalization

Two busy intervals are merged if the gap between them is shorter than `min_probe_duration_ns + safety_margin_ns`. This ensures that only gaps large enough for a real probe are treated as separate idle windows.

### Per-path timelines

Events are grouped by `(src_dev, dst_dev, direction, src_numa, dst_numa)`. Each group gets its own busy-idle timeline, enabling path-specific prediction.

### Synthetic trace labeling

All synthetic events carry `quality_flags & SYNTHETIC`, allowing downstream code to distinguish generated data from real hardware traces.

## Dependencies

Python 3.8+ standard library only. No external packages required.

## Design documentation

See `../../docs/trace_parser_design.md` for detailed design rationale.
