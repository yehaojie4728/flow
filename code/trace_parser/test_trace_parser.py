#!/usr/bin/env python3
"""Unit tests for FlowGap trace parser and intervalization.

Usage:
    cd code && python -m pytest trace_parser/test_trace_parser.py -v
    cd code && python trace_parser/test_trace_parser.py
"""

import csv
import os
import sys
import tempfile
import unittest

# Ensure code/ is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trace_parser.schema import (
    FlowEvent, BusyInterval, Gap, Direction, QualityFlag,
    HOST_DEVICE_ID, UNKNOWN_NUMA, UNKNOWN_DEVICE,
    validate_event, FLOWGAP_COLUMNS, HOSTDIAG_COLUMNS_V2,
)
from trace_parser.parse_trace import (
    parse_csv, parse_hostdiag_csv, group_by_path, compute_path_key,
    _parse_hostdiag_source, _infer_direction_from_hostdiag, _detect_format,
)
from trace_parser.intervalize import (
    build_busy_intervals,
    build_busy_intervals_probe_aware,
    build_timeline,
    extract_gaps,
    calc_overlap,
    compute_gap_stats,
    compute_safe_window_availability,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(start_ns: int, end_ns: int, size: int = 1024 * 1024,
                path_id: int = 0, direction: int = Direction.H2D,
                pid: int = 100, tid: int = 100) -> FlowEvent:
    """Create a minimal FlowEvent for testing."""
    return FlowEvent(
        ts_enter_ns=start_ns,
        ts_exit_ns=end_ns,
        ts_submit_ns=start_ns,
        ts_end_est_ns=end_ns,
        ts_wall_ns=start_ns,
        pid=pid, tid=tid,
        src_dev=HOST_DEVICE_ID, dst_dev=0,
        src_numa=0, dst_numa=UNKNOWN_NUMA,
        size=size, direction=direction,
        path_id=path_id,
        quality_flags=QualityFlag.SYNTHETIC,
    )


def _write_csv(path: str, header: list, rows: list):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSchema(unittest.TestCase):

    def test_flowevent_properties(self):
        ev = FlowEvent(ts_enter_ns=1000, ts_exit_ns=3000, size=1048576)
        self.assertAlmostEqual(ev.latency_us, 2.0)
        self.assertAlmostEqual(ev.size_mb, 1.0, places=4)
        self.assertGreater(ev.bw_gbps, 0)

    def test_flowevent_is_async(self):
        ev_sync = FlowEvent(async_flag=0)
        ev_async = FlowEvent(async_flag=1)
        self.assertFalse(ev_sync.is_async)
        self.assertTrue(ev_async.is_async)

    def test_flowevent_is_synthetic(self):
        ev = FlowEvent(quality_flags=int(QualityFlag.SYNTHETIC))
        self.assertTrue(ev.is_synthetic)
        ev2 = FlowEvent(quality_flags=0)
        self.assertFalse(ev2.is_synthetic)

    def test_validate_event_valid(self):
        ev = _make_event(1000, 3000)
        errors = validate_event(ev)
        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")

    def test_validate_event_invalid_times(self):
        ev = _make_event(3000, 1000)
        errors = validate_event(ev)
        self.assertGreater(len(errors), 0)

    def test_validate_event_zero_size(self):
        ev = _make_event(1000, 3000, size=0)
        errors = validate_event(ev)
        self.assertGreater(len(errors), 0)

    def test_direction_from_kind(self):
        self.assertEqual(Direction.from_kind(0), Direction.H2H)
        self.assertEqual(Direction.from_kind(1), Direction.H2D)
        self.assertEqual(Direction.from_kind(2), Direction.D2H)
        self.assertEqual(Direction.from_kind(3), Direction.D2D)

    def test_busy_interval_duration(self):
        bi = BusyInterval(start_ns=100, end_ns=500)
        self.assertEqual(bi.duration_ns, 400)

    def test_gap_is_safe_for_probe(self):
        g = Gap(start_ns=1000, end_ns=2000, path_id=0)
        self.assertTrue(g.is_safe_for_probe(500, 100))
        self.assertFalse(g.is_safe_for_probe(950, 100))
        self.assertFalse(g.is_safe_for_probe(900, 101))


# ---------------------------------------------------------------------------
# HostDiagV2 parsing tests
# ---------------------------------------------------------------------------

class TestHostdiagParsing(unittest.TestCase):

    def test_parse_hostdiag_source(self):
        self.assertEqual(_parse_hostdiag_source("Host(NUMA 0)"),
                         (HOST_DEVICE_ID, 0))
        self.assertEqual(_parse_hostdiag_source("NPU 2"),
                         (2, UNKNOWN_NUMA))
        self.assertEqual(_parse_hostdiag_source("Device ?"),
                         (UNKNOWN_DEVICE, UNKNOWN_NUMA))
        self.assertEqual(_parse_hostdiag_source("Host(NUMA 3)"),
                         (HOST_DEVICE_ID, 3))

    def test_infer_direction(self):
        self.assertEqual(_infer_direction_from_hostdiag("Host(NUMA 0)", "NPU 2"),
                         Direction.H2D)
        self.assertEqual(_infer_direction_from_hostdiag("NPU 0", "Host(NUMA 1)"),
                         Direction.D2H)
        self.assertEqual(_infer_direction_from_hostdiag("NPU 0", "NPU 1"),
                         Direction.D2D)

    def test_detect_format_hostdiag(self):
        self.assertEqual(_detect_format(HOSTDIAG_COLUMNS_V2), "hostdiag_v2")

    def test_detect_format_flowgap(self):
        self.assertEqual(_detect_format(FLOWGAP_COLUMNS), "flowgap")

    def test_detect_format_unknown(self):
        self.assertEqual(_detect_format(["a", "b", "c"]), "unknown")

    def test_parse_hostdiag_csv_minimal(self):
        """Parse a minimal HostDiagV2 CSV."""
        header = HOSTDIAG_COLUMNS_V2
        rows = [
            [2771269, 2771269, "Host(NUMA 0)", "NPU 2",
             "24.50", "2885.74", "8.90",
             "716340471897747", "716340474783487",
             "1777455000471492872", "1777455000474378612"],
            [2771269, 2771269, "Host(NUMA 0)", "NPU 2",
             "31.50", "3649.31", "9.05",
             "716340474914468", "716340478563781",
             "1777455000473516458", "1777455000477165771"],
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _write_csv(f.name, header, rows)
            tmp = f.name

        try:
            events = parse_hostdiag_csv(tmp)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].pid, 2771269)
            self.assertEqual(events[0].src_dev, HOST_DEVICE_ID)
            self.assertEqual(events[0].src_numa, 0)
            self.assertEqual(events[0].dst_dev, 2)
            self.assertEqual(events[0].dst_numa, UNKNOWN_NUMA)
            self.assertEqual(events[0].direction, Direction.H2D)
            self.assertAlmostEqual(events[0].size_mb, 24.50, places=1)
            self.assertAlmostEqual(events[0].latency_us, 2885.74, places=1)
            self.assertEqual(events[0].async_flag, 0)
            self.assertEqual(events[0].api_type, 0)
        finally:
            os.unlink(tmp)

    def test_parse_hostdiag_csv_device_unknown(self):
        """Parse a row with Device ? — should set quality flag."""
        header = HOSTDIAG_COLUMNS_V2
        rows = [
            [2770322, 2770322, "Host(NUMA 1)", "Device ?",
             "128.00", "10341.58", "12.98",
             "716340517169366", "716340527510942",
             "1777455000515844287", "1777455000526185863"],
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _write_csv(f.name, header, rows)
            tmp = f.name

        try:
            events = parse_hostdiag_csv(tmp)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].dst_dev, UNKNOWN_DEVICE)
            self.assertTrue(events[0].quality_flags & QualityFlag.UNKNOWN_DEVICE)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# FlowGap format parsing tests
