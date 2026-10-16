"""Structural B-tree carver for Freeblocks, Unallocated Space, and Freelist Pages."""

from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set

from uniforensic.carver.candidate import CandidateRecord, RegionType
from uniforensic.carver.schema_matcher import match_best_schema
from uniforensic.generator.schemas import ALL_SCHEMAS, TableSchema
from uniforensic.parser.integrity import (
    DatabaseHeader,
    get_freelist_leaf_pages,
    parse_database_header,
    read_page,
)
from uniforensic.parser.page import (
    BTreePage,
    parse_btree_page,
    parse_table_leaf_cell,
)
from uniforensic.parser.record import ParsedRecord, parse_record_payload
from uniforensic.parser.varint import decode_varint


class BTreeCarver:
    """Carves deleted records from SQLite B-Tree structures."""

    def __init__(
        self,
        db_path: Path,
        schemas: Optional[Dict[str, TableSchema]] = None,
        min_payload_size: int = 4,
        max_candidate_scan_stride: int = 1,
    ):
        self.db_path = Path(db_path)
        self.schemas = schemas or ALL_SCHEMAS
        self.min_payload_size = min_payload_size
        self.scan_stride = max_candidate_scan_stride


        with open(self.db_path, "rb") as f:
            header_bytes = f.read(100)
        self.db_header = parse_database_header(header_bytes)
        if self.db_header is None:
            raise ValueError(f"File {self.db_path} is not a valid SQLite 3 database")

        self.page_size = self.db_header.page_size
        self.encoding = self.db_header.encoding_str
        file_size = self.db_path.stat().st_size
        self.total_pages = max(1, file_size // self.page_size)

    def carve_all(self, include_live: bool = True) -> List[CandidateRecord]:
        """Carve all candidates from the database file."""
        candidates: List[CandidateRecord] = []
        seen_hashes: Set[str] = set()

        # Step 1: Carve all pages in database
        for page_num in range(1, self.total_pages + 1):
            page_bytes = read_page(self.db_path, page_num, self.page_size)
            page = parse_btree_page(page_bytes, page_num)

            # A: Live cells
            if include_live and page.header and page.header.is_table and page.header.is_leaf:
                for cell_offset in page.cell_offsets:
                    cell = parse_table_leaf_cell(page_bytes, cell_offset)
                    if cell and len(cell.local_payload_bytes) >= self.min_payload_size:
                        parsed = parse_record_payload(cell.local_payload_bytes, encoding=self.encoding)
                        if parsed.is_valid and len(parsed.values) > 0:
                            cand = self._create_candidate(
                                page_num=page_num,
                                page_offset=cell_offset,
                                region_type=RegionType.LIVE_CELL,
                                parsed=parsed,
                                rowid=cell.rowid,
                            )
                            candidates.append(cand)

            # B: Freeblocks
            for fb in page.freeblocks:
                fb_cands = self._carve_freeblock(page_num, fb.offset_in_page, fb.raw_bytes)
                for cand in fb_cands:
                    h = f"{cand.page_number}_{cand.page_offset}_{cand.value_hash}"
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        candidates.append(cand)

            # C: Unallocated space within active B-Tree leaf pages
            if page.header and page.header.is_leaf:
                for start, end in page.unallocated_ranges:
                    unalloc_cands = self._carve_buffer(
                        page_num=page_num,
                        base_page_offset=start,
                        buffer=page_bytes[start:end],
                        region_type=RegionType.UNALLOCATED_SPACE,
                    )
                    for cand in unalloc_cands:
                        h = f"{cand.page_number}_{cand.page_offset}_{cand.value_hash}"
                        if h not in seen_hashes:
                            seen_hashes.add(h)
                            candidates.append(cand)

        # Step 2: Carve Freelist Leaf Pages
        freelist_pages = get_freelist_leaf_pages(self.db_path, self.db_header)
        for fl_page_num in freelist_pages:
            fl_bytes = read_page(self.db_path, fl_page_num, self.page_size)
            # Carve whole page buffer
            fl_cands = self._carve_buffer(
                page_num=fl_page_num,
                base_page_offset=0,
                buffer=fl_bytes,
                region_type=RegionType.FREELIST_PAGE,
            )
            for cand in fl_cands:
                h = f"{cand.page_number}_{cand.page_offset}_{cand.value_hash}"
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    candidates.append(cand)

        return candidates

    def _carve_freeblock(
        self, page_num: int, fb_page_offset: int, fb_bytes: bytes
    ) -> List[CandidateRecord]:
        """Carve candidates specifically from a freeblock buffer."""
        candidates = []
        fb_len = len(fb_bytes)
        if fb_len < self.min_payload_size:
            return []

        # Attempt 1: Check if the freeblock contains a table leaf cell directly
        cell = parse_table_leaf_cell(fb_bytes, 0)
        if cell and len(cell.local_payload_bytes) >= self.min_payload_size:
            parsed = parse_record_payload(cell.local_payload_bytes, encoding=self.encoding)
            if parsed.is_valid and len(parsed.values) > 0:
                cand = self._create_candidate(
                    page_num=page_num,
                    page_offset=fb_page_offset,
                    region_type=RegionType.FREEBLOCK,
                    parsed=parsed,
                    rowid=cell.rowid,
                )
                candidates.append(cand)
                return candidates

        # Attempt 2: After the 4-byte freeblock header (offset 4)
        if fb_len >= 8:
            parsed_at_4 = parse_record_payload(fb_bytes[4:], encoding=self.encoding)
            if parsed_at_4.is_valid and len(parsed_at_4.values) > 0:
                cand = self._create_candidate(
                    page_num=page_num,
                    page_offset=fb_page_offset + 4,
                    region_type=RegionType.FREEBLOCK,
                    parsed=parsed_at_4,
                )
                candidates.append(cand)
                return candidates

        # Attempt 3: Sliding window scan within the freeblock
        candidates.extend(
            self._carve_buffer(
                page_num=page_num,
                base_page_offset=fb_page_offset,
                buffer=fb_bytes,
                region_type=RegionType.FREEBLOCK,
            )
        )
        return candidates

    def _carve_buffer(
        self,
        page_num: int,
        base_page_offset: int,
        buffer: bytes,
        region_type: RegionType,
    ) -> List[CandidateRecord]:
        """Scan a byte slice for valid candidate records defensively."""
        candidates: List[CandidateRecord] = []
        buf_len = len(buffer)
        offset = 0

        while offset < buf_len - self.min_payload_size:
            # Quick check: varint header length must be plausibly small
            # (records in SMS/browser/call tables have header len typically 3 to 30)
            b0 = buffer[offset]
            if b0 < 2 or b0 > 60:
                offset += self.scan_stride
                continue

            # Try parsing record payload starting here
            candidate_slice = buffer[offset:]
            parsed = parse_record_payload(candidate_slice, encoding=self.encoding)

            if parsed.is_valid and len(parsed.values) >= 2:
                # Check schema compatibility
                best_table, score, notes = match_best_schema(parsed, self.schemas)
                if best_table is not None and score >= 0.4:
                    cand = self._create_candidate(
                        page_num=page_num,
                        page_offset=base_page_offset + offset,
                        region_type=region_type,
                        parsed=parsed,
                        matched_table=best_table,
                        schema_score=score,
                    )
                    candidates.append(cand)
                    # Advance past this record to avoid overlapping sub-fragments
                    offset += max(1, parsed.total_payload_size)
                    continue

            offset += self.scan_stride

        return candidates

    def _create_candidate(
        self,
        page_num: int,
        page_offset: int,
        region_type: RegionType,
        parsed: ParsedRecord,
        rowid: Optional[int] = None,
        matched_table: Optional[str] = None,
        schema_score: float = 0.0,
    ) -> CandidateRecord:
        if matched_table is None:
            best_t, s, _ = match_best_schema(parsed, self.schemas)
            matched_table = best_t
            schema_score = s

        abs_offset = ((page_num - 1) * self.page_size) + page_offset
        cand_id = f"cand_{page_num}_{page_offset}_{region_type.value}"

        return CandidateRecord(
            candidate_id=cand_id,
            source_file=self.db_path.name,
            page_number=page_num,
            byte_offset=abs_offset,
            page_offset=page_offset,
            region_type=region_type,
            raw_bytes=parsed.raw_payload_bytes,
            header_length=parsed.header_length,
            serial_types=parsed.serial_types,
            values=parsed.values,
            is_structurally_valid=parsed.is_valid,
            diagnostics=parsed.diagnostics,
            rowid=rowid,
            matched_table=matched_table,
            schema_compatibility_score=schema_score,
        )
