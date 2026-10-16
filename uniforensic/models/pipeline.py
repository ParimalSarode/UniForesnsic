"""End-to-end model training, calibration, and comparative evaluation pipeline."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

from uniforensic.features.baseline_rules import StructuralOnlyClassifier
from uniforensic.models.calibration import (
    CalibrationMetrics,
    CalibratedRanker,
    evaluate_calibration,
)
from uniforensic.models.classifier import ForensicCandidateClassifier
from uniforensic.models.dataset_builder import (
    LabeledCandidate,
    build_split_dataset,
)


@dataclass
class EvaluationSummary:
    model_name: str
    precision: float
    recall: float
    f1: float
    accuracy: float
    roc_auc: float
    brier_score: float
    expected_calibration_error: float
    total_candidates: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    calibration_metrics: Optional[CalibrationMetrics] = None


class ForensicMLPipeline:
    """End-to-end training, calibration, and benchmarking pipeline."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rf_classifier = ForensicCandidateClassifier(
            model_type="random_forest", seed=seed, n_estimators=100
        )
        self.gb_classifier = ForensicCandidateClassifier(
            model_type="gradient_boosting", seed=seed, n_estimators=100
        )
        self.calibrated_rf: Optional[CalibratedRanker] = None
        self.structural_baseline = StructuralOnlyClassifier()

    def train_and_calibrate(
        self,
        train_dbs: List[Any],
        calib_dbs: List[Any],
    ) -> Dict[str, Any]:
        """Train models on train_dbs and calibrate on calib_dbs."""
        # 1. Build train dataset
        X_train, y_train, labeled_train = build_split_dataset(train_dbs, include_live=True)
        if len(y_train) == 0:
            raise ValueError("Training split is empty")

        # Fit Random Forest baseline
        self.rf_classifier.fit(X_train, y_train)

        # Fit Gradient Boosting comparison model
        self.gb_classifier.fit(X_train, y_train)

        # 2. Build calibration dataset
        X_calib, y_calib, labeled_calib = build_split_dataset(calib_dbs, include_live=True)
        if len(y_calib) == 0:
            raise ValueError("Calibration split is empty")

        # Fit probability calibrator on held-out calibration split
        self.calibrated_rf = CalibratedRanker(self.rf_classifier, method="isotonic")
        self.calibrated_rf.calibrate(X_calib, y_calib)

        return {
            "n_train_samples": len(y_train),
            "n_train_positives": int(np.sum(y_train)),
            "n_calib_samples": len(y_calib),
            "n_calib_positives": int(np.sum(y_calib)),
            "feature_importances": self.rf_classifier.get_feature_importances(),
        }

    def evaluate_model(
        self,
        model_name: str,
        predict_fn,
        predict_proba_fn,
        X_test: np.ndarray,
        y_test: np.ndarray,
        threshold: float = 0.5,
    ) -> EvaluationSummary:
        """Evaluate a candidate recovery model on test data."""
        if len(y_test) == 0:
            return EvaluationSummary(model_name, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        probs = predict_proba_fn(X_test)
        pos_probs = probs[:, 1] if probs.ndim == 2 else probs

        if predict_fn is not None:
            preds = predict_fn(X_test)
        else:
            preds = (pos_probs >= threshold).astype(int)

        # Metrics
        prec = float(precision_score(y_test, preds, zero_division=0))
        rec = float(recall_score(y_test, preds, zero_division=0))
        f1 = float(f1_score(y_test, preds, zero_division=0))
        acc = float(accuracy_score(y_test, preds))

        try:
            auc = float(roc_auc_score(y_test, pos_probs))
        except Exception:
            auc = 0.5

        # Calibration
        calib_res = evaluate_calibration(y_test, pos_probs)

        # Confusion matrix elements
        tp = int(np.sum((preds == 1) & (y_test == 1)))
        fp = int(np.sum((preds == 1) & (y_test == 0)))
        fn = int(np.sum((preds == 0) & (y_test == 1)))
        tn = int(np.sum((preds == 0) & (y_test == 0)))

        return EvaluationSummary(
            model_name=model_name,
            precision=round(prec, 4),
            recall=round(rec, 4),
            f1=round(f1, 4),
            accuracy=round(acc, 4),
            roc_auc=round(auc, 4),
            brier_score=calib_res.brier_score,
            expected_calibration_error=calib_res.expected_calibration_error,
            total_candidates=len(y_test),
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            true_negatives=tn,
            calibration_metrics=calib_res,
        )

    def benchmark_all_baselines(
        self,
        test_dbs: List[Any],
        include_live: bool = False,
    ) -> List[EvaluationSummary]:
        """Run all baselines on a designated test split."""
        X_test, y_test, labeled_test = build_split_dataset(test_dbs, include_live=include_live)
        candidates = [lc.candidate for lc in labeled_test]

        results = []

        # 1. Structural-Only Baseline
        res_struct = self.evaluate_model(
            model_name="Structural-Only Baseline",
            predict_fn=lambda X: self.structural_baseline.predict(candidates),
            predict_proba_fn=lambda X: self.structural_baseline.predict_proba(candidates),
            X_test=X_test,
            y_test=y_test,
        )
        results.append(res_struct)

        # 2. Random Forest Baseline (Uncalibrated)
        res_rf = self.evaluate_model(
            model_name="Random Forest (Uncalibrated)",
            predict_fn=self.rf_classifier.predict,
            predict_proba_fn=self.rf_classifier.predict_proba,
            X_test=X_test,
            y_test=y_test,
        )
        results.append(res_rf)

        # 3. Random Forest (Calibrated)
        if self.calibrated_rf:
            res_cal = self.evaluate_model(
                model_name="Random Forest (Calibrated)",
                predict_fn=self.calibrated_rf.predict,
                predict_proba_fn=self.calibrated_rf.predict_proba,
                X_test=X_test,
                y_test=y_test,
            )
            results.append(res_cal)

        # 4. Gradient Boosted Trees (Comparison)
        res_gb = self.evaluate_model(
            model_name="Gradient Boosted Trees",
            predict_fn=self.gb_classifier.predict,
            predict_proba_fn=self.gb_classifier.predict_proba,
            X_test=X_test,
            y_test=y_test,
        )
        results.append(res_gb)

        return results
