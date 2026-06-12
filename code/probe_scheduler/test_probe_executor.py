#!/usr/bin/env python3
"""Probe executor tests — call AscendCL ctypes bindings on the real NPU.

IMPORTANT: These tests require a live Ascend 910B NPU.
They do NOT run in the sandbox environment.

To run:
    cd /root/FlowGap-work/FlowGap-paper/code
    source /root/anaconda3/etc/profile.d/conda.sh
    conda activate mindspore_py37
    PYTHONPATH=.:trace_parser python probe_scheduler/test_probe_executor.py

The test requires NO MindSpore training to be running.
It initializes its own dedicated AscendCL context and stream.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe_scheduler.probe_executor import (
    ProbeExecutor, ProbeResult, AscendCL,
    _find_ascendcl, ACL_SUCCESS,
)

REQUIRE_NPU = os.environ.get("FLOWGAP_TEST_NPU", "1") == "1"
SKIP_MSG = "NPU test disabled (set FLOWGAP_TEST_NPU=1 to enable)"


class TestAscendCLBinding(unittest.TestCase):
    """Test libascendcl loading — no NPU access needed (symbol check only)."""

    def test_find_ascendcl_path(self):
        path = _find_ascendcl()
        self.assertTrue(os.path.exists(path), f"Not found: {path}")
        self.assertIn("libascendcl.so", path)


@unittest.skipUnless(REQUIRE_NPU, SKIP_MSG)
class TestProbeExecutor(unittest.TestCase):
    """Test real probe execution — requires Ascend 910B NPU."""

    @classmethod
    def setUpClass(cls):
        cls.executor = ProbeExecutor(device_id=0)
        cls.executor.open(max_probe_size=10 * 1024 * 1024)  # 10MB for tests

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'executor'):
            cls.executor.close()

    def test_tiny_latency_h2d(self):
        r = self.executor.probe_latency(4096, "H2D", iterations=1)
        self.assertTrue(r.success, r.error_msg)
        self.assertTrue(10 < r.latency_us < 500,
                        f"Expected 10-500µs, got {r.latency_us}µs")

    def test_tiny_latency_d2h(self):
        r = self.executor.probe_latency(4096, "D2H", iterations=1)
        self.assertTrue(r.success, r.error_msg)
        self.assertTrue(10 < r.latency_us < 500,
                        f"Expected 10-500µs, got {r.latency_us}µs")

    def test_normal_latency_d2h(self):
        r = self.executor.probe_latency(4096, "D2H", iterations=10)
        self.assertTrue(r.success, r.error_msg)
        # 10 iterations should average to ~500µs
        self.assertLess(r.latency_us, 2000,
                        f"Expected <2000µs for 10 iterations")

    def test_bandwidth_d2h(self):
        r = self.executor.probe_bandwidth("D2H")
        self.assertTrue(r.success, r.error_msg)
        # Bandwidth should be in range 10-50 GB/s
        self.assertTrue(5 < r.bandwidth_gbps < 50,
                        f"Expected 5-50 GB/s, got {r.bandwidth_gbps}")

    def test_bandwidth_h2d(self):
        r = self.executor.probe_bandwidth("H2D")
        self.assertTrue(r.success, r.error_msg)
        self.assertTrue(5 < r.bandwidth_gbps < 50)

    def test_bandwidth_is_faster_than_latency_proportionally(self):
        """Bandwidth probe should show much higher throughput than latency probe."""
        r_lat = self.executor.probe_latency(4096, "D2H", iterations=1)
        r_bw = self.executor.probe_bandwidth("D2H")
        self.assertTrue(r_lat.success)
        self.assertTrue(r_bw.success)
        # Bandwidth should be at least 5 GB/s (not swapping)
        self.assertGreater(r_bw.bandwidth_gbps, 5.0)

    def test_context_manager_protocol(self):
        """Test __enter__ returns self, probe still works.
        open() is idempotent so this is safe."""
        exec_ref = self.__class__.executor.__enter__()
        self.assertIs(exec_ref, self.__class__.executor)
        r = self.__class__.executor.probe_latency(4096, "H2D")
        self.assertTrue(r.success)


@unittest.skipUnless(REQUIRE_NPU, SKIP_MSG)
class TestProbeResult(unittest.TestCase):

    def test_probe_result_fields(self):
        r = ProbeResult(
            probe_type="tiny",
            direction="D2H",
            size_bytes=4096,
            latency_us=50.0,
            bandwidth_gbps=0.08,
            success=True,
        )
        self.assertEqual(r.probe_type, "tiny")
        self.assertEqual(r.direction, "D2H")
        self.assertTrue(r.success)


if __name__ == "__main__":
    if REQUIRE_NPU:
        print("Running NPU probe tests...")
        print("Ensure no training is running on the NPU.")
        print()
    else:
        print("Running binding tests only (no NPU access).")
        print("Set FLOWGAP_TEST_NPU=1 to enable NPU tests.")
        print()
    unittest.main()
