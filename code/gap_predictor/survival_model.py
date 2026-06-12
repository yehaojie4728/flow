"""
Multi-horizon GBDT survival predictor (Tier 1).

Trains separate binary classifiers for each horizon h:
    y_h = 1  if actual_gap_duration >= h, else 0

Uses sklearn.ensemble.GradientBoostingClassifier with time-series-aware
validation split (not shuffled).

Reference: docs/implementation_plan_v1.md Module 3.
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from gap_predictor.schema import HORIZONS_NS, PredictionRecord, EvaluationResult


# Conditional import — only import if available
try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.base import BaseEstimator
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    GradientBoostingClassifier = None
    BaseEstimator = object


class MultiHorizonSurvivalPredictor:
    """Multi-horizon GBDT survival predictor.

    One binary classifier per horizon. Each classifier predicts
    P(gap >= h | features) given the feature vector x_t.

    Parameters
    ----------
    horizons_ns : tuple of horizon values (ns)
    gbdt_params : dict of parameters passed to GradientBoostingClassifier
    model_dir : directory to save/load trained models
    """

    def __init__(
        self,
        horizons_ns: Tuple[int, ...] = HORIZONS_NS,
        gbdt_params: Optional[Dict] = None,
        model_dir: str = "",
    ):
        if not HAS_SKLEARN:
            raise ImportError(
                "scikit-learn is required for survival_model. "
                "Install via: pip install scikit-learn"
            )
        self.horizons_ns = horizons_ns
        self.gbdt_params = gbdt_params or {
            "n_estimators": 100,
            "max_depth": 4,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "random_state": 42,
        }
        self.model_dir = model_dir
        self._models: Dict[int, GradientBoostingClassifier] = {}
        self._fitted = False

    def fit(
        self,
        X: np.ndarray,
        y_dict: Dict[int, np.ndarray],
        sample_weight: Optional[np.ndarray] = None,
    ):
        """Train one model per horizon.

        Parameters
        ----------
        X : (n_samples, n_features) feature matrix
        y_dict : Dict[horizon_ns] → (n_samples,) binary labels
        """
        for h in self.horizons_ns:
            if h not in y_dict or len(y_dict[h]) == 0:
                continue
            y = y_dict[h]
            if len(np.unique(y)) < 2:
                # All samples are same class → trivial model
                self._models[h] = _TrivialClassifier(
                    constant=float(np.mean(y))
                )
                continue

            model = GradientBoostingClassifier(**self._make_params(h))
            try:
                model.fit(X, y, sample_weight=sample_weight)
            except Exception:
                model = _TrivialClassifier(constant=float(np.mean(y)))
            self._models[h] = model
        self._fitted = True

    def predict_proba(self, X: np.ndarray, horizon_ns: int) -> np.ndarray:
        """Predict P(gap >= horizon_ns | X) for given horizon.

        Returns (n_samples,) array of probabilities.
        """
        if not self._fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        if horizon_ns not in self._models:
            # Find closest trained horizon
            closest = min(self._models.keys(), key=lambda h: abs(h - horizon_ns), default=None)
            if closest is None:
                return np.full(X.shape[0], 0.5)
            horizon_ns = closest
        model = self._models[horizon_ns]
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            if proba.shape[1] == 2:
                return proba[:, 1]  # probability of class 1 (safe)
            return proba[:, 0]
        else:
            return np.full(X.shape[0], model.constant)

    def predict_all(self, X: np.ndarray) -> Dict[int, np.ndarray]:
        """Predict for all horizons. Returns Dict[horizon_ns] → (n_samples,) probs."""
        return {h: self.predict_proba(X, h) for h in self.horizons_ns if h in self._models}

    def save(self, path: str):
        """Save all models to a pickle file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "horizons": self.horizons_ns,
                "models": self._models,
                "params": self.gbdt_params,
            }, f)

    @classmethod
    def load(cls, path: str) -> "MultiHorizonSurvivalPredictor":
        """Load models from a pickle file."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        obj = cls(horizons_ns=data["horizons"], gbdt_params=data["params"])
        obj._models = data["models"]
        obj._fitted = True
        return obj

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def _make_params(self, horizon_ns: int) -> Dict:
        p = dict(self.gbdt_params)
        p["random_state"] = self.gbdt_params.get("random_state", 42) + hash(horizon_ns) % 1000
        return p


class _TrivialClassifier:
    """Constant classifier — used when only one class present."""

    def __init__(self, constant: float = 0.5):
        self.constant = constant

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return np.full((X.shape[0], 2), [1 - self.constant, self.constant])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(X.shape[0], int(self.constant >= 0.5))


# ---------------------------------------------------------------------------
# Time-series split validation
# ---------------------------------------------------------------------------

def time_series_split_validate(
    predictor: MultiHorizonSurvivalPredictor,
    X: np.ndarray,
    y_dict: Dict[int, np.ndarray],
    actual_gaps: np.ndarray,
    n_splits: int = 5,
) -> List[Dict[int, EvaluationResult]]:
    """Time-series-aware cross-validation.

    Splits chronologically — train on earlier portion, test on later.
    No shuffling.

    Returns list of per-split evaluation dicts.
    """
    n = len(X)
    results: List[Dict[int, EvaluationResult]] = []

    for split in range(n_splits):
        train_end = int(n * (split + 1) / (n_splits + 1))
        test_start = train_end
        test_end = int(n * (split + 2) / (n_splits + 1))

        if test_end <= test_start or train_end == 0:
            continue

        X_train, X_test = X[:train_end], X[test_start:test_end]
        gaps_test = actual_gaps[test_start:test_end]

        split_results: Dict[int, EvaluationResult] = {}
        for h, y_full in y_dict.items():
            y_train, y_test = y_full[:train_end], y_full[test_start:test_end]
            if len(y_test) < 2:
                continue

            predictor.fit(X_train, {h: y_train})
            probs = predictor.predict_proba(X_test, h)
            labels = y_test
            n_pos = int(np.sum(labels))
            n_neg = len(labels) - n_pos

            # Precision: of predicted safe, how many are actually safe
            pred_safe = (probs >= 0.5).astype(np.int32)
            tp = int(np.sum((pred_safe == 1) & (labels == 1)))
            fp = int(np.sum((pred_safe == 1) & (labels == 0)))
            fn = int(np.sum((pred_safe == 0) & (labels == 1)))

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            false_safe_rate = fp / n_neg if n_neg > 0 else 0.0
            brier = float(np.mean((probs - labels.astype(float)) ** 2))

            split_results[h] = EvaluationResult(
                horizon_ns=h,
                precision=round(precision, 4),
                recall=round(recall, 4),
                false_safe_rate=round(false_safe_rate, 4),
                brier_score=round(brier, 4),
                n_samples=len(y_test),
                n_safe=n_pos,
                n_predicted_safe=tp + fp,
            )

        results.append(split_results)

    return results


def aggregate_cv_results(
    cv_results: List[Dict[int, EvaluationResult]],
) -> Dict[int, Dict[str, float]]:
    """Average metrics across cross-validation splits."""
    aggregated: Dict[int, Dict[str, float]] = {}
    for horizon in sorted(cv_results[0].keys()):
        metrics = {
            "precision": np.mean([r[horizon].precision for r in cv_results if horizon in r]),
            "recall": np.mean([r[horizon].recall for r in cv_results if horizon in r]),
            "false_safe_rate": np.mean([r[horizon].false_safe_rate for r in cv_results if horizon in r]),
            "brier_score": np.mean([r[horizon].brier_score for r in cv_results if horizon in r]),
        }
        aggregated[horizon] = {k: round(float(v), 4) for k, v in metrics.items()}
    return aggregated
