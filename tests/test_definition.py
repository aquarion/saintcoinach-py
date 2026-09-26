"""Unit tests for sheet-definition loading.

Covers the EXDSchema field-flattening logic against synthetic schema
fragments, branch-resolution logic against a synthetic branch list, and
``load_definitions()``'s fetch/fallback behaviour with the network layer
mocked out -- none of this hits GitHub.
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach.ex import definition  # noqa: E402
from saintcoinach.ex._exdschema import flatten_sheet  # noqa: E402

# --- field flattening -------------------------------------------------


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


# --- branch resolution --------------------------------------------------

_BRANCHES = [
    "latest",
    "main",
    "ver/2023.07.26.0000.0000",
    "ver/2023.09.28.0000.0000",
    "ver/2025.06.28.0000.0000",
    "ver/2025.07.30.0000.0000",
]


def test_resolve_branch_none_version_uses_latest():
    assert definition._resolve_branch(None, _BRANCHES) == "latest"


def test_resolve_branch_exact_match():
    assert (
        definition._resolve_branch("2025.07.30.0000.0000", _BRANCHES)
        == "ver/2025.07.30.0000.0000"
    )


def test_resolve_branch_picks_nearest_older():
    # Between the two 2025 branches -- should pick the older, not "latest".
    assert (
        definition._resolve_branch("2025.07.01.0000.0000", _BRANCHES)
        == "ver/2025.06.28.0000.0000"
    )


def test_resolve_branch_newer_than_everything_still_picks_nearest_older():
    # A patch newer than any known branch: nearest older beats "latest",
    # which may not correspond to this exact patch either.
    assert (
        definition._resolve_branch("2026.09.01.0000.0000", _BRANCHES)
        == "ver/2025.07.30.0000.0000"
    )


def test_resolve_branch_older_than_everything_uses_oldest_available():
    assert (
        definition._resolve_branch("2020.01.01.0000.0000", _BRANCHES)
        == "ver/2023.07.26.0000.0000"
    )


def test_resolve_branch_unparseable_version_uses_latest():
    assert definition._resolve_branch("not-a-version", _BRANCHES) == "latest"


def test_resolve_branch_no_versioned_branches_uses_latest():
    assert definition._resolve_branch("2025.07.30.0000.0000", ["latest", "main"]) == "latest"


# --- zip archive parsing -------------------------------------------------


def _make_zip(root: str, files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{root}/", "")  # GitHub's export zips include a dir entry
        for path, content in files.items():
            zf.writestr(f"{root}/{path}", content)
    return buf.getvalue()


def test_flatten_zip_bytes_reads_top_level_yml_files():
    # Mirrors a real codeload export: an arbitrary sanitized root folder,
    # a subdirectory that must be ignored, and a non-.yml file alongside
    # the sheet definitions.
    payload = _make_zip(
        "EXDSchema-ver-2023.07.26.0000.0000",
        {
            "Item.yml": "name: Item\nfields:\n  - name: Name\n  - name: Singular\n",
            "Action.yml": "name: Action\nfields:\n  - name: Name\n",
            "README.md": "not a schema file",
            "sub/Nested.yml": "name: ShouldBeIgnored\nfields:\n  - name: X\n",
        },
    )
    sheets = definition._flatten_zip_bytes(payload)
    assert sheets == {
        "Item": ["Name", "Singular"],
        "Action": ["Name"],
    }


def test_flatten_zip_bytes_empty_archive_raises():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass
    try:
        definition._flatten_zip_bytes(buf.getvalue())
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for an empty archive")


# --- Definitions / load_definitions --------------------------------------


def test_definitions_get_and_available():
    d = definition.Definitions({"Item": ["Name", "Singular"]}, source="test")
    assert d.available() == frozenset({"Item"})
    got = d.get("Item")
    assert got is not None
    assert got.name == "Item"
    assert got.columns == ("Name", "Singular")
    assert d.get("NoSuchSheet") is None


def test_load_definitions_uses_fetched_data_when_available():
    fake = ({"Item": ["Foo", "Bar"]}, "exdschema:ver/9999.01.01.0000.0000")
    with patch.object(definition, "_fetch_definitions", return_value=fake):
        d = definition.load_definitions("9999.01.01.0000.0000")
    assert d.source == "exdschema:ver/9999.01.01.0000.0000"
    assert d.get("Item").columns == ("Foo", "Bar")


def test_load_definitions_falls_back_when_fetch_fails():
    with patch.object(definition, "_fetch_definitions", return_value=None):
        d = definition.load_definitions("2026.09.01.0000.0000")
    assert d.source == "bundled fallback"
    assert "Name" in d.get("Item").columns


def test_fetch_definitions_end_to_end_resolves_downloads_and_caches(tmp_path):
    # Exercises the real wiring between branch resolution, zip download,
    # flattening and on-disk caching -- only the two network calls are
    # mocked, everything in between (definition._fetch_definitions itself)
    # runs for real.
    zip_bytes = _make_zip(
        "EXDSchema-ver-2025.07.30.0000.0000",
        {"Item.yml": "name: Item\nfields:\n  - name: Name\n"},
    )
    with (
        patch.object(definition, "_cache_dir", return_value=tmp_path),
        patch.object(definition, "_list_branches", return_value=_BRANCHES) as list_branches,
        patch.object(
            definition, "_download_branch_zip", return_value=zip_bytes
        ) as download,
    ):
        result = definition._fetch_definitions("2025.07.30.0000.0000")
        assert result == ({"Item": ["Name"]}, "exdschema:ver/2025.07.30.0000.0000")
        list_branches.assert_called_once()
        download.assert_called_once_with("ver/2025.07.30.0000.0000")

        cached = tmp_path / "2025.07.30.0000.0000.json"
        assert cached.exists()

        # Second call: cache hit, no network calls at all.
        result2 = definition._fetch_definitions("2025.07.30.0000.0000")
        assert result2 == ({"Item": ["Name"]}, "exdschema:ver/2025.07.30.0000.0000")
        list_branches.assert_called_once()
        download.assert_called_once()


def test_fetch_definitions_returns_none_on_network_failure(tmp_path):
    with (
        patch.object(definition, "_cache_dir", return_value=tmp_path),
        patch.object(definition, "_list_branches", side_effect=OSError("no network")),
    ):
        assert definition._fetch_definitions("2025.07.30.0000.0000") is None


def test_bundled_fallback_is_large_and_has_no_duplicate_columns():
    with patch.object(definition, "_fetch_definitions", return_value=None):
        d = definition.load_definitions()
    names = d.available()
    assert "Item" in names
    assert "Action" in names
    # Sanity check against the real EXDSchema snapshot size, not a game-data
    # fact -- just guards against a badly truncated vendoring run.
    assert len(names) > 1000
    for name in names:
        columns = d.get(name).columns
        assert len(columns) == len(set(columns)), name
