"""Explainable candidate feature extraction derived strictly from SQLite structural properties."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional
import numpy as np

from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.parser.record import SerialType


FEATURE_NAMES: List[str] = [
    "header_length",
    "num_serial_types",
    "header_varint_len",
    "header_len_ratio",
    "has_illegal_serial_types",
    "varint_decode_error_count",
    "total_payload_bytes",
    "declared_vs_avail_diff",
    "declared_vs_avail_ratio",
    "is_payload_truncated",
    "num_text_fields",
    "num_int_fields",
    "num_blob_fields",
    "num_null_fields",
    "text_valid_utf8_ratio",
    "text_printable_ascii_ratio",
    "has_embedded_nul_in_text",
    "has_plausible_timestamp",
    "max_int_magnitude_log",
    "avg_text_length",
    "byte_entropy",
    "zero_byte_fraction",
    "ascii_byte_fraction",
    "schema_compatibility_score",
    "column_count_delta",
    "region_is_freeblock",
    "region_is_unallocated",
    "region_is_freelist",
    "region_is_wal",
    "page_offset_ratio",
]


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of byte sequence (0.0 to 8.0 bits)."""
    if not data:
        return 0.0
    length = len(data)
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    entropy = 0.0
    for count in counts:
        if count > 0:
            p = count / length
            entropy -= p * math.log2(p)
    return entropy


def extract_candidate_features(
    candidate: CandidateRecord,
    page_size: int = 4096,
) -> Dict[str, float]:
    """
    Extract a dictionary of numerical features for a single candidate record.

    Ensures zero leakage of ground-truth labels.
    """
    raw = candidate.raw_bytes
    raw_len = len(raw)

    # 1. Header properties
    hdr_len = float(candidate.header_length)
    num_st = float(len(candidate.serial_types))
    hdr_varint_len = 1.0 if hdr_len <= 127 else 2.0
    hdr_ratio = (hdr_len / raw_len) if raw_len > 0 else 0.0

    has_illegal_st = 1.0 if any(
        st.type_name in ("RESERVED", "INVALID") for st in candidate.serial_types
    ) else 0.0

    diag_err_count = float(len(candidate.diagnostics))

    # 2. Declared vs available payload sizes
    sum_declared_content = sum(st.content_size for st in candidate.serial_types)
    declared_total = hdr_len + sum_declared_content
    diff = float(raw_len - declared_total)
    ratio = (raw_len / declared_total) if declared_total > 0 else 1.0
    is_truncated = 1.0 if raw_len < declared_total else 0.0

    # 3. Serial type composition
    num_text = sum(1 for st in candidate.serial_types if st.type_name == "TEXT")
    num_int = sum(1 for st in candidate.serial_types if st.type_name.startswith("INT"))
    num_blob = sum(1 for st in candidate.serial_types if st.type_name == "BLOB")
    num_null = sum(1 for st in candidate.serial_types if st.type_name in ("NULL", "INT_ZERO", "INT_ONE"))

    # 4. Content sanity
    text_values = [v for st, v in zip(candidate.serial_types, candidate.values) if st.type_name == "TEXT" and isinstance(v, str)]
    text_count = len(text_values)

    if text_count > 0:
        valid_utf8_count = sum(1 for d in candidate.diagnostics if "Invalid text encoding" in d)
        utf8_ratio = 1.0 - (valid_utf8_count / text_count)
        has_nul = 1.0 if any("\x00" in t for t in text_values) else 0.0

        total_chars = sum(len(t) for t in text_values)
        if total_chars > 0:
            printable_chars = sum(sum(1 for ch in t if 32 <= ord(ch) <= 126) for t in text_values)
            ascii_ratio = printable_chars / total_chars
            avg_text_len = total_chars / text_count
        else:
            ascii_ratio = 1.0
            avg_text_len = 0.0
    else:
        utf8_ratio = 1.0
        has_nul = 0.0
        ascii_ratio = 1.0
        avg_text_len = 0.0

    # Timestamp plausibility (Unix timestamps between year 2001 and 2033: 1e9 to 2e9)
    int_values = [v for st, v in zip(candidate.serial_types, candidate.values) if st.type_name == "INT" and isinstance(v, int)]
    has_plausible_ts = 1.0 if any(1000000000 <= v <= 2000000000 for v in int_values) else 0.0
    max_int = max([abs(v) for v in int_values], default=0)
    max_int_log = math.log10(max_int + 1)

    # 5. Information theoretic features
    entropy = calculate_entropy(raw)
    zero_count = raw.count(0x00)
    zero_frac = (zero_count / raw_len) if raw_len > 0 else 0.0
    ascii_bytes_count = sum(1 for b in raw if 32 <= b <= 126)
    ascii_byte_frac = (ascii_bytes_count / raw_len) if raw_len > 0 else 0.0

    # 6. Schema & Location
    schema_score = float(candidate.schema_compatibility_score)
    col_delta = abs(num_st - 7.0)  # SMS and Call logs have 7-8 columns

    reg_fb = 1.0 if candidate.region_type == RegionType.FREEBLOCK else 0.0
    reg_unalloc = 1.0 if candidate.region_type == RegionType.UNALLOCATED_SPACE else 0.0
    reg_freelist = 1.0 if candidate.region_type == RegionType.FREELIST_PAGE else 0.0
    reg_wal = 1.0 if candidate.region_type == RegionType.WAL_FRAME else 0.0
    page_offset_ratio = float(candidate.page_offset) / float(page_size)

    return {
        "header_length": hdr_len,
        "num_serial_types": num_st,
        "header_varint_len": hdr_varint_len,
        "header_len_ratio": hdr_ratio,
        "has_illegal_serial_types": has_illegal_st,
        "varint_decode_error_count": diag_err_count,
        "total_payload_bytes": float(raw_len),
        "declared_vs_avail_diff": diff,
        "declared_vs_avail_ratio": ratio,
        "is_payload_truncated": is_truncated,
        "num_text_fields": float(num_text),
        "num_int_fields": float(num_int),
        "num_blob_fields": float(num_blob),
        "num_null_fields": float(num_null),
        "text_valid_utf8_ratio": utf8_ratio,
        "text_printable_ascii_ratio": ascii_ratio,
        "has_embedded_nul_in_text": has_nul,
        "has_plausible_timestamp": has_plausible_ts,
        "max_int_magnitude_log": max_int_log,
        "avg_text_length": avg_text_len,
        "byte_entropy": entropy,
        "zero_byte_fraction": zero_frac,
        "ascii_byte_fraction": ascii_byte_frac,
        "schema_compatibility_score": schema_score,
        "column_count_delta": col_delta,
        "region_is_freeblock": reg_fb,
        "region_is_unallocated": reg_unalloc,
        "region_is_freelist": reg_freelist,
        "region_is_wal": reg_wal,
        "page_offset_ratio": page_offset_ratio,
    }


def candidates_to_feature_matrix(
    candidates: List[CandidateRecord],
    page_size: int = 4096,
) -> np.ndarray:
    """Convert a list of CandidateRecords to a 2D NumPy array of shape (N, num_features)."""
    rows = []
    for cand in candidates:
        feat_dict = extract_candidate_features(cand, page_size)
        rows.append([feat_dict[k] for k in FEATURE_NAMES])
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
    return np.array(rows, dtype=np.float32)
