"""Entry point tying the packs and game data together.

A trimmed equivalent of ``SaintCoinach.ARealmReversed`` covering the data
extraction path (no definition/relational layer, no self-updating).
"""

from __future__ import annotations

import os

from .ex.collection import ExCollection
from .ex.language import Language
from .io.pack import PackCollection

__all__ = ["GameData"]


def _resolve_sqpack(path: str) -> str:
    """Find the ``sqpack`` directory given a game install or sqpack path."""
    candidates = [
        path,
        os.path.join(path, "sqpack"),
        os.path.join(path, "game", "sqpack"),
    ]
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "ffxiv")):
            return candidate
    raise FileNotFoundError(
        f"Could not locate a 'sqpack' directory under '{path}'. "
        "Pass the game install directory or the sqpack directory itself."
    )


class GameData:
    """Top-level access to a game installation's data."""

    def __init__(self, game_directory: str, language: Language = Language.ENGLISH):
        self.game_directory = game_directory
        self.sqpack_directory = _resolve_sqpack(game_directory)
        self.packs = PackCollection(self.sqpack_directory)
        self.game_data = ExCollection(self.packs)
        self.game_data.active_language = language

    @property
    def active_language(self) -> Language:
        return self.game_data.active_language

    @active_language.setter
    def active_language(self, value: Language) -> None:
        self.game_data.active_language = value

    def get_sheet(self, name: str):
        return self.game_data.get_sheet(self.game_data.fix_name(name))

    @property
    def game_version(self) -> str | None:
        for rel in ("game/ffxivgame.ver", "ffxivgame.ver"):
            path = os.path.join(self.game_directory, rel)
            if os.path.exists(path):
                with open(path, "r", encoding="ascii", errors="replace") as fh:
                    return fh.read().strip()
        return None

    def close(self) -> None:
        self.packs.close()

    def __enter__(self) -> "GameData":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
