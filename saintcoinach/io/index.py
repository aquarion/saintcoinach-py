"""Parsing of ``*.win32.index`` files.

Port of ``SaintCoinach.IO.Index``, ``IndexHeader``, ``IndexDirectory`` and
``IndexFile``.  Everything in an index file is little-endian.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import ordered
from .pack_identifier import PackIdentifier

__all__ = ["Index", "IndexDirectory", "IndexFile"]

_SQPACK_MAGIC = 0x00006B6361507153  # "SqPack\0\0"


@dataclass
class IndexFile:
    """A single file entry inside an index."""

    pack_id: PackIdentifier
    file_key: int
    directory_key: int
    dat_file: int
    offset: int

    @classmethod
    def read(cls, pack_id: PackIdentifier, buffer: bytes, position: int) -> "IndexFile":
        file_key = ordered.to_uint32(buffer, position, False)
        directory_key = ordered.to_uint32(buffer, position + 4, False)
        base_offset = ordered.to_int32(buffer, position + 8, False)
        dat_file = (base_offset & 0x000F) // 2
        offset = (base_offset - (base_offset & 0x000F)) * 0x08
        # position + 12 is a trailing zero
        return cls(pack_id, file_key, directory_key, dat_file, offset)


class IndexDirectory:
    """A directory entry inside an index, holding its file table."""

    ENTRY_LENGTH = 0x10

    def __init__(self, pack_id: PackIdentifier, buffer: bytes, position: int):
        self.pack_id = pack_id
        self.key = ordered.to_uint32(buffer, position, False)
        self.offset = ordered.to_int32(buffer, position + 4, False)
        length = ordered.to_int32(buffer, position + 8, False)
        self.count = length // self.ENTRY_LENGTH
        # position + 12 is a trailing zero

        self.files: dict[int, IndexFile] = {}
        pos = self.offset
        for _ in range(self.count):
            entry = IndexFile.read(pack_id, buffer, pos)
            self.files[entry.file_key] = entry
            pos += self.ENTRY_LENGTH


class Index:
    """The full contents of a ``*.index`` file."""

    ENTRY_LENGTH = 0x10

    def __init__(self, pack_id: PackIdentifier, path: str):
        self.pack_id = pack_id
        with open(path, "rb") as fh:
            buffer = fh.read()
        self._build(buffer)

    def _build(self, buffer: bytes) -> None:
        magic = ordered.to_uint64(buffer, 0, False)
        if magic != _SQPACK_MAGIC:
            raise ValueError("Input file is not a SqPack file.")

        header_offset = ordered.to_int32(buffer, 0x0C, False)
        # IndexHeader
        files_offset = ordered.to_int32(buffer, header_offset + 0x08, False)
        files_length = ordered.to_int32(buffer, header_offset + 0x0C, False)
        files_count = files_length // self.ENTRY_LENGTH  # noqa: F841 (kept for parity)

        directories_offset = ordered.to_int32(buffer, header_offset + 0xE4, False)
        dir_length = ordered.to_int32(buffer, header_offset + 0xE8, False)
        directories_count = dir_length // self.ENTRY_LENGTH

        self.directories: dict[int, IndexDirectory] = {}
        pos = directories_offset
        for _ in range(directories_count):
            directory = IndexDirectory(self.pack_id, buffer, pos)
            self.directories[directory.key] = directory
            pos += self.ENTRY_LENGTH
