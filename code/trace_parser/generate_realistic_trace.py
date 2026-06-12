#!/usr/bin/env python3
"""
Realistic synthetic Ascend memcpy trace generator for FlowGap.

Models AI training workloads (GLM-6B finetuning on 8× Ascend 910B) with:
  - Multi-path: 1 dominant data-loader path + N secondary worker paths
  - Iteration-aligned: burst (data loading) → gap (compute) cycles
  - Realistic sizes: 24MB-1GB per memcpy, matching GLM-6B trace ranges
  - Realistic BW: 0.6-23 GB/s depending on NUMA proximity

Output: data/processed/trace_synthetic_realistic_v2.csv
        data/processed/trace_synthetic_small_v2.csv  (200-event test set)

Clearly labeled SYNTHETIC via quality_flags.
"""

import csv
import os
import random
import sys
from pathlib import Path

# Add parent to path for schema
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trace_parser"))

from schema import QualityFlag, FLOWGAP_COLUMNS, Direction, HOST_DEVICE_ID, UNKNOWN_NUMA


# ============================================================================
# Configuration
# ============================================================================

CROSS_NUMA_BW_RANGE = (0.6, 10.0)     # cross-NUMA H2D — slower
LOCAL_NUMA_BW_RANGE = (8.0, 23.0)     # same-NUMA H2D — faster

MEMCPY_SIZES_MB = [
    24.5, 31.5, 64.0, 128.0, 259.0, 388.0, 1040.0,
]

# ============================================================================
# Path definitions (matching GLM-6B finetuning on 8× Ascend 910B)
# ============================================================================

def build_glm_finetune_paths(n_npus: int = 8, data_loader_numa: int = 0):
    """Build path list matching GLM-6B finetuning topology.

    Returns list of (src_dev, dst_dev, src_numa, dst_numa, direction, local_numa).
    """
    # Ascend 910B: NPU 0-3 on NUMA 0-3, NPU 4-7 on NUMA 0-3 (second fabric)
    # CPU groups: NPU 4,5 → NUMA 0,1; NPU 6,7 → NUMA 2,3; NPU 2,3 → NUMA 4,5; NPU 0,1 → NUMA 6,7
    npu_to_numa = {0: 6, 1: 7, 2: 4, 3: 5, 4: 0, 5: 1, 6: 2, 7: 3}

    paths = []
    # Dominant data-loader path: NUMA 0 → its local NPU
    for npu_id in range(n_npus):
        numa_id = npu_to_numa.get(npu_id, npu_id % 8)
        local = (numa_id == data_loader_numa)
        paths.append({
            "src_dev": HOST_DEVICE_ID, "dst_dev": npu_id,
            "src_numa": data_loader_numa, "dst_numa": UNKNOWN_NUMA,
            "direction": Direction.H2D,
            "local_numa": local,
            "weight": 0.80 if npu_id == 2 else 0.02,  # 80% to primary NPU
        })
    return paths


def build_simple_paths(n_paths: int = 3):
    """Build simple 3-path topology for unit testing."""
    paths = []
    for i in range(n_paths):
        paths.append({
            "src_dev": HOST_DEVICE_ID, "dst_dev": i,
            "src_numa": i, "dst_numa": UNKNOWN_NUMA,
            "direction": Direction.H2D,
            "local_numa": (i == 0),
            "weight": 1.0 / n_paths,
        })
    return paths


# ============================================================================
# Generator
# ============================================================================