# ---------------------------------------------------------------------------

class TestFlowgapParsing(unittest.TestCase):

    def test_parse_flowgap_csv(self):
        header = FLOWGAP_COLUMNS
        rows = [
            [100, 101, str(HOST_DEVICE_ID), "0", "0", str(UNKNOWN_NUMA),
             "64.00", "5000.00", "12.80",
             "1000000000000", "1000000050000",
             "1777455000000000000", "1777455000005000000",
             "1", "0", "0",
             "0", "1", "0",
             f"{int(QualityFlag.SYNTHETIC)}"],
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _write_csv(f.name, header, rows)
            tmp = f.name

        try:
            events = parse_csv(tmp)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].pid, 100)
            self.assertEqual(events[0].src_dev, HOST_DEVICE_ID)
            self.assertEqual(events[0].dst_dev, 0)
            self.assertEqual(events[0].direction, Direction.H2D)
            self.assertTrue(events[0].is_synthetic)
            self.assertEqual(events[0].path_id, 1)
        finally:
            os.unlink(tmp)

    def test_group_by_path(self):
        events = [
            _make_event(1000, 2000, path_id=0, direction=Direction.H2D,
                        pid=100, tid=100),
            _make_event(3000, 4000, path_id=1, direction=Direction.D2H,
                        pid=200, tid=200),
            _make_event(5000, 6000, path_id=0, direction=Direction.H2D,
                        pid=100, tid=101),
        ]
        groups = group_by_path(events)
        self.assertEqual(len(groups), 2)

    def test_parse_csv_sorts_by_time(self):
        """Events should be sorted by start_ns regardless of CSV order."""
        header = FLOWGAP_COLUMNS
        rows = [
            [100, 101, str(HOST_DEVICE_ID), "0", "0", str(UNKNOWN_NUMA),
             "10.00", "100.00", "100.00",
             "5000", "5100", "5000", "5100",
             "1", "0", "0", "0", "0", "0",
             f"{int(QualityFlag.SYNTHETIC)}"],
            [100, 102, str(HOST_DEVICE_ID), "0", "0", str(UNKNOWN_NUMA),
             "10.00", "100.00", "100.00",
             "1000", "1100", "1000", "1100",
             "1", "0", "0", "0", "0", "0",
             f"{int(QualityFlag.SYNTHETIC)}"],
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _write_csv(f.name, header, rows)
            tmp = f.name

        try:
            events = parse_csv(tmp)
            self.assertEqual(len(events), 2)
            self.assertLess(events[0].ts_enter_ns, events[1].ts_enter_ns)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Intervalization tests
# ---------------------------------------------------------------------------

class TestIntervalization(unittest.TestCase):

    def test_single_event(self):
        events = [_make_event(1000, 2000)]
        busy = build_busy_intervals(events, micro_gap_threshold_ns=500)
        self.assertEqual(len(busy), 1)
        self.assertEqual(busy[0].start_ns, 1000)
        self.assertEqual(busy[0].end_ns, 2000)

    def test_merge_overlapping_events(self):
        events = [
            _make_event(1000, 3000),
            _make_event(2000, 4000),  # overlaps
        ]
        busy = build_busy_intervals(events, micro_gap_threshold_ns=500)
        self.assertEqual(len(busy), 1)
        self.assertEqual(busy[0].start_ns, 1000)
        self.assertEqual(busy[0].end_ns, 4000)
        self.assertTrue(busy[0].merged)

    def test_merge_small_gap(self):
        """Events with gap=100ns < threshold=500ns should merge."""
        events = [
            _make_event(1000, 2000),
            _make_event(2100, 3000),  # gap = 100ns
        ]
        busy = build_busy_intervals(events, micro_gap_threshold_ns=500)
        self.assertEqual(len(busy), 1)
        self.assertEqual(busy[0].end_ns, 3000)
        self.assertTrue(busy[0].merged)

    def test_no_merge_large_gap(self):
        """Events with gap=1000ns > threshold=500ns should NOT merge."""
        events = [
            _make_event(1000, 2000),
            _make_event(3000, 4000),  # gap = 1000ns
        ]
        busy = build_busy_intervals(events, micro_gap_threshold_ns=500)
        self.assertEqual(len(busy), 2)
        self.assertEqual(busy[0].end_ns, 2000)
        self.assertEqual(busy[1].start_ns, 3000)

    def test_edge_case_exact_threshold(self):
        """Gap == threshold: should merge (gap < threshold)."""
        events = [
            _make_event(1000, 2000),
            _make_event(2500, 3000),  # gap = 500ns == threshold → NOT merged
        ]
        busy = build_busy_intervals(events, micro_gap_threshold_ns=500)
        # threshold = 500, gap = 500, condition is s <= last.end_ns + threshold
        # 2500 <= 2000 + 500 = 2500 → TRUE → merged
        self.assertEqual(len(busy), 1)

    def test_probe_aware_threshold(self):
        """Probe-aware with min_probe=100us + margin=50us."""
        events = [
            _make_event(1_000_000, 2_000_000),
            _make_event(2_100_000, 3_000_000),  # gap = 100us < threshold=150us
        ]
        busy = build_busy_intervals_probe_aware(
            events, min_probe_duration_ns=100_000, safety_margin_ns=50_000
        )
        self.assertEqual(len(busy), 1)  # merged

    def test_probe_aware_no_merge(self):
        events = [
            _make_event(1_000_000, 2_000_000),
            _make_event(2_200_000, 3_000_000),  # gap = 200us > threshold=150us
        ]
        busy = build_busy_intervals_probe_aware(
            events, min_probe_duration_ns=100_000, safety_margin_ns=50_000
        )
        self.assertEqual(len(busy), 2)  # NOT merged

    def test_empty_events(self):
        busy = build_busy_intervals([], micro_gap_threshold_ns=500)
        self.assertEqual(len(busy), 0)

    def test_extract_gaps_empty(self):
        gaps = extract_gaps([], path_id=0)
        self.assertEqual(len(gaps), 0)

    def test_extract_gaps_single_interval(self):
        intervals = [BusyInterval(start_ns=1000, end_ns=2000, path_id=0)]
        gaps = extract_gaps(intervals, path_id=0)
        self.assertEqual(len(gaps), 0)

    def test_extract_gaps(self):
        intervals = [
            BusyInterval(start_ns=1000, end_ns=2000, path_id=0),
            BusyInterval(start_ns=3000, end_ns=4000, path_id=0),
        ]
        gaps = extract_gaps(intervals, path_id=0)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].start_ns, 2000)
        self.assertEqual(gaps[0].end_ns, 3000)
        self.assertEqual(gaps[0].duration_ns, 1000)

    def test_build_timeline(self):
        events = [
            _make_event(1000, 2000, path_id=0),
            _make_event(5000, 6000, path_id=0),  # gap = 3000ns
            _make_event(6500, 7000, path_id=0),  # gap = 500ns → merged
        ]
        busy, gaps = build_timeline(
            events, min_probe_duration_ns=1000, safety_margin_ns=500, path_id=0
        )
        self.assertEqual(len(busy), 2)  # first standalone, second+third merged
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].start_ns, 2000)
        self.assertEqual(gaps[0].end_ns, 5000)


