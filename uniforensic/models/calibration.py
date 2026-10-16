"""Probability calibration, Brier score, Expected Calibration Error (ECE), and reliability curves."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss, log_loss

from uniforensic.models.classifier import ForensicCandidateClassifier


@dataclass
class CalibrationMetrics:
    brier_score: float
    expected_calibration_error: float
    log_loss_score: float
    prob_true: List[float]
    prob_pred: List[float]
    bin_counts: List[int]


def calculate_ece(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> Tuple[float, List[float], List[float], List[int]]:
    """
    Calculate Expected Calibration Error (ECE) and bin statistics.

    ECE = sum_m ( |B_m| / N ) * | acc(B_m) - conf(B_m) |
    """
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total_samples = len(y_true)

    prob_true = []
    prob_pred = []
    bin_counts = []

    if total_samples == 0:
        return 0.0, [], [], []

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            in_bin = (y_prob >= low) & (y_prob <= high)
        else:
            in_bin = (y_prob >= low) & (y_prob < high)

        count = int(np.sum(in_bin))
        bin_counts.append(count)

        if count > 0:
            bin_acc = float(np.mean(y_true[in_bin]))
            bin_conf = float(np.mean(y_prob[in_bin]))
            prob_true.append(bin_acc)
            prob_pred.append(bin_conf)
            ece += (count / total_samples) * abs(bin_acc - bin_conf)
        else:
            prob_true.append(0.0)
            prob_pred.append((low + high) / 2.0)

    return float(ece), prob_true, prob_pred, bin_counts


def evaluate_calibration(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> CalibrationMetrics:
    """Evaluate full calibration metrics: Brier score, ECE, log loss, and reliability curve."""
    if len(y_true) == 0:
        return CalibrationMetrics(0.0, 0.0, 0.0, [], [], [])

    # Ensure y_prob is 1D probabilities for class 1
    if y_prob.ndim == 2:
        y_prob = y_prob[:, 1]

    # Brier score
    brier = float(brier_score_loss(y_true, y_prob))

    # Log loss (clipped to prevent inf)
    clipped_prob = np.clip(y_prob, 1e-15, 1 - 1e-15)
    ll = float(log_loss(y_true, clipped_prob))

    # ECE and curve points
    ece, p_true, p_pred, b_counts = calculate_ece(y_true, y_prob, n_bins=n_bins)

    return CalibrationMetrics(
        brier_score=round(brier, 4),
        expected_calibration_error=round(ece, 4),
        log_loss_score=round(ll, 4),
        prob_true=[round(p, 4) for p in p_true],
        prob_pred=[round(p, 4) for p in p_pred],
        bin_counts=b_counts,
    )


class CalibratedRanker:
    """Calibrates predicted probabilities of a pre-fitted classifier on a hold-out calibration split."""

    def __init__(
        self,
        base_classifier: ForensicCandidateClassifier,
        method: str = "isotonic",
    ):
        self.base_classifier = base_classifier
        self.method = method
        self.calibrator: Optional[CalibratedClassifierCV] = None
        self.is_calibrated = False

    def calibrate(self, X_calib: np.ndarray, y_calib: np.ndarray) -> "CalibratedRanker":
        """Fit probability calibration on the held-out calibration split."""
        if not self.base_classifier.is_fitted:
            raise RuntimeError("Base classifier must be fitted before calibration")

        try:
            from sklearn.frozen import FrozenEstimator
            self.calibrator = CalibratedClassifierCV(
                estimator=FrozenEstimator(self.base_classifier.model),
                method=self.method,
            )
        except ImportError:
            self.calibrator = CalibratedClassifierCV(
                estimator=self.base_classifier.model,
                method=self.method,
                cv="prefit",
            )
        self.calibrator.fit(X_calib, y_calib)
        self.is_calibrated = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_calibrated or self.calibrator is None:
            # Fallback to uncalibrated probabilities
            return self.base_classifier.predict_proba(X)
        return self.calibrator.predict_proba(X)

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)
        pos_probs = probs[:, 1] if probs.ndim == 2 else probs
        return (pos_probs >= threshold).astype(int)
