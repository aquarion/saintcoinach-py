"""Endian-aware readers for byte buffers.

This mirrors ``OrderedBitConverter`` from the original C# library.  The SqPack
container structures (index/dat headers) are little-endian while the EX header
(``*.exh``) and EX data (``*.exd``) payloads are big-endian, so every read site
has to be explicit about which order it wants.
"""

from __future__ import annotations

import struct

__all__ = [
    "to_int16",
    "to_uint16",
    "to_int32",
    "to_uint32",
    "to_int64",
    "to_uint64",
    "to_single",
    "to_double",
]


def _fmt(base: str, big_endian: bool) -> str:
    return (">" if big_endian else "<") + base


def to_int16(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("h", big_endian), buffer, offset)[0]


def to_uint16(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("H", big_endian), buffer, offset)[0]


def to_int32(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("i", big_endian), buffer, offset)[0]


def to_uint32(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("I", big_endian), buffer, offset)[0]


def to_int64(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("q", big_endian), buffer, offset)[0]


def to_uint64(buffer: bytes, offset: int, big_endian: bool) -> int:
    return struct.unpack_from(_fmt("Q", big_endian), buffer, offset)[0]


def to_single(buffer: bytes, offset: int, big_endian: bool) -> float:
    return struct.unpack_from(_fmt("f", big_endian), buffer, offset)[0]


def to_double(buffer: bytes, offset: int, big_endian: bool) -> float:
    return struct.unpack_from(_fmt("d", big_endian), buffer, offset)[0]