# ---------------------------------------------------------------------------
# Overlap tests
# ---------------------------------------------------------------------------

class TestOverlap(unittest.TestCase):

    def test_overlap_true(self):
        busy = [BusyInterval(start_ns=1000, end_ns=3000)]
        flag, idle = calc_overlap(2000, 2500, busy)
        self.assertTrue(flag)

    def test_overlap_false(self):
        busy = [BusyInterval(start_ns=1000, end_ns=3000)]
        flag, idle = calc_overlap(4000, 4500, busy)
        self.assertFalse(flag)

    def test_overlap_partial(self):
        """Probe starts in gap, ends in busy."""
        busy = [BusyInterval(start_ns=3000, end_ns=5000)]
        flag, idle = calc_overlap(2000, 3500, busy)
        self.assertTrue(flag)
        self.assertEqual(idle, 1000)  # 3000 - 2000


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------

class TestStats(unittest.TestCase):

    def test_gap_stats(self):
        gaps = [
            Gap(1000, 2000, 0),
            Gap(3000, 6000, 0),
            Gap(7000, 8000, 0),
        ]
        stats = compute_gap_stats(gaps)
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["min_ns"], 1000)
        self.assertEqual(stats["max_ns"], 3000)
        self.assertEqual(stats["p50_ns"], 1000)

    def test_gap_stats_empty(self):
        stats = compute_gap_stats([])
        self.assertEqual(stats["count"], 0)

    def test_safe_window_availability(self):
        gaps = [
            Gap(1000, 2000, 0),   # 1000ns
            Gap(3000, 8000, 0),   # 5000ns
        ]
        result = compute_safe_window_availability(
            gaps, probe_durations_ns=[500, 1500, 6000], safety_margin_ns=0
        )
        self.assertEqual(result[500], (2, 2, 1.0))
        self.assertEqual(result[1500], (1, 2, 0.5))
        self.assertEqual(result[6000], (0, 2, 0.0))


# ---------------------------------------------------------------------------
# Full pipeline test with synthetic trace
# ---------------------------------------------------------------------------

class TestSyntheticFullPipeline(unittest.TestCase):

    def test_full_pipeline_synthetic(self):
        """End-to-end: generate synthetic → parse → intervalize → stats."""
        from trace_parser.generate_synthetic_trace import generate_synthetic_trace

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = f.name

        try:
            generate_synthetic_trace(tmp, num_events=60, seed=123)
            events = parse_csv(tmp)
            self.assertGreater(len(events), 10, "Should have many synthetic events")
            self.assertTrue(all(e.is_synthetic for e in events))

            groups = group_by_path(events)
            self.assertEqual(len(groups), 3, "3 paths expected")

            for pk, evs in groups.items():
                path_id = hash(pk) & 0xFFFF
                busy, gaps = build_timeline(
                    evs, min_probe_duration_ns=50_000, safety_margin_ns=100_000,
                    path_id=path_id,
                )
                stats = compute_gap_stats(gaps)
                self.assertGreater(stats["count"], 0,
                                   f"Path {pk} should have gaps")
                self.assertGreater(stats["p90_ns"], 0)
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
