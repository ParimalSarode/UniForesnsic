"""Candidate feature extraction and structural-only baseline package."""

from uniforensic.features.baseline_rules import (
    StructuralBaselineDecision,
    StructuralOnlyClassifier,
)
from uniforensic.features.extractor import (
    FEATURE_NAMES,
    calculate_entropy,
    candidates_to_feature_matrix,
    extract_candidate_features,
)

__all__ = [
    "FEATURE_NAMES",
    "calculate_entropy",
    "candidates_to_feature_matrix",
    "extract_candidate_features",
    "StructuralBaselineDecision",
    "StructuralOnlyClassifier",
]
