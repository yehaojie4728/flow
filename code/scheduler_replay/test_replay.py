#!/usr/bin/env python3
"""Unit tests for scheduler replay module.

Run:
    cd /root/FlowGap-work/FlowGap-paper/code
    PYTHONPATH=.:trace_parser python scheduler_replay/test_replay.py
"""

import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "trace_parser"))

from trace_parser.intervalize import Gap, BusyInterval
from scheduler_replay.schema import (
    ProbeType, ProbeConfig, ProbeOutcome, RunMetrics, ReplayConfig,
    PROBE_LATENCY_SAME_NUMA_NS, CROSS_NUMA_FACTOR_D2H, CROSS_NUMA_FACTOR_H2D,
    probe_latency_ns, POLICY_NAMES,
)
from scheduler_replay.policies import (
    no_probing, make_fixed_interval, make_random, make_threshold,
    make_ewma, make_oracle, GapSnapshot, PolicyContext, make_policy,
)
from scheduler_replay.replay import replay_trace, compare_policies
from scheduler_replay.metrics import (
    compute_summary, compare_results, metrics_table,
    probing_overhead, probe_rate_per_second, per_probe_type_breakdown,
    calculate_gap_coverage,
)


def _make_gaps(durations_ns: list) -> list:
    gaps = []
    t = 1_000_000_000
    for dur in durations_ns:
        gaps.append(Gap(start_ns=t, end_ns=t + dur, path_id=0))
        t += dur + 1_000_000
    return gaps


def _make_timelines(durations_ns: list) -> dict:
    gaps = _make_gaps(durations_ns)
    busy = [BusyInterval(start_ns=0, end_ns=1, path_id=0)]
    return {0: (busy, gaps)}


def _snap(dur_ns: int, prev: list = None) -> GapSnapshot:
    return GapSnapshot(
        path_id=0,
        gap=Gap(start_ns=0, end_ns=dur_ns, path_id=0),
        previous_gaps=prev or [],
        previous_busy=[],
    )


# ============================================================================
class TestSchema(unittest.TestCase):

    def test_probe_latencies_are_realistic(self):
        """Ascend 910B latencies must be in expected ranges."""
        tiny = PROBE_LATENCY_SAME_NUMA_NS[ProbeType.TINY_LATENCY]
        bw = PROBE_LATENCY_SAME_NUMA_NS[ProbeType.BANDWIDTH]
        self.assertGreater(tiny, 10_000)   # at least 10µs
        self.assertLess(tiny, 100_000)     # at most 100µs
        self.assertGreater(bw, 1_000_000)  # at least 1ms
        self.assertLess(bw, 10_000_000)    # at most 10ms

    def test_cross_numa_factors(self):
        """Cross-NUMA must be penalised."""
        self.assertGreater(CROSS_NUMA_FACTOR_H2D, CROSS_NUMA_FACTOR_D2H)
        self.assertGreater(CROSS_NUMA_FACTOR_D2H, 1.0)

    def test_probe_latency_cross_numa(self):
        base = probe_latency_ns(ProbeType.BANDWIDTH, cross_numa=False, direction=2)
        cross = probe_latency_ns(ProbeType.BANDWIDTH, cross_numa=True, direction=2)
        self.assertGreater(cross, base)

    def test_policy_names(self):
        self.assertEqual(len(POLICY_NAMES), 7)
        self.assertIn("oracle", POLICY_NAMES)
        self.assertIn("no_probing", POLICY_NAMES)

    def test_probe_config_description(self):
        pc = ProbeConfig(ProbeType.BANDWIDTH, path_id=7)
        self.assertIn("bw", pc.description)
        self.assertIn("7", pc.description)

    def test_probe_outcome_defaults_safe(self):
        pc = ProbeConfig(ProbeType.TINY_LATENCY)
        po = ProbeOutcome(probe=pc)
        self.assertTrue(po.safe)
        self.assertFalse(po.is_unsafe)


