#!/usr/bin/env python3
"""Unit tests for FlowGap gap predictor module.

Run:
    cd code && PYTHONPATH=trace_parser python gap_predictor/test_gap_predictor.py
    cd code && python -m pytest gap_predictor/test_gap_predictor.py -v
"""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trace_parser"))

from trace_parser.schema import Gap, BusyInterval, FlowEvent, Direction, HOST_DEVICE_ID, UNKNOWN_NUMA
from gap_predictor.schema import (
    SafeWindow, HORIZONS_NS, ETA_TINY_LATENCY, ETA_NORMAL_LATENCY, ETA_BANDWIDTH,
    confidence_to_probe_type, ReasonCode, ProbeType, PredictionRecord, EvaluationResult,
)
from gap_predictor.features import (
    FeatureExtractor, make_multi_horizon_labels, build_training_dataset,
)
from gap_predictor.ewma_baseline import EWMABaseline, QuantileBaseline
from gap_predictor.lower_bound import LowerBoundEstimator, estimate_lower_bound_simple
from gap_predictor.calibrator import CalibrationTable, ConfidenceComposer
from gap_predictor.drift_detector import DriftDetector, RollingStats, detect_phase_shift


def _make_gaps(durations_ns: list) -> list:
    """Create Gap objects at evenly spaced times."""
    gaps = []
    t = 1_000_000_000
    for dur in durations_ns:
        s = t
        e = t + dur
        gaps.append(Gap(start_ns=s, end_ns=e, path_id=0))
        t = e + 500_000  # 0.5ms between gaps
    return gaps


def _make_busy(durations_ns: list) -> list:
    """Create BusyInterval objects."""
    busy = []
    t = 0
    for dur in durations_ns:
        busy.append(BusyInterval(start_ns=t, end_ns=t + dur, path_id=0))
        t += dur + 1_000_000  # 1ms spacing
    return busy


# ============================================================================
# Schema Tests
# ============================================================================

class TestSchema(unittest.TestCase):

    def test_safe_window_safe(self):
        sw = SafeWindow(path_id=1, p_safe=0.92, confidence=0.92,
                        horizon_ns=50_000, allowed_probe_type=ProbeType.TINY_LATENCY)
        self.assertTrue(sw.is_safe)
        self.assertEqual(sw.probe_type_label, "TINY_LATENCY")

    def test_safe_window_unsafe(self):
        sw = SafeWindow(path_id=1, reason_code=ReasonCode.LOW_CONFIDENCE)
        self.assertFalse(sw.is_safe)

    def test_confidence_to_probe_type(self):
        self.assertEqual(confidence_to_probe_type(0.99), ProbeType.BANDWIDTH)
        self.assertEqual(confidence_to_probe_type(0.96), ProbeType.NORMAL_LATENCY)
        self.assertEqual(confidence_to_probe_type(0.91), ProbeType.TINY_LATENCY)
        self.assertEqual(confidence_to_probe_type(0.80), ProbeType.NONE)

    def test_horizons_ordered(self):
        self.assertEqual(HORIZONS_NS, tuple(sorted(HORIZONS_NS)))


# ============================================================================
# Feature Extraction Tests
# ============================================================================

