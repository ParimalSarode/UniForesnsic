"""SQLite B-Tree page header parser, cell pointer array, freeblocks, and unallocated space extractor."""

from dataclasses import dataclass, field
import struct
from typing import List, Optional, Tuple

from uniforensic.parser.varint import decode_varint


@dataclass
class FreeblockInfo:
    offset_in_page: int
    size: int
    next_offset: int
    raw_bytes: bytes


@dataclass
class BTreePageHeader:
    page_number: int
    page_type: int  # 0x02, 0x05, 0x0a, 0x0d
    first_freeblock: int
    num_cells: int
    cell_content_offset: int
    fragmented_bytes: int
    right_most_pointer: Optional[int]
    header_offset: int  # 100 for page 1, 0 for others
    header_size: int    # 8 for leaf, 12 for interior

    @property
    def is_leaf(self) -> bool:
        return self.page_type in (0x0A, 0x0D)

    @property
    def is_table(self) -> bool:
        return self.page_type in (0x05, 0x0D)

    @property
    def page_type_name(self) -> str:
        names = {
            0x02: "Interior Index",
            0x05: "Interior Table",
            0x0A: "Leaf Index",
            0x0D: "Leaf Table",
        }
        return names.get(self.page_type, f"Unknown (0x{self.page_type:02x})")


@dataclass
class TableLeafCell:
    cell_offset: int
    payload_size: int
    rowid: int
    header_varint_len: int
    rowid_varint_len: int
    local_payload_bytes: bytes
    overflow_page: Optional[int] = None


@dataclass
class BTreePage:
    page_number: int
    page_size: int
    page_bytes: bytes
    header: Optional[BTreePageHeader]
    cell_offsets: List[int] = field(default_factory=list)
    freeblocks: List[FreeblockInfo] = field(default_factory=list)
    unallocated_ranges: List[Tuple[int, int]] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)


def parse_page_header(page_bytes: bytes, page_number: int) -> Optional[BTreePageHeader]:
    """Parse B-Tree page header defensively."""
    hdr_offset = 100 if page_number == 1 else 0
    if len(page_bytes) < hdr_offset + 8:
        return None

    ptype = page_bytes[hdr_offset]
    if ptype not in (0x02, 0x05, 0x0A, 0x0D):
        return None

    is_interior = ptype in (0x02, 0x05)
    hdr_size = 12 if is_interior else 8

    if len(page_bytes) < hdr_offset + hdr_size:
        return None

    first_freeblock = struct.unpack(">H", page_bytes[hdr_offset + 1 : hdr_offset + 3])[0]
    num_cells = struct.unpack(">H", page_bytes[hdr_offset + 3 : hdr_offset + 5])[0]
    cell_content_offset = struct.unpack(">H", page_bytes[hdr_offset + 5 : hdr_offset + 7])[0]
    if cell_content_offset == 0:
        cell_content_offset = 65536  # Special SQLite representation for 65536
    fragmented_bytes = page_bytes[hdr_offset + 7]

    right_most = None
    if is_interior:
        right_most = struct.unpack(">I", page_bytes[hdr_offset + 8 : hdr_offset + 12])[0]

    return BTreePageHeader(
        page_number=page_number,
        page_type=ptype,
        first_freeblock=first_freeblock,
        num_cells=num_cells,
        cell_content_offset=cell_content_offset,
        fragmented_bytes=fragmented_bytes,
        right_most_pointer=right_most,
        header_offset=hdr_offset,
        header_size=hdr_size,
    )