# ============================================================================
class TestPolicies(unittest.TestCase):

    def setUp(self):
        self.ctx = PolicyContext()

    def test_no_probing_returns_empty(self):
        snap = _snap(500_000)
        self.assertEqual(no_probing(snap, self.ctx), [])

    def test_fixed_interval(self):
        pol = make_fixed_interval(period_ns=100_000)
        snap = _snap(500_000)
        probes = pol(snap, self.ctx)
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].probe_type, ProbeType.TINY_LATENCY)

    def test_fixed_interval_respects_period(self):
        pol = make_fixed_interval(period_ns=1_000_000_000)  # 1 sec
        ctx = PolicyContext(last_probe_time_ns=500_000_000)
        snap = GapSnapshot(path_id=0,
                           gap=Gap(start_ns=600_000_000, end_ns=700_000_000, path_id=0),
                           previous_gaps=[], previous_busy=[])
        self.assertEqual(pol(snap, ctx), [])  # too early

    def test_random_probing(self):
        pol = make_random(probability=1.0)  # always
        ctx = PolicyContext(last_probe_time_ns=0)
        snap = _snap(10_000_000)
        probes = pol(snap, ctx)
        self.assertEqual(len(probes), 1)
        # Truly random picks any of the 3 probe types
        self.assertIn(probes[0].probe_type,
                      [ProbeType.TINY_LATENCY, ProbeType.NORMAL_LATENCY, ProbeType.BANDWIDTH])

    def test_random_probing_zero(self):
        pol = make_random(probability=0.0)
        snap = _snap(10_000_000)
        self.assertEqual(pol(snap, PolicyContext()), [])

    def test_threshold_bandwidth(self):
        pol = make_threshold(low_threshold_ns=500_000, high_threshold_ns=5_000_000)
        snap = _snap(10_000_000)
        probes = pol(snap, PolicyContext())
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].probe_type, ProbeType.BANDWIDTH)

    def test_threshold_small_gap(self):
        pol = make_threshold(low_threshold_ns=500_000, high_threshold_ns=5_000_000)
        snap = _snap(100_000)  # too small
        self.assertEqual(pol(snap, PolicyContext()), [])

    def test_oracle_bandwidth(self):
        pol = make_oracle()
        snap = _snap(10_000_000)
        probes = pol(snap, PolicyContext())
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0].probe_type, ProbeType.BANDWIDTH)

    def test_oracle_skips_too_small(self):
        pol = make_oracle()
        snap = _snap(10_000)  # too small for tiny probe
        self.assertEqual(pol(snap, PolicyContext()), [])

    def test_ewma_needs_warmup(self):
        pol = make_ewma(alpha=0.1)
        snap = _snap(500_000)
        # First few gaps — not enough history
        result = pol(snap, PolicyContext())
        self.assertEqual(result, [])  # needs >=10 samples

    def test_make_policy_factory(self):
        for name in POLICY_NAMES:
            fn = make_policy(name)
            self.assertTrue(callable(fn), f"{name} not callable")

    def test_make_policy_unknown(self):
        with self.assertRaises(ValueError):
            make_policy("nonexistent_policy")


# ============================================================================
class TestReplay(unittest.TestCase):

    def test_replay_no_probing(self):
        tlines = _make_timelines([500_000] * 20)
        result = replay_trace(tlines, "no_probing")
        self.assertEqual(result.total_probes_executed, 0)
        self.assertEqual(result.safe_probing_ratio, 0)

    def test_replay_oracle_all_safe(self):
        """Oracle on long gaps must produce 100% safe probes."""
        tlines = _make_timelines([50_000_000] * 10)  # 50ms gaps
        result = replay_trace(tlines, "oracle")
        self.assertGreater(result.total_probes_executed, 0)
        self.assertEqual(result.safe_probing_ratio, 1.0)
        self.assertEqual(result.unsafe_probes, 0)

    def test_replay_fixed_interval(self):
        tlines = _make_timelines([1_000_000] * 100)
        result = replay_trace(tlines, "fixed_interval")
        self.assertGreater(result.total_probes_executed, 0)

    def test_replay_random(self):
        tlines = _make_timelines([10_000_000] * 50)
        config = ReplayConfig(policy="random", random_probability=1.0)
        result = replay_trace(tlines, "random", config)
        self.assertGreater(result.total_probes_executed, 0)

    def test_replay_threshold(self):
        tlines = _make_timelines([100_000, 1_000_000, 10_000_000] * 10)
        result = replay_trace(tlines, "threshold")
        self.assertGreater(result.total_probes_executed, 0)

    def test_compare_policies(self):
        tlines = _make_timelines([5_000_000] * 30)
        results = compare_policies(tlines, policies=["no_probing", "oracle", "threshold"])
        self.assertIn("no_probing", results)
        self.assertIn("oracle", results)
        self.assertEqual(results["no_probing"].total_probes_executed, 0)
        self.assertGreater(results["oracle"].total_probes_executed, 0)


