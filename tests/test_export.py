"""Tests for saintcoinach.export and the CLI's exd/rawexd commands.

Uses the synthetic 1-sheet collections from tests/synthetic.py -- no game
installation needed.
"""

from __future__ import annotations

import io
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach import cli, export  # noqa: E402
from saintcoinach.ex.definition import Definitions  # noqa: E402

import synthetic  # noqa: E402

_SHEET_NAME = "Widget"
_V2_SHEET_NAME = "Gadget"


def _with_definitions(collection, sheets: dict[str, list[str]]):
    fake = Definitions(sheets, source="test")
    return patch.object(type(collection), "definitions", property(lambda self: fake))


# --- saintcoinach.export --------------------------------------------------


def test_sheet_column_headers_index_mode():
    collection = synthetic.make_collection(_SHEET_NAME)
    header = collection.get_header(_SHEET_NAME)
    assert export.sheet_column_headers(header, named=False) == ["0", "1", "2"]


def test_sheet_column_headers_named_mode():
    collection = synthetic.make_collection(_SHEET_NAME)
    with _with_definitions(collection, {_SHEET_NAME: list(synthetic.COLUMN_NAMES)}):
        header = collection.get_header(_SHEET_NAME)
        assert export.sheet_column_headers(header, named=True) == list(synthetic.COLUMN_NAMES)


def test_sheet_column_headers_named_mode_raises_without_definition():
    collection = synthetic.make_collection(_SHEET_NAME)
    with _with_definitions(collection, {}):
        header = collection.get_header(_SHEET_NAME)
        try:
            export.sheet_column_headers(header, named=True)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError with no definition available")


def test_sheet_rows_variant1():
    collection = synthetic.make_collection(_SHEET_NAME)
    sheet = collection.get_sheet(_SHEET_NAME)
    assert list(export.sheet_rows(sheet)) == [(1, ["Hello", 42, 12345])]


def test_sheet_rows_variant2():
    collection = synthetic.make_variant2_collection(_V2_SHEET_NAME)
    sheet = collection.get_sheet(_V2_SHEET_NAME)
    assert list(export.sheet_rows(sheet)) == [("5.0", ["World", 7, 999])]


def test_write_csv_index_mode_with_type_row():
    fh = io.StringIO()
    export.write_csv(
        fh,
        ["0", "1", "2"],
        [(1, ["Hello", 42, 12345])],
        type_row=["str", "byte", "int32"],
    )
    assert fh.getvalue() == (
        "key,0,1,2\r\n"
        ",str,byte,int32\r\n"
        "1,Hello,42,12345\r\n"
    )


def test_write_csv_named_mode_has_no_type_row():
    fh = io.StringIO()
    export.write_csv(fh, list(synthetic.COLUMN_NAMES), [(1, ["Hello", 42, 12345])])
    assert fh.getvalue() == "key,Name,Flag,Amount\r\n1,Hello,42,12345\r\n"


def test_write_csv_formats_none_as_empty_string():
    fh = io.StringIO()
    export.write_csv(fh, ["A"], [(1, [None])])
    assert fh.getvalue() == "key,A\r\n1,\r\n"


# --- CLI: exd / rawexd -----------------------------------------------------


class _FakeGameData:
    def __init__(self, game_data, game_version=None):
        self.game_data = game_data
        self.game_version = game_version


def _read_csv_raw(path) -> str:
    # newline="": read back exactly the \r\n line endings write_csv (via the
    # csv module) actually wrote, rather than pathlib's default universal
    # newline translation to "\n".
    with open(path, "r", newline="", encoding="utf-8") as fh:
        return fh.read()


def test_cli_export_sheet_csv_named(tmp_path):
    collection = synthetic.make_collection(_SHEET_NAME)
    with _with_definitions(collection, {_SHEET_NAME: list(synthetic.COLUMN_NAMES)}):
        game = _FakeGameData(collection)
        cli._export_sheet_csv(game, str(tmp_path), _SHEET_NAME, named=True)

    content = _read_csv_raw(tmp_path / "exd" / f"{_SHEET_NAME}.csv")
    assert content == "key,Name,Flag,Amount\r\n1,Hello,42,12345\r\n"


def test_cli_export_sheet_csv_raw_has_index_headers_and_type_row(tmp_path):
    collection = synthetic.make_collection(_SHEET_NAME)
    game = _FakeGameData(collection)
    cli._export_sheet_csv(game, str(tmp_path), _SHEET_NAME, named=False)

    content = _read_csv_raw(tmp_path / "exd" / f"{_SHEET_NAME}.csv")
    assert content == ("key,0,1,2\r\n" ",str,byte,int32\r\n" "1,Hello,42,12345\r\n")


def test_cli_export_csv_named_skips_sheet_without_definition_but_continues(tmp_path, capsys):
    names = [_SHEET_NAME, "OtherWidget"]
    collection = synthetic.make_multi_sheet_collection(names)
    # Only OtherWidget gets a matching definition; Widget has none.
    with _with_definitions(collection, {"OtherWidget": list(synthetic.COLUMN_NAMES)}):
        game = _FakeGameData(collection)  # game_version=None -> output root is "<out>/output"
        args = type("Args", (), {"sheets": names, "out": str(tmp_path)})()
        cli._cmd_export_csv(game, args, named=True)

    captured = capsys.readouterr()
    assert f"{_SHEET_NAME}:" in captured.err  # logged the failure, didn't crash
    assert "Exported OtherWidget" in captured.out

    exd_dir = tmp_path / "output" / "exd"
    assert not (exd_dir / f"{_SHEET_NAME}.csv").exists()
    other_content = _read_csv_raw(exd_dir / "OtherWidget.csv")
    assert other_content == "key,Name,Flag,Amount\r\n1,Hello,42,12345\r\n"


def test_cli_rawexd_command_wired_up():
    parser = cli._build_parser()
    args = parser.parse_args(["/fake/game", "rawexd", _SHEET_NAME])
    assert args.func is cli._cmd_rawexd
    assert args.sheets == [_SHEET_NAME]


def test_cli_exd_command_wired_up():
    parser = cli._build_parser()
    args = parser.parse_args(["/fake/game", "exd", _SHEET_NAME])
    assert args.func is cli._cmd_exd
    assert args.sheets == [_SHEET_NAME]