class TestFeatureExtraction(unittest.TestCase):

    def setUp(self):
        self.extractor = FeatureExtractor(window_size=20, min_events=5)

    def test_extract_shape(self):
        gaps = _make_gaps([50_000, 60_000, 70_000, 80_000, 90_000,
                           100_000, 110_000, 120_000, 130_000, 140_000])
        busy = _make_busy([500_000] * 5)
        features = self.extractor.extract(gaps, busy, path_id=1, direction=1, now_ns=0)
        self.assertEqual(len(features), self.extractor.n_features())

    def test_extract_insufficient_data(self):
        features = self.extractor.extract([], [], path_id=0, direction=1, now_ns=0)
        self.assertEqual(len(features), 0)

    def test_extract_gap_stats_correct(self):
        self.extractor.min_events = 3
        gaps = _make_gaps([100_000, 200_000, 300_000])
        busy = _make_busy([100_000])
        features = self.extractor.extract(gaps, busy, path_id=0, direction=1, now_ns=0)
        self.assertGreater(len(features), 0)
        # gap_p50 should be ~200000
        self.assertAlmostEqual(features[1], 200_000, delta=5000)

    def test_feature_names(self):
        names = FeatureExtractor.feature_names()
        self.assertEqual(len(names), FeatureExtractor.n_features())

    def test_make_multi_horizon_labels(self):
        gaps = _make_gaps([10_000, 60_000, 200_000, 1_500_000])
        labels = make_multi_horizon_labels(gaps, horizons_ns=(50_000, 500_000, 2_000_000))
        self.assertEqual(len(labels[50_000]), 4)
        # gap >= 50K? [no, yes, yes, yes] → [0, 1, 1, 1]
        self.assertEqual(list(labels[50_000]), [0, 1, 1, 1])
        # gap >= 500K? [no, no, no, yes] → [0, 0, 0, 1]
        self.assertEqual(list(labels[500_000]), [0, 0, 0, 1])

    def test_build_training_dataset_empty(self):
        X, y = build_training_dataset([], [])
        self.assertEqual(X.shape[0], 0)


# ============================================================================
# EWMA Baseline Tests
# ============================================================================

class TestEWMABaseline(unittest.TestCase):

    def setUp(self):
        self.ewma = EWMABaseline(window_size=20, alpha=0.2, min_samples=5)

    def test_not_ready_initially(self):
        self.assertFalse(self.ewma.is_ready(0))

    def test_predict_after_samples(self):
        for dur in [50_000, 60_000, 55_000, 52_000, 58_000]:
            self.ewma.update(0, dur)
        self.assertTrue(self.ewma.is_ready(0))
        preds = self.ewma.predict(0)
        self.assertIn(50_000, preds)
        self.assertGreater(preds[50_000], 0)  # most gaps >= 50K

    def test_predict_all_zero_when_no_history(self):
        preds = self.ewma.predict(999)
        self.assertEqual(preds[50_000], 0.0)

    def test_mean_gap_tracks_ewma(self):
        for dur in [100_000] * 20:
            self.ewma.update(0, dur)
        mu = self.ewma.mean_gap(0)
        self.assertAlmostEqual(mu, 100_000, delta=1000)

    def test_reset(self):
        self.ewma.update(0, 50_000)
        self.ewma.reset_path(0)
        self.assertFalse(self.ewma.is_ready(0))

    def test_quantile_baseline_more_conservative(self):
        qb = QuantileBaseline(window_size=20, alpha=0.2, min_samples=5)
        for dur in [10_000, 20_000, 15_000, 12_000, 18_000]:
            qb.update(0, dur)
        preds = qb.predict(0)
        # QuantileBaseline applies 0.5 penalty when p10 < horizon
        self.assertLess(preds[50_000], 0.5)


# ============================================================================
# Lower Bound Estimator Tests
# ============================================================================

class TestLowerBound(unittest.TestCase):

    def setUp(self):
        self.lb = LowerBoundEstimator(quantile=0.1, window_size=50, min_samples=10)

    def test_insufficient_data_returns_zero(self):
        self.assertEqual(self.lb.estimate(0), 0.0)

    def test_estimate_returns_p10(self):
        for dur in [10_000, 20_000, 30_000, 40_000, 50_000,
                    60_000, 70_000, 80_000, 90_000, 100_000]:
            self.lb.update(0, dur)
        est = self.lb.estimate(0)
        # p10 of uniform 10K-100K ≈ 19K
        self.assertGreater(est, 10_000)
        self.assertLess(est, 30_000)

    def test_simple_estimator(self):
        est = estimate_lower_bound_simple([10_000, 20_000, 30_000, 40_000, 50_000,
                                           60_000, 70_000, 80_000, 90_000, 100_000])
        self.assertGreater(est, 10_000)
        self.assertLess(est, 25_000)

    def test_estimate_less_than_mean(self):
        for dur in range(50_000, 150_000, 5_000):
            self.lb.update(0, dur)
        est = self.lb.estimate(0)
        mean_gap = 100_000
        self.assertLess(est, mean_gap)


