"""SQLite Write-Ahead Log (WAL) parser and frame extractor."""

from dataclasses import dataclass, field
from pathlib import Path
import struct
from typing import Iterator, List, Optional


WAL_MAGIC_LE = 0x377F0682
WAL_MAGIC_BE = 0x377F0683


@dataclass
class WALHeader:
    magic: int
    version: int
    page_size: int
    seq_number: int
    salt1: int
    salt2: int
    checksum1: int
    checksum2: int
    is_big_endian: bool


@dataclass
class WALFrame:
    frame_index: int
    page_number: int
    db_size_pages: int
    salt1: int
    salt2: int
    checksum1: int
    checksum2: int
    is_commit: bool
    page_bytes: bytes
    diagnostics: List[str] = field(default_factory=list)


def parse_wal_header(data: bytes) -> Optional[WALHeader]:
    """Parse the 32-byte SQLite WAL header."""
    if len(data) < 32:
        return None

    magic_be = struct.unpack(">I", data[0:4])[0]
    magic_le = struct.unpack("<I", data[0:4])[0]

    if magic_be in (WAL_MAGIC_LE, WAL_MAGIC_BE):
        endian = ">"
        magic = magic_be
    elif magic_le in (WAL_MAGIC_LE, WAL_MAGIC_BE):
        endian = "<"
        magic = magic_le
    else:
        return None

    version = struct.unpack(f"{endian}I", data[4:8])[0]
    page_size = struct.unpack(f"{endian}I", data[8:12])[0]
    seq_number = struct.unpack(f"{endian}I", data[12:16])[0]
    salt1 = struct.unpack(f"{endian}I", data[16:20])[0]
    salt2 = struct.unpack(f"{endian}I", data[20:24])[0]
    chk1 = struct.unpack(f"{endian}I", data[24:28])[0]
    chk2 = struct.unpack(f"{endian}I", data[28:32])[0]

    return WALHeader(
        magic=magic,
        version=version,
        page_size=page_size,
        seq_number=seq_number,
        salt1=salt1,
        salt2=salt2,
        checksum1=chk1,
        checksum2=chk2,
        is_big_endian=(endian == ">"),
    )


def iterate_wal_frames(wal_path: Path, page_size: Optional[int] = None) -> Iterator[WALFrame]:
    """
    Iterate over frames in a WAL file defensively.

    Yields:
        WALFrame objects containing extracted page bytes and frame headers.
    """
    wal_path = Path(wal_path)
    if not wal_path.exists() or wal_path.stat().st_size < 32:
        return

    with open(wal_path, "rb") as f:
        header_bytes = f.read(32)
        wal_hdr = parse_wal_header(header_bytes)
        if wal_hdr is None:
            return

        p_size = wal_hdr.page_size if (wal_hdr.page_size and wal_hdr.page_size >= 512) else (page_size or 4096)
        frame_size = 24 + p_size
        frame_idx = 1
        endian = ">" if wal_hdr.is_big_endian else "<"

        while True:
            frame_hdr_bytes = f.read(24)
            if len(frame_hdr_bytes) < 24:
                break  # Clean end of file or incomplete frame

            page_num = struct.unpack(f"{endian}I", frame_hdr_bytes[0:4])[0]
            db_size = struct.unpack(f"{endian}I", frame_hdr_bytes[4:8])[0]
            salt1 = struct.unpack(f"{endian}I", frame_hdr_bytes[8:12])[0]
            salt2 = struct.unpack(f"{endian}I", frame_hdr_bytes[12:16])[0]
            chk1 = struct.unpack(f"{endian}I", frame_hdr_bytes[16:20])[0]
            chk2 = struct.unpack(f"{endian}I", frame_hdr_bytes[20:24])[0]

            frame_page_data = f.read(p_size)
            diagnostics = []
            if len(frame_page_data) < p_size:
                diagnostics.append(
                    f"Truncated frame data: expected {p_size} bytes, got {len(frame_page_data)}"
                )

            # Check salt consistency with WAL header
            if salt1 != wal_hdr.salt1 or salt2 != wal_hdr.salt2:
                diagnostics.append("Frame salt does not match WAL header salt")

            yield WALFrame(
                frame_index=frame_idx,
                page_number=page_num,
                db_size_pages=db_size,
                salt1=salt1,
                salt2=salt2,
                checksum1=chk1,
                checksum2=chk2,
                is_commit=(db_size > 0),
                page_bytes=frame_page_data,
                diagnostics=diagnostics,
            )

            frame_idx += 1
