"""EX column definitions.

Port of ``SaintCoinach.Ex.Column``.
"""

from __future__ import annotations

from .. import ordered
from .data_reader import _String, get_reader

__all__ = ["Column"]


class Column:
    def __init__(self, header, index: int, buffer: bytes, offset: int):
        self.header = header
        self.index = index
        self.type = ordered.to_uint16(buffer, offset + 0x00, True)
        self.offset = ordered.to_uint16(buffer, offset + 0x02, True)
        self.reader = get_reader(self.type)

    @property
    def value_type(self) -> str:
        return self.reader.name

    def read(self, buffer: bytes, row):
        field_offset = self.offset + row.offset
        if isinstance(self.reader, _String):
            end_of_fixed = row.offset + self.header.fixed_size_data_length
            return _String.read_string(buffer, field_offset, end_of_fixed)
        return self.reader.read(buffer, field_offset)
