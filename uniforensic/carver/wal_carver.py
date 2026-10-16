"""Carver for SQLite Write-Ahead Log (WAL) frames."""

from pathlib import Path
from typing import Dict, List, Optional, Set

from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.carver.schema_matcher import match_best_schema
from uniforensic.generator.schemas import ALL_SCHEMAS, TableSchema
from uniforensic.parser.page import parse_btree_page, parse_table_leaf_cell
from uniforensic.parser.record import parse_record_payload
from uniforensic.parser.wal import WALFrame, iterate_wal_frames


class WALCarver:
    """Extracts candidate records from Write-Ahead Log (WAL) frames."""

    def __init__(
        self,
        wal_path: Path,
        schemas: Optional[Dict[str, TableSchema]] = None,
        page_size: int = 4096,
        encoding: str = "utf-8",
        min_payload_size: int = 4,
    ):
        self.wal_path = Path(wal_path)
        self.schemas = schemas or ALL_SCHEMAS

        self.page_size = page_size
        self.encoding = encoding
        self.min_payload_size = min_payload_size

    def carve(self) -> List[CandidateRecord]:
        """Iterate all frames and carve candidates from leaf pages."""
        if not self.wal_path.exists():
            return []

        candidates: List[CandidateRecord] = []
        seen_hashes: Set[str] = set()

        for frame in iterate_wal_frames(self.wal_path, page_size=self.page_size):
            pbytes = frame.page_bytes
            page = parse_btree_page(pbytes, frame.page_number)

            if not page.header or not page.header.is_leaf:
                continue

            frame_hdr_offset = 32 + (frame.frame_index - 1) * (24 + self.page_size)
            page_data_offset = frame_hdr_offset + 24

            # 1. Carve table cells in WAL page
            for cell_offset in page.cell_offsets:
                cell = parse_table_leaf_cell(pbytes, cell_offset)
                if cell and len(cell.local_payload_bytes) >= self.min_payload_size:
                    parsed = parse_record_payload(cell.local_payload_bytes, encoding=self.encoding)
                    if parsed.is_valid and len(parsed.values) > 0:
                        best_table, score, _ = match_best_schema(parsed, self.schemas)
                        if best_table is not None and score >= 0.4:
                            cand = CandidateRecord(
                                candidate_id=f"wal_f{frame.frame_index}_p{frame.page_number}_{cell_offset}",
                                source_file=self.wal_path.name,
                                page_number=frame.page_number,
                                byte_offset=page_data_offset + cell_offset,
                                page_offset=cell_offset,
                                region_type=RegionType.WAL_FRAME,
                                raw_bytes=parsed.raw_payload_bytes,
                                header_length=parsed.header_length,
                                serial_types=parsed.serial_types,
                                values=parsed.values,
                                is_structurally_valid=parsed.is_valid,
                                diagnostics=parsed.diagnostics + frame.diagnostics,
                                rowid=cell.rowid,
                                matched_table=best_table,
                                schema_compatibility_score=score,
                            )
                            h = f"{cand.page_number}_{cand.page_offset}_{cand.value_hash}"
                            if h not in seen_hashes:
                                seen_hashes.add(h)
                                candidates.append(cand)

            # 2. Carve Freeblocks inside WAL page
            for fb in page.freeblocks:
                cell = parse_table_leaf_cell(fb.raw_bytes, 0)
                if cell and len(cell.local_payload_bytes) >= self.min_payload_size:
                    parsed = parse_record_payload(cell.local_payload_bytes, encoding=self.encoding)
                    if parsed.is_valid and len(parsed.values) > 0:
                        best_t, sc, _ = match_best_schema(parsed, self.schemas)
                        if best_t and sc >= 0.4:
                            cand = CandidateRecord(
                                candidate_id=f"wal_f{frame.frame_index}_fb_{fb.offset_in_page}",
                                source_file=self.wal_path.name,
                                page_number=frame.page_number,
                                byte_offset=page_data_offset + fb.offset_in_page,
                                page_offset=fb.offset_in_page,
                                region_type=RegionType.WAL_FRAME,
                                raw_bytes=parsed.raw_payload_bytes,
                                header_length=parsed.header_length,
                                serial_types=parsed.serial_types,
                                values=parsed.values,
                                is_structurally_valid=parsed.is_valid,
                                diagnostics=parsed.diagnostics + ["Carved from WAL freeblock"],
                                rowid=cell.rowid,
                                matched_table=best_t,
                                schema_compatibility_score=sc,
                            )
                            h = f"{cand.page_number}_{cand.page_offset}_{cand.value_hash}"
                            if h not in seen_hashes:
                                seen_hashes.add(h)
                                candidates.append(cand)

        return candidates
