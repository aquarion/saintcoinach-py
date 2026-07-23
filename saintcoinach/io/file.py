"""Reading of individual files out of the SqPack ``*.dat`` containers.

Port of ``SaintCoinach.IO.FileCommonHeader``, ``FileDefault`` and the block
decompression helpers on ``SaintCoinach.IO.File``.  ``Default`` files (every
``*.exl``/``*.exh``/``*.exd``) and ``Image`` files (``*.tex``) are supported;
``Model`` files are recognised but not decoded.

The container structures are little-endian.
"""

from __future__ import annotations

import struct
import zlib
from enum import IntEnum

__all__ = ["FileType", "FileCommonHeader", "SqPackFile", "FileDefault", "read_file"]

_COMPRESSION_THRESHOLD = 0x7D00
_BLOCK_PADDING = 0x80
_BLOCK_HEADER_LENGTH = 0x10
_BLOCK_MAGIC = 0x00000010


class FileType(IntEnum):
    UNKNOWN = 0
    EMPTY = 1
    DEFAULT = 2
    MODEL = 3
    IMAGE = 4


def inflate(buffer: bytes) -> bytes:
    """Raw DEFLATE inflate (no zlib header), matching Ionic.Zlib."""
    return zlib.decompress(buffer, -zlib.MAX_WBITS)


def read_block(stream) -> bytes:
    """Read and, if needed, inflate a single SqPack data block."""
    header = stream.read(_BLOCK_HEADER_LENGTH)
    if len(header) != _BLOCK_HEADER_LENGTH:
        raise EOFError("Unexpected end of stream reading block header.")

    magic, _unknown, source_size, raw_size = struct.unpack_from("<IIII", header, 0)
    if magic != _BLOCK_MAGIC:
        raise ValueError("Block magic number not present.")

    is_compressed = source_size < _COMPRESSION_THRESHOLD
    block_size = source_size if is_compressed else raw_size

    if is_compressed and (block_size + _BLOCK_HEADER_LENGTH) % _BLOCK_PADDING != 0:
        block_size += _BLOCK_PADDING - ((block_size + _BLOCK_HEADER_LENGTH) % _BLOCK_PADDING)

    buffer = stream.read(block_size)
    if len(buffer) != block_size:
        raise EOFError("Unexpected end of stream reading block data.")

    if is_compressed:
        result = inflate(buffer)
        if len(result) != raw_size:
            raise ValueError("Inflated block does not match indicated size.")
        return result
    return buffer[:raw_size]


class FileCommonHeader:
    """Shared header preceding every file in a ``*.dat`` container."""

    _FILE_TYPE_OFFSET = 0x04
    _FILE_LENGTH_OFFSET = 0x10
    _FILE_LENGTH_SHIFT = 7

    def __init__(self, index_file, stream):
        self.index = index_file

        length_bytes = stream.read(4)
        if len(length_bytes) != 4:
            raise EOFError("Unexpected end of stream reading header length.")
        length = struct.unpack("<i", length_bytes)[0]

        remaining = stream.read(length - 4)
        if len(remaining) != length - 4:
            raise EOFError("Unexpected end of stream reading header.")
        self.buffer = length_bytes + remaining

        self.file_type = FileType(struct.unpack_from("<i", self.buffer, self._FILE_TYPE_OFFSET)[0])
        raw_len = struct.unpack_from("<i", self.buffer, self._FILE_LENGTH_OFFSET)[0]
        self.length = raw_len << self._FILE_LENGTH_SHIFT
        self.end_of_header = stream.tell()


class SqPackFile:
    """Base class for a file stored inside SqPack."""

    def __init__(self, pack, common_header: FileCommonHeader):
        self.pack = pack
        self.common_header = common_header
        self.index = common_header.index
        self.path: str | None = None

    def get_source_stream(self):
        return self.pack.get_data_stream(self.index.dat_file)

    def get_data(self) -> bytes:  # pragma: no cover - abstract
        raise NotImplementedError

    def __str__(self) -> str:
        return self.path or f"{self.index.file_key:08X}"


class FileDefault(SqPackFile):
    """A ``Default`` file inside SqPack, with lazily-decoded data."""

    _BLOCK_COUNT_OFFSET = 0x14
    _BLOCK_INFO_OFFSET = 0x18
    _BLOCK_INFO_LENGTH = 0x08

    def __init__(self, pack, common_header: FileCommonHeader):
        super().__init__(pack, common_header)
        self._data: bytes | None = None

    def get_data(self) -> bytes:
        if self._data is None:
            self._data = self._read()
        return self._data

    def _read(self) -> bytes:
        header = self.common_header
        block_count = struct.unpack_from("<h", header.buffer, self._BLOCK_COUNT_OFFSET)[0]

        stream = self.get_source_stream()
        chunks: list[bytes] = []
        for i in range(block_count):
            block_offset = struct.unpack_from(
                "<i", header.buffer, self._BLOCK_INFO_OFFSET + i * self._BLOCK_INFO_LENGTH
            )[0]
            stream.seek(header.end_of_header + block_offset)
            chunks.append(read_block(stream))
        return b"".join(chunks)


def read_file(pack, index_file) -> SqPackFile:
    """Factory mirroring ``FileFactory.Get`` for the supported file types."""
    stream = pack.get_data_stream(index_file.dat_file)
    stream.seek(index_file.offset)
    header = FileCommonHeader(index_file, stream)

    if header.file_type in (FileType.DEFAULT, FileType.EMPTY):
        return FileDefault(pack, header)
    if header.file_type == FileType.IMAGE:
        from ..imaging.image_file import ImageFile  # local import avoids a cycle

        return ImageFile(pack, header)
    if header.file_type == FileType.MODEL:
        raise NotImplementedError("Model files are not supported by the Python port yet.")
    raise ValueError(f"Unknown file type {int(header.file_type):#x}")
