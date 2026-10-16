"""Live-row false-positive control and segregation engine.

Distinguishes genuine recovered deleted records from live table rows,
preventing live-row false positives from corrupting forensic recovery claims.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

from uniforensic.carver.candidate import CandidateRecord
from uniforensic.generator.ground_truth import (
    DatabaseGroundTruth,
    GroundTruthRecord,
    RecordStatus,
)


class CollisionType(str, Enum):
    NONE = "NONE"
    PRIMARY_KEY = "PRIMARY_KEY"
    EXACT_TUPLE = "EXACT_TUPLE"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"


@dataclass
class FilterResult:
    candidate_id: str
    is_live_collision: bool
    collision_type: CollisionType
    matched_live_row_id: Optional[Any] = None
    confidence_reduction: float = 0.0
    diagnostics: str = ""


@dataclass
class SegregatedMetrics:
    total_candidates: int
    true_positives: int
    false_positives_live: int
    false_positives_ghost: int
    false_negatives: int
    true_negatives: int

    @property
    def total_false_positives(self) -> int:
        return self.false_positives_live + self.false_positives_ghost

    @property
    def raw_precision(self) -> float:
        denom = self.true_positives + self.total_false_positives
        return round(self.true_positives / denom, 4) if denom > 0 else 0.0

    @property
    def filtered_precision(self) -> float:
        """Precision when live-row collisions are successfully filtered out."""
        denom = self.true_positives + self.false_positives_ghost
        return round(self.true_positives / denom, 4) if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return round(self.true_positives / denom, 4) if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        prec = self.filtered_precision
        rec = self.recall
        return round(2 * (prec * rec) / (prec + rec), 4) if (prec + rec) > 0 else 0.0

    @property
    def live_fp_rate(self) -> float:
        """Fraction of all candidates that were live-row false positives."""
        return round(self.false_positives_live / self.total_candidates, 4) if self.total_candidates > 0 else 0.0

    @property
    def ghost_fp_rate(self) -> float:
        """Fraction of all candidates that were ghost/slack noise false positives."""
        return round(self.false_positives_ghost / self.total_candidates, 4) if self.total_candidates > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "true_positives": self.true_positives,
            "false_positives_live": self.false_positives_live,
            "false_positives_ghost": self.false_positives_ghost,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "raw_precision": self.raw_precision,
            "filtered_precision": self.filtered_precision,
            "recall": self.recall,
            "f1": self.f1,
            "live_fp_rate": self.live_fp_rate,
            "ghost_fp_rate": self.ghost_fp_rate,
        }


class LiveRowFilter:
    """
    Forensic engine extracting active live records to detect and prevent
    live-row false positives among carved candidates.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.live_rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
        self.pk_index: Dict[Tuple[str, Any], Dict[str, Any]] = {}
        self.tuple_hash_index: Set[Tuple[str, str]] = set()
        self._extract_live_tables()

    def _extract_live_tables(self) -> None:
        """Query active SQLite tables and populate index structures."""
        if not self.db_path.exists():
            return

        try:
            conn = sqlite3.connect(f"file:{self.db_path.resolve()}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Find all tables including sqlite_master
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            tables.append("sqlite_master")

            for t_name in tables:
                try:
                    # Get column info
                    cursor.execute(f"PRAGMA table_info({t_name});")
                    col_defs = cursor.fetchall()
                    col_names = [c[1] for c in col_defs]
                    pk_cols = [c[1] for c in col_defs if c[5] > 0]

                    cursor.execute(f"SELECT rowid, * FROM {t_name};")
                    rows = cursor.fetchall()
                except Exception:
                    continue

                self.live_rows_by_table[t_name] = []
                for row in rows:
                    r_id = row[0]
                    vals = row[1:]
                    row_dict = {col: v for col, v in zip(col_names, vals)}
                    row_dict["_rowid"] = r_id
                    self.live_rows_by_table[t_name].append(row_dict)

                    # Primary key index
                    if pk_cols:
                        for pk in pk_cols:
                            self.pk_index[(t_name, row_dict.get(pk))] = row_dict
                    self.pk_index[(t_name, r_id)] = row_dict

                    # Normalized tuple hash (non-null string/int values)
                    norm_tuple = tuple(sorted(
                        (k, str(v)) for k, v in row_dict.items()
                        if k != "_rowid" and v is not None and str(v).strip() != ""
                    ))
                    h = hashlib.sha256(str(norm_tuple).encode("utf-8")).hexdigest()
                    self.tuple_hash_index.add((t_name, h))

            conn.close()
        except Exception:
            # Fallback if db cannot be opened directly via sqlite3 (e.g. locked or corrupt header)
            pass

    def check_collision(self, candidate: CandidateRecord) -> FilterResult:
        """
        Check if candidate collides with any active live row in the database.
        """
        t_name = candidate.matched_table
        if not t_name or t_name not in self.live_rows_by_table:
            return FilterResult(
                candidate_id=candidate.candidate_id,
                is_live_collision=False,
                collision_type=CollisionType.NONE,
            )

        cand_vals = candidate.values
        live_rows = self.live_rows_by_table[t_name]

        # 1. Primary key / rowid match
        if candidate.rowid is not None:
            if (t_name, candidate.rowid) in self.pk_index:
                live_match = self.pk_index[(t_name, candidate.rowid)]
                # Confirm at least one other field matches to rule out random integer collision
                match_count = sum(1 for v in cand_vals if any(str(v) == str(lv) for lv in live_match.values()))
                if match_count >= 2:
                    return FilterResult(
                        candidate_id=candidate.candidate_id,
                        is_live_collision=True,
                        collision_type=CollisionType.PRIMARY_KEY,
                        matched_live_row_id=candidate.rowid,
                        confidence_reduction=1.0,
                        diagnostics=f"Matched live rowid={candidate.rowid} in table '{t_name}'",
                    )

        # 2. Check integer values for primary key collision
        for v in cand_vals:
            if isinstance(v, int) and (t_name, v) in self.pk_index:
                live_match = self.pk_index[(t_name, v)]
                # Check for strong similarity with this live row
                str_matches = sum(
                    1 for cv in cand_vals
                    if isinstance(cv, str) and len(cv) >= 4 and any(cv in str(lv) or str(lv) in cv for lv in live_match.values())
                )
                if str_matches >= 1:
                    return FilterResult(
                        candidate_id=candidate.candidate_id,
                        is_live_collision=True,
                        collision_type=CollisionType.PRIMARY_KEY,
                        matched_live_row_id=v,
                        confidence_reduction=1.0,
                        diagnostics=f"Matched live PK={v} with corroborating text in table '{t_name}'",
                    )

        # 3. Exact tuple collision or strong partial overlap
        for row in live_rows:
            # Count exact value matches
            exact_matches = 0
            partial_matches = 0
            non_null_live = [v for k, v in row.items() if k != "_rowid" and v is not None]

            for cv in cand_vals:
                if cv in non_null_live:
                    exact_matches += 1
                elif isinstance(cv, str) and len(cv) >= 5:
                    if any(isinstance(lv, str) and (cv in lv or lv in cv) for lv in non_null_live):
                        partial_matches += 1

            if len(non_null_live) > 0 and exact_matches >= max(2, len(non_null_live) - 1):
                return FilterResult(
                    candidate_id=candidate.candidate_id,
                    is_live_collision=True,
                    collision_type=CollisionType.EXACT_TUPLE,
                    matched_live_row_id=row.get("_rowid"),
                    confidence_reduction=1.0,
                    diagnostics=f"Exact tuple collision with live rowid={row.get('_rowid')} in table '{t_name}'",
                )

            # Partial overlap (e.g. matching timestamp and sender or phone number)
            if exact_matches >= 2 and partial_matches >= 1:
                return FilterResult(
                    candidate_id=candidate.candidate_id,
                    is_live_collision=True,
                    collision_type=CollisionType.PARTIAL_OVERLAP,
                    matched_live_row_id=row.get("_rowid"),
                    confidence_reduction=0.85,
                    diagnostics=f"Significant partial overlap with live rowid={row.get('_rowid')} in table '{t_name}'",
                )

        return FilterResult(
            candidate_id=candidate.candidate_id,
            is_live_collision=False,
            collision_type=CollisionType.NONE,
        )

    def filter_candidates(
        self,
        candidates: List[CandidateRecord],
        filter_live: bool = True,
    ) -> Tuple[List[CandidateRecord], List[FilterResult]]:
        """
        Screen a list of carved candidates.

        If filter_live is True, removes all candidates that collide with live rows.
        Returns:
            (filtered_candidates, list_of_all_filter_results)
        """
        passed: List[CandidateRecord] = []
        results: List[FilterResult] = []

        for cand in candidates:
            res = self.check_collision(cand)
            results.append(res)
            if filter_live and res.is_live_collision:
                continue
            passed.append(cand)

        return passed, results


def compute_segregated_metrics(
    candidates: List[CandidateRecord],
    predictions: List[int],
    ground_truth: DatabaseGroundTruth,
    live_filter: Optional[LiveRowFilter] = None,
) -> SegregatedMetrics:
    """
    Compute segregated forensic recovery metrics:
    - TP: Genuine deleted record correctly identified.
    - FP_live: Live table row mistakenly classified as recovered deleted record.
    - FP_ghost: Noise, corrupt fragment, or overwritten space classified as record.
    - FN: Genuine deleted record in ground truth missed.
    - TN: Non-records or live rows correctly rejected.
    """
    total_candidates = len(candidates)
    tp = 0
    fp_live = 0
    fp_ghost = 0
    tn = 0

    # Index genuine deleted ground truth records
    gt_deleted_records = [
        rec for rec in ground_truth.records
        if rec.status in (
            RecordStatus.DELETED_RECOVERABLE,
            RecordStatus.UPDATED_OLD_VERSION,
        )
    ]
    gt_live_records = [
        rec for rec in ground_truth.records
        if rec.status == RecordStatus.LIVE
    ]
    recovered_gt_keys: Set[int] = set()

    for cand, pred in zip(candidates, predictions):
        # Determine ground truth status
        matched_gt: Optional[GroundTruthRecord] = None

        cand_vals = cand.values
        t_name = cand.matched_table

        # Check against ground truth
        for gt_rec in ground_truth.records:
            if gt_rec.table_name != t_name:
                continue
            # Match heuristics
            if t_name == "messages":
                gt_body = str(gt_rec.values.get("body", ""))
                gt_ts = gt_rec.values.get("timestamp")
                gt_sender = str(gt_rec.values.get("sender", ""))
                b_match = any(isinstance(v, str) and (gt_body in v or v in gt_body) and len(v) > 5 for v in cand_vals)
                ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
                if b_match or (ts_match and gt_sender in [str(v) for v in cand_vals]):
                    matched_gt = gt_rec
                    break
            elif t_name == "call_history":
                gt_phone = str(gt_rec.values.get("phone_number", ""))
                gt_ts = gt_rec.values.get("timestamp")
                p_match = any(v == gt_phone for v in cand_vals if isinstance(v, str))
                ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
                if p_match and ts_match:
                    matched_gt = gt_rec
                    break
            elif t_name == "browser_history":
                gt_url = str(gt_rec.values.get("url", ""))
                gt_ts = gt_rec.values.get("visit_time")
                u_match = any(v == gt_url for v in cand_vals if isinstance(v, str))
                ts_match = any(v == gt_ts for v in cand_vals if isinstance(v, int))
                if u_match or ts_match:
                    matched_gt = gt_rec
                    break

        # Check live filter directly if available
        collision_res = live_filter.check_collision(cand) if live_filter else None
        has_filter_collision = collision_res.is_live_collision if collision_res else False

        is_gt_live = matched_gt is not None and matched_gt.status == RecordStatus.LIVE
        is_gt_deleted = matched_gt is not None and matched_gt.status in (
            RecordStatus.DELETED_RECOVERABLE,
            RecordStatus.UPDATED_OLD_VERSION,
        )

        if pred == 1:
            if is_gt_deleted:
                tp += 1
                recovered_gt_keys.add(matched_gt.record_id)
            elif is_gt_live or has_filter_collision:
                fp_live += 1
            else:
                fp_ghost += 1
        else:
            if is_gt_deleted:
                pass  # Missed deleted record
            else:
                tn += 1

    fn = max(0, len(gt_deleted_records) - len(recovered_gt_keys))

    return SegregatedMetrics(
        total_candidates=total_candidates,
        true_positives=tp,
        false_positives_live=fp_live,
        false_positives_ghost=fp_ghost,
        false_negatives=fn,
        true_negatives=tn,
    )
