"""
Main predictor orchestrator.

Feature → predict → calibrate → publish SafeWindow.

Supports:
  - EWMA baseline (cold start)
  - GBDT survival model (trained)
  - Automatic fallback on drift detection

Reference: docs/implementation_plan_v1.md Module 3.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from gap_predictor.schema import (
    SafeWindow, PredictionRecord, EvaluationResult,
    HORIZONS_NS, ETA_TINY_LATENCY, ETA_NORMAL_LATENCY, ETA_BANDWIDTH,
    confidence_to_probe_type, ReasonCode, ProbeType,
)
from gap_predictor.features import FeatureExtractor, make_multi_horizon_labels
from gap_predictor.ewma_baseline import EWMABaseline
from gap_predictor.survival_model import MultiHorizonSurvivalPredictor
from gap_predictor.lower_bound import LowerBoundEstimator
from gap_predictor.calibrator import CalibrationTable, ConfidenceComposer
from gap_predictor.drift_detector import DriftDetector
from trace_parser.intervalize import Gap, BusyInterval


class GapPredictor:
    """Main predictor: manages training, prediction, calibration, and fallback.

    Parameters
    ----------
    model_dir : directory for saving trained models
    horizons : tuple of horizon values (ns) to predict for
    online_update_interval : re-train every N events
    """

    def __init__(
        self,
        model_dir: str = "",
        horizons: Tuple[int, ...] = HORIZONS_NS,
        online_update_interval: int = 1000,
    ):
        self.model_dir = model_dir
        self.horizons = horizons
        self.online_update_interval = online_update_interval

        # Sub-models
        self.ewma = EWMABaseline(window_size=100, alpha=0.1, min_samples=10)
        self.survival = MultiHorizonSurvivalPredictor(
            horizons_ns=horizons, model_dir=model_dir
        )
        self.lower_bound = LowerBoundEstimator(
            quantile=0.05, window_size=100, min_samples=20
        )
        self.calibration = CalibrationTable(n_bins=10)
        self.composer = ConfidenceComposer()
        self.drift = DriftDetector(window_size=200, threshold=0.3)
        self.feature_extractor = FeatureExtractor(window_size=50, min_events=5)

        # State
        self._path_gaps: Dict[int, List[Gap]] = defaultdict(list)
        self._path_busy: Dict[int, List[BusyInterval]] = defaultdict(list)
        self._event_count = 0
        self._prediction_history: List[PredictionRecord] = []
        self._use_gbdt = False  # True after first training

    def train(self, timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]]):
        """Train the full predictor from per-path busy-idle timelines.

        Parameters
        ----------
        timelines : Dict[path_id] → (busy_intervals, gaps)
        """
        all_gaps_list = []
        all_busy_list = []

        for path_id, (busy, gaps) in timelines.items():
            # Store for online prediction
            self._path_busy[path_id] = list(busy)
            self._path_gaps[path_id] = list(gaps)

            # Feed to EWMA
            for g in gaps:
                self.ewma.update(path_id, g.duration_ns)
                self.lower_bound.update(path_id, g.duration_ns)

            all_gaps_list.append(gaps)
            all_busy_list.append(busy)

        # Build training dataset
        from features import build_training_dataset
        X, y_dict = build_training_dataset(
            all_gaps_list, all_busy_list,
            extractor=self.feature_extractor,
        )

        if X.shape[0] >= 50:
            try:
                self.survival.fit(X, y_dict)
                self._use_gbdt = True
            except Exception:
                self._use_gbdt = False

        # Initial calibration
        if self._use_gbdt:
            all_probs = []
            all_labels = []
            for h in self.horizons:
                if h in y_dict and len(y_dict[h]) > 0:
                    probs = self.survival.predict_proba(X, h)
                    all_probs.extend(probs.tolist())
                    all_labels.extend(y_dict[h].tolist())
            if all_probs:
                self.calibration.update(all_probs, all_labels)

        self._event_count = sum(len(g) for g in all_gaps_list)

    def predict(
        self,
        path_id: int,
        gaps: List[Gap],
        busy: List[BusyInterval],
        now_ns: int = 0,
    ) -> List[SafeWindow]:
        """Predict safe windows for a path.

        Returns one SafeWindow per horizon.
        """
        results: List[SafeWindow] = []

        # Feature extraction
        features = self.feature_extractor.extract(
            gaps, busy, path_id=path_id, direction=1, now_ns=now_ns
        )

        # Drift check
        drift_score = self.drift.score(features) if len(features) > 0 and self.drift.is_ready() else 0.0

        # Choose model
        if self._use_gbdt and len(features) > 0:
            for h in self.horizons:
                if h not in self.survival._models:
                    continue
                try:
                    raw_prob = float(self.survival.predict_proba(features.reshape(1, -1), h)[0])
                except Exception:
                    raw_prob = 0.5
                calibrated = self.calibration.calibrate(raw_prob)
                c_data = self.composer.data_quality_confidence()
                c_drift = self.composer.drift_confidence(drift_score)
                confidence = self.composer.compose(raw_prob, calibrated, c_data, c_drift)

                g_lb = self.lower_bound.estimate(path_id)
                probe_type = confidence_to_probe_type(confidence)
                sw = SafeWindow(
                    path_id=path_id,
                    t_publish=now_ns,
                    t_valid_from=now_ns,
                    g_lower_bound=int(g_lb),
                    p_safe=round(raw_prob, 4),
                    confidence=round(confidence, 4),
                    horizon_ns=h,
                    allowed_probe_type=probe_type,
                    reason_code=ReasonCode.SAFE if confidence >= ETA_TINY_LATENCY else ReasonCode.LOW_CONFIDENCE,
                )
                results.append(sw)
        else:
            # EWMA fallback
            ewma_preds = self.ewma.predict(path_id, self.horizons)
            g_lb = self.lower_bound.estimate(path_id)
            c_data = self.composer.data_quality_confidence()
            c_drift = self.composer.drift_confidence(drift_score)

            for h, raw_prob in ewma_preds.items():
                confidence = raw_prob  # EWMA has no calibration yet
                probe_type = confidence_to_probe_type(confidence)
                sw = SafeWindow(
                    path_id=path_id,
                    t_publish=now_ns,
                    t_valid_from=now_ns,
                    g_lower_bound=int(g_lb),
                    p_safe=round(raw_prob, 4),
                    confidence=round(confidence, 4),
                    horizon_ns=h,
                    allowed_probe_type=probe_type,
                    reason_code=ReasonCode.SAFE if confidence >= ETA_TINY_LATENCY else ReasonCode.LOW_CONFIDENCE,
                )
                results.append(sw)

        return results

    def evaluate(
        self,
        timelines: Dict[int, Tuple[List[BusyInterval], List[Gap]]],
    ) -> Dict[int, Dict[str, float]]:
        """Evaluate predictor on held-out timelines.

        Returns Dict[horizon_ns] → {precision, recall, false_safe_rate, brier}.
        """
        all_records: List[PredictionRecord] = []

        for path_id, (busy, gaps) in timelines.items():
            for i, gap in enumerate(gaps):
                # Use gaps observed before this point for prediction
                hist_gaps = gaps[:i]
                hist_busy = busy[:i]

                features = self.feature_extractor.extract(
                    hist_gaps, hist_busy,
                    path_id=path_id, direction=1, now_ns=gap.start_ns,
                )

                if len(features) == 0:
                    continue

                for h in self.horizons:
                    try:
                        prob = float(self.survival.predict_proba(features.reshape(1, -1), h)[0])
                    except Exception:
                        prob = float(self.ewma.predict(path_id, (h,)).get(h, 0.5))
                    actual_safe = gap.duration_ns >= h
                    rec = PredictionRecord(
                        path_id=path_id, horizon_ns=h,
                        p_safe_raw=round(prob, 4),
                        p_safe_calibrated=round(self.calibration.calibrate(prob), 4),
                        actual_gap_ns=gap.duration_ns,
                        actual_safe=actual_safe,
                        timestamp_ns=gap.start_ns,
                    )
                    all_records.append(rec)

        # Aggregate by horizon
        by_horizon: Dict[int, List[PredictionRecord]] = defaultdict(list)
        for rec in all_records:
            by_horizon[rec.horizon_ns].append(rec)

        result: Dict[int, Dict[str, float]] = {}
        for h, records in by_horizon.items():
            probs = np.array([r.p_safe_calibrated for r in records])
            labels = np.array([r.actual_safe for r in records], dtype=np.int32)
            preds = (probs >= 0.5).astype(np.int32)

            tp = int(np.sum((preds == 1) & (labels == 1)))
            fp = int(np.sum((preds == 1) & (labels == 0)))
            fn = int(np.sum((preds == 0) & (labels == 1)))
            tn = int(np.sum((preds == 0) & (labels == 0)))

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
            brier = float(np.mean((probs - labels.astype(float)) ** 2))

            result[h] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "false_safe_rate": round(fpr, 4),
                "brier_score": round(brier, 4),
                "n_samples": len(records),
            }

        return result

    def save(self, path: str = ""):
        """Save predictor state (survival model + calibration)."""
        p = path or os.path.join(self.model_dir, "predictor.pkl")
        self.survival.save(p)

    def load(self, path: str = ""):
        """Load predictor state."""
        p = path or os.path.join(self.model_dir, "predictor.pkl")
        self.survival = MultiHorizonSurvivalPredictor.load(p)
        self._use_gbdt = True

    @property
    def is_trained(self) -> bool:
        return self._use_gbdt

    @property
    def cold_start_precision_curve(self) -> List[Tuple[int, float]]:
        """Precision vs number of training events (for cold-start analysis)."""
        return []  # filled by cold_start module

    @property
    def cold_start_convergence_point(self) -> int:
        """Events needed to reach target precision."""
        return -1  # filled by cold_start module