def parse_btree_page(page_bytes: bytes, page_number: int) -> BTreePage:
    """Defensively parse a complete SQLite B-tree page."""
    page_size = len(page_bytes)
    hdr = parse_page_header(page_bytes, page_number)
    diagnostics: List[str] = []

    if hdr is None:
        return BTreePage(
            page_number=page_number,
            page_size=page_size,
            page_bytes=page_bytes,
            header=None,
            diagnostics=["Not a valid B-Tree page header"],
        )

    # 1. Parse Cell Pointer Array
    cell_ptr_start = hdr.header_offset + hdr.header_size
    cell_offsets: List[int] = []
    for i in range(hdr.num_cells):
        ptr_pos = cell_ptr_start + (i * 2)
        if ptr_pos + 2 > page_size:
            diagnostics.append(f"Cell pointer array exceeded page size at index {i}")
            break
        offset = struct.unpack(">H", page_bytes[ptr_pos : ptr_pos + 2])[0]
        if offset >= page_size:
            diagnostics.append(f"Cell pointer {offset} at index {i} out of bounds")
        else:
            cell_offsets.append(offset)

    # 2. Parse Freeblocks Linked List
    freeblocks: List[FreeblockInfo] = []
    fb_offset = hdr.first_freeblock
    visited_offsets = set()

    while fb_offset > 0:
        if fb_offset in visited_offsets:
            diagnostics.append(f"Cycle detected in freeblock linked list at offset {fb_offset}")
            break
        visited_offsets.add(fb_offset)

        if fb_offset + 4 > page_size:
            diagnostics.append(f"Freeblock header at {fb_offset} exceeds page size")
            break

        next_fb = struct.unpack(">H", page_bytes[fb_offset : fb_offset + 2])[0]
        fb_size = struct.unpack(">H", page_bytes[fb_offset + 2 : fb_offset + 4])[0]

        if fb_size < 4:
            diagnostics.append(f"Freeblock at {fb_offset} has invalid size {fb_size} (< 4)")
            break

        if fb_offset + fb_size > page_size:
            diagnostics.append(f"Freeblock at {fb_offset} size {fb_size} overflows page boundary")
            break

        raw_fb_data = page_bytes[fb_offset : fb_offset + fb_size]
        freeblocks.append(
            FreeblockInfo(
                offset_in_page=fb_offset,
                size=fb_size,
                next_offset=next_fb,
                raw_bytes=raw_fb_data,
            )
        )
        fb_offset = next_fb

    # 3. Calculate Unallocated Space
    # The region between end of cell pointer array and cell_content_offset
    unallocated_ranges: List[Tuple[int, int]] = []
    cell_ptr_end = cell_ptr_start + (hdr.num_cells * 2)
    unalloc_end = min(hdr.cell_content_offset, page_size)
    if unalloc_end > cell_ptr_end:
        unallocated_ranges.append((cell_ptr_end, unalloc_end))

    return BTreePage(
        page_number=page_number,
        page_size=page_size,
        page_bytes=page_bytes,
        header=hdr,
        cell_offsets=cell_offsets,
        freeblocks=freeblocks,
        unallocated_ranges=unallocated_ranges,
        diagnostics=diagnostics,
    )


def parse_table_leaf_cell(page_bytes: bytes, cell_offset: int) -> Optional[TableLeafCell]:
    """Parse a Table Leaf Cell (0x0d) defensively."""
    page_size = len(page_bytes)
    if cell_offset < 0 or cell_offset >= page_size:
        return None

    try:
        payload_size, payload_varint_len = decode_varint(page_bytes, cell_offset, page_size)
        rowid, rowid_varint_len = decode_varint(
            page_bytes, cell_offset + payload_varint_len, page_size
        )
    except Exception:
        return None

    payload_start = cell_offset + payload_varint_len + rowid_varint_len
    if payload_start > page_size:
        return None

    # Determine local payload size vs overflow
    # For forensic carving, we read up to page_size
    avail_local = min(payload_size, page_size - payload_start)
    local_bytes = page_bytes[payload_start : payload_start + avail_local]

    return TableLeafCell(
        cell_offset=cell_offset,
        payload_size=payload_size,
        rowid=rowid,
        header_varint_len=payload_varint_len,
        rowid_varint_len=rowid_varint_len,
        local_payload_bytes=local_bytes,
    )
