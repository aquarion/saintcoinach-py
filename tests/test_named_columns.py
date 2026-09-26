"""Named-column (``row["Name"]``) access on sheets and rows.

Builds a minimal synthetic ``*.exh``/``*.exd`` pair in memory (no game
installation needed, same approach as test_file_reading.py) for one
variant-1 sheet with three columns, then exercises index access, name
access, and the fallback behaviour when a definition is missing or its
column count doesn't match the real header.
"""

from __future__ import annotations

import os
import struct
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach.ex.collection import ExCollection  # noqa: E402
from saintcoinach.ex.definition import Definitions  # noqa: E402

_SHEET_NAME = "Widget"
_COLUMN_NAMES = ("Name", "Flag", "Amount")


def _build_exh() -> bytes:
    buf = bytearray(0x36)
    struct.pack_into("<I", buf, 0x00, 0x46485845)  # magic "EXHF" (read little-endian)
    struct.pack_into(">H", buf, 0x06, 10)  # fixed_size_data_length
    struct.pack_into(">H", buf, 0x08, 3)  # column count
    struct.pack_into(">H", buf, 0x0A, 1)  # partial file count
    struct.pack_into(">H", buf, 0x0C, 1)  # language count
    struct.pack_into(">H", buf, 0x10, 1)  # variant

    # Columns, at 0x20: (type, offset) pairs, 4 bytes each.
    struct.pack_into(">HH", buf, 0x20, 0x0000, 0)  # Name: string @0
    struct.pack_into(">HH", buf, 0x24, 0x0003, 4)  # Flag: byte @4
    struct.pack_into(">HH", buf, 0x28, 0x0006, 6)  # Amount: int32 @6

    # One partial file range: start=0, length=1.
    struct.pack_into(">ii", buf, 0x2C, 0, 1)

    # One language: Language.NONE (id 0).
    buf[0x34] = 0

    return bytes(buf)


def _build_exd() -> bytes:
    buf = bytearray(0x46)
    struct.pack_into(">i", buf, 0x08, 8)  # header length -> 1 entry

    # One row-offset entry at 0x20: key=1, offset=0x30.
    struct.pack_into(">ii", buf, 0x20, 1, 0x30)

    # Row metadata (6 bytes, unused by DataRow) at 0x30; fields start 0x36.
    row_offset = 0x30 + 6
    end_of_fixed = row_offset + 10  # matches fixed_size_data_length

    struct.pack_into(">i", buf, row_offset + 0, 0)  # Name: string ptr -> end_of_fixed+0
    buf[row_offset + 4] = 42  # Flag: byte
    struct.pack_into(">i", buf, row_offset + 6, 12345)  # Amount: int32

    buf[end_of_fixed : end_of_fixed + 6] = b"Hello\x00"

    return bytes(buf)


class _FakeFile:
    def __init__(self, data: bytes):
        self._data = data

    def get_data(self) -> bytes:
        return self._data


class _FakePacks:
    def __init__(self, files: dict[str, bytes]):
        self._files = files

    def get_file(self, path: str) -> _FakeFile:
        return _FakeFile(self._files[path])


def _make_collection(game_version: str | None = None) -> ExCollection:
    files = {
        "exd/root.exl": f"EXLT,2\n{_SHEET_NAME},1\n".encode("ascii"),
        f"exd/{_SHEET_NAME}.exh": _build_exh(),
        f"exd/{_SHEET_NAME}_0.exd": _build_exd(),
    }
    return ExCollection(_FakePacks(files), game_version=game_version)


def test_index_access_still_works():
    collection = _make_collection()
    row = collection.get_sheet(_SHEET_NAME)[1]
    assert row[0] == "Hello"
    assert row[1] == 42
    assert row[2] == 12345
    assert row.column_values() == ["Hello", 42, 12345]


def _raise(*_args, **_kwargs):
    raise AssertionError("definitions should not be resolved for pure index access")


def test_index_access_never_resolves_definitions():
    collection = _make_collection()
    with patch.object(type(collection), "definitions", property(_raise)):
        row = collection.get_sheet(_SHEET_NAME)[1]
        assert row[0] == "Hello"
        assert row.column_values() == ["Hello", 42, 12345]


def test_name_access_with_matching_definition():
    collection = _make_collection()
    fake_definitions = Definitions({_SHEET_NAME: list(_COLUMN_NAMES)}, source="test")
    with patch.object(type(collection), "definitions", property(lambda self: fake_definitions)):
        row = collection.get_sheet(_SHEET_NAME)[1]
        assert row["Name"] == "Hello"
        assert row["Flag"] == 42
        assert row["Amount"] == 12345
        # Both access styles read the same underlying columns.
        assert row["Name"] == row[0]

        header = collection.get_header(_SHEET_NAME)
        assert header.has_column_names
        assert header.column_names == _COLUMN_NAMES
        assert header.get_column_index("Amount") == 2


def test_name_access_raises_for_unknown_column_name():
    collection = _make_collection()
    fake_definitions = Definitions({_SHEET_NAME: list(_COLUMN_NAMES)}, source="test")
    with patch.object(type(collection), "definitions", property(lambda self: fake_definitions)):
        row = collection.get_sheet(_SHEET_NAME)[1]
        try:
            row["NoSuchColumn"]
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError for an unknown column name")


