"""Loading of vendored sheet definitions (column names).

The definitions are a pinned snapshot of `EXDSchema
<https://github.com/xivdev/EXDSchema>`_, vendored as flattened, ordered
column-name lists by ``scripts/vendor_definitions.py`` (see that script's
docstring for how to refresh the snapshot against a newer game patch).

This module only loads names; it does not attach them to sheets/rows for
``row["Name"]``-style access -- see the named-column access work for that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

__all__ = ["SheetDefinition", "get_definition", "available_definitions"]


@dataclass(frozen=True)
class SheetDefinition:
    """The ordered column names for one sheet, as vendored from EXDSchema."""

    name: str
    columns: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_all() -> dict[str, list[str]]:
    data = resources.files(__package__).joinpath("definitions/sheets.json").read_text(
        encoding="utf-8"
    )
    return json.loads(data)["sheets"]


def available_definitions() -> frozenset[str]:
    """Names of all sheets with a vendored definition."""
    return frozenset(_load_all())


def get_definition(name: str) -> SheetDefinition | None:
    """Look up the vendored column-name definition for a sheet, if any."""
    columns = _load_all().get(name)
    if columns is None:
        return None
    return SheetDefinition(name=name, columns=tuple(columns))