# ============================================================================
# Calibration Tests
# ============================================================================

class TestCalibration(unittest.TestCase):

    def setUp(self):
        self.cal = CalibrationTable(n_bins=10)

    def test_update_and_calibrate(self):
        # Perfect calibration: all probs 0.9 correspond to label 1
        probs = [0.9] * 100 + [0.1] * 100
        labels = [1] * 100 + [0] * 100
        self.cal.update(probs, labels)
        # 0.9 should calibrate close to 1.0
        cal = self.cal.calibrate(0.9)
        self.assertAlmostEqual(cal, 1.0, delta=0.1)

    def test_calibrate_without_fitting(self):
        self.assertEqual(self.cal.calibrate(0.5), 0.5)

    def test_expected_calibration_error_zero_on_perfect(self):
        probs = [0.9] * 100 + [0.1] * 100
        labels = [1] * 100 + [0] * 100
        self.cal.update(probs, labels)
        ece = self.cal.expected_calibration_error()
        self.assertLess(ece, 0.2)

    def test_plot_table(self):
        probs = [0.45, 0.55] * 10
        labels = [0, 1] * 10
        self.cal.update(probs, labels)
        tbl = self.cal.plot_table()
        self.assertEqual(len(tbl), 10)


class TestConfidenceComposer(unittest.TestCase):

    def setUp(self):
        self.composer = ConfidenceComposer()

    def test_compose_takes_min(self):
        c = self.composer.compose(0.95, 0.85, 0.90, 0.80)
        self.assertEqual(c, 0.80)

    def test_data_quality_perfect(self):
        c = self.composer.data_quality_confidence()
        self.assertEqual(c, 1.0)

    def test_data_quality_high_drop_rate(self):
        c = self.composer.data_quality_confidence(drop_rate=0.5)
        self.assertEqual(c, 0.7)

    def test_drift_confidence(self):
        c = self.composer.drift_confidence(0.3)
        self.assertEqual(c, 0.7)


# ============================================================================
# Drift Detection Tests
# ============================================================================

class TestDriftDetection(unittest.TestCase):

    def setUp(self):
        self.detector = DriftDetector(window_size=50, threshold=0.3)

    def test_no_drift_on_identical(self):
        import numpy as np
        for _ in range(60):
            self.detector.update(np.zeros(30))
        score = self.detector.score(np.zeros(30))
        self.assertLess(score, 0.1)

    def test_drive_score_high_on_divergence(self):
        import numpy as np
        for _ in range(60):
            self.detector.update(np.zeros(30))
        score = self.detector.score(np.ones(30) * 10)
        self.assertGreater(score, 0.5)

    def test_not_ready_initial(self):
        self.assertFalse(self.detector.is_ready())

    def test_reset(self):
        import numpy as np
        self.detector.update(np.zeros(30))
        self.detector.reset()
        self.assertEqual(self.detector.n_samples(), 0)


class TestRollingStats(unittest.TestCase):

    def test_mean_std(self):
        rs = RollingStats(window_size=10)
        for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            rs.update(v)
        self.assertAlmostEqual(rs.mean(), 5.5, delta=0.5)
        self.assertGreater(rs.std(), 2.0)

    def test_relative_change(self):
        rs = RollingStats(window_size=10)
        for _ in range(10):
            rs.update(100.0)
        self.assertAlmostEqual(rs.relative_change(200.0), 1.0, delta=0.1)


class TestPhaseShift(unittest.TestCase):

    def test_no_shift_small_window(self):
        self.assertFalse(detect_phase_shift([100_000] * 50, window_size=50, threshold=0.3))

    def test_detect_shift(self):
        history = [50_000] * 100 + [150_000] * 60
        self.assertTrue(detect_phase_shift(history, window_size=50, threshold=0.3))


if __name__ == "__main__":
    unittest.main()
