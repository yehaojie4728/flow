#!/usr/bin/env python3
"""
Generate a synthetic Ascend memcpy trace for FlowGap parser testing.
Clearly labeled as SYNTHETIC — not from real Ascend hardware.

Produces a raw CSV trace with controllable burst-gap patterns,
suitable for unit testing the trace parser and intervalizer.

Output: data/processed/trace_synthetic_burst1ms.csv
"""

import csv
import os
import random
import sys

from pathlib import Path

# Add parent to path so we can import schema
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "trace_parser"))

from schema import (
    QualityFlag,
    FLOWGAP_COLUMNS,
    Direction,
    HOST_DEVICE_ID,
    UNKNOWN_NUMA,
)


def generate_synthetic_trace(
    output_path: str,
    num_events: int = 200,
    seed: int = 42,
):
    """Generate synthetic trace with structured burst-gap patterns.

    Pattern per path:
      - Burst: 3-5 memcpy events with 0.5-2ms gaps between events
      - Gap: 5-20ms idle between bursts
      - 3 distinct paths: H2D to NPU 0, H2D to NPU 1, D2H from NPU 0

    Parameters
    ----------
    output_path : where to write CSV
    num_events : total events across all paths (~67 per path for 3 paths)
    seed : random seed for reproducibility
    """
    random.seed(seed)
    rng = random.Random(seed)

    BASE_TIME_NS = 1_000_000_000_000  # 1000s monotonic offset
    WALL_BASE_NS = 1_777_455_000_000_000_000  # approximate wall clock from HostDiagV2 sample

    # Path definitions: (src_dev, dst_dev, src_numa, dst_numa, direction)
    paths = [
        (HOST_DEVICE_ID, 0, 0, UNKNOWN_NUMA, Direction.H2D),   # Host NUMA 0 → NPU 0
        (HOST_DEVICE_ID, 1, 1, UNKNOWN_NUMA, Direction.H2D),   # Host NUMA 1 → NPU 1
        (0, HOST_DEVICE_ID, UNKNOWN_NUMA, 2, Direction.D2H),   # NPU 0 → Host NUMA 2
    ]

    events = []

    for path_idx, (src_dev, dst_dev, src_numa, dst_numa, direction) in enumerate(paths):
        # Each path: alternate bursts and gaps
        t_ns = BASE_TIME_NS + path_idx * 50_000_000_000  # stagger paths by 50ms
        pid = 2771200 + path_idx
        tid = pid
        events_per_path = num_events // len(paths)
        ev_count = 0

        while ev_count < events_per_path:
            # ---- Burst phase: 3-5 events with small inter-event gaps ----
            burst_size = rng.randint(3, 5)
            for i in range(burst_size):
                if ev_count >= events_per_path:
                    break
                size_bytes = rng.choice([
                    24 * 1024 * 1024,
                    31 * 1024 * 1024,
                    64 * 1024 * 1024,
                    128 * 1024 * 1024,
                    256 * 1024 * 1024,
                ])
                # Latency depends on size + direction
                if direction == Direction.H2D:
                    bw_gbps = rng.uniform(6.0, 16.0)
                else:
                    bw_gbps = rng.uniform(5.0, 12.0)
                latency_us = (size_bytes / 1e9) / (bw_gbps / 1e6)
                t_end = t_ns + int(latency_us * 1000)

                e = [
                    pid, tid,
                    src_dev, dst_dev, src_numa, dst_numa,
                    f"{size_bytes / 1e6:.2f}",
                    f"{latency_us:.2f}",
                    f"{bw_gbps:.2f}",
                    t_ns, t_end,
                    WALL_BASE_NS + t_ns,
                    WALL_BASE_NS + t_end,
                    int(direction), 0, 0,  # async_flag=0, api_type=0 (MEMCPY)
                    0,                    # stream_id
                    0, 0,                 # path_id, link_bitmap (computed by normalizer)
                    int(QualityFlag.SYNTHETIC),
                ]
                events.append(e)

                # inter-event gap within burst
                inter_event_gap_us = rng.randint(500, 2000)  # 0.5-2 ms
                t_ns = t_end + inter_event_gap_us * 1000
                ev_count += 1

            # ---- Gap phase: longer idle ----
            gap_us = rng.randint(5_000, 20_000)  # 5-20 ms
            t_ns += gap_us * 1000

    # Sort all events by start_ns
    events.sort(key=lambda e: int(float(e[9])))  # start_ns is column 9

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FLOWGAP_COLUMNS)
        for e in events:
            writer.writerow(e)

    print(f"[synthetic_trace] Wrote {len(events)} synthetic events → {output_path}")
    print(f"[synthetic_trace] seed={seed}, paths={len(paths)}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data/processed/trace_synthetic_burst1ms.csv"
    generate_synthetic_trace(output)
