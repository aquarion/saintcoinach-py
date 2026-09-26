"""Unit tests for the vendored sheet-definition loader.

Covers the EXDSchema field-flattening logic against synthetic schema
fragments (no need for real game data), plus the loader reading the
actually-vendored ``definitions/sheets.json``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach.ex import definition  # noqa: E402
from saintcoinach.ex._exdschema import flatten_sheet  # noqa: E402


def test_flatten_plain_scalar_and_typed_fields():
    doc = {
        "name": "Widget",
        "fields": [
            {"name": "Name"},
            {"name": "Icon", "type": "icon"},
            {"name": "Owner", "type": "link", "targets": ["Character"]},
        ],
    }
    assert flatten_sheet(doc) == ["Name", "Icon", "Owner"]


def test_flatten_simple_array():
    doc = {
        "name": "Widget",
        "fields": [
            {"name": "Before"},
            {"name": "Values", "type": "array", "count": 3},
            {"name": "After"},
        ],
    }
    assert flatten_sheet(doc) == [
        "Before",
        "Values[0]",
        "Values[1]",
        "Values[2]",
        "After",
    ]


def test_flatten_array_of_unnamed_link():
    # A bare typed sub-field (no name) is the whole array element -- it
    # doesn't get its own name suffix beyond the repeat index.
    doc = {
        "name": "Widget",
        "fields": [
            {
                "name": "RewardItem",
                "type": "array",
                "count": 2,
                "fields": [{"type": "link", "targets": ["Item"]}],
            },
        ],
    }
    assert flatten_sheet(doc) == ["RewardItem[0]", "RewardItem[1]"]


def test_flatten_array_of_struct_with_named_subfields():
    doc = {
        "name": "Widget",
        "fields": [
            {
                "name": "Param",
                "type": "array",
                "count": 2,
                "fields": [
                    {"name": "RequestedItem", "type": "link", "targets": ["Item"]},
                    {"name": "Quantity"},
                ],
            },
        ],
    }
    assert flatten_sheet(doc) == [
        "Param[0].RequestedItem",
        "Param[0].Quantity",
        "Param[1].RequestedItem",
        "Param[1].Quantity",
    ]


def test_flatten_nested_array_in_struct_in_array():
    # Mirrors HugeCraftworksNpc.HugeCraftworksRewardParam in the real
    # schema: an array of structs where one struct field is itself an
    # array (of an unnamed link).
    doc = {
        "name": "Widget",
        "fields": [
            {
                "name": "RewardParam",
                "type": "array",
                "count": 2,
                "fields": [
                    {
                        "name": "RewardItem",
                        "type": "array",
                        "count": 2,
                        "fields": [{"type": "link", "targets": ["Item"]}],
                    },
                    {"name": "RewardQuantity", "type": "array", "count": 2},
                ],
            },
        ],
    }
    assert flatten_sheet(doc) == [
        "RewardParam[0].RewardItem[0]",
        "RewardParam[0].RewardItem[1]",
        "RewardParam[0].RewardQuantity[0]",
        "RewardParam[0].RewardQuantity[1]",
        "RewardParam[1].RewardItem[0]",
        "RewardParam[1].RewardItem[1]",
        "RewardParam[1].RewardQuantity[0]",
        "RewardParam[1].RewardQuantity[1]",
    ]


def test_get_definition_returns_vendored_columns():
    d = definition.get_definition("Item")
    assert d is not None
    assert d.name == "Item"
    assert "Name" in d.columns
    assert "Singular" in d.columns


def test_get_definition_unknown_sheet_returns_none():
    assert definition.get_definition("ThisSheetDoesNotExist") is None


def test_available_definitions_is_a_large_set_containing_known_sheets():
    names = definition.available_definitions()
    assert "Item" in names
    assert "Action" in names
    # Sanity check against the real EXDSchema snapshot size, not a game-data
    # fact -- just guards against a badly truncated vendoring run.
    assert len(names) > 1000


def test_no_sheet_has_duplicate_flattened_column_names():
    for name in definition.available_definitions():
        columns = definition.get_definition(name).columns
        assert len(columns) == len(set(columns)), name
