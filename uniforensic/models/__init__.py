"""Machine learning models, probability calibration, and benchmarking pipeline."""

from uniforensic.models.calibration import (
    CalibrationMetrics,
    CalibratedRanker,
    calculate_ece,
    evaluate_calibration,
)
from uniforensic.models.classifier import ForensicCandidateClassifier
from uniforensic.models.dataset_builder import (
    LabeledCandidate,
    build_split_dataset,
    extract_database_dataset,
    match_candidate_to_ground_truth,
)
from uniforensic.models.pipeline import (
    EvaluationSummary,
    ForensicMLPipeline,
)

__all__ = [
    "CalibrationMetrics",
    "CalibratedRanker",
    "calculate_ece",
    "evaluate_calibration",
    "ForensicCandidateClassifier",
    "LabeledCandidate",
    "build_split_dataset",
    "extract_database_dataset",
    "match_candidate_to_ground_truth",
    "EvaluationSummary",
    "ForensicMLPipeline",
]
