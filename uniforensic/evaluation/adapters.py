"""Standardized evaluation adapters for comparative forensics benchmarking.

Adapts UniForensic structural baseline, ML rankers, DoD Cyber Crime Center's
sqlite_dissect, and DFRWS bring2lite into a unified recovery interface.
"""

import abc
from dataclasses import dataclass, field
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from uniforensic.carver.btree_carver import BTreeCarver
from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.carver.wal_carver import WALCarver
from uniforensic.features.baseline_rules import StructuralOnlyClassifier
from uniforensic.features.extractor import FEATURE_NAMES, extract_candidate_features
from uniforensic.filter.live_filter import LiveRowFilter
from uniforensic.generator.ground_truth import DatabaseGroundTruth
from uniforensic.models.calibration import CalibratedRanker
from uniforensic.models.classifier import ForensicCandidateClassifier


@dataclass
class RecoveredCandidate:
    system_name: str
    table_name: Optional[str]
    values: List[Any]
    confidence: float
    raw_bytes: bytes = b""
    is_live_collision: bool = False
    source_info: str = ""


class BaseCarverAdapter(abc.ABC):
    """Abstract interface for SQLite recovery systems."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def recover(
        self,
        db_path: Path,
        live_filter: Optional[LiveRowFilter] = None,
    ) -> Tuple[List[RecoveredCandidate], float]:
        """
        Carve and rank records from the database.
        Returns (recovered_records, elapsed_seconds).
        """
        raise NotImplementedError


class StructuralOnlyAdapter(BaseCarverAdapter):
    """Baseline structural SQLite carver without machine learning ranking."""

    def __init__(self):
        self.classifier = StructuralOnlyClassifier()

    @property
    def name(self) -> str:
        return "Structural-Only Carver"

    def recover(
        self,
        db_path: Path,
        live_filter: Optional[LiveRowFilter] = None,
    ) -> Tuple[List[RecoveredCandidate], float]:
        t0 = time.perf_counter()
        carver = BTreeCarver(db_path)
        candidates = carver.carve_all(include_live=False)

        wal_path = db_path.parent / f"{db_path.name}-wal"
        if wal_path.exists() and wal_path.stat().st_size > 32:
            wal_carver = WALCarver(wal_path)
            candidates.extend(wal_carver.carve())

        preds = self.classifier.predict(candidates)
        probs = self.classifier.predict_proba(candidates)
        pos_probs = probs[:, 1] if (probs.ndim == 2 and probs.shape[1] >= 2) else probs

        recovered: List[RecoveredCandidate] = []
        for cand, pred, prob in zip(candidates, preds, pos_probs):
            if pred == 1:
                is_live = False
                if live_filter:
                    is_live = live_filter.check_collision(cand).is_live_collision

                recovered.append(RecoveredCandidate(
                    system_name=self.name,
                    table_name=cand.matched_table,
                    values=cand.values,
                    confidence=float(prob),
                    raw_bytes=cand.raw_bytes,
                    is_live_collision=is_live,
                    source_info=f"{cand.region_type.value}:p{cand.page_number}",
                ))

        elapsed = time.perf_counter() - t0
        return recovered, elapsed


class MLRankerAdapter(BaseCarverAdapter):
    """ML-assisted candidate ranker (Random Forest or Gradient Boosting)."""

    def __init__(
        self,
        model: Any,
        name: str,
        threshold: float = 0.5,
    ):
        self._model = model
        self._name = name
        self.threshold = threshold

    @property
    def name(self) -> str:
        return self._name

    def recover(
        self,
        db_path: Path,
        live_filter: Optional[LiveRowFilter] = None,
    ) -> Tuple[List[RecoveredCandidate], float]:
        t0 = time.perf_counter()
        carver = BTreeCarver(db_path)
        candidates = carver.carve_all(include_live=False)

        wal_path = db_path.parent / f"{db_path.name}-wal"
        if wal_path.exists() and wal_path.stat().st_size > 32:
            wal_carver = WALCarver(wal_path)
            candidates.extend(wal_carver.carve())

        if not candidates:
            return [], time.perf_counter() - t0

        # Feature matrix
        feat_rows = []
        for c in candidates:
            f_dict = extract_candidate_features(c)
            feat_rows.append([f_dict[k] for k in FEATURE_NAMES])
        X = np.array(feat_rows, dtype=np.float32)

        # Predict
        probs = self._model.predict_proba(X)
        pos_probs = probs[:, 1] if probs.ndim == 2 else probs

        recovered: List[RecoveredCandidate] = []
        for cand, prob in zip(candidates, pos_probs):
            if prob >= self.threshold:
                is_live = False
                if live_filter:
                    is_live = live_filter.check_collision(cand).is_live_collision

                recovered.append(RecoveredCandidate(
                    system_name=self.name,
                    table_name=cand.matched_table,
                    values=cand.values,
                    confidence=float(prob),
                    raw_bytes=cand.raw_bytes,
                    is_live_collision=is_live,
                    source_info=f"{cand.region_type.value}:p{cand.page_number}",
                ))

        elapsed = time.perf_counter() - t0
        return recovered, elapsed


class SqliteDissectAdapter(BaseCarverAdapter):
    """Adapter for DoD Cyber Crime Center (DC3) sqlite_dissect."""

    @property
    def name(self) -> str:
        return "sqlite_dissect (DoD DC3)"

    def recover(
        self,
        db_path: Path,
        live_filter: Optional[LiveRowFilter] = None,
    ) -> Tuple[List[RecoveredCandidate], float]:
        t0 = time.perf_counter()
        recovered: List[RecoveredCandidate] = []

        try:
            import sqlite_dissect
            from sqlite_dissect.file.database.database import Database

            # Initialize Database with file_size=None to bypass the strict_format_checking parameter bug
            db = Database(str(db_path.resolve()), file_size=None, strict_format_checking=False)

            tables = [e.name for e in db.master_schema.master_schema_entries if not e.without_row_id]
            for t_name in tables:
                if t_name.startswith("sqlite_"):
                    continue
                try:
                    sig = sqlite_dissect.create_table_signature(t_name, db)
                    carved_cells = sqlite_dissect.carve_table(t_name, sig, db)

                    for cell in carved_cells:
                        if hasattr(cell, "payload") and cell.payload and hasattr(cell.payload, "record_columns"):
                            vals = []
                            for col in cell.payload.record_columns:
                                v = col.value
                                if isinstance(v, bytes):
                                    try:
                                        v = v.decode("utf-8")
                                    except UnicodeDecodeError:
                                        v = str(v)
                                vals.append(v)

                            # Synthetic CandidateRecord for live collision check
                            cand_synth = CandidateRecord(
                                candidate_id=f"dissect_{cell.page_number}_{cell.start_offset}",
                                source_file=db_path.name,
                                page_number=cell.page_number,
                                byte_offset=cell.file_offset if hasattr(cell, "file_offset") else 0,
                                page_offset=cell.start_offset if hasattr(cell, "start_offset") else 0,
                                region_type=RegionType.FREEBLOCK,
                                raw_bytes=b"",
                                header_length=0,
                                serial_types=[],
                                values=vals,
                                is_structurally_valid=True,
                                matched_table=t_name,
                                rowid=getattr(cell, "row_id", None),
                            )

                            is_live = False
                            if live_filter:
                                is_live = live_filter.check_collision(cand_synth).is_live_collision

                            recovered.append(RecoveredCandidate(
                                system_name=self.name,
                                table_name=t_name,
                                values=vals,
                                confidence=1.0,
                                is_live_collision=is_live,
                                source_info=f"p{cell.page_number}:{cell.location}",
                            ))
                except Exception:
                    continue
        except Exception:
            pass

        elapsed = time.perf_counter() - t0
        return recovered, elapsed


class Bring2LiteAdapter(BaseCarverAdapter):
    """Adapter for Christian Meng & Harald Baier's bring2lite (DFRWS)."""

    @property
    def name(self) -> str:
        return "bring2lite (Meng & Baier)"

    def recover(
        self,
        db_path: Path,
        live_filter: Optional[LiveRowFilter] = None,
    ) -> Tuple[List[RecoveredCandidate], float]:
        t0 = time.perf_counter()
        recovered: List[RecoveredCandidate] = []

        try:
            import sys
            b2l_path = Path("third_party/bring2lite")
            if str(b2l_path.resolve()) not in sys.path:
                sys.path.insert(0, str(b2l_path.resolve()))

            from bring2lite.classes.sqlite_parser import SQLiteParser

            parser = SQLiteParser()
            with tempfile.TemporaryDirectory() as tmp_dir:
                out_path = os.path.join(tmp_dir, "b2l_out.json")
                res = parser.parse(str(db_path.resolve()), out_path, format=2)

                body = res.get("body", {})
                # Extract records from freelist leaf pages and regular pages
                all_raw_records = []
                for k, v in body.items():
                    if isinstance(v, dict):
                        for page_k, recs in v.items():
                            if isinstance(recs, list):
                                all_raw_records.extend(recs)
                    elif isinstance(v, list):
                        all_raw_records.extend(v)

                for item in all_raw_records:
                    if not isinstance(item, list):
                        continue
                    # item format: [['TEXT', b'val'], ['32bit', 12345], ...]
                    extracted_vals = []
                    for col in item:
                        if isinstance(col, list) and len(col) >= 2:
                            val = col[1]
                            if isinstance(val, bytes):
                                try:
                                    val = val.decode("utf-8")
                                except UnicodeDecodeError:
                                    val = str(val)
                            extracted_vals.append(val)
                        else:
                            extracted_vals.append(col)

                    # Infer matched table
                    inferred_table = None
                    if len(extracted_vals) == 8:
                        inferred_table = "messages"
                    elif len(extracted_vals) == 7:
                        inferred_table = "browser_history"
                    elif len(extracted_vals) == 6:
                        inferred_table = "call_history"

                    cand_synth = CandidateRecord(
                        candidate_id="b2l_cand",
                        source_file=db_path.name,
                        page_number=0,
                        byte_offset=0,
                        page_offset=0,
                        region_type=RegionType.FREELIST_PAGE,
                        raw_bytes=b"",
                        header_length=0,
                        serial_types=[],
                        values=extracted_vals,
                        is_structurally_valid=True,
                        matched_table=inferred_table,
                    )

                    is_live = False
                    if live_filter:
                        is_live = live_filter.check_collision(cand_synth).is_live_collision

                    recovered.append(RecoveredCandidate(
                        system_name=self.name,
                        table_name=inferred_table,
                        values=extracted_vals,
                        confidence=1.0,
                        is_live_collision=is_live,
                        source_info="bring2lite_carved",
                    ))
        except Exception:
            pass

        elapsed = time.perf_counter() - t0
        return recovered, elapsed
