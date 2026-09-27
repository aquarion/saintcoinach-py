"""Shared synthetic ``*.exh``/``*.exd`` builders for tests.

Not a test module itself (no ``test_*`` functions) -- built and reused by
test_named_columns.py and test_export.py so they don't each hand-roll the
same byte-level EXH/EXD layout. Always the same 3-column shape: a string
("Name"), a byte ("Flag") and an int32 ("Amount"), for one variant-1 row
and one variant-2 row (a single sub-row each), with fixed sample values.
"""

from __future__ import annotations

import struct

from saintcoinach.ex.collection import ExCollection

COLUMN_NAMES = ("Name", "Flag", "Amount")

# Variant 1 sample row: key=1, ("Hello", 42, 12345).
VARIANT1_KEY = 1
VARIANT1_VALUES = ("Hello", 42, 12345)

# Variant 2 sample row: parent key=5, one sub-row (key=0), ("World", 7, 999).
VARIANT2_PARENT_KEY = 5
VARIANT2_SUB_KEY = 0
VARIANT2_VALUES = ("World", 7, 999)


def _build_exh(variant: int) -> bytes:
    buf = bytearray(0x36)
    struct.pack_into("<I", buf, 0x00, 0x46485845)  # magic "EXHF" (read little-endian)
    struct.pack_into(">H", buf, 0x06, 10)  # fixed_size_data_length
    struct.pack_into(">H", buf, 0x08, 3)  # column count
    struct.pack_into(">H", buf, 0x0A, 1)  # partial file count
    struct.pack_into(">H", buf, 0x0C, 1)  # language count
    struct.pack_into(">H", buf, 0x10, variant)

    # Columns, at 0x20: (type, offset) pairs, 4 bytes each.
    struct.pack_into(">HH", buf, 0x20, 0x0000, 0)  # Name: string @0
    struct.pack_into(">HH", buf, 0x24, 0x0003, 4)  # Flag: byte @4
    struct.pack_into(">HH", buf, 0x28, 0x0006, 6)  # Amount: int32 @6

    struct.pack_into(">ii", buf, 0x2C, 0, 1)  # one partial file range: start=0, length=1
    buf[0x34] = 0  # one language: Language.NONE (id 0)

    return bytes(buf)


def build_variant1_exh() -> bytes:
    return _build_exh(variant=1)


def build_variant2_exh() -> bytes:
    return _build_exh(variant=2)


def build_variant1_exd() -> bytes:
    buf = bytearray(0x46)
    struct.pack_into(">i", buf, 0x08, 8)  # header length -> 1 entry

    # One row-offset entry at 0x20: key=1, offset=0x30.
    struct.pack_into(">ii", buf, 0x20, VARIANT1_KEY, 0x30)

    # Row metadata (6 bytes, unused by DataRow) at 0x30; fields start 0x36.
    row_offset = 0x30 + 6
    end_of_fixed = row_offset + 10  # matches fixed_size_data_length

    name, flag, amount = VARIANT1_VALUES
    struct.pack_into(">i", buf, row_offset + 0, 0)  # Name: string ptr -> end_of_fixed+0
    buf[row_offset + 4] = flag
    struct.pack_into(">i", buf, row_offset + 6, amount)

    buf[end_of_fixed : end_of_fixed + len(name) + 1] = name.encode("ascii") + b"\x00"

    return bytes(buf)


def build_variant2_exd() -> bytes:
    buf = bytearray(0x50)
    struct.pack_into(">i", buf, 0x08, 8)  # header length -> 1 entry

    entry_offset = 0x30
    struct.pack_into(">ii", buf, 0x20, VARIANT2_PARENT_KEY, entry_offset)

    struct.pack_into(">h", buf, entry_offset + 4, 1)  # sub_row_count = 1
    data_offset = entry_offset + 6  # Variant2Row.METADATA_LENGTH
    struct.pack_into(">h", buf, data_offset, VARIANT2_SUB_KEY)

    sub_row_offset = data_offset + 2
    end_of_fixed = sub_row_offset + 10  # fixed_size_data_length

    name, flag, amount = VARIANT2_VALUES
    struct.pack_into(">i", buf, sub_row_offset + 0, 0)  # Name: string ptr
    buf[sub_row_offset + 4] = flag
    struct.pack_into(">i", buf, sub_row_offset + 6, amount)

    buf[end_of_fixed : end_of_fixed + len(name) + 1] = name.encode("ascii") + b"\x00"

    return bytes(buf)


class FakeFile:
    def __init__(self, data: bytes):
        self._data = data

    def get_data(self) -> bytes:
        return self._data


class FakePacks:
    def __init__(self, files: dict[str, bytes]):
        self._files = files

    def get_file(self, path: str) -> FakeFile:
        return FakeFile(self._files[path])


def make_collection(sheet_name: str, game_version: str | None = None) -> ExCollection:
    """A 1-sheet ExCollection with one variant-1 row (see module docstring)."""
    files = {
        "exd/root.exl": f"EXLT,2\n{sheet_name},1\n".encode("ascii"),
        f"exd/{sheet_name}.exh": build_variant1_exh(),
        f"exd/{sheet_name}_0.exd": build_variant1_exd(),
    }
    return ExCollection(FakePacks(files), game_version=game_version)


def make_variant2_collection(sheet_name: str, game_version: str | None = None) -> ExCollection:
    """A 1-sheet ExCollection with one variant-2 row/sub-row (see module docstring)."""
    files = {
        "exd/root.exl": f"EXLT,2\n{sheet_name},1\n".encode("ascii"),
        f"exd/{sheet_name}.exh": build_variant2_exh(),
        f"exd/{sheet_name}_0.exd": build_variant2_exd(),
    }
    return ExCollection(FakePacks(files), game_version=game_version)


def make_multi_sheet_collection(sheet_names: list[str], game_version: str | None = None) -> ExCollection:
    """An ExCollection with several identically-shaped variant-1 sheets."""
    files = {"exd/root.exl": ("EXLT,2\n" + "".join(f"{n},{i}\n" for i, n in enumerate(sheet_names))).encode("ascii")}
    for name in sheet_names:
        files[f"exd/{name}.exh"] = build_variant1_exh()
        files[f"exd/{name}_0.exd"] = build_variant1_exd()
    return ExCollection(FakePacks(files), game_version=game_version)
