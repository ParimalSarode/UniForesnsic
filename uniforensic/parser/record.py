"""SQLite Record Format parser and serial-type decoder."""

from dataclasses import dataclass, field
import struct
from typing import Any, List, Optional, Tuple

from uniforensic.parser.varint import decode_varint


@dataclass
class SerialType:
    code: int
    content_size: int
    type_name: str  # NULL, INT, FLOAT, BLOB, TEXT, RESERVED


def decode_serial_type(code: int) -> SerialType:
    """Decode an SQLite serial type code into its content size and category."""
    if code == 0:
        return SerialType(code, 0, "NULL")
    elif code == 1:
        return SerialType(code, 1, "INT")
    elif code == 2:
        return SerialType(code, 2, "INT")
    elif code == 3:
        return SerialType(code, 3, "INT")
    elif code == 4:
        return SerialType(code, 4, "INT")
    elif code == 5:
        return SerialType(code, 6, "INT")
    elif code == 6:
        return SerialType(code, 8, "INT")
    elif code == 7:
        return SerialType(code, 8, "FLOAT")
    elif code == 8:
        return SerialType(code, 0, "INT_ZERO")
    elif code == 9:
        return SerialType(code, 0, "INT_ONE")
    elif code in (10, 11):
        return SerialType(code, 0, "RESERVED")
    elif code >= 12 and code % 2 == 0:
        return SerialType(code, (code - 12) // 2, "BLOB")
    elif code >= 13 and code % 2 == 1:
        return SerialType(code, (code - 13) // 2, "TEXT")
    else:
        return SerialType(code, 0, "INVALID")


@dataclass
class ParsedRecord:
    header_length: int
    serial_types: List[SerialType]
    values: List[Any]
    raw_payload_bytes: bytes
    total_payload_size: int
    is_valid: bool
    diagnostics: List[str] = field(default_factory=list)


def parse_record_payload(
    payload_bytes: bytes,
    encoding: str = "utf-8",
    max_payload_limit: int = 65536,
) -> ParsedRecord:
    """
    Defensively parse an SQLite record payload into values and diagnostics.

    Args:
        payload_bytes: The byte slice containing the record header and body.
        encoding: Text encoding ('utf-8', 'utf-16le', 'utf-16be').
        max_payload_limit: Maximum safe payload boundary to prevent runaway parsing.

    Returns:
        ParsedRecord dataclass containing parsed values, status, and diagnostics.
    """
    diagnostics: List[str] = []
    buf_len = len(payload_bytes)

    if buf_len < 2:
        return ParsedRecord(
            header_length=0,
            serial_types=[],
            values=[],
            raw_payload_bytes=payload_bytes,
            total_payload_size=buf_len,
            is_valid=False,
            diagnostics=["Payload buffer too small (< 2 bytes)"],
        )

    # 1. Parse header length varint
    try:
        header_len, varint_len = decode_varint(payload_bytes, 0, limit=buf_len)
    except Exception as e:
        return ParsedRecord(
            header_length=0,
            serial_types=[],
            values=[],
            raw_payload_bytes=payload_bytes,
            total_payload_size=buf_len,
            is_valid=False,
            diagnostics=[f"Corrupt record header size varint: {e}"],
        )

    if header_len < varint_len:
        diagnostics.append(f"Header length ({header_len}) smaller than varint itself ({varint_len})")
        return ParsedRecord(
            header_length=header_len,
            serial_types=[],
            values=[],
            raw_payload_bytes=payload_bytes,
            total_payload_size=buf_len,
            is_valid=False,
            diagnostics=diagnostics,
        )

    if header_len > buf_len:
        diagnostics.append(f"Header length ({header_len}) exceeds buffer length ({buf_len})")
        return ParsedRecord(
            header_length=header_len,
            serial_types=[],
            values=[],
            raw_payload_bytes=payload_bytes,
            total_payload_size=buf_len,
            is_valid=False,
            diagnostics=diagnostics,
        )

    # 2. Parse serial types in header
    serial_types: List[SerialType] = []
    hdr_offset = varint_len
    while hdr_offset < header_len:
        try:
            st_code, st_varint_len = decode_varint(payload_bytes, hdr_offset, limit=header_len)
            st = decode_serial_type(st_code)
            if st.type_name == "RESERVED" or st.type_name == "INVALID":
                diagnostics.append(f"Illegal serial type code {st_code} at header offset {hdr_offset}")
            serial_types.append(st)
            hdr_offset += st_varint_len
        except Exception as e:
            diagnostics.append(f"Failed parsing serial type at header offset {hdr_offset}: {e}")
            break

    # 3. Read body values
    data_offset = header_len
    values: List[Any] = []
    is_valid = len(diagnostics) == 0

    for idx, st in enumerate(serial_types):
        size = st.content_size
        if data_offset + size > buf_len:
            diagnostics.append(
                f"Field {idx} ({st.type_name}, size {size}) exceeds available payload (offset {data_offset} + {size} > {buf_len})"
            )
            is_valid = False
            values.append(None)
            continue

        field_bytes = payload_bytes[data_offset : data_offset + size]
        data_offset += size

        try:
            if st.type_name == "NULL":
                values.append(None)
            elif st.type_name == "INT_ZERO":
                values.append(0)
            elif st.type_name == "INT_ONE":
                values.append(1)
            elif st.type_name == "INT":
                if size == 1:
                    values.append(struct.unpack(">b", field_bytes)[0])
                elif size == 2:
                    values.append(struct.unpack(">h", field_bytes)[0])
                elif size == 3:
                    # 24-bit big-endian signed integer
                    b = b"\x00" + field_bytes if field_bytes[0] < 0x80 else b"\xFF" + field_bytes
                    values.append(struct.unpack(">i", b)[0])
                elif size == 4:
                    values.append(struct.unpack(">i", field_bytes)[0])
                elif size == 6:
                    # 48-bit big-endian signed integer
                    b = b"\x00\x00" + field_bytes if field_bytes[0] < 0x80 else b"\xFF\xFF" + field_bytes
                    values.append(struct.unpack(">q", b)[0])
                elif size == 8:
                    values.append(struct.unpack(">q", field_bytes)[0])
                else:
                    values.append(int.from_bytes(field_bytes, "big", signed=True))
            elif st.type_name == "FLOAT":
                values.append(struct.unpack(">d", field_bytes)[0])
            elif st.type_name == "TEXT":
                if b"\x00" in field_bytes:
                    diagnostics.append(f"Embedded NUL character in TEXT field {idx}")
                    is_valid = False
                try:
                    text_val = field_bytes.decode(encoding, errors="strict")
                    values.append(text_val)
                except UnicodeDecodeError:
                    diagnostics.append(f"Invalid text encoding in field {idx}")
                    values.append(field_bytes.decode(encoding, errors="replace"))
                    is_valid = False
            elif st.type_name == "BLOB":
                values.append(field_bytes)
            else:
                values.append(field_bytes)
        except Exception as e:
            diagnostics.append(f"Error parsing field {idx}: {e}")
            values.append(None)
            is_valid = False

    return ParsedRecord(
        header_length=header_len,
        serial_types=serial_types,
        values=values,
        raw_payload_bytes=payload_bytes[:data_offset],
        total_payload_size=data_offset,
        is_valid=is_valid,
        diagnostics=diagnostics,
    )
