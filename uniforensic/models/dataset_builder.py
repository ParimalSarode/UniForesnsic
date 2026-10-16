"""Dataset builder matching carved candidates against ground truth for ML training and evaluation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

from uniforensic.carver.btree_carver import BTreeCarver
from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.carver.wal_carver import WALCarver
from uniforensic.features.extractor import FEATURE_NAMES, extract_candidate_features
from uniforensic.generator.ground_truth import (
    DatabaseGroundTruth,
    GroundTruthRecord,
    RecordStatus,
)


@dataclass
class LabeledCandidate:
    candidate: CandidateRecord
    label: int  # 1 = valid ground-truth record, 0 = invalid fragment/noise
    matched_gt_record: Optional[GroundTruthRecord] = None
    gt_status: Optional[str] = None


def match_candidate_to_ground_truth(
    candidate: CandidateRecord,
    ground_truth: DatabaseGroundTruth,
) -> Tuple[int, Optional[GroundTruthRecord]]:
    """
    Determine if a candidate corresponds to a genuine ground truth record.

    Matches by table name and core identity fields:
    - messages: sender/recipient and timestamp, or body snippet
    - call_history: phone_number and timestamp
    - browser_history: url and visit_time
    """
    if not candidate.is_structurally_valid or not candidate.matched_table:
        return 0, None

    cand_vals = candidate.values
    t_name = candidate.matched_table

    # Search through ground truth records for this table
    for gt_rec in ground_truth.records:
        if gt_rec.table_name != t_name:
            continue

        gt_vals = gt_rec.values

        if t_name == "messages":
            # Match on sender, recipient, timestamp, or body
            gt_body = str(gt_vals.get("body", ""))
            gt_ts = gt_vals.get("timestamp")
            gt_sender = str(gt_vals.get("sender", ""))

            # Check if values match
            body_match = any(isinstance(v, str) and (gt_body in v or v in gt_body) and len(v) > 5 for v in cand_vals)
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))

            if body_match or (ts_match and gt_sender in [str(v) for v in cand_vals]):
                return 1, gt_rec

        elif t_name == "call_history":
            gt_phone = str(gt_vals.get("phone_number", ""))
            gt_ts = gt_vals.get("timestamp")

            phone_match = any(v == gt_phone for v in cand_vals if isinstance(v, str))
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))

            if phone_match and ts_match:
                return 1, gt_rec

        elif t_name == "browser_history":
            gt_url = str(gt_vals.get("url", ""))
            gt_ts = gt_vals.get("visit_time")

            url_match = any(v == gt_url for v in cand_vals if isinstance(v, str))
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))

            if url_match or (ts_match and any(isinstance(v, str) and gt_vals.get("title", "") in v for v in cand_vals)):
                return 1, gt_rec

    return 0, None


def extract_database_dataset(
    db_path: Path,
    ground_truth: DatabaseGroundTruth,
    include_live: bool = True,
) -> Tuple[np.ndarray, np.ndarray, List[LabeledCandidate]]:
    """
    Carve all candidates from a database and its WAL file, label them, and extract feature matrix.

    Returns:
        (X: shape (N, num_features), y: shape (N,), labeled_candidates)
    """
    db_carver = BTreeCarver(db_path)
    candidates = db_carver.carve_all(include_live=include_live)

    wal_path = db_path.parent / f"{db_path.name}-wal"
    if wal_path.exists() and wal_path.stat().st_size > 32:
        wal_carver = WALCarver(wal_path)
        wal_cands = wal_carver.carve()
        candidates.extend(wal_cands)

    labeled: List[LabeledCandidate] = []
    feature_rows = []
    labels = []

    for cand in candidates:
        label, gt_rec = match_candidate_to_ground_truth(cand, ground_truth)
        gt_st = gt_rec.status.value if gt_rec else None

        # If it was marked DISTRACTOR_NOISE in ground truth, label is strictly 0
        if gt_rec and gt_rec.status == RecordStatus.DISTRACTOR_NOISE:
            label = 0

        # If it was marked DELETED_OVERWRITTEN (zeroed out by secure_delete), label is strictly 0
        if gt_rec and gt_rec.status == RecordStatus.DELETED_OVERWRITTEN:
            label = 0

        labeled_cand = LabeledCandidate(
            candidate=cand,
            label=label,
            matched_gt_record=gt_rec,
            gt_status=gt_st,
        )
        labeled.append(labeled_cand)

        feats = extract_candidate_features(cand)
        feature_rows.append([feats[k] for k in FEATURE_NAMES])
        labels.append(label)

    if not feature_rows:
        X = np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
        y = np.empty((0,), dtype=int)
    else:
        X = np.array(feature_rows, dtype=np.float32)
        y = np.array(labels, dtype=int)

    return X, y, labeled


def build_split_dataset(
    db_items: List[Tuple[Path, DatabaseGroundTruth]],
    include_live: bool = True,
) -> Tuple[np.ndarray, np.ndarray, List[LabeledCandidate]]:
    """Build aggregated dataset from a list of databases belonging to a single split."""
    X_list = []
    y_list = []
    all_labeled = []

    for db_path, gt in db_items:
        X_sub, y_sub, labeled_sub = extract_database_dataset(db_path, gt, include_live=include_live)
        if len(y_sub) > 0:
            X_list.append(X_sub)
            y_list.append(y_sub)
            all_labeled.extend(labeled_sub)

    if not X_list:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float32), np.empty((0,), dtype=int), []

    X = np.vstack(X_list)
    y = np.concatenate(y_list)
    return X, y, all_labeled
