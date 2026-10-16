"""Unit and integration tests for ML candidate rankers, probability calibration, and pipeline."""

from pathlib import Path
import numpy as np
import pytest

from uniforensic.generator.scenarios import ForensicDatabaseGenerator, ScenarioConfig
from uniforensic.models.calibration import (
    CalibratedRanker,
    calculate_ece,
    evaluate_calibration,
)
from uniforensic.models.classifier import ForensicCandidateClassifier
from uniforensic.models.dataset_builder import extract_database_dataset
from uniforensic.models.pipeline import ForensicMLPipeline


def test_ece_calculation():
    # Perfectly calibrated case: y_prob matches y_true
    y_true = np.array([1, 1, 0, 0, 1, 0, 1, 0, 1, 1])
    y_prob = np.array([0.9, 0.9, 0.1, 0.1, 0.8, 0.2, 0.8, 0.1, 0.9, 0.9])
    ece, p_true, p_pred, b_counts = calculate_ece(y_true, y_prob, n_bins=5)
    assert ece < 0.15
    assert len(b_counts) == 5

    # Completely uncalibrated case: all predict 0.9, but all true are 0
    y_true_bad = np.zeros(20, dtype=int)
    y_prob_bad = np.ones(20, dtype=float) * 0.95
    ece_bad, _, _, _ = calculate_ece(y_true_bad, y_prob_bad, n_bins=5)
    assert pytest.approx(ece_bad, 0.05) == 0.95


def test_model_training_and_calibration_pipeline(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)

    # Generate 1 train DB, 1 calib DB, 1 test DB
    train_db = gen.generate(ScenarioConfig("pipe_train", seed=10, num_sms_initial=25, num_sms_delete=8))
    calib_db = gen.generate(ScenarioConfig("pipe_calib", seed=20, num_sms_initial=20, num_sms_delete=6))
    test_db = gen.generate(ScenarioConfig("pipe_test", seed=30, num_sms_initial=20, num_sms_delete=6))

    pipeline = ForensicMLPipeline(seed=42)

    # Train and calibrate
    train_res = pipeline.train_and_calibrate([train_db], [calib_db])
    assert train_res["n_train_samples"] > 0
    assert train_res["n_calib_samples"] > 0
    assert len(train_res["feature_importances"]) > 0

    # Benchmark baselines on test DB
    benchmarks = pipeline.benchmark_all_baselines([test_db], include_live=False)
    assert len(benchmarks) == 4

    names = [b.model_name for b in benchmarks]
    assert "Structural-Only Baseline" in names
    assert "Random Forest (Uncalibrated)" in names
    assert "Random Forest (Calibrated)" in names
    assert "Gradient Boosted Trees" in names

    for b in benchmarks:
        assert 0.0 <= b.precision <= 1.0
        assert 0.0 <= b.recall <= 1.0
        assert 0.0 <= b.f1 <= 1.0
        assert 0.0 <= b.brier_score <= 1.0
        assert 0.0 <= b.expected_calibration_error <= 1.0
        assert b.total_candidates > 0
