"""Sheet export helpers shared across CLI export commands and formats.

Separates *which* columns and rows to emit for a sheet from *how* to
serialize that to a particular file format, so a future export format
(e.g. the ``sql`` command from ``SaintCoinach.Cmd``, or ``exdheader``) can
reuse the variant 1/2 row-walking and named-vs-index column selection
without re-implementing them -- only ``write_csv`` (or an equivalent for
that format) is format-specific.
"""

from __future__ import annotations

import csv
from typing import Iterable, Iterator

from .ex.header import Header
from .ex.sheet import Variant2Row

__all__ = ["sheet_column_headers", "sheet_rows", "write_csv"]


def sheet_column_headers(header: Header, named: bool) -> list[str]:
    """Column header labels for a sheet: names if ``named``, else indices.

    Raises ``ValueError`` if ``named`` is requested but this sheet has no
    column-name definition available (see ``Header.has_column_names``) --
    callers exporting many sheets in bulk should catch this per sheet
    rather than silently falling back to indices for just that one.
    """
    if named:
        names = header.column_names
        if names is None:
            raise ValueError(f"sheet {header.name!r} has no column-name definition available")
        return list(names)
    return [str(c.index) for c in header.columns]


def sheet_rows(sheet) -> Iterator[tuple[int | str, list]]:
    """``(key, column_values)`` for every row (or variant-2 sub-row) in a sheet."""
    for row in sheet.rows():
        if isinstance(row, Variant2Row):
            for sub in row.sub_rows():
                yield sub.full_key, sub.column_values()
        else:
            yield row.key, row.column_values()


def write_csv(
    fh,
    column_headers: list[str],
    rows: Iterable[tuple[int | str, list]],
    type_row: list[str] | None = None,
) -> None:
    """Write a sheet's rows as CSV: a ``key`` column plus one per header.

    ``type_row``, if given, is written as a second header line (as
    ``rawexd`` does for its raw reader-type names); named export omits it.
    """
    writer = csv.writer(fh)
    writer.writerow(["key"] + column_headers)
    if type_row is not None:
        writer.writerow([""] + type_row)
    for key, values in rows:
        writer.writerow([key] + [_format_value(v) for v in values])


def _format_value(value) -> str:
    if value is None:
        return ""
    return str(value)
