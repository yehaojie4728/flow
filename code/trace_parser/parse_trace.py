"""
Trace parser — reads raw CSV traces (HostDiagV2 legacy or FlowGap extended format),
validates, normalizes, and converts to FlowEvent stream.

Supports two input CSV formats:
  - HostDiagV2 legacy: 11 columns (pid..wall_end_ns) with string src/dst
  - FlowGap extended: 21 columns (pid..quality_flags) with numeric src/dst

Output: sorted list of FlowEvent objects.
"""

from __future__ import annotations

import csv
import os
import sys
from typing import Iterator, List, Optional, Tuple

from schema import (
    FlowEvent,
    Direction,
    ApiType,
    QualityFlag,
    HOST_DEVICE_ID,
    UNKNOWN_NUMA,
    UNKNOWN_DEVICE,
    HOSTDIAG_COLUMNS_V2,
    FLOWGAP_COLUMNS,
)


# ---------------------------------------------------------------------------
# HostDiagV2 → FlowGap normalization helpers
# ---------------------------------------------------------------------------

def _parse_hostdiag_source(s: str) -> Tuple[int, int]:
    """Parse 'Host(NUMA 0)' → (HOST_DEVICE_ID, 0),
    'NPU 2' → (2, UNKNOWN_NUMA), 'Device ?' → (UNKNOWN_DEVICE, UNKNOWN_NUMA).
    """
    s = s.strip()
    if s.startswith("Host(NUMA "):
        try:
            numa = int(s[len("Host(NUMA "):-1])
            return (HOST_DEVICE_ID, numa)
        except (ValueError, IndexError):
            return (HOST_DEVICE_ID, UNKNOWN_NUMA)
    if s.startswith("NPU "):
        try:
            npu = int(s[4:])
            return (npu, UNKNOWN_NUMA)
        except ValueError:
            return (UNKNOWN_DEVICE, UNKNOWN_NUMA)
    if s == "Device ?":
        return (UNKNOWN_DEVICE, UNKNOWN_NUMA)
    return (UNKNOWN_DEVICE, UNKNOWN_NUMA)


def _infer_direction_from_hostdiag(src: str, dst: str) -> int:
    """Infer direction from HostDiagV2 string source/destination.
    Host→NPU = H2D, NPU→Host = D2H, NPU→NPU = D2D, Host→Host = H2H.
    """
    src_is_host = src.startswith("Host")
    dst_is_host = dst.startswith("Host")
    src_is_npu = src.startswith("NPU")
    dst_is_npu = dst.startswith("NPU")
    if src_is_host and dst_is_npu:
        return Direction.H2D
    if src_is_npu and dst_is_host:
        return Direction.D2H
    if src_is_npu and dst_is_npu:
        return Direction.D2D
    if src_is_host and dst_is_host:
        return Direction.H2H
    return Direction.H2D  # default


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

def _detect_format(header: List[str]) -> str:
    """Return 'hostdiag_v2', 'flowgap', or 'unknown' based on header."""
    header_lower = [h.lower().strip() for h in header]
    # Size field is mandatory for both formats
    has_size = any(h in header_lower for h in ("size_mb", "size_mb"))
    has_bw = any(h in header_lower for h in ("bw_gbps", "bandwidth_gbps"))
    if has_size and has_bw:
        if "quality_flags" in header_lower:
            return "flowgap"
        if "source" in header_lower and "destination" in header_lower:
            return "hostdiag_v2"
        # bare minimum: pid, size, start_ns, end_ns
        has_start = any(h in header_lower for h in ("start_ns", "start_ns"))
        has_end = any(h in header_lower for h in ("end_ns", "end_ns"))
        if has_start and has_end:
            return "hostdiag_v2"
    # Fallback: try matching specific known headers
    if "source" in header_lower and "destination" in header_lower:
        return "hostdiag_v2"
    return "unknown"


