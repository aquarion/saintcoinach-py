"""Parsing of EX header files (``*.exh``).

Port of ``SaintCoinach.Ex.Header``.  EX headers are big-endian.
"""

from __future__ import annotations

from .. import ordered
from .column import Column
from .language import LANGUAGE_MAP, Language

__all__ = ["Header"]

_MAGIC = 0x46485845  # "EXHF"
_MINIMUM_LENGTH = 0x2E


class Header:
    def __init__(self, collection, name: str, file):
        self.collection = collection
        self.name = name
        self.file = file

        buffer = file.get_data()
        if len(buffer) < _MINIMUM_LENGTH:
            raise ValueError("EXH file is too short")
        if ordered.to_uint32(buffer, 0, False) != _MAGIC:
            raise ValueError("File is not an EX header")

        self.fixed_size_data_length = ordered.to_uint16(buffer, 0x06, True)
        self.variant = ordered.to_uint16(buffer, 0x10, True)
        if self.variant not in (1, 2):
            raise NotImplementedError(f"Unsupported EXH variant {self.variant}")

        pos = 0x20
        pos = self._read_columns(buffer, pos)
        pos = self._read_partial_files(buffer, pos)
        self._read_suffixes(buffer, pos)

    def _read_columns(self, buffer: bytes, pos: int) -> int:
        count = ordered.to_uint16(buffer, 0x08, True)
        self.columns: list[Column] = []
        for i in range(count):
            self.columns.append(Column(self, i, buffer, pos))
            pos += 0x04
        return pos

    def _read_partial_files(self, buffer: bytes, pos: int) -> int:
        count = ordered.to_uint16(buffer, 0x0A, True)
        # Each range is (start, length) as it appears in the file.
        self.data_file_ranges: list[tuple[int, int]] = []
        for _ in range(count):
            start = ordered.to_int32(buffer, pos + 0x00, True)
            length = ordered.to_int32(buffer, pos + 0x04, True)
            self.data_file_ranges.append((start, length))
            pos += 0x08
        return pos

    def _read_suffixes(self, buffer: bytes, pos: int) -> int:
        count = ordered.to_uint16(buffer, 0x0C, True)
        langs: list[Language] = []
        for _ in range(count):
            langs.append(LANGUAGE_MAP[buffer[pos]])
            pos += 0x02
        self.available_languages = [lang for lang in langs if lang != Language.UNSUPPORTED]
        return pos

    @property
    def column_count(self) -> int:
        return len(self.columns)

    @property
    def available_languages_count(self) -> int:
        return sum(1 for lang in self.available_languages if lang != Language.NONE)

    def get_column(self, index: int) -> Column:
        return self.columns[index]

    def range_contains(self, data_range: tuple[int, int], row: int) -> bool:
        start, length = data_range
        return start <= row < start + length
