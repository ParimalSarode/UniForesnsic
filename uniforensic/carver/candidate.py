"""Data structures for carved candidate records and diagnostic tracing."""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional

from uniforensic.parser.record import SerialType


class RegionType(str, Enum):
    FREEBLOCK = "FREEBLOCK"
    UNALLOCATED_SPACE = "UNALLOCATED_SPACE"
    FREELIST_PAGE = "FREELIST_PAGE"
    WAL_FRAME = "WAL_FRAME"
    LIVE_CELL = "LIVE_CELL"


@dataclass
class CandidateRecord:
    candidate_id: str
    source_file: str
    page_number: int
    byte_offset: int          # Absolute byte offset in source file
    page_offset: int          # Byte offset within page [0, page_size)
    region_type: RegionType
    raw_bytes: bytes
    header_length: int
    serial_types: List[SerialType]
    values: List[Any]
    is_structurally_valid: bool
    diagnostics: List[str] = field(default_factory=list)
    rowid: Optional[int] = None
    matched_table: Optional[str] = None
    schema_compatibility_score: float = 0.0

    @property
    def value_hash(self) -> str:
        """Deterministic hash of extracted candidate values."""
        val_str = str([(st.code, val) for st, val in zip(self.serial_types, self.values)])
        return hashlib.sha256(val_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_file": self.source_file,
            "page_number": self.page_number,
            "byte_offset": self.byte_offset,
            "page_offset": self.page_offset,
            "region_type": self.region_type.value,
            "raw_bytes_len": len(self.raw_bytes),
            "header_length": self.header_length,
            "num_columns": len(self.values),
            "values": [str(v)[:100] for v in self.values],
            "is_structurally_valid": self.is_structurally_valid,
            "diagnostics": self.diagnostics,
            "rowid": self.rowid,
            "matched_table": self.matched_table,
            "schema_compatibility_score": self.schema_compatibility_score,
        }
