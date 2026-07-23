"""Typed readers for EX column data.

Port of ``SaintCoinach.Ex.DataReader`` and its concrete readers.  All numeric
values in EX data are big-endian.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import ordered
from ..text import xiv_string

__all__ = ["Quad", "get_reader", "STRING_TYPE"]

STRING_TYPE = 0x0000


@dataclass(frozen=True)
class Quad:
    """A packed 64-bit value exposed as four signed 16-bit lanes."""

    value1: int
    value2: int
    value3: int
    value4: int

    @classmethod
    def read(cls, buffer: bytes, offset: int) -> "Quad":
        data = ordered.to_int64(buffer, offset, True)
        def s16(x: int) -> int:
            x &= 0xFFFF
            return x - 0x10000 if x >= 0x8000 else x
        return cls(s16(data), s16(data >> 16), s16(data >> 32), s16(data >> 48))

    def __str__(self) -> str:
        return f"{self.value1}, {self.value2}, {self.value3}, {self.value4}"


class DataReader:
    name = "unknown"
    length = 0
    is_string = False

    def read(self, buffer: bytes, offset: int):  # pragma: no cover - abstract
        raise NotImplementedError


class _Delegate(DataReader):
    def __init__(self, name: str, length: int, func):
        self.name = name
        self.length = length
        self._func = func

    def read(self, buffer: bytes, offset: int):
        return self._func(buffer, offset)


class _PackedBoolean(DataReader):
    length = 1

    def __init__(self, mask: int):
        self.mask = mask
        self.name = f"bit&{mask:02X}"

    def read(self, buffer: bytes, offset: int):
        return (buffer[offset] & self.mask) != 0


class _String(DataReader):
    name = "str"
    length = 4
    is_string = True

    def read(self, buffer: bytes, offset: int):  # pragma: no cover - handled in Column
        raise NotImplementedError("String reads require row context; use Column.read.")

    @staticmethod
    def read_string(buffer: bytes, field_offset: int, end_of_fixed: int):
        start = end_of_fixed + ordered.to_int32(buffer, field_offset, True)
        if start < 0:
            return None
        end = start
        while end < len(buffer) and buffer[end] != 0:
            end += 1
        if end == start:
            return ""
        return xiv_string.decode(buffer[start:end])


def _s8(x: int) -> int:
    return x - 0x100 if x >= 0x80 else x


_READERS: dict[int, DataReader] = {
    0x0000: _String(),
    0x0001: _Delegate("bool", 1, lambda d, o: d[o] != 0),
    0x0002: _Delegate("sbyte", 1, lambda d, o: _s8(d[o])),
    0x0003: _Delegate("byte", 1, lambda d, o: d[o]),
    0x0004: _Delegate("int16", 2, lambda d, o: ordered.to_int16(d, o, True)),
    0x0005: _Delegate("uint16", 2, lambda d, o: ordered.to_uint16(d, o, True)),
    0x0006: _Delegate("int32", 4, lambda d, o: ordered.to_int32(d, o, True)),
    0x0007: _Delegate("uint32", 4, lambda d, o: ordered.to_uint32(d, o, True)),
    0x0009: _Delegate("single", 4, lambda d, o: ordered.to_single(d, o, True)),
    0x000B: _Delegate("int64", 8, lambda d, o: Quad.read(d, o)),
}
for _i in range(8):
    _READERS[0x19 + _i] = _PackedBoolean(1 << _i)


def get_reader(type_id: int) -> DataReader:
    reader = _READERS.get(type_id)
    if reader is None:
        raise NotImplementedError(f"Unsupported data type {type_id:#06x}")
    return reader
