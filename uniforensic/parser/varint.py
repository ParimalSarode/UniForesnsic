"""Defensive SQLite varint encoding and decoding with strict buffer bounds checking."""

from typing import Optional, Tuple


def decode_varint(data: bytes, offset: int = 0, limit: Optional[int] = None) -> Tuple[int, int]:
    """
    Decodes an SQLite variable-length integer (varint) from bytes starting at offset.

    An SQLite varint is 1 to 9 bytes:
    - For the first 8 bytes, the high bit (0x80) indicates if another byte follows.
      The lower 7 bits are payload.
    - If a 9th byte is reached, all 8 bits are payload.

    Args:
        data: Buffer containing bytes.
        offset: Starting byte offset in data.
        limit: Optional maximum byte boundary (defaults to len(data)).

    Returns:
        (value, bytes_consumed)

    Raises:
        ValueError: If buffer bounds are exceeded or data is truncated.
    """
    if limit is None:
        limit = len(data)

    if offset < 0 or offset >= limit:
        raise ValueError(f"Varint decode offset {offset} out of bounds [0, {limit})")

    result = 0
    bytes_read = 0

    for i in range(8):
        pos = offset + i
        if pos >= limit:
            raise ValueError(f"Varint truncated at index {pos} before terminal byte")

        b = data[pos]
        bytes_read += 1
        result = (result << 7) | (b & 0x7F)

        if not (b & 0x80):
            return result, bytes_read

    # 9th byte (all 8 bits used)
    pos = offset + 8
    if pos >= limit:
        raise ValueError(f"Varint truncated at 9th byte index {pos}")

    b = data[pos]
    bytes_read += 1
    result = (result << 8) | b
    return result, bytes_read


def encode_varint(val: int) -> bytes:
    """Encode an integer as an SQLite variable-length integer (1-9 bytes)."""
    if val < 0:
        # SQLite varints are signed two's complement for 64-bit
        val = val & 0xFFFFFFFFFFFFFFFF

    if val <= 0x7F:
        return bytes([val])

    buf = bytearray()
    if val > 0x00FFFFFFFFFFFFFF:
        # Requires 9 bytes
        buf.append(val & 0xFF)
        val >>= 8
        while val > 0:
            buf.append(0x80 | (val & 0x7F))
            val >>= 7
        buf.reverse()
        return bytes(buf)

    # 1 to 8 bytes
    parts = []
    parts.append(val & 0x7F)
    val >>= 7
    while val > 0:
        parts.append(0x80 | (val & 0x7F))
        val >>= 7
    parts.reverse()
    return bytes(parts)
