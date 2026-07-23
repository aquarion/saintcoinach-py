"""Command-line asset exporter.

A Python equivalent of the subset of ``SaintCoinach.Cmd`` that the data-export
workflow relies on: UI icon export (``ui``/``uihd``), single image export
(``image``), raw file export (``raw``) and sheet CSV export (``rawexd``).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from . import GameData, Language

# Localisation sub-folders tried for each icon, mirroring UiCommand.
_UI_VERSIONS = ["", "/en", "/ja", "/fr", "/de", "/hq", "/chs"]


def _output_root(game: GameData, out_dir: str) -> str:
    version = game.game_version or "output"
    return os.path.join(out_dir, version)


def _save_image_file(image_file, dest_png: str) -> None:
    try:
        image = image_file.get_image()
    except ImportError as exc:  # Pillow missing
        raise SystemExit(
            "Pillow is required for image export. Install it with 'pip install Pillow'."
        ) from exc
    os.makedirs(os.path.dirname(dest_png), exist_ok=True)
    image.save(dest_png)


def _export_icons(game: GameData, out_dir: str, low: int, high: int, hr: bool) -> int:
    fmt = "ui/icon/{0:03d}000{1}/{2:06d}{3}.tex"
    suffix = "_hr1" if hr else ""
    root = _output_root(game, out_dir)
    count = 0
    for i in range(low, high + 1):
        for version in _UI_VERSIONS:
            path = fmt.format(i // 1000, version, i, suffix)
            file = game.packs.try_get_file(path)
            if file is None:
                continue
            if not hasattr(file, "get_image"):
                print(f"{path} is not an image.", file=sys.stderr)
                continue
            dest = os.path.join(root, os.path.splitext(path)[0] + ".png")
            try:
                _save_image_file(file, dest)
                count += 1
            except Exception as exc:  # noqa: BLE001 - match the tool's per-item tolerance
                print(f"{i:06d}: {exc}", file=sys.stderr)
    return count


def _cmd_ui(game: GameData, args) -> None:
    count = _export_icons(game, args.out, args.first, args.last, hr=False)
    print(f"{count} images processed")


def _cmd_uihd(game: GameData, args) -> None:
    count = _export_icons(game, args.out, args.first, args.last, hr=True)
    print(f"{count} images processed")


def _cmd_image(game: GameData, args) -> None:
    file = game.packs.try_get_file(args.path)
    if file is None:
        raise SystemExit(f"File not found: {args.path}")
    if not hasattr(file, "get_image"):
        raise SystemExit(f"{args.path} is not an image.")
    root = _output_root(game, args.out)
    dest = os.path.join(root, os.path.splitext(args.path)[0] + ".png")
    _save_image_file(file, dest)
    print(f"Wrote {dest}")


def _cmd_raw(game: GameData, args) -> None:
    file = game.packs.try_get_file(args.path)
    if file is None:
        raise SystemExit(f"File not found: {args.path}")
    root = _output_root(game, args.out)
    dest = os.path.join(root, args.path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(file.get_data())
    print(f"Wrote {dest}")


def _cmd_rawexd(game: GameData, args) -> None:
    names = args.sheets or sorted(game.game_data.available_sheets)
    root = _output_root(game, args.out)
    for name in names:
        try:
            _export_sheet_csv(game, root, name)
            print(f"Exported {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: {exc}", file=sys.stderr)


def _export_sheet_csv(game: GameData, root: str, name: str) -> None:
    from .ex.sheet import Variant2Row

    sheet = game.game_data.get_sheet(game.game_data.fix_name(name))
    header = sheet.header
    dest = os.path.join(root, "exd", name + ".csv")
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    with open(dest, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["key"] + [str(c.index) for c in header.columns])
        writer.writerow([""] + [c.value_type for c in header.columns])
        for row in sheet.rows():
            if isinstance(row, Variant2Row):
                for sub in row.sub_rows():
                    writer.writerow([sub.full_key] + [_fmt(v) for v in sub.column_values()])
            else:
                writer.writerow([row.key] + [_fmt(v) for v in row.column_values()])


def _fmt(value) -> str:
    if value is None:
        return ""
    return str(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saintcoinach",
        description="Extract assets from a FINAL FANTASY XIV installation.",
    )
    parser.add_argument(
        "game_directory",
        help="Path to the game install (or its sqpack directory).",
    )
    parser.add_argument("-o", "--out", default="output", help="Output directory (default: ./output).")
    parser.add_argument(
        "-l",
        "--language",
        default="en",
        help="Language code for localised data (default: en).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_range(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("first", nargs="?", type=int, default=0)
        p.add_argument("last", nargs="?", type=int, default=None)
        p.set_defaults(func=func)
        return p

    add_range("ui", _cmd_ui, "Export a single, a range of, or all UI icons as PNG.")
    add_range("uihd", _cmd_uihd, "Export HD UI icons as PNG.")

    p_image = sub.add_parser("image", help="Export a single image file to PNG.")
    p_image.add_argument("path", help="SqPack path, e.g. ui/icon/012000/012345.tex")
    p_image.set_defaults(func=_cmd_image)

    p_raw = sub.add_parser("raw", help="Export a file without any conversion.")
    p_raw.add_argument("path", help="SqPack path of the file to export.")
    p_raw.set_defaults(func=_cmd_raw)

    p_exd = sub.add_parser("rawexd", help="Export sheets as CSV (raw, index-based columns).")
    p_exd.add_argument("sheets", nargs="*", help="Sheet names; omit to export all.")
    p_exd.set_defaults(func=_cmd_rawexd)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # For the range commands: no args exports everything, a single positional
    # means "just that one icon".
    if getattr(args, "command", None) in ("ui", "uihd"):
        if args.last is None:
            args.last = args.first if args.first else 999999

    language = Language.from_code(args.language)
    if language == Language.UNSUPPORTED:
        parser.error(f"Unsupported language code '{args.language}'.")

    try:
        with GameData(args.game_directory, language) as game:
            args.func(game, args)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"error: unknown sheet {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