def _resolve_column(row: list, idx: dict, *names: str, default: str = "0") -> str:
    """Try multiple column names (case-insensitive), return first match."""
    for name in names:
        if name in idx:
            return row[idx[name]]
        alias = name.lower().strip()
        for k, v in idx.items():
            if k.lower().strip() == alias:
                return row[v]
    return default


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_hostdiag_csv(path: str) -> List[FlowEvent]:
    """Parse HostDiagV2 legacy CSV into FlowEvent list. Normalizes string
    src/dst to numeric dev/nouma, infers direction from src/dst strings."""
    events: List[FlowEvent] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path}: empty file")

        fmt = _detect_format(header)
        if fmt == "unknown":
            raise ValueError(
                f"{path}: unknown CSV format. "
                f"Expected HostDiagV2 (11 cols) or FlowGap extended (21 cols). "
                f"Got header: {header[:5]}..."
            )

        # build column index
        idx: dict = {}
        for i, col in enumerate(header):
            idx[col.lower().strip()] = i

        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue

            try:
                pid = int(row[idx.get("pid", 0)])
                tid = int(row[idx.get("tid", 0)])
                size_mb = float(row[idx.get("size_mb", 0)])
                start_ns = int(float(row[idx.get("start_ns", 0)]))
                end_ns = int(float(row[idx.get("end_ns", 0)]))
                wall_start_ns = int(float(row[idx.get("wall_start_ns", 0)]))
                wall_end_ns = int(float(row[idx.get("wall_end_ns", 0)]))
            except (ValueError, IndexError, KeyError) as e:
                print(f"[parse_trace] skipping row: {e}", file=sys.stderr)
                continue

            if fmt == "hostdiag_v2":
                # parse string src/dst
                src_str = row[idx.get("source", idx.get("source", 0))] if "source" in idx else "?"
                dst_str = row[idx.get("destination", idx.get("destination", 0))] if "destination" in idx else "?"
                src_dev, src_numa = _parse_hostdiag_source(src_str)
                dst_dev, dst_numa = _parse_hostdiag_source(dst_str)
                direction = _infer_direction_from_hostdiag(src_str, dst_str)
                async_flag = 0      # HostDiagV2 only hooks sync aclrtMemcpy
                api_type = ApiType.MEMCPY
                stream_id = 0
                path_id = 0
                link_bitmap = 0
                quality_flags = QualityFlag.NONE
                if src_dev == UNKNOWN_DEVICE or dst_dev == UNKNOWN_DEVICE:
                    quality_flags |= QualityFlag.UNKNOWN_DEVICE
            elif fmt == "flowgap":
                src_dev = int(row[idx.get("src_dev", 0)])
                dst_dev = int(row[idx.get("dst_dev", 0)])
                src_numa = int(row[idx.get("src_numa", 0)])
                dst_numa = int(row[idx.get("dst_numa", 0)])
                direction = int(row[idx.get("direction", Direction.H2D)])
                async_flag = int(row[idx.get("async_flag", 0)])
                api_type = int(row[idx.get("api_type", ApiType.MEMCPY)])
                stream_id = int(row[idx.get("stream_id", 0)])
                path_id = int(row[idx.get("path_id", 0)])
                link_bitmap = int(row[idx.get("link_bitmap", 0)])
                quality_flags = int(row[idx.get("quality_flags", 0)])
            else:
                continue

            size_bytes = int(size_mb * 1024 * 1024)
            latency_us = (end_ns - start_ns) / 1000.0

            event = FlowEvent(
                ts_enter_ns=start_ns,
                ts_exit_ns=end_ns,
                ts_submit_ns=start_ns,          # sync: same as enter
                ts_end_est_ns=end_ns,            # sync: same as exit
                ts_wall_ns=wall_start_ns,
                pid=pid,
                tid=tid,
                stream_id=stream_id,
                src_dev=src_dev,
                dst_dev=dst_dev,
                src_numa=src_numa,
                dst_numa=dst_numa,
                size=size_bytes,
                direction=direction,
                async_flag=async_flag,
                api_type=api_type,
                path_id=path_id,
                link_bitmap=link_bitmap,
                quality_flags=quality_flags,
            )
            events.append(event)

    return events


def parse_flowgap_csv(path: str) -> List[FlowEvent]:
    """Parse FlowGap extended CSV (21 columns) into FlowEvent list."""
    # Same function, just calls through parse_hostdiag_csv which detects format
    return parse_hostdiag_csv(path)


def parse_csv(path: str) -> List[FlowEvent]:
    """Parse any supported CSV format. Returns sorted list (by start_ns)."""
    events = parse_hostdiag_csv(path)
    events.sort(key=lambda e: e.ts_enter_ns)
    return events


def compute_path_key(event: FlowEvent) -> Tuple[int, int, int, int, int]:
    """Compute a stable path grouping key from an event.

    Returns (src_dev, dst_dev, direction, src_numa, dst_numa).
    Events with the same key belong to the same logical path.
    """
    return (event.src_dev, event.dst_dev, event.direction,
            event.src_numa, event.dst_numa)


def group_by_path(events: List[FlowEvent]) -> dict:
    """Group events by path key. Returns dict[path_key] → List[FlowEvent]."""
    groups: dict = {}
    for ev in events:
        key = compute_path_key(ev)
        groups.setdefault(key, []).append(ev)
    return groups


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Parse FlowGap / HostDiagV2 trace CSV")
    parser.add_argument("input", help="Path to raw trace CSV")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    parser.add_argument("--output", default="", help="Output CSV path (flowgap format)")
    args = parser.parse_args()

    events = parse_csv(args.input)
    print(f"Parsed {len(events)} events from {args.input}")

    if args.summary:
        groups = group_by_path(events)
        print(f"Unique paths: {len(groups)}")
        print(f"Time range: {events[0].ts_enter_ns} → {events[-1].ts_exit_ns} ns "
              f"({(events[-1].ts_exit_ns - events[0].ts_enter_ns) / 1e9:.3f} s)")
        for pk, evs in sorted(groups.items()):
            print(f"  Path {pk}: {len(evs)} events, "
                  f"{sum(e.size for e in evs) / 1e6:.1f} MB total")

    if args.output:
        with open(args.output, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(FLOWGAP_COLUMNS)
            for ev in events:
                w.writerow([
                    ev.pid, ev.tid,
                    ev.src_dev, ev.dst_dev, ev.src_numa, ev.dst_numa,
                    f"{ev.size_mb:.2f}", f"{ev.latency_us:.2f}", f"{ev.bw_gbps:.2f}",
                    ev.ts_enter_ns, ev.ts_exit_ns,
                    ev.ts_wall_ns, ev.ts_wall_ns,  # wall_start, wall_end ≈ submit time for parsed
                    ev.direction, ev.async_flag, ev.api_type,
                    ev.stream_id,
                    ev.path_id, ev.link_bitmap,
                    ev.quality_flags,
                ])
        print(f"Wrote FlowGap CSV → {args.output}")


if __name__ == "__main__":
    main()
