"""Unit tests for candidate feature extraction and structural-only baseline."""

import numpy as np
import pytest

from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.features.baseline_rules import StructuralOnlyClassifier
from uniforensic.features.extractor import (
    FEATURE_NAMES,
    calculate_entropy,
    candidates_to_feature_matrix,
    extract_candidate_features,
)
from uniforensic.parser.record import SerialType


def test_entropy_calculation():
    # All identical bytes -> entropy 0.0
    zero_bytes = b"\x00" * 100
    assert calculate_entropy(zero_bytes) == 0.0

    # Two equally probable bytes -> entropy 1.0
    binary_bytes = b"\x00\xFF" * 50
    assert pytest.approx(calculate_entropy(binary_bytes), 0.01) == 1.0

    # High entropy bytes (all 256 byte values equally) -> entropy 8.0
    all_bytes = bytes(range(256))
    assert pytest.approx(calculate_entropy(all_bytes), 0.01) == 8.0


def test_feature_extraction_structure():
    cand = CandidateRecord(
        candidate_id="cand_test_1",
        source_file="test.sqlite",
        page_number=2,
        byte_offset=4100,
        page_offset=4,
        region_type=RegionType.FREEBLOCK,
        raw_bytes=b"\x03\x01\x17\x2aHELLO",
        header_length=3,
        serial_types=[
            SerialType(1, 1, "INT"),
            SerialType(23, 5, "TEXT"),
        ],
        values=[42, "HELLO"],
        is_structurally_valid=True,
        diagnostics=[],
        matched_table="messages",
        schema_compatibility_score=0.85,
    )

    feats = extract_candidate_features(cand)
    assert len(feats) == len(FEATURE_NAMES)
    for name in FEATURE_NAMES:
        assert name in feats
        assert isinstance(feats[name], (int, float))

    assert feats["header_length"] == 3.0
    assert feats["num_serial_types"] == 2.0
    assert feats["has_illegal_serial_types"] == 0.0
    assert feats["region_is_freeblock"] == 1.0
    assert feats["region_is_wal"] == 0.0
    assert feats["text_valid_utf8_ratio"] == 1.0
    assert feats["text_printable_ascii_ratio"] == 1.0
    assert feats["has_embedded_nul_in_text"] == 0.0


def test_matrix_conversion():
    cand = CandidateRecord(
        candidate_id="cand_test_2",
        source_file="test.sqlite",
        page_number=1,
        byte_offset=100,
        page_offset=100,
        region_type=RegionType.LIVE_CELL,
        raw_bytes=b"\x03\x01\x17\x2aHELLO",
        header_length=3,
        serial_types=[SerialType(1, 1, "INT"), SerialType(23, 5, "TEXT")],
        values=[42, "HELLO"],
        is_structurally_valid=True,
    )

    mat = candidates_to_feature_matrix([cand, cand])
    assert mat.shape == (2, len(FEATURE_NAMES))
    assert mat.dtype == np.float32

    empty_mat = candidates_to_feature_matrix([])
    assert empty_mat.shape == (0, len(FEATURE_NAMES))


def test_structural_only_classifier():
    clf = StructuralOnlyClassifier()

    # Valid candidate
    valid_cand = CandidateRecord(
        candidate_id="valid_1",
        source_file="test.sqlite",
        page_number=2,
        byte_offset=5000,
        page_offset=904,
        region_type=RegionType.FREEBLOCK,
        raw_bytes=b"\x04\x01\x04\x17\x01\x00\x00\x00\x05HELLO",
        header_length=4,
        serial_types=[SerialType(1, 1, "INT"), SerialType(4, 4, "INT"), SerialType(23, 5, "TEXT")],
        values=[1, 5, "HELLO"],
        is_structurally_valid=True,
        matched_table="messages",
        schema_compatibility_score=0.9,
    )
    decision = clf.evaluate(valid_cand)
    assert decision.is_valid
    assert decision.confidence >= 0.5

    # Invalid candidate with illegal serial type
    invalid_cand = CandidateRecord(
        candidate_id="invalid_1",
        source_file="test.sqlite",
        page_number=2,
        byte_offset=5100,
        page_offset=1004,
        region_type=RegionType.FREEBLOCK,
        raw_bytes=b"\x03\x0a\x01",
        header_length=3,
        serial_types=[SerialType(10, 0, "RESERVED")],
        values=[None],
        is_structurally_valid=False,
    )
    decision_inv = clf.evaluate(invalid_cand)
    assert not decision_inv.is_valid
    assert decision_inv.confidence == 0.0
    assert any("Illegal serial type" in r for r in decision_inv.reasons)
