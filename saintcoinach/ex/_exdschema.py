"""Flattening of EXDSchema field definitions into ordered column names.

`EXDSchema <https://github.com/xivdev/EXDSchema>`_ describes each sheet as a
list of fields "ordered by offset". Most fields are a single column, but a
field can be a fixed-size repeating array, optionally of a struct with its
own (possibly array-typed) sub-fields, which expands to several physical
columns each. This module turns that declarative shape into the flat,
ordered list of column names needed to match the raw column layout read
from a sheet's ``*.exh`` header.

Used both by ``scripts/vendor_definitions.py``, to build the bundled
fallback snapshot in ``saintcoinach/ex/definitions/sheets.json`` (already
flat, so it needs no further flattening once loaded), and by
``saintcoinach.ex.definition`` at runtime, to flatten schema fetched fresh
from EXDSchema for the game version being read.
"""

from __future__ import annotations

__all__ = ["flatten_sheet"]


def _flatten_field(field: dict) -> list[str]:
    """The ordered *relative* name suffixes contributed by one field.

    A plain (non-array) field is a single column with no suffix (``""``).
    An array field expands to one suffix per repeat, recursively including
    any nested struct sub-fields (which may themselves be arrays).
    """
    if field.get("type") != "array":
        return [""]

    count = field["count"]
    subfields = field.get("fields")
    suffixes: list[str] = []
    for i in range(count):
        if not subfields:
            suffixes.append(f"[{i}]")
            continue
        for sub in subfields:
            sub_name = sub.get("name")
            for sub_suffix in _flatten_field(sub):
                if sub_name:
                    suffixes.append(f"[{i}].{sub_name}{sub_suffix}")
                else:
                    # An unnamed sub-field (e.g. a bare `link`) is the whole
                    # array element; don't invent a name for it.
                    suffixes.append(f"[{i}]{sub_suffix}")
    return suffixes


def flatten_sheet(doc: dict) -> list[str]:
    """Flatten an EXDSchema sheet document into its ordered column names."""
    columns: list[str] = []
    for field in doc["fields"]:
        name = field["name"]
        for suffix in _flatten_field(field):
            columns.append(f"{name}{suffix}")
    return columns
