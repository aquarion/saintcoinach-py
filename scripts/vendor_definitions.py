#!/usr/bin/env python3
"""Refresh the bundled offline-fallback sheet definitions.

At runtime, ``saintcoinach.ex.definition.load_definitions()`` fetches sheet
definitions from `EXDSchema <https://github.com/xivdev/EXDSchema>`_ for the
game version being read. ``saintcoinach/ex/definitions/sheets.json`` is only
the *fallback* used when that fetch fails (no network, GitHub unreachable):
a snapshot of EXDSchema's ``latest`` branch as of whenever this script was
last run. This script (re)generates that snapshot; it's run on a monthly
schedule by ``.github/workflows/update-definitions.yml`` so the fallback
doesn't drift too far from the current game version, but can also be run by
hand:

    git clone --branch latest https://github.com/xivdev/EXDSchema /tmp/exdschema
    python scripts/vendor_definitions.py /tmp/exdschema

It flattens each of EXDSchema's per-sheet ``<SheetName>.yml`` files into an
ordered list of column names (see ``saintcoinach/ex/_exdschema.py``, which
is also used to flatten definitions fetched at runtime) and writes the
result to ``saintcoinach/ex/definitions/sheets.json``.

Requires PyYAML (``pip install PyYAML``) to read the upstream YAML.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saintcoinach.ex._exdschema import flatten_sheet  # noqa: E402

OUTPUT = (
    Path(__file__).resolve().parent.parent
    / "saintcoinach"
    / "ex"
    / "definitions"
    / "sheets.json"
)


def _commit(checkout: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checkout",
        type=Path,
        help="Path to an EXDSchema checkout (its root holds *.yml files)",
    )
    args = parser.parse_args()

    paths = sorted(args.checkout.glob("*.yml"))
    if not paths:
        parser.error(f"no *.yml files found under {args.checkout}")

    sheets: dict[str, list[str]] = {}
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        sheets[doc["name"]] = flatten_sheet(doc)

    payload = {
        "_source": "https://github.com/xivdev/EXDSchema",
        "_commit": _commit(args.checkout),
        "sheets": sheets,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(sheets)} sheet definitions to {OUTPUT}")


if __name__ == "__main__":
    main()
