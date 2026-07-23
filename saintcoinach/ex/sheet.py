"""EX data sheets and rows (``*.exd``).

Port of ``SaintCoinach.Ex.DataSheet``, ``PartialDataSheet``, ``MultiSheet`` and
the variant 1/2 row types.  EX data is big-endian.

Columns are exposed by index only; the human-readable column names live in the
relational/definition layer (``SaintCoinach.History.zip``), which is not part of
this port.  This mirrors the original ``rawexd`` export.
"""

from __future__ import annotations

from typing import Iterator

from .. import ordered
from .header import Header
from .language import Language

__all__ = ["DataSheet", "MultiSheet", "PartialDataSheet", "DataRow", "SubRow"]


class DataRow:
    """A variant 1 row: a flat record of columns."""

    METADATA_LENGTH = 0x06

    def __init__(self, sheet: "PartialDataSheet", key: int, entry_offset: int):
        self.sheet = sheet
        self.key = key
        self.offset = entry_offset + self.METADATA_LENGTH

    def __getitem__(self, column_index: int):
        column = self.sheet.header.get_column(column_index)
        return column.read(self.sheet.get_buffer(), self)

    def column_values(self) -> list:
        buffer = self.sheet.get_buffer()
        return [column.read(buffer, self) for column in self.sheet.header.columns]


class SubRow:
    """A single sub-record inside a variant 2 row."""

    def __init__(self, sheet: "PartialDataSheet", parent_key: int, key: int, offset: int):
        self.sheet = sheet
        self.parent_key = parent_key
        self.key = key
        self.offset = offset

    @property
    def full_key(self) -> str:
        return f"{self.parent_key}.{self.key}"

    def __getitem__(self, column_index: int):
        column = self.sheet.header.get_column(column_index)
        return column.read(self.sheet.get_buffer(), self)

    def column_values(self) -> list:
        buffer = self.sheet.get_buffer()
        return [column.read(buffer, self) for column in self.sheet.header.columns]


class Variant2Row:
    """A variant 2 row: a container of :class:`SubRow` records."""

    METADATA_LENGTH = 0x06

    def __init__(self, sheet: "PartialDataSheet", key: int, entry_offset: int):
        self.sheet = sheet
        self.key = key
        buffer = sheet.get_buffer()
        self.sub_row_count = ordered.to_int16(buffer, entry_offset + 4, True)
        self._data_offset = entry_offset + self.METADATA_LENGTH

    def sub_rows(self) -> Iterator[SubRow]:
        buffer = self.sheet.get_buffer()
        fixed = self.sheet.header.fixed_size_data_length
        o = self._data_offset
        for _ in range(self.sub_row_count):
            sub_key = ordered.to_int16(buffer, o, True)
            o += 2
            yield SubRow(self.sheet, self.key, sub_key, o)
            o += fixed


class PartialDataSheet:
    """One ``*.exd`` partition of a sheet for a given language."""

    _HEADER_LENGTH_OFFSET = 0x08
    _ENTRIES_OFFSET = 0x20
    _ENTRY_LENGTH = 0x08

    def __init__(self, source_sheet: "DataSheet", start: int, file):
        self.source_sheet = source_sheet
        self.header = source_sheet.header
        self.start = start
        self.file = file
        self._buffer: bytes | None = None
        self._row_offsets: dict[int, int] = {}
        self._build()

    def get_buffer(self) -> bytes:
        if self._buffer is None:
            self._buffer = self.file.get_data()
        return self._buffer

    def _build(self) -> None:
        buffer = self.get_buffer()
        header_len = ordered.to_int32(buffer, self._HEADER_LENGTH_OFFSET, True)
        count = header_len // self._ENTRY_LENGTH
        pos = self._ENTRIES_OFFSET
        for _ in range(count):
            key = ordered.to_int32(buffer, pos + 0x00, True)
            offset = ordered.to_int32(buffer, pos + 0x04, True)
            self._row_offsets[key] = offset
            pos += self._ENTRY_LENGTH

    @property
    def keys(self):
        return self._row_offsets.keys()

    def __contains__(self, key: int) -> bool:
        return key in self._row_offsets

    def get_row(self, key: int):
        offset = self._row_offsets[key]
        if self.header.variant == 1:
            return DataRow(self, key, offset)
        return Variant2Row(self, key, offset)

    def rows(self):
        for key in self._row_offsets:
            yield self.get_row(key)


class DataSheet:
    """A sheet in a single language, spread across partial ``*.exd`` files."""

    def __init__(self, collection, header: Header, language: Language):
        self.collection = collection
        self.header = header
        self.language = language
        self._partials: dict[int, PartialDataSheet] | None = None

    @property
    def name(self) -> str:
        return self.header.name + self.language.suffix

    def _ensure_partials(self) -> dict[int, PartialDataSheet]:
        if self._partials is None:
            self._partials = {}
            for start, _length in self.header.data_file_ranges:
                file = self._get_partial_file(start)
                self._partials[start] = PartialDataSheet(self, start, file)
        return self._partials

    def _get_partial_file(self, start: int):
        name = f"exd/{self.header.name}_{start}{self.language.suffix}.exd"
        return self.collection.packs.get_file(name)

    @property
    def keys(self):
        keys: list[int] = []
        for partial in self._ensure_partials().values():
            keys.extend(partial.keys)
        return keys

    def __len__(self) -> int:
        return sum(len(list(p.keys)) for p in self._ensure_partials().values())

    def __contains__(self, key: int) -> bool:
        return any(key in p for p in self._ensure_partials().values())

    def __getitem__(self, key: int):
        for partial in self._ensure_partials().values():
            if key in partial:
                return partial.get_row(key)
        raise KeyError(key)

    def rows(self):
        for partial in self._ensure_partials().values():
            yield from partial.rows()

    def __iter__(self):
        return self.rows()


class MultiSheet:
    """A sheet available in several languages."""

    def __init__(self, collection, header: Header):
        self.collection = collection
        self.header = header
        self._localised: dict[Language, DataSheet] = {}

    @property
    def name(self) -> str:
        return self.header.name

    def get_localised_sheet(self, language: Language) -> DataSheet:
        if language not in self.header.available_languages:
            raise NotImplementedError(f"Language {language} not available for {self.name}")
        sheet = self._localised.get(language)
        if sheet is None:
            sheet = DataSheet(self.collection, self.header, language)
            self._localised[language] = sheet
        return sheet

    @property
    def active_sheet(self) -> DataSheet:
        return self.get_localised_sheet(self.collection.active_language)

    @property
    def keys(self):
        return self.active_sheet.keys

    def __len__(self) -> int:
        return len(self.active_sheet)

    def __contains__(self, key: int) -> bool:
        return key in self.active_sheet

    def __getitem__(self, key: int):
        return self.active_sheet[key]

    def rows(self):
        return self.active_sheet.rows()

    def __iter__(self):
        return self.rows()
