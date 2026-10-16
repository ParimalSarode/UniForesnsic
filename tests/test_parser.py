"""Unit tests for SQLite structural parser modules."""

from pathlib import Path
import struct
import pytest

from uniforensic.generator.scenarios import ForensicDatabaseGenerator, ScenarioConfig
from uniforensic.parser.integrity import (
    parse_database_header,
    read_page,
)
from uniforensic.parser.page import (
    parse_btree_page,
    parse_page_header,
    parse_table_leaf_cell,
)
from uniforensic.parser.record import (
    decode_serial_type,
    parse_record_payload,
)
from uniforensic.parser.varint import decode_varint, encode_varint
from uniforensic.parser.wal import iterate_wal_frames, parse_wal_header


def test_varint_encode_decode():
    # 1-byte varints (0 to 127)
    for v in [0, 1, 42, 127]:
        b = encode_varint(v)
        assert len(b) == 1
        val, consumed = decode_varint(b, 0)
        assert val == v
        assert consumed == 1

    # Multi-byte varints
    test_values = [128, 255, 16384, 1000000, 2**32 - 1, 2**48 - 1, 2**63 - 1]
    for v in test_values:
        b = encode_varint(v)
        val, consumed = decode_varint(b, 0)
        assert val == v
        assert consumed == len(b)

    # Truncated varint raises ValueError
    with pytest.raises(ValueError):
        decode_varint(b"\x80\x80", 0, limit=2)

    # Offset out of bounds
    with pytest.raises(ValueError):
        decode_varint(b"\x01", 5)


def test_serial_type_decoding():
    assert decode_serial_type(0).content_size == 0   # NULL
    assert decode_serial_type(1).content_size == 1   # 8-bit int
    assert decode_serial_type(2).content_size == 2   # 16-bit int
    assert decode_serial_type(3).content_size == 3   # 24-bit int
    assert decode_serial_type(4).content_size == 4   # 32-bit int
    assert decode_serial_type(5).content_size == 6   # 48-bit int
    assert decode_serial_type(6).content_size == 8   # 64-bit int
    assert decode_serial_type(7).content_size == 8   # float
    assert decode_serial_type(8).content_size == 0   # constant 0
    assert decode_serial_type(9).content_size == 0   # constant 1
    assert decode_serial_type(10).type_name == "RESERVED"
    assert decode_serial_type(12).content_size == 0  # BLOB 0 bytes
    assert decode_serial_type(14).content_size == 1  # BLOB 1 byte
    assert decode_serial_type(13).content_size == 0  # TEXT 0 chars
    assert decode_serial_type(23).content_size == 5  # TEXT 5 chars ((23-13)/2)


def test_record_payload_parsing():
    # Construct a valid synthetic record payload:
    # Column 0: int 42 (serial type 1, 1 byte)
    # Column 1: text "HELLO" (serial type 23, 5 bytes)
    # Header: header_len (varint) + serial_type_0 (varint) + serial_type_1 (varint)
    # header_len = 3 (1 byte for len, 1 byte for st0, 1 byte for st1)
    payload = bytes([3, 1, 23, 42]) + b"HELLO"
    parsed = parse_record_payload(payload)
    assert parsed.is_valid
    assert len(parsed.values) == 2
    assert parsed.values[0] == 42
    assert parsed.values[1] == "HELLO"
    assert parsed.diagnostics == []


def test_malformed_record_resilience():
    # 1. Truncated header
    p1 = parse_record_payload(b"\x80")
    assert not p1.is_valid
    assert len(p1.diagnostics) > 0

    # 2. Header declaring 100 bytes on 5 byte buffer
    p2 = parse_record_payload(b"\x64\x01\x02\x03\x04")
    assert not p2.is_valid
    assert "exceeds buffer length" in p2.diagnostics[0]

    # 3. Serial type declaring 500 bytes of text on a 10 byte buffer
    # st = 13 + 500*2 = 1013 -> varint encode
    st_varint = encode_varint(1013)
    hdr = encode_varint(1 + len(st_varint)) + st_varint
    p3 = parse_record_payload(hdr + b"short")
    assert not p3.is_valid
    assert any("exceeds available payload" in d for d in p3.diagnostics)


def test_btree_page_and_cell_parsing(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="parser_test_db",
        seed=777,
        num_sms_initial=30,
        num_sms_delete=10,
        freelist_burst_count=10,
    )
    db_path, gt = gen.generate(cfg)

    with open(db_path, "rb") as f:
        db_bytes = f.read()

    # Parse database header
    dbh = parse_database_header(db_bytes)
    assert dbh is not None
    assert dbh.page_size == 4096
    assert dbh.encoding_str == "utf-8"

    # Parse Page 1
    p1_bytes = read_page(db_path, 1, 4096)
    p1 = parse_btree_page(p1_bytes, 1)
    assert p1.header is not None
    assert p1.header.is_table

    # Find leaf table pages and parse cells & freeblocks
    total_pages = len(db_bytes) // 4096
    leaf_pages_found = 0
    freeblocks_found = 0

    for pnum in range(1, total_pages + 1):
        pbytes = read_page(db_path, pnum, 4096)
        page = parse_btree_page(pbytes, pnum)
        if page.header and page.header.page_type == 0x0D:
            leaf_pages_found += 1
            if len(page.freeblocks) > 0:
                freeblocks_found += len(page.freeblocks)
            for offset in page.cell_offsets:
                cell = parse_table_leaf_cell(pbytes, offset)
                assert cell is not None
                assert cell.payload_size > 0

    assert leaf_pages_found >= 1
    # Deleting 10 SMS creates freeblocks in leaf pages
    assert freeblocks_found >= 1


def test_wal_parsing(tmp_path: Path):
    gen = ForensicDatabaseGenerator(tmp_path)
    cfg = ScenarioConfig(
        name="wal_test_db",
        seed=888,
        journal_mode="WAL",
        wal_checkpoint_mode="PASSIVE",
        num_sms_initial=20,
        num_sms_delete=5,
    )
    db_path, gt = gen.generate(cfg)
    wal_path = tmp_path / "wal_test_db.sqlite-wal"

    if wal_path.exists() and wal_path.stat().st_size >= 32:
        frames = list(iterate_wal_frames(wal_path))
        assert len(frames) > 0
        assert all(isinstance(f.page_number, int) for f in frames)
        assert all(len(f.page_bytes) == 4096 for f in frames)
