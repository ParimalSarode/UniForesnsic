"""Defensive SQLite low-level structural parser modules."""

from uniforensic.parser.integrity import (
    DatabaseHeader,
    SQLITE_MAGIC,
    get_freelist_leaf_pages,
    parse_database_header,
    read_page,
)
from uniforensic.parser.page import (
    BTreePage,
    BTreePageHeader,
    FreeblockInfo,
    TableLeafCell,
    parse_btree_page,
    parse_page_header,
    parse_table_leaf_cell,
)
from uniforensic.parser.record import (
    ParsedRecord,
    SerialType,
    decode_serial_type,
    parse_record_payload,
)
from uniforensic.parser.varint import decode_varint, encode_varint
from uniforensic.parser.wal import (
    WALFrame,
    WALHeader,
    iterate_wal_frames,
    parse_wal_header,
)

__all__ = [
    "DatabaseHeader",
    "SQLITE_MAGIC",
    "get_freelist_leaf_pages",
    "parse_database_header",
    "read_page",
    "BTreePage",
    "BTreePageHeader",
    "FreeblockInfo",
    "TableLeafCell",
    "parse_btree_page",
    "parse_page_header",
    "parse_table_leaf_cell",
    "ParsedRecord",
    "SerialType",
    "decode_serial_type",
    "parse_record_payload",
    "decode_varint",
    "encode_varint",
    "WALFrame",
    "WALHeader",
    "iterate_wal_frames",
    "parse_wal_header",
]