# ============================================================================
class TestMetrics(unittest.TestCase):

    def test_compute_summary_empty(self):
        m = compute_summary([])
        self.assertEqual(m.total_probes_executed, 0)
        self.assertEqual(m.safe_probing_ratio, 0)

    def test_compute_summary(self):
        pc = ProbeConfig(ProbeType.TINY_LATENCY)
        outcomes = [
            ProbeOutcome(probe=pc, safe=True, gap_during_probe_ns=100_000),
            ProbeOutcome(probe=pc, safe=False, gap_during_probe_ns=10_000,
                         busy_overlap_ns=5000),
        ]
        m = compute_summary(outcomes, "test")
        self.assertEqual(m.total_probes_executed, 2)
        self.assertEqual(m.safe_probes, 1)
        self.assertEqual(m.unsafe_probes, 1)
        self.assertEqual(m.safe_probing_ratio, 0.5)
        self.assertEqual(m.harmful_probe_count, 1)

    def test_compare_results(self):
        r = {
            "oracle": RunMetrics(policy="oracle", total_probes_executed=10,
                                 safe_probes=10, unsafe_probes=0,
                                 safe_probing_ratio=1.0, probe_overlap_ratio=0.0),
            "none": RunMetrics(policy="none", total_probes_executed=0),
        }
        comp = compare_results(r)
        self.assertEqual(comp["oracle"]["safe_pct"], 100.0)
        self.assertEqual(comp["none"]["executed"], 0)

    def test_metrics_table(self):
        r = {
            "oracle": RunMetrics(policy="oracle", total_probes_executed=10,
                                 safe_probes=10, safe_probing_ratio=1.0),
            "no_probing": RunMetrics(policy="no_probing", total_probes_executed=0),
        }
        tbl = metrics_table(r)
        self.assertIn("oracle", tbl)
        self.assertIn("no_probing", tbl)

    def test_probing_overhead(self):
        self.assertEqual(probing_overhead(1000, 10000), 10.0)
        self.assertEqual(probing_overhead(0, 1000), 0)

    def test_probe_rate(self):
        self.assertEqual(probe_rate_per_second(100, 1_000_000_000), 100.0)

    def test_per_probe_type(self):
        pcs = [
            ProbeOutcome(probe=ProbeConfig(ProbeType.TINY_LATENCY), safe=True),
            ProbeOutcome(probe=ProbeConfig(ProbeType.BANDWIDTH), safe=True),
            ProbeOutcome(probe=ProbeConfig(ProbeType.TINY_LATENCY), safe=True),
        ]
        bd = per_probe_type_breakdown(pcs)
        self.assertEqual(bd[ProbeType.TINY_LATENCY], 2)
        self.assertEqual(bd[ProbeType.BANDWIDTH], 1)

    def test_gap_coverage(self):
        pcs = [
            ProbeOutcome(probe=ProbeConfig(ProbeType.TINY_LATENCY), safe=True,
                         gap_during_probe_ns=50000),
        ]
        cov = calculate_gap_coverage(pcs, pcs, 100)
        self.assertEqual(cov["total_gaps"], 100)
        self.assertEqual(cov["gaps_probed"], 1)


if __name__ == "__main__":
    unittest.main()
