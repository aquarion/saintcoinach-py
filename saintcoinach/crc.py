"""CRC32-based filename hashing used by the SqPack index files.

Port of ``SaintCoinach.IO.Hash``.  Paths are hashed case-insensitively (ASCII
upper-case letters are folded to lower-case before hashing), which is why the
table-driven implementation is reproduced verbatim rather than delegating to
``zlib.crc32`` -- the folding has to happen per byte inside the loop.
"""

from __future__ import annotations

__all__ = ["compute", "try_get_sqpack_key", "try_get_sqpack_name"]

CRC_INITIAL_SEED = 0xFFFFFFFF


def _build_table() -> list[int]:
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
        table.append(c & 0xFFFFFFFF)
    return table


_CRC_TABLE = _build_table()


def _compute(seed: int, buffer: bytes, start: int, size: int) -> int:
    crc = seed & 0xFFFFFFFF
    for i in range(start, start + size):
        b = buffer[i]
        if 0x41 <= b <= 0x5A:  # fold ASCII 'A'-'Z' to lower-case
            b += 0x20
        crc = (crc >> 8) ^ _CRC_TABLE[(b ^ crc) & 0xFF]
    return crc & 0xFFFFFFFF


def compute(value: str) -> int:
    """Compute the SqPack hash of a directory or file name."""
    data = value.encode("ascii")
    return _compute(CRC_INITIAL_SEED, data, 0, len(data))


_ROOT_TO_SQ = {
    "common": 0x00,
    "bgcommon": 0x01,
    "bg": 0x02,
    "cut": 0x03,
    "chara": 0x04,
    "shader": 0x05,
    "ui": 0x06,
    "sound": 0x07,
    "vfx": 0x08,
    "ui_script": 0x09,
    "exd": 0x0A,
    "game_script": 0x0B,
    "music": 0x0C,
    "_sqpack_test": 0x12,
    "_debug": 0x13,
}
_SQ_TO_ROOT = {v: k for k, v in _ROOT_TO_SQ.items()}


def try_get_sqpack_key(path: str) -> int | None:
    search = path.split("/", 1)[0]
    return _ROOT_TO_SQ.get(search)


def try_get_sqpack_name(key: int) -> str | None:
    return _SQ_TO_ROOT.get(key)
