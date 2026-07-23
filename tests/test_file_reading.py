"""Validate the SqPack file read path against a synthetic container.

No game installation is available in CI, so this builds a minimal in-memory
``dat`` stream containing one ``Default`` file with one compressed block and
checks that the header parsing, block padding and raw-DEFLATE inflate all line
up the way the original C# reader expects.
"""

from __future__ import annotations

import io
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saintcoinach.io.file import FileDefault, read_file  # noqa: E402


class _FakeIndexFile:
    def __init__(self, offset: int, dat_file: int = 0):
        self.offset = offset
        self.dat_file = dat_file
        self.file_key = 0x1234


class _FakePack:
    def __init__(self, stream):
        self._stream = stream

    def get_data_stream(self, dat_file: int = 0):
        return self._stream


def _build_default_file(payload: bytes, file_offset: int) -> bytes:
    # --- Common header (0x20 bytes: 0x18 base + one 0x08 block-info entry) ---
    header = bytearray(0x20)
    struct.pack_into("<i", header, 0x00, 0x20)  # header length
    struct.pack_into("<i", header, 0x04, 2)  # FileType.Default
    struct.pack_into("<i", header, 0x10, 0)  # content length >> 7 (unused here)
    struct.pack_into("<h", header, 0x14, 1)  # block count
    struct.pack_into("<i", header, 0x18, 0)  # block offset (relative to end of header)

    # --- One block: raw DEFLATE, padded so (size + 0x10) % 0x80 == 0 ---
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(payload) + compressor.flush()
    source_size = len(compressed)
    block_size = source_size
    if (block_size + 0x10) % 0x80 != 0:
        block_size += 0x80 - ((block_size + 0x10) % 0x80)
    padded = compressed + bytes(block_size - source_size)

    block_header = struct.pack("<IIII", 0x10, 0, source_size, len(payload))
    block = block_header + padded

    # The stream: leading padding up to file_offset, then header, then block.
    return bytes(file_offset) + bytes(header) + block


def test_default_file_roundtrip():
    payload = b"The quick brown fox jumps over the lazy dog. " * 4
    file_offset = 0x80
    data = _build_default_file(payload, file_offset)

    stream = io.BytesIO(data)
    pack = _FakePack(stream)
    index_file = _FakeIndexFile(file_offset)

    file = read_file(pack, index_file)
    assert isinstance(file, FileDefault)
    assert file.get_data() == payload
    # Cached second read returns the same bytes.
    assert file.get_data() == payload


if __name__ == "__main__":
    import traceback

    try:
        test_default_file_roundtrip()
        print("PASS test_default_file_roundtrip")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(1)
