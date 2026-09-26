"""Loading of sheet definitions (column names) for a given game version.

Definitions come from `EXDSchema <https://github.com/xivdev/EXDSchema>`_,
the community successor to the original's ``SaintCoinach.History.zip``.
EXDSchema keeps one branch per game patch (``ver/2026.09.01.0000.0000``,
plus a ``latest``), so unlike a single vendored snapshot, fetching lets us
always resolve the schema that actually matches the game install being
read, rather than hoping a frozen snapshot hasn't drifted.

Resolution for a given ``game_version``:

1. List EXDSchema's branches and pick the exact ``ver/<game_version>``
   match, or failing that the nearest *older* version, or failing that the
   oldest branch available (all preferable to a schema for a newer patch
   than the data actually being read).
2. If ``game_version`` is unknown (``None``), just use ``latest``.
3. The resolved branch is fetched once (as a zip, to avoid the GitHub API's
   per-file rate limit) and cached under the platform's user data
   directory (``platformdirs.user_data_dir``), keyed by the *requested*
   ``game_version`` -- so repeat use against the same game install never
   re-lists branches over the network at all, not even to re-resolve.
4. If fetching fails for any reason (no network, GitHub unreachable, an
   unexpected response), fall back to a small bundled snapshot vendored at
   release time (``definitions/sheets.json``, kept current by a monthly CI
   job -- see ``scripts/vendor_definitions.py``).

This module only loads names; it does not attach them to sheets/rows for
``row["Name"]``-style access -- see the named-column access work for that.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import yaml
from platformdirs import user_data_dir

from ._exdschema import flatten_sheet

__all__ = ["SheetDefinition", "Definitions", "load_definitions"]

_REPO = "xivdev/EXDSchema"
_BRANCH_RE = re.compile(r"^ver/(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)$")
_REQUEST_TIMEOUT = 30

# Errors that mean "the network/upstream didn't cooperate" -- anything else
# (a bug in our own parsing/flattening) should still raise.
_FETCH_ERRORS = (URLError, OSError, zipfile.BadZipFile, yaml.YAMLError, KeyError)


@dataclass(frozen=True)
class SheetDefinition:
    """The ordered column names for one sheet."""

    name: str
    columns: tuple[str, ...]


class Definitions:
    """Column-name definitions for sheets, resolved to one game version."""

    def __init__(self, sheets: dict[str, list[str]], source: str):
        self._sheets = sheets
        self.source = source

    def get(self, name: str) -> SheetDefinition | None:
        """Look up the column-name definition for a sheet, if any."""
        columns = self._sheets.get(name)
        if columns is None:
            return None
        return SheetDefinition(name=name, columns=tuple(columns))

    def available(self) -> frozenset[str]:
        """Names of all sheets with a definition."""
        return frozenset(self._sheets)


def _cache_dir() -> Path:
    return Path(user_data_dir("saintcoinach", appauthor=False)) / "exdschema"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.strip().split("."))


def _list_branches() -> list[str]:
    branches: list[str] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{_REPO}/branches?per_page=100&page={page}"
        with urlopen(url, timeout=_REQUEST_TIMEOUT) as resp:  # noqa: S310
            batch = json.loads(resp.read().decode("utf-8"))
        if not batch:
            break
        branches.extend(b["name"] for b in batch)
        if len(batch) < 100:
            break
        page += 1
    return branches


def _resolve_branch(game_version: str | None, branches: list[str]) -> str:
    if game_version is None:
        return "latest"

    try:
        target = _version_key(game_version)
    except ValueError:
        return "latest"

    versioned: list[tuple[tuple[int, ...], str]] = []
    for branch in branches:
        m = _BRANCH_RE.match(branch)
        if m:
            versioned.append((tuple(int(g) for g in m.groups()), branch))
    if not versioned:
        return "latest"
    versioned.sort()

    # The newest branch that isn't newer than the installed game version...
    older_or_equal = [b for key, b in versioned if key <= target]
    if older_or_equal:
        return older_or_equal[-1]
    # ...or, for a game install older than anything EXDSchema has, the
    # oldest branch available -- closer than jumping to "latest".
    return versioned[0][1]


def _download_branch_zip(branch: str) -> bytes:
    zip_url = f"https://codeload.github.com/{_REPO}/zip/refs/heads/{branch}"
    with urlopen(zip_url, timeout=_REQUEST_TIMEOUT) as resp:  # noqa: S310
        return resp.read()


def _flatten_zip_bytes(payload: bytes) -> dict[str, list[str]]:
    """Flatten every top-level ``*.yml`` sheet definition in a zip archive.

    Doesn't assume any particular root folder naming (GitHub's codeload
    zips name it ``<repo>-<sanitized-ref>/``) -- it's derived from the
    archive's own first entry instead.
    """
    sheets: dict[str, list[str]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if not names:
            raise KeyError("empty archive")
        root = names[0].split("/", 1)[0] + "/"
        for name in names:
            rest = name[len(root):] if name.startswith(root) else None
            if not rest or "/" in rest or not rest.endswith(".yml"):
                continue
            doc = yaml.safe_load(zf.read(name).decode("utf-8"))
            sheets[doc["name"]] = flatten_sheet(doc)
    return sheets


def _download_and_flatten(branch: str) -> dict[str, list[str]]:
    return _flatten_zip_bytes(_download_branch_zip(branch))


def _fetch_definitions(game_version: str | None) -> tuple[dict[str, list[str]], str] | None:
    # Cached by the *requested* version (not the resolved branch): that way
    # repeat use against the same game install never re-lists branches over
    # the network at all, only the first time it's seen. The cost is that a
    # newer, closer-matching EXDSchema branch for an already-cached version
    # won't be picked up until that version's cache entry is cleared.
    cache_key = re.sub(r"[^A-Za-z0-9.-]", "_", game_version or "latest")
    cache_path = _cache_dir() / f"{cache_key}.json"
    try:
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return payload["sheets"], payload["source"]

        branches = [] if game_version is None else _list_branches()
        branch = _resolve_branch(game_version, branches)
        sheets = _download_and_flatten(branch)
        source = f"exdschema:{branch}"

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"source": source, "sheets": sheets}, sort_keys=True),
            encoding="utf-8",
        )
        return sheets, source
    except _FETCH_ERRORS:
        return None


@lru_cache(maxsize=1)
def _fallback_sheets() -> dict[str, list[str]]:
    data = resources.files("saintcoinach.ex").joinpath("definitions/sheets.json").read_text(
        encoding="utf-8"
    )
    return json.loads(data)["sheets"]


def load_definitions(game_version: str | None = None) -> Definitions:
    """Load column-name definitions matching ``game_version``.

    Falls back to a bundled offline snapshot if fetching from EXDSchema
    fails for any reason (see module docstring).
    """
    fetched = _fetch_definitions(game_version)
    if fetched is not None:
        sheets, source = fetched
        return Definitions(sheets, source=source)
    return Definitions(_fallback_sheets(), source="bundled fallback")
