"""Structural-only candidate classifier baseline using deterministic SQLite heuristic rules."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

from uniforensic.carver.candidate import CandidateRecord
from uniforensic.features.extractor import extract_candidate_features


@dataclass
class StructuralBaselineDecision:
    is_valid: bool
    confidence: float
    reasons: List[str]


class StructuralOnlyClassifier:
    """
    Baseline candidate recovery using structural SQLite invariants and heuristic constraints.
    Does not use machine learning.
    """

    def __init__(
        self,
        schema_threshold: float = 0.5,
        min_entropy: float = 1.5,
        max_entropy: float = 7.8,
    ):
        self.schema_threshold = schema_threshold
        self.min_entropy = min_entropy
        self.max_entropy = max_entropy

    def evaluate(self, candidate: CandidateRecord) -> StructuralBaselineDecision:
        feats = extract_candidate_features(candidate)
        reasons: List[str] = []
        penalties = 0.0

        # Rule 1: Must not have illegal serial types (codes 10, 11, or out of range)
        if feats["has_illegal_serial_types"] > 0:
            reasons.append("Illegal serial type in header")
            return StructuralBaselineDecision(is_valid=False, confidence=0.0, reasons=reasons)

        # Rule 2: Must not have varint decode errors
        if feats["varint_decode_error_count"] > 0:
            reasons.append("Varint decoding errors detected")
            penalties += 0.4

        # Rule 3: Declared payload must not severely exceed available bytes
        if feats["is_payload_truncated"] > 0:
            reasons.append("Payload truncated relative to declared serial type length")
            penalties += 0.5

        # Rule 4: Text fields must not contain embedded NUL characters
        if feats["has_embedded_nul_in_text"] > 0:
            reasons.append("Embedded NUL character in text field")
            return StructuralBaselineDecision(is_valid=False, confidence=0.0, reasons=reasons)

        # Rule 5: Schema compatibility must meet minimum threshold
        schema_score = feats["schema_compatibility_score"]
        if schema_score < self.schema_threshold:
            reasons.append(f"Schema compatibility score {schema_score:.2f} < {self.schema_threshold}")
            penalties += 0.3

        # Rule 6: Entropy bounds (detect pure zeroes or encrypted high-entropy junk)
        entropy = feats["byte_entropy"]
        if entropy < self.min_entropy:
            reasons.append(f"Entropy too low ({entropy:.2f} < {self.min_entropy}): repetitive/zeroed bytes")
            return StructuralBaselineDecision(is_valid=False, confidence=0.0, reasons=reasons)
        elif entropy > self.max_entropy:
            reasons.append(f"Entropy too high ({entropy:.2f} > {self.max_entropy}): random/distractor noise")
            penalties += 0.3

        # Rule 7: Text UTF-8 validity
        if feats["text_valid_utf8_ratio"] < 0.9:
            reasons.append("Text fields contain invalid UTF-8 sequences")
            penalties += 0.4

        confidence = max(0.0, min(1.0, schema_score - penalties))
        is_valid = (penalties < 0.5) and (confidence >= 0.4)

        return StructuralBaselineDecision(
            is_valid=is_valid,
            confidence=round(confidence, 4),
            reasons=reasons,
        )

    def predict(self, candidates: List[CandidateRecord]) -> np.ndarray:
        """Return binary predictions (1 = valid, 0 = invalid) for candidates."""
        return np.array([1 if self.evaluate(c).is_valid else 0 for c in candidates], dtype=int)

    def predict_proba(self, candidates: List[CandidateRecord]) -> np.ndarray:
        """Return confidence probabilities array of shape (N, 2)."""
        probs = []
        for c in candidates:
            conf = self.evaluate(c).confidence
            probs.append([1.0 - conf, conf])
        return np.array(probs, dtype=np.float32)
