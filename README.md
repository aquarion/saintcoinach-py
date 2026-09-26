# SaintCoinach (Python port)

A Python port of the **data-extraction** half of
[SaintCoinach](https://github.com/aquarion/SaintCoinach), the .NET library for
reading **Final Fantasy XIV** game assets. It reproduces the pipeline the
original uses to read data out of the game's SqPack archives:

- **SqPack extraction** — CRC filename hashing, `*.index` parsing, and reading
  files out of the `*.dat*` containers (including the block/DEFLATE
  decompression).
- **EX sheets** — `*.exh` header parsing and `*.exd` row reading, across
  variants 1 and 2 and all available languages.
- **Game strings** — decoding of the game's rich-text format to plain text
  (tags are structurally skipped, matching the original's "good string for
  most queries" behaviour).
- **Textures** — decoding `*.tex` image files (A8R8G8B8, A1R5G5B5, A4R4G4B4,
  R3G3B2, A16R16G16B16F, DXT1/3/5, and BC7) to PNG. BC7 — used by icons
  re-encoded in later game patches, and not handled by the original .NET
  library — is decoded via Pillow's native DDS reader. DXT1/3/5 decode uses a
  vectorised numpy implementation when numpy is installed (~15-20x faster,
  useful for bulk exports), falling back to a pure-Python per-pixel decoder
  otherwise.

## Scope

This port targets the **data + CLI export** workflow. It intentionally does
**not** include the WPF/DirectX 3D model viewer (`SaintCoinach.Graphics.Viewer`
/ `Godbert`).

Column *names* — vendored from [EXDSchema](https://github.com/xivdev/EXDSchema),
the community successor to the original's `SaintCoinach.History.zip` — can be
loaded via `saintcoinach.ex.get_definition("Item")`, but are not yet wired into
row/sheet access. Sheet export is therefore still by **column index**
(equivalent to the original's `rawexd`), not named columns; that's tracked
separately.

## Install

```bash
pip install -e .          # core data reading
pip install -e '.[images]' # + Pillow (PNG export) and numpy (faster DXT decode)
```

Pure data reading has no third-party dependencies. Pillow is required for
image/PNG output; numpy is optional on top of that and only speeds up
DXT1/3/5 decode — bulk texture export (e.g. exporting every icon) is
meaningfully faster with it, but single-icon export is fine without it.

## CLI

The CLI mirrors the subset of `SaintCoinach.Cmd` used for export. Point it at
your game install directory (the one containing `game/sqpack`) or the
`sqpack` directory itself.

```bash
# Export a single UI icon to PNG (the common case)
saintcoinach "/path/to/FINAL FANTASY XIV Online" ui 51474

# Export a range of icons
saintcoinach "/path/to/game" ui 51000 51999

# Export every icon (slow)
saintcoinach "/path/to/game" ui

# HD icons
saintcoinach "/path/to/game" uihd 51474

# A single image by SqPack path
saintcoinach "/path/to/game" image ui/icon/051000/051474.tex

# A raw file, no conversion
saintcoinach "/path/to/game" raw exd/root.exl

# Sheets as CSV (index-based columns)
saintcoinach "/path/to/game" rawexd Item Action
saintcoinach "/path/to/game" rawexd        # all sheets

# Options
saintcoinach "/path/to/game" -o out_dir -l ja rawexd Item
```

Output is written under `<out>/<game version>/…`, preserving the SqPack path
(with `.png` substituted for exported images).

`python -m saintcoinach …` works identically to the `saintcoinach` entry point.

## Library

```python
from saintcoinach import GameData, Language

with GameData("/path/to/FINAL FANTASY XIV Online", Language.ENGLISH) as game:
    # UI icon -> PNG
    from saintcoinach.imaging import get_icon
    icon = get_icon(game.packs, 51474)
    icon.get_image().save("51474.png")

    # Read a sheet
    sheet = game.get_sheet("Item")
    print(len(sheet), "rows")
    row = sheet[1601]
    print([row[i] for i in range(sheet.header.column_count)])
```

## Tests

```bash
python3 tests/test_core.py          # pure logic: CRC, endian, DXT, strings
python3 tests/test_file_reading.py  # synthetic SqPack read path
# or, with pytest installed:  pytest tests
```

### Validation status

The self-contained logic (CRC hashing with case folding, endianness, DXT1/3/5
decode, string decoding, format conversion) and the binary file-read path
(header parsing, block padding, raw-DEFLATE inflate) are covered by unit tests
against synthetic inputs. **End-to-end reads against real game files have not
been run in this environment** (no game installation is available here); the
SqPack/EXH/EXD parsing is a structural port of the C# source and should be
spot-checked against a real installation — comparing a handful of exported
icons and CSV rows against the .NET tool's output is the quickest way to
confirm parity.

## Mapping to the original

| C# | Python |
| --- | --- |
| `SaintCoinach.IO.Hash` | `saintcoinach.crc` |
| `OrderedBitConverter` | `saintcoinach.ordered` |
| `IO.PackIdentifier` / `Index` / `Pack` / `PackCollection` | `saintcoinach.io.*` |
| `IO.FileDefault` / block decompression | `saintcoinach.io.file` |
| `Imaging.ImageFile` / `ImageConverter` | `saintcoinach.imaging.image_file` |
| `DotSquish` (decode only) | `saintcoinach.imaging.squish` |
| `Ex.ExCollection` / `Header` / `Column` / sheets | `saintcoinach.ex.*` |
| `Text.XivStringDecoder` (plain-text subset) | `saintcoinach.text.xiv_string` |
| `ARealmReversed` (data path) | `saintcoinach.realm.GameData` |
| `SaintCoinach.Cmd` (export subset) | `saintcoinach.cli` |

## License

Released under the WTFPL, matching the original
[SaintCoinach](https://github.com/aquarion/SaintCoinach) project this is ported
from. See [`LICENSE`](LICENSE).
