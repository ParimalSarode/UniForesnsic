"""Evaluation metrics for comparative forensics benchmarking."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.metrics import brier_score_loss

from uniforensic.evaluation.adapters import RecoveredCandidate
from uniforensic.generator.ground_truth import (
    DatabaseGroundTruth,
    GroundTruthRecord,
    RecordStatus,
)
from uniforensic.models.calibration import calculate_ece


@dataclass
class BenchmarkMetrics:
    system_name: str
    scenario_name: str
    runtime_seconds: float
    total_recovered: int
    true_positives: int
    false_positives_live: int
    false_positives_ghost: int
    false_negatives: int
    raw_precision: float
    filtered_precision: float
    recall: float
    f1_score: float
    live_fp_rate: float
    ghost_fp_rate: float
    brier_score: float
    expected_calibration_error: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_name": self.system_name,
            "scenario_name": self.scenario_name,
            "runtime_seconds": round(self.runtime_seconds, 4),
            "total_recovered": self.total_recovered,
            "true_positives": self.true_positives,
            "false_positives_live": self.false_positives_live,
            "false_positives_ghost": self.false_positives_ghost,
            "false_negatives": self.false_negatives,
            "raw_precision": round(self.raw_precision, 4),
            "filtered_precision": round(self.filtered_precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "live_fp_rate": round(self.live_fp_rate, 4),
            "ghost_fp_rate": round(self.ghost_fp_rate, 4),
            "brier_score": round(self.brier_score, 4),
            "expected_calibration_error": round(self.expected_calibration_error, 4),
        }


def match_recovered_to_ground_truth(
    recovered: RecoveredCandidate,
    ground_truth: DatabaseGroundTruth,
) -> Tuple[Optional[GroundTruthRecord], Optional[RecordStatus]]:
    """Match a recovered candidate to ground truth records."""
    t_name = recovered.table_name
    cand_vals = recovered.values

    for gt_rec in ground_truth.records:
        if t_name and gt_rec.table_name != t_name:
            continue

        gt_vals = gt_rec.values
        # Match table messages
        if gt_rec.table_name == "messages":
            gt_body = str(gt_vals.get("body", ""))
            gt_ts = gt_vals.get("timestamp")
            gt_sender = str(gt_vals.get("sender", ""))
            b_match = any(isinstance(v, str) and (gt_body in v or v in gt_body) and len(v) > 5 for v in cand_vals)
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
            if b_match or (ts_match and gt_sender in [str(v) for v in cand_vals]):
                return gt_rec, gt_rec.status

        # Match table call_history
        elif gt_rec.table_name == "call_history":
            gt_phone = str(gt_vals.get("phone_number", ""))
            gt_ts = gt_vals.get("timestamp")
            p_match = any(v == gt_phone for v in cand_vals if isinstance(v, str))
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
            if p_match and ts_match:
                return gt_rec, gt_rec.status

        # Match table browser_history
        elif gt_rec.table_name == "browser_history":
            gt_url = str(gt_vals.get("url", ""))
            gt_ts = gt_vals.get("visit_time")
            u_match = any(v == gt_url for v in cand_vals if isinstance(v, str))
            ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
            if u_match or ts_match:
                return gt_rec, gt_rec.status

    return None, None


def evaluate_system_run(
    system_name: str,
    scenario_name: str,
    recovered_records: List[RecoveredCandidate],
    ground_truth: DatabaseGroundTruth,
    runtime_seconds: float,
) -> BenchmarkMetrics:
    """Evaluate a recovery run against database ground truth."""
    tp = 0
    fp_live = 0
    fp_ghost = 0
    recovered_gt_ids: Set[int] = set()

    y_true: List[int] = []
    y_prob: List[float] = []

    # Count genuine deleted ground truth records
    gt_deleted_count = sum(
        1 for r in ground_truth.records
        if r.status in (RecordStatus.DELETED_RECOVERABLE, RecordStatus.UPDATED_OLD_VERSION)
    )

    for rec in recovered_records:
        gt_rec, gt_status = match_recovered_to_ground_truth(rec, ground_truth)

        is_deleted = gt_status in (RecordStatus.DELETED_RECOVERABLE, RecordStatus.UPDATED_OLD_VERSION)
        is_live = (gt_status == RecordStatus.LIVE) or rec.is_live_collision
        is_distractor = (gt_status == RecordStatus.DISTRACTOR_NOISE)

        if is_deleted:
            tp += 1
            if gt_rec:
                recovered_gt_ids.add(gt_rec.record_id)
            y_true.append(1)
        elif is_live:
            fp_live += 1
            y_true.append(0)
        else:
            fp_ghost += 1
            y_true.append(0)

        y_prob.append(rec.confidence)

    fn = max(0, gt_deleted_count - len(recovered_gt_ids))
    total = len(recovered_records)

    # Precision & Recall
    raw_prec = tp / (tp + fp_live + fp_ghost) if (tp + fp_live + fp_ghost) > 0 else 0.0
    filt_prec = tp / (tp + fp_ghost) if (tp + fp_ghost) > 0 else 0.0
    rec_val = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (filt_prec * rec_val) / (filt_prec + rec_val) if (filt_prec + rec_val) > 0 else 0.0

    live_rate = fp_live / total if total > 0 else 0.0
    ghost_rate = fp_ghost / total if total > 0 else 0.0

    # Calibration & Brier score
    if len(y_true) > 0:
        y_true_arr = np.array(y_true, dtype=int)
        y_prob_arr = np.array(y_prob, dtype=float)
        brier = float(brier_score_loss(y_true_arr, y_prob_arr))
        ece, _, _, _ = calculate_ece(y_true_arr, y_prob_arr, n_bins=5)
    else:
        brier = 0.0
        ece = 0.0

    return BenchmarkMetrics(
        system_name=system_name,
        scenario_name=scenario_name,
        runtime_seconds=runtime_seconds,
        total_recovered=total,
        true_positives=tp,
        false_positives_live=fp_live,
        false_positives_ghost=fp_ghost,
        false_negatives=fn,
        raw_precision=raw_prec,
        filtered_precision=filt_prec,
        recall=rec_val,
        f1_score=f1,
        live_fp_rate=live_rate,
        ghost_fp_rate=ghost_rate,
        brier_score=brier,
        expected_calibration_error=ece,
    )
