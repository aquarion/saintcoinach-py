"""Unit tests for the self-contained parts of the port.

These need no game installation: CRC hashing, endian helpers, the string
decoder, DXT decompression and format conversions are all exercised against
synthetic inputs.
"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach import crc, ordered  # noqa: E402
from saintcoinach.ex.data_reader import Quad, get_reader  # noqa: E402
from saintcoinach.imaging import image_file, squish  # noqa: E402
from saintcoinach.imaging.image_file import ImageFormat, convert_to_bgra  # noqa: E402
from saintcoinach.io.pack_identifier import PackIdentifier  # noqa: E402
from saintcoinach.text import xiv_string  # noqa: E402


def test_crc_matches_zlib_semantics_case_folding():
    # Case folding: upper- and lower-case paths must hash identically.
    assert crc.compute("exd/Item.exh") == crc.compute("exd/item.exh")
    # Known-stable property: distinct names hash differently.
    assert crc.compute("exd") != crc.compute("bg")


def test_crc_sqpack_key_roundtrip():
    assert crc.try_get_sqpack_key("exd/root.exl") == 0x0A
    assert crc.try_get_sqpack_name(0x0A) == "exd"


def test_ordered_endianness():
    buf = struct.pack(">I", 0x01020304)
    assert ordered.to_uint32(buf, 0, True) == 0x01020304
    assert ordered.to_uint32(buf, 0, False) == 0x04030201
    assert ordered.to_int16(struct.pack(">h", -5), 0, True) == -5


def test_pack_identifier_parsing():
    pid = PackIdentifier.get("exd/root.exl")
    assert pid.type == "exd"
    assert pid.expansion == "ffxiv"
    assert pid.type_key == 0x0A

    pid2 = PackIdentifier.get("bg/ex1/01_foo/bar.dat")
    assert pid2.expansion == "ex1"
    assert str(pid2).startswith("ex1/")


def test_quad_reader():
    reader = get_reader(0x000B)
    data = struct.pack(">q", (4 << 48) | (3 << 32) | (2 << 16) | 1)
    q = reader.read(data, 0)
    assert isinstance(q, Quad)
    assert (q.value1, q.value2, q.value3, q.value4) == (1, 2, 3, 4)
    assert str(q) == "1, 2, 3, 4"


def test_numeric_readers_big_endian():
    assert get_reader(0x0006).read(struct.pack(">i", -12345), 0) == -12345
    assert get_reader(0x0002).read(bytes([0xFF]), 0) == -1  # sbyte
    assert get_reader(0x0003).read(bytes([0xFF]), 0) == 255  # byte
    assert get_reader(0x0001).read(bytes([0x01]), 0) is True
    # Packed booleans read individual bits.
    assert get_reader(0x19).read(bytes([0b0000_0001]), 0) is True
    assert get_reader(0x1A).read(bytes([0b0000_0010]), 0) is True
    assert get_reader(0x1A).read(bytes([0b0000_0001]), 0) is False


def test_string_decoder_plain_and_tagged():
    assert xiv_string.decode(b"Hello") == "Hello"
    # A tag (0x02 <type> <len=0x01 -> value 0> 0x03) between two runs is skipped.
    tagged = b"A" + bytes([0x02, 0x10, 0x01, 0x03]) + b"B"
    assert xiv_string.decode(tagged) == "AB"
    # UTF-8 multibyte survives.
    assert xiv_string.decode("Café".encode("utf-8")) == "Café"


def test_convert_a8r8g8b8_is_passthrough():
    src = bytes([10, 20, 30, 40, 50, 60, 70, 80])  # two BGRA pixels
    out = convert_to_bgra(src, ImageFormat.A8R8G8B8_1, 2, 1)
    assert out == src


def test_dxt1_solid_block_decodes_to_constant_colour():
    # Build a DXT1 block whose two endpoints are identical (pure red in 565),
    # so every pixel decodes to that colour.
    red565 = (31 << 11)  # r=31, g=0, b=0
    block = struct.pack("<HH", red565, red565) + bytes([0, 0, 0, 0])
    out = squish.decompress_image(block, 4, 4, squish.SquishOptions.DXT1)
    # Output is BGRA; red endpoint -> B=0, G=0, R=255, A=255.
    for i in range(16):
        b, g, r, a = out[i * 4 : i * 4 + 4]
        assert (b, g, r, a) == (0, 0, 255, 255)


def test_processors_cover_all_declared_formats():
    # Every format the original supports must have a processor here.
    supported = {
        ImageFormat.A16R16G16B16_FLOAT,
        ImageFormat.A1R5G5B5,
        ImageFormat.A4R4G4B4,
        ImageFormat.A8R8G8B8_1,
        ImageFormat.A8R8G8B8_2,
        ImageFormat.A8R8G8B8_CUBE,
        ImageFormat.A8R8G8B8_4,
        ImageFormat.A8R8G8B8_5,
        ImageFormat.DXT1,
        ImageFormat.DXT3,
        ImageFormat.DXT5,
        ImageFormat.R3G3B2,
    }
    assert supported <= set(image_file._PROCESSORS)


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    raise SystemExit(1 if failures else 0)
