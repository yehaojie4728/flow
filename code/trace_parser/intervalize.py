"""
Probe-aware event-driven intervalization.

Converts a sorted list of FlowEvent objects (per path) into:
  1. Busy intervals — merged when gaps are smaller than the micro-gap threshold.
  2. Gaps — idle periods between busy intervals, classified as safe/unsafe.

Key algorithm (probe-aware merging):
  For a sorted list of events on the same path:
    1. Start with an empty busy interval list.
    2. For each event [t_start, t_end]:
       - If it overlaps or the gap to the previous interval < threshold: merge.
       - Otherwise: flush previous, start new.
    3. After merging, gaps between remaining intervals form the idle timeline.

Reference: docs/outline.md §4.2.3, docs/trace_schema.md §3.1
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from schema import (
    FlowEvent,
    BusyInterval,
    Gap,
    QualityFlag,
)


# ---------------------------------------------------------------------------
# Probe-aware busy interval merging
# ---------------------------------------------------------------------------

def build_busy_intervals(
    events: List[FlowEvent],
    micro_gap_threshold_ns: int,
    safety_margin_ns: int = 0,
) -> List[BusyInterval]:
    """Convert sorted event list to merged busy intervals.

    Two consecutive intervals [A.end, B.start] are merged if:
        B.start - A.end < micro_gap_threshold_ns

    Parameters
    ----------
    events : sorted list of FlowEvent (ascending ts_enter_ns)
    micro_gap_threshold_ns : gaps shorter than this are merged
    safety_margin_ns : additional safety margin added to threshold
                       (effective threshold = micro_gap_threshold_ns + safety_margin_ns)

    Returns
    -------
    List of BusyInterval, sorted by start_ns.
    """
    if not events:
        return []

    threshold = micro_gap_threshold_ns + safety_margin_ns
    intervals: List[BusyInterval] = []

    for ev in events:
        s, e = ev.ts_enter_ns, ev.ts_exit_ns
        # Sanity check
        if e < s:
            continue

        if not intervals:
            intervals.append(BusyInterval(
                start_ns=s, end_ns=e,
                path_id=ev.path_id, link_bitmap=ev.link_bitmap,
                bytes_total=ev.size, event_count=1,
            ))
            continue

        last = intervals[-1]

        # Overlap case: event starts before last interval ends
        if s <= last.end_ns + threshold:
            last.end_ns = max(last.end_ns, e)
            last.bytes_total += ev.size
            last.event_count += 1
            last.merged = True
        else:
            intervals.append(BusyInterval(
                start_ns=s, end_ns=e,
                path_id=ev.path_id, link_bitmap=ev.link_bitmap,
                bytes_total=ev.size, event_count=1,
            ))

    return intervals


def build_busy_intervals_probe_aware(
    events: List[FlowEvent],
    min_probe_duration_ns: int,
    safety_margin_ns: int,
) -> List[BusyInterval]:
    """Probe-aware intervalization: merge gaps that are too short
    for any probe (gap < min_probe_duration_ns + safety_margin_ns).

    This is the primary intervalization method for FlowGap.

    Parameters
    ----------
    events : sorted list of FlowEvent
    min_probe_duration_ns : minimum duration of the smallest probe (e.g., 50_000 ns for tiny latency)
    safety_margin_ns : additional safety margin

    Returns
    -------
    List of merged BusyInterval.
    """
    threshold = min_probe_duration_ns + safety_margin_ns
    return build_busy_intervals(events, micro_gap_threshold_ns=threshold)


# ---------------------------------------------------------------------------
# Gap extraction
# ---------------------------------------------------------------------------

def extract_gaps(
    intervals: List[BusyInterval],
    path_id: int,
    link_bitmap: int = 0,
) -> List[Gap]:
    """Extract idle gaps between busy intervals.

    For consecutive busy intervals I_i, I_{i+1}:
        gap = Gap(start_ns=I_i.end_ns, end_ns=I_{i+1}.start_ns)
    """
    if len(intervals) < 2:
        return []

    gaps: List[Gap] = []
    for i in range(len(intervals) - 1):
        gap = Gap(
            start_ns=intervals[i].end_ns,
            end_ns=intervals[i + 1].start_ns,
            path_id=path_id,
            link_bitmap=link_bitmap,
        )
        if gap.duration_ns > 0:
            gaps.append(gap)
    return gaps


# ---------------------------------------------------------------------------
# Timeline building
# ---------------------------------------------------------------------------

def build_timeline(
    events: List[FlowEvent],
    min_probe_duration_ns: int,
    safety_margin_ns: int,
    path_id: int,
    link_bitmap: int = 0,
) -> Tuple[List[BusyInterval], List[Gap]]:
    """Build the full busy-idle timeline for a single path.

    Returns (busy_intervals, gaps).
    """
    if not events:
        return ([], [])

    # Ensure sorted by start time
    events = sorted(events, key=lambda e: e.ts_enter_ns)

    busy = build_busy_intervals_probe_aware(
        events, min_probe_duration_ns, safety_margin_ns
    )
    gaps = extract_gaps(busy, path_id, link_bitmap)
    return (busy, gaps)


# ---------------------------------------------------------------------------
# Overlap calculation for probe events
# ---------------------------------------------------------------------------

def calc_overlap(
    probe_start_ns: int,
    probe_end_ns: int,
    busy_intervals: List[BusyInterval],
) -> Tuple[bool, int]:
    """Check if a probe overlaps with any busy interval.

    Returns (overlap_flag: bool, actual_idle_before_ns: int).
    actual_idle_before_ns = duration of gap before the first busy interval
    that the probe intersects.
    """
    for bi in busy_intervals:
        # Probe starts or spans into a busy interval
        if probe_start_ns < bi.end_ns and probe_end_ns > bi.start_ns:
            # How much idle time before this busy interval?
            # This is approximate; for precise measurement need gap info.
            idle_before = max(0, bi.start_ns - probe_start_ns)
            return (True, idle_before)
    return (False, 0)


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def compute_gap_stats(gaps: List[Gap]) -> dict:
    """Compute summary statistics over a list of gaps.

    Returns dict with keys: count, min_ns, max_ns, p50_ns, p90_ns, total_ns.
    """
    if not gaps:
        return {"count": 0, "min_ns": 0, "max_ns": 0,
                "p50_ns": 0, "p90_ns": 0, "total_ns": 0}

    durations = sorted(g.duration_ns for g in gaps)
    n = len(durations)
    p50 = durations[n // 2]
    p90 = durations[int(n * 0.9)]
    return {
        "count": n,
        "min_ns": durations[0],
        "max_ns": durations[-1],
        "p50_ns": p50,
        "p90_ns": p90,
        "total_ns": sum(durations),
    }


def compute_safe_window_availability(
    gaps: List[Gap],
    probe_durations_ns: List[int],
    safety_margin_ns: int,
) -> dict:
    """For each probe duration, compute how many gaps can safely accommodate it.

    Returns dict[probe_duration_ns] → (safe_count, total_count, ratio).
    """
    result = {}
    for pd in probe_durations_ns:
        safe = sum(1 for g in gaps if g.is_safe_for_probe(pd, safety_margin_ns))
        ratio = safe / len(gaps) if gaps else 0.0
        result[pd] = (safe, len(gaps), ratio)
    return result


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_agg_csv(
    busy_intervals: List[BusyInterval],
    path: str,
    path_id: int = 0,
    link_bitmap: int = 0,
    src_dev: int = 0,
    dst_dev: int = 0,
    src_numa: int = 0,
    dst_numa: int = 0,
    direction: int = 1,
):
    """Export busy intervals to aggregated trace CSV."""
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        from schema import AGG_COLUMNS
        w.writerow(AGG_COLUMNS)
        for bi in busy_intervals:
            dur_ms = bi.duration_ns / 1e6
            w.writerow([
                bi.start_ns, bi.end_ns,
                src_dev, dst_dev, src_numa, dst_numa,
                path_id, bi.link_bitmap or link_bitmap,
                f"{bi.size_mb:.2f}", f"{bi.bandwidth_gbps:.2f}",
                bi.start_ns, bi.end_ns,  # wall times ≈ monotonic for synthetic
                f"{dur_ms:.3f}",
                bi.event_count,
                direction,
            ])


def export_gap_csv(gaps: List[Gap], path: str):
    """Export gaps to CSV."""
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gap_start_ns", "gap_end_ns", "duration_us", "path_id"])
        for g in gaps:
            w.writerow([
                g.start_ns, g.end_ns,
                f"{g.duration_ns / 1000.0:.2f}",
                g.path_id,
            ])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="FlowGap intervalization — build busy-idle timelines"
    )
    parser.add_argument("input", help="Path to raw trace CSV")
    parser.add_argument("--min-probe-duration-ns", type=int, default=50_000,
                        help="Minimum probe duration in ns (default: 50000 = 50us)")
    parser.add_argument("--safety-margin-ns", type=int, default=100_000,
                        help="Safety margin in ns (default: 100000 = 100us)")
    parser.add_argument("--per-path", action="store_true",
                        help="Group and process each path separately")
    parser.add_argument("--output-agg", default="",
                        help="Output path for aggregated CSV")
    parser.add_argument("--output-gaps", default="",
                        help="Output path for gaps CSV")
    args = parser.parse_args()

    from parse_trace import parse_csv, group_by_path, compute_path_key

    events = parse_csv(args.input)
    print(f"Loaded {len(events)} events")

    if args.per_path and len(events) > 0:
        groups = group_by_path(events)
        print(f"Processing {len(groups)} unique paths")
        all_busy: List[BusyInterval] = []
        all_gaps: List[Gap] = []
        for pk, evs in sorted(groups.items()):
            path_id = hash(pk) & 0xFFFF
            busy, gaps = build_timeline(
                evs, args.min_probe_duration_ns, args.safety_margin_ns,
                path_id=path_id,
            )
            stats = compute_gap_stats(gaps)
            print(f"  Path {pk}: {len(busy)} busy, {len(gaps)} gaps, "
                  f"gap p50={stats['p50_ns']/1e3:.1f}us p90={stats['p90_ns']/1e3:.1f}us")
            all_busy.extend(busy)
            all_gaps.extend(gaps)
    else:
        # Single-path mode
        path_id = 0
        busy, gaps = build_timeline(
            events, args.min_probe_duration_ns, args.safety_margin_ns,
            path_id=path_id,
        )
        stats = compute_gap_stats(gaps)
        print(f"Busy intervals: {len(busy)}, Gaps: {len(gaps)}")
        print(f"Gap stats: p50={stats['p50_ns']/1e3:.1f}us "
              f"p90={stats['p90_ns']/1e3:.1f}us "
              f"min={stats['min_ns']/1e3:.1f}us "
              f"max={stats['max_ns']/1e3:.1f}us")
        all_busy = busy
        all_gaps = gaps

    threshold = args.min_probe_duration_ns + args.safety_margin_ns
    print(f"Micro-gap merge threshold: {threshold/1e3:.0f}us "
          f"(probe={args.min_probe_duration_ns/1e3:.0f}us + margin={args.safety_margin_ns/1e3:.0f}us)")

    # Export
    if args.output_agg and all_busy:
        export_agg_csv(all_busy, args.output_agg)
        print(f"Wrote agg CSV → {args.output_agg}")
    if args.output_gaps and all_gaps:
        export_gap_csv(all_gaps, args.output_gaps)
        print(f"Wrote gaps CSV → {args.output_gaps}")


if __name__ == "__main__":
    main()