def generate_realistic_trace(
    output_path: str,
    paths: list = None,
    num_iterations: int = 50,
    events_per_burst: tuple = (3, 8),
    inter_burst_gap_ms: tuple = (20, 500),
    intra_burst_gap_us: tuple = (200, 3000),
    seed: int = 42,
):
    """Generate an iteration-aligned synthetic trace.

    Workload model:
      Each iteration:
        1. BURST phase: events_per_burst memcpy calls, each targeting a
           path chosen by weighted random. Intra-burst gaps: 200us-3ms.
        2. GAP phase: 20-500ms idle (compute phase).

    Parameters
    ----------
    output_path : where to write CSV
    paths : list of path dicts from build_glm_finetune_paths() or build_simple_paths()
    num_iterations : number of training iterations
    events_per_burst : (min, max) events per iteration burst
    inter_burst_gap_ms : (min, max) gap between iterations in ms
    intra_burst_gap_us : (min, max) gap between events within a burst in us
    seed : random seed
    """
    if paths is None:
        paths = build_simple_paths(3)

    rng = random.Random(seed)
    random.seed(seed)

    BASE_TIME_NS = 1_000_000_000_000
    WALL_BASE_NS = 1_777_455_000_000_000_000

    events = []
    pid_base = 2771200
    t_ns = BASE_TIME_NS
    global_ev = 0

    # Weighted path selection
    path_weights = [p["weight"] for p in paths]
    total_weight = sum(path_weights)

    for iteration in range(num_iterations):
        # ---- BURST phase ----
        burst_n = rng.randint(events_per_burst[0], events_per_burst[1])

        for _ in range(burst_n):
            # Weighted random path selection
            r = rng.uniform(0, total_weight)
            cumulative = 0.0
            chosen = paths[0]
            for p in paths:
                cumulative += p["weight"]
                if r <= cumulative:
                    chosen = p
                    break

            size_bytes = int(rng.choice(MEMCPY_SIZES_MB) * 1024 * 1024)
            bw_range = LOCAL_NUMA_BW_RANGE if chosen["local_numa"] else CROSS_NUMA_BW_RANGE
            bw_gbps = rng.uniform(bw_range[0], bw_range[1])
            latency_us = (size_bytes / 1e9) / (bw_gbps / 1e6)
            t_end = t_ns + int(latency_us * 1000)

            e = [
                pid_base + (chosen["dst_dev"] % 8),
                pid_base + (chosen["dst_dev"] % 8) + iteration,
                chosen["src_dev"], chosen["dst_dev"],
                chosen["src_numa"], chosen["dst_numa"],
                f"{size_bytes / 1e6:.2f}",
                f"{latency_us:.2f}",
                f"{bw_gbps:.2f}",
                t_ns, t_end,
                WALL_BASE_NS + t_ns,
                WALL_BASE_NS + t_end,
                int(chosen["direction"]), 0, 0,
                0, 0, 0,
                int(QualityFlag.SYNTHETIC),
            ]
            events.append(e)

            # Intra-burst gap
            gap_us = rng.randint(intra_burst_gap_us[0], intra_burst_gap_us[1])
            t_ns = t_end + gap_us * 1000
            global_ev += 1

        # ---- GAP phase ----
        gap_ms = rng.randint(inter_burst_gap_ms[0], inter_burst_gap_ms[1])
        t_ns += gap_ms * 1_000_000

    # Sort by start_ns
    events.sort(key=lambda e: int(float(e[9])))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FLOWGAP_COLUMNS)
        for e in events:
            writer.writerow(e)

    print(f"[synthetic] Wrote {len(events)} events → {output_path}")
    print(f"[synthetic] {num_iterations} iterations, {len(paths)} paths, seed={seed}")


# ============================================================================
# Analysis function
# ============================================================================

def analyze_trace(path: str):
    """Print summary statistics for any trace CSV."""
    sys.path.insert(0, "trace_parser")
    from parse_trace import parse_csv, group_by_path
    from intervalize import build_timeline, compute_gap_stats, compute_safe_window_availability

    events = parse_csv(path)
    is_synth = all(e.is_synthetic for e in events)
    is_real = all(not e.is_synthetic for e in events)
    source = "SYNTHETIC" if is_synth else ("REAL" if is_real else "MIXED")

    dur = (events[-1].ts_exit_ns - events[0].ts_enter_ns) / 1e9
    print(f"\n{'='*60}")
    print(f"Trace: {path}  [{source}]")
    print(f"Events: {len(events)}, Duration: {dur:.0f}s")
    print(f"Directions: {set(e.direction_label for e in events)}")
    print(f"Sizes: {min(e.size_mb for e in events):.0f}-{max(e.size_mb for e in events):.0f} MB")

    groups = group_by_path(events)
    print(f"Unique paths: {len(groups)}")

    for pk, evs in sorted(groups.items(), key=lambda x: -len(x[1])):
        busy, gaps = build_timeline(evs, 50_000, 100_000, path_id=hash(pk) & 0xFFFF)
        stats = compute_gap_stats(gaps)
        dir_label = evs[0].direction_label
        print(f"  Path ({dir_label}): {len(evs)} ev, gaps: {stats['count']}, "
              f"p50={stats['p50_ns']/1e6:.1f}ms p90={stats['p90_ns']/1e6:.1f}ms")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate realistic synthetic Ascend memcpy traces")
    parser.add_argument("--mode", choices=["glm", "simple", "analyze"], default="glm",
                        help="Workload mode: glm=GLM-6B style, simple=basic 3-path, analyze=analyze existing trace")
    parser.add_argument("--output", default="data/processed/trace_synthetic_realistic_v2.csv")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--events-per-burst", type=int, nargs=2, default=[3, 8])
    parser.add_argument("--burst-gap-ms", type=int, nargs=2, default=[20, 500])
    parser.add_argument("--intra-gap-us", type=int, nargs=2, default=[200, 3000])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", default="", help="Path to trace for analyze mode")
    args = parser.parse_args()

    if args.mode == "analyze":
        analyze_trace(args.input or args.output)
    elif args.mode == "glm":
        paths = build_glm_finetune_paths(8)
        generate_realistic_trace(
            args.output, paths,
            num_iterations=args.iterations,
            events_per_burst=tuple(args.events_per_burst),
            inter_burst_gap_ms=tuple(args.burst_gap_ms),
            intra_burst_gap_us=tuple(args.intra_gap_us),
            seed=args.seed,
        )
        analyze_trace(args.output)
    else:  # simple
        paths = build_simple_paths(3)
        generate_realistic_trace(
            args.output, paths,
            num_iterations=args.iterations,
            events_per_burst=tuple(args.events_per_burst),
            inter_burst_gap_ms=tuple(args.burst_gap_ms),
            intra_burst_gap_us=tuple(args.intra_gap_us),
            seed=args.seed,
        )
        analyze_trace(args.output)
