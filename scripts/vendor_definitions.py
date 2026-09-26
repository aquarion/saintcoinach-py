#!/usr/bin/env python3
"""Vendor a pinned snapshot of EXDSchema into the package's sheet definitions.

`EXDSchema <https://github.com/xivdev/EXDSchema>`_ is the actively-maintained
community source of FFXIV sheet column names/structure (superseding the old
``SaintCoinach.History.zip``). Its ``latest`` branch holds one
``<SheetName>.yml`` file per sheet. This script flattens each of those into
an ordered list of column names (see ``saintcoinach/ex/_exdschema.py``) and
writes the result to ``saintcoinach/ex/definitions/sheets.json``, which is
what the library actually loads at runtime.

To refresh the snapshot against a newer game patch::

    git clone --branch latest https://github.com/xivdev/EXDSchema /tmp/exdschema
    python scripts/vendor_definitions.py /tmp/exdschema

Requires PyYAML (``pip install PyYAML``) to read the upstream YAML; this is
a tool-only dependency for running this script, not a runtime dependency of
the library, which only ever reads the generated JSON.
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
