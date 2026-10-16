"""SQLite database header, freelist page resolution, and evidence bounds checking."""

from dataclasses import dataclass, field
from pathlib import Path
import struct
from typing import List, Optional, Tuple


SQLITE_MAGIC = b"SQLite format 3\x00"


@dataclass
class DatabaseHeader:
    page_size: int
    write_version: int  # 1=legacy, 2=WAL
    read_version: int   # 1=legacy, 2=WAL
    reserved_space: int
    text_encoding: int  # 1=UTF-8, 2=UTF-16le, 3=UTF-16be
    freelist_trunk_page: int
    total_freelist_pages: int
    page_count: int

    @property
    def encoding_str(self) -> str:
        if self.text_encoding == 1:
            return "utf-8"
        elif self.text_encoding == 2:
            return "utf-16le"
        elif self.text_encoding == 3:
            return "utf-16be"
        return "utf-8"


def parse_database_header(data: bytes) -> Optional[DatabaseHeader]:
    """Parse the 100-byte SQLite database header from Page 1."""
    if len(data) < 100:
        return None

    if data[:16] != SQLITE_MAGIC:
        return None

    raw_page_size = struct.unpack(">H", data[16:18])[0]
    page_size = 65536 if raw_page_size == 1 else raw_page_size

    write_ver = data[18]
    read_ver = data[19]
    reserved = data[20]
    freelist_trunk = struct.unpack(">I", data[32:36])[0]
    total_freelist = struct.unpack(">I", data[36:40])[0]
    page_count = struct.unpack(">I", data[28:32])[0]
    encoding = struct.unpack(">I", data[56:60])[0]

    return DatabaseHeader(
        page_size=page_size,
        write_version=write_ver,
        read_version=read_ver,
        reserved_space=reserved,
        text_encoding=encoding,
        freelist_trunk_page=freelist_trunk,
        total_freelist_pages=total_freelist,
        page_count=page_count,
    )


def read_page(db_path: Path, page_number: int, page_size: int) -> bytes:
    """Read an exact page from a database file safely (1-indexed page number)."""
    if page_number < 1:
        raise ValueError(f"Invalid page number {page_number}")

    offset = (page_number - 1) * page_size
    with open(db_path, "rb") as f:
        f.seek(offset)
        page_data = f.read(page_size)
    return page_data


def get_freelist_leaf_pages(db_path: Path, header: DatabaseHeader) -> List[int]:
    """
    Traverse SQLite freelist trunk pages to find all freelist leaf page numbers.

    Each trunk page structure:
    - Bytes 0-3: Next trunk page number (or 0 if last)
    - Bytes 4-7: Number of leaf page numbers on this trunk page
    - Bytes 8+: Array of 4-byte big-endian leaf page numbers
    """
    leaf_pages: List[int] = []
    trunk_page_num = header.freelist_trunk_page
    visited_trunks = set()

    with open(db_path, "rb") as f:
        file_size = db_path.stat().st_size
        total_pages = file_size // header.page_size

        while trunk_page_num > 0 and trunk_page_num not in visited_trunks:
            visited_trunks.add(trunk_page_num)
            if trunk_page_num > total_pages:
                break

            offset = (trunk_page_num - 1) * header.page_size
            f.seek(offset)
            trunk_data = f.read(header.page_size)
            if len(trunk_data) < 8:
                break

            next_trunk = struct.unpack(">I", trunk_data[0:4])[0]
            num_leaves = struct.unpack(">I", trunk_data[4:8])[0]

            # Read leaf page numbers
            ptr = 8
            for _ in range(num_leaves):
                if ptr + 4 > len(trunk_data):
                    break
                leaf_num = struct.unpack(">I", trunk_data[ptr : ptr + 4])[0]
                if 1 <= leaf_num <= total_pages:
                    leaf_pages.append(leaf_num)
                ptr += 4

            trunk_page_num = next_trunk

    return leaf_pages
