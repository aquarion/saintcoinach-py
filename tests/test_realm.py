"""``GameData.game_version`` resolution for both documented input styles.

Constructs a ``GameData`` instance without running its ``__init__`` (which
would otherwise need a full, working SqPack directory just to read one
version file) and exercises the ``game_version`` property directly against
synthetic directory trees.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import saintcoinach.realm as realm  # noqa: E402
from saintcoinach.realm import GameData, _resolve_sqpack  # noqa: E402

_VERSION = "2026.09.01.0000.0000"


def _make_install(tmp_path) -> str:
    """A standard install layout: <root>/game/sqpack/ffxiv/... plus ver file."""
    root = tmp_path / "install"
    (root / "game" / "sqpack" / "ffxiv").mkdir(parents=True)
    (root / "game" / "ffxivgame.ver").write_text(_VERSION, encoding="ascii")
    return str(root)


def _game_data_for(game_directory: str) -> GameData:
    instance = object.__new__(GameData)
    instance.game_directory = game_directory
    instance.sqpack_directory = _resolve_sqpack(game_directory)
    return instance


def test_game_version_from_install_root(tmp_path):
    root = _make_install(tmp_path)
    game_data = _game_data_for(root)
    assert game_data.sqpack_directory == os.path.join(root, "game", "sqpack")
    assert game_data.game_version == _VERSION


def test_game_version_from_sqpack_directory_itself(tmp_path):
    root = _make_install(tmp_path)
    sqpack_dir = os.path.join(root, "game", "sqpack")
    game_data = _game_data_for(sqpack_dir)
    assert game_data.sqpack_directory == sqpack_dir
    assert game_data.game_version == _VERSION


def test_game_version_from_sqpack_directory_with_trailing_separator(tmp_path):
    # os.path.dirname() on a path with a trailing separator is a no-op
    # instead of stepping up to the parent -- must be normalized first.
    root = _make_install(tmp_path)
    sqpack_dir_with_slash = os.path.join(root, "game", "sqpack") + os.sep
    game_data = _game_data_for(sqpack_dir_with_slash)
    assert game_data.game_version == _VERSION


def test_game_version_none_when_missing(tmp_path):
    root = tmp_path / "install"
    (root / "game" / "sqpack" / "ffxiv").mkdir(parents=True)
    game_data = _game_data_for(str(root))
    assert game_data.game_version is None


def test_game_data_init_passes_resolved_game_version_to_excollection(tmp_path):
    # Runs the real GameData.__init__ (unlike the tests above, which bypass
    # it) to guard against a regression to ExCollection(self.packs) with no
    # game_version -- that would leave every test above passing while named
    # lookup silently fell back to resolving against "latest" instead of
    # the installed game's actual version.
    root = _make_install(tmp_path)
    with patch.object(realm, "ExCollection") as mock_ex_collection:
        GameData(root)

    mock_ex_collection.assert_called_once()
    _, kwargs = mock_ex_collection.call_args
    assert kwargs.get("game_version") == _VERSION
