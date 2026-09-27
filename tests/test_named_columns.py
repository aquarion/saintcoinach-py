"""Named-column (``row["Name"]``) access on sheets and rows.

Builds a minimal synthetic ``*.exh``/``*.exd`` pair in memory (no game
installation needed, same approach as test_file_reading.py) for one
variant-1 sheet with three columns, then exercises index access, name
access, and the fallback behaviour when a definition is missing or its
column count doesn't match the real header.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach.ex.definition import Definitions  # noqa: E402

import synthetic  # noqa: E402

_SHEET_NAME = "Widget"
_V2_SHEET_NAME = "Gadget"
_COLUMN_NAMES = synthetic.COLUMN_NAMES


def test_index_access_still_works():
    collection = synthetic.make_collection(_SHEET_NAME)
    row = collection.get_sheet(_SHEET_NAME)[1]
    assert row[0] == "Hello"
    assert row[1] == 42
    assert row[2] == 12345
    assert row.column_values() == ["Hello", 42, 12345]


def _raise(*_args, **_kwargs):
    raise AssertionError("definitions should not be resolved for pure index access")


def test_index_access_never_resolves_definitions():
    collection = synthetic.make_collection(_SHEET_NAME)
    with patch.object(type(collection), "definitions", property(_raise)):
        row = collection.get_sheet(_SHEET_NAME)[1]
        assert row[0] == "Hello"
        assert row.column_values() == ["Hello", 42, 12345]


def test_name_access_with_matching_definition():
    collection = synthetic.make_collection(_SHEET_NAME)
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
    collection = synthetic.make_collection(_SHEET_NAME)
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
    collection = synthetic.make_collection(_SHEET_NAME)
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
    collection = synthetic.make_collection(_SHEET_NAME)
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
    collection = synthetic.make_collection(_SHEET_NAME)
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


def test_subrow_index_and_name_access():
    collection = synthetic.make_variant2_collection(_V2_SHEET_NAME)
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