def test_no_definition_available_disables_name_access_only():
    collection = _make_collection()
    fake_definitions = Definitions({}, source="test")  # no entry for "Widget" at all
    with patch.object(type(collection), "definitions", property(lambda self: fake_definitions)):
        header = collection.get_header(_SHEET_NAME)
        assert not header.has_column_names
        assert header.column_names is None

        row = collection.get_sheet(_SHEET_NAME)[1]
        assert row[0] == "Hello"  # index access unaffected
        try:
            row["Name"]
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError with no definition available")


def test_column_count_mismatch_disables_name_access_only():
    # A stale/wrong-version definition (2 names for a 3-column sheet) must
    # not get silently mapped to the wrong columns -- name access is
    # disabled for this sheet entirely, index access still works.
    collection = _make_collection()
    fake_definitions = Definitions({_SHEET_NAME: ["Name", "Flag"]}, source="test")
    with patch.object(type(collection), "definitions", property(lambda self: fake_definitions)):
        header = collection.get_header(_SHEET_NAME)
        assert not header.has_column_names

        row = collection.get_sheet(_SHEET_NAME)[1]
        assert row[2] == 12345
        try:
            row["Name"]
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError on a column-count mismatch")


def test_definitions_resolved_once_and_cached_on_header():
    collection = _make_collection()
    calls = []

    def _fake_load_definitions(game_version):
        calls.append(game_version)
        return Definitions({_SHEET_NAME: list(_COLUMN_NAMES)}, source="test")

    with patch("saintcoinach.ex.collection.load_definitions", side_effect=_fake_load_definitions):
        sheet = collection.get_sheet(_SHEET_NAME)
        assert sheet[1]["Name"] == "Hello"
        assert sheet[1]["Flag"] == 42
        # A second row's name lookup, and repeated calls, don't re-resolve.
        assert len(calls) == 1


# --- variant 2 (SubRow) ---------------------------------------------------

_V2_SHEET_NAME = "Gadget"


def _build_exh_variant2() -> bytes:
    buf = bytearray(0x36)
    struct.pack_into("<I", buf, 0x00, 0x46485845)  # magic "EXHF"
    struct.pack_into(">H", buf, 0x06, 10)  # fixed_size_data_length (per sub-row)
    struct.pack_into(">H", buf, 0x08, 3)  # column count
    struct.pack_into(">H", buf, 0x0A, 1)  # partial file count
    struct.pack_into(">H", buf, 0x0C, 1)  # language count
    struct.pack_into(">H", buf, 0x10, 2)  # variant 2

    struct.pack_into(">HH", buf, 0x20, 0x0000, 0)  # Name: string @0
    struct.pack_into(">HH", buf, 0x24, 0x0003, 4)  # Flag: byte @4
    struct.pack_into(">HH", buf, 0x28, 0x0006, 6)  # Amount: int32 @6

    struct.pack_into(">ii", buf, 0x2C, 0, 1)  # partial file range
    buf[0x34] = 0  # Language.NONE

    return bytes(buf)


def _build_exd_variant2() -> bytes:
    buf = bytearray(0x50)
    struct.pack_into(">i", buf, 0x08, 8)  # header length -> 1 entry

    entry_offset = 0x30
    struct.pack_into(">ii", buf, 0x20, 5, entry_offset)  # key=5 (parent key)

    struct.pack_into(">h", buf, entry_offset + 4, 1)  # sub_row_count = 1
    data_offset = entry_offset + 6  # Variant2Row.METADATA_LENGTH
    struct.pack_into(">h", buf, data_offset, 0)  # sub-row key = 0

    sub_row_offset = data_offset + 2
    end_of_fixed = sub_row_offset + 10  # fixed_size_data_length

    struct.pack_into(">i", buf, sub_row_offset + 0, 0)  # Name: string ptr
    buf[sub_row_offset + 4] = 7  # Flag
    struct.pack_into(">i", buf, sub_row_offset + 6, 999)  # Amount

    buf[end_of_fixed : end_of_fixed + 6] = b"World\x00"

    return bytes(buf)


def _make_variant2_collection() -> ExCollection:
    files = {
        "exd/root.exl": f"EXLT,2\n{_V2_SHEET_NAME},1\n".encode("ascii"),
        f"exd/{_V2_SHEET_NAME}.exh": _build_exh_variant2(),
        f"exd/{_V2_SHEET_NAME}_0.exd": _build_exd_variant2(),
    }
    return ExCollection(_FakePacks(files))


def test_subrow_index_and_name_access():
    collection = _make_variant2_collection()
    fake_definitions = Definitions({_V2_SHEET_NAME: list(_COLUMN_NAMES)}, source="test")
    with patch.object(type(collection), "definitions", property(lambda self: fake_definitions)):
        variant2_row = collection.get_sheet(_V2_SHEET_NAME)[5]
        sub_rows = list(variant2_row.sub_rows())
        assert len(sub_rows) == 1
        sub_row = sub_rows[0]

        assert sub_row[0] == "World"
        assert sub_row[1] == 7
        assert sub_row[2] == 999
        assert sub_row["Name"] == "World"
        assert sub_row["Flag"] == 7
        assert sub_row["Amount"] == 999
        assert sub_row.column_values() == ["World", 7, 999]

        try:
            sub_row["NoSuchColumn"]
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError for an unknown column name")
