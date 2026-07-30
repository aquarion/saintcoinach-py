"""Decoding of ``*.tex`` image files stored inside SqPack.

Port of ``SaintCoinach.Imaging.ImageFile``, ``ImageHeader`` and
``ImageConverter``.  Produces a BGRA byte buffer (matching the original) and,
via :meth:`ImageFile.get_image`, a Pillow image ready to be saved as PNG.
"""

from __future__ import annotations

import struct
from enum import IntEnum

from ..io.file import FileCommonHeader, SqPackFile, read_block
from . import squish

__all__ = ["ImageFormat", "ImageHeader", "ImageFile", "convert_to_bgra"]


class ImageFormat(IntEnum):
    UNKNOWN = 0
    A16R16G16B16_FLOAT = 0x2460

    A8R8G8B8_1 = 0x1131
    A8R8G8B8_2 = 0x1450
    A8R8G8B8_CUBE = 0x1451
    A8R8G8B8_4 = 0x2150
    A8R8G8B8_5 = 0x4401

    A4R4G4B4 = 0x1440
    A1R5G5B5 = 0x1441
    R3G3B2 = 0x1130

    DXT1 = 0x3420
    DXT3 = 0x3430
    DXT5 = 0x3431

    # BC7 (DXGI_FORMAT_BC7). Not part of the original SaintCoinach enum; FFXIV
    # re-encoded a range of icons to BC7 in later patches.
    BC7 = 0x6432


class ImageHeader:
    """The 0x50-byte header at the start of an image file's payload."""

    LENGTH = 0x50
    _FORMAT_OFFSET = 0x04
    _WIDTH_OFFSET = 0x08
    _HEIGHT_OFFSET = 0x0A

    def __init__(self, stream):
        self.buffer = stream.read(self.LENGTH)
        if len(self.buffer) != self.LENGTH:
            raise EOFError("Unexpected end of stream reading image header.")
        self.width = struct.unpack_from("<h", self.buffer, self._WIDTH_OFFSET)[0]
        self.height = struct.unpack_from("<h", self.buffer, self._HEIGHT_OFFSET)[0]
        self.raw_format = struct.unpack_from("<H", self.buffer, self._FORMAT_OFFSET)[0]
        try:
            self.format = ImageFormat(self.raw_format)
        except ValueError:
            self.format = ImageFormat.UNKNOWN
        self.end_of_header = stream.tell()


class ImageFile(SqPackFile):
    """An image file, decodable to raw pixels or a Pillow image."""

    _COUNT_OFFSET = 0x14
    _ENTRY_LENGTH = 0x14
    _BLOCK_INFO_OFFSET = 0x18

    def __init__(self, pack, common_header: FileCommonHeader):
        super().__init__(pack, common_header)
        stream = self.get_source_stream()
        stream.seek(common_header.end_of_header)
        self.image_header = ImageHeader(stream)
        self._data: bytes | None = None

    @property
    def width(self) -> int:
        return self.image_header.width

    @property
    def height(self) -> int:
        return self.image_header.height

    @property
    def format(self) -> ImageFormat:
        return self.image_header.format

    def get_data(self) -> bytes:
        if self._data is None:
            self._data = self._read()
        return self._data

    def _block_offsets(self) -> list[int]:
        buffer = self.common_header.buffer
        count = struct.unpack_from("<h", buffer, self._COUNT_OFFSET)[0]
        offsets: list[int] = []
        current = 0
        i = self._BLOCK_INFO_OFFSET + count * self._ENTRY_LENGTH
        while i + 2 <= len(buffer):
            length = struct.unpack_from("<H", buffer, i)[0]
            if length == 0:
                break
            offsets.append(current)
            current += length
            i += 2
        return offsets

    def _read(self) -> bytes:
        stream = self.get_source_stream()
        chunks: list[bytes] = []
        for offset in self._block_offsets():
            stream.seek(self.image_header.end_of_header + offset)
            chunks.append(read_block(stream))
        return b"".join(chunks)

    def get_bgra(self) -> bytes:
        """Return the image as a width*height*4 BGRA byte buffer."""
        try:
            return convert_to_bgra(
                self.get_data(), self.format, self.width, self.height
            )
        except NotImplementedError:
            raise NotImplementedError(
                f"Unsupported texture format 0x{self.image_header.raw_format:04x}"
                f" ({self.format.name}) for {self.path or 'image'}"
            ) from None

    def get_image(self):
        """Return a Pillow ``Image`` (requires Pillow to be installed)."""
        from PIL import Image

        bgra = self.get_bgra()
        return Image.frombytes(
            "RGBA", (self.width, self.height), bytes(bgra), "raw", "BGRA"
        )


# -- format conversion --------------------------------------------------------


def _process_a8r8g8b8(src: bytes, dst: bytearray, width: int, height: int) -> None:
    length = min(len(src), len(dst))
    dst[:length] = src[:length]


def _process_a1r5g5b5(src: bytes, dst: bytearray, width: int, height: int) -> None:
    for i in range(0, 2 * width * height, 2):
        v = struct.unpack_from("<H", src, i)[0]
        a = v & 0x8000
        r = v & 0x7C00
        g = v & 0x03E0
        b = v & 0x001F
        rgb = (r << 9) | (g << 6) | (b << 3)
        argb = (a * 0x1FE00) | rgb | ((rgb >> 5) & 0x070707)
        for j in range(4):
            dst[i * 2 + j] = (argb >> (8 * j)) & 0xFF


def _process_a4r4g4b4(src: bytes, dst: bytearray, width: int, height: int) -> None:
    for i in range(0, 2 * width * height, 2):
        v = struct.unpack_from("<H", src, i)[0]
        for j in range(4):
            dst[i * 2 + j] = ((v >> (4 * j)) & 0x0F) << 4


def _process_r3g3b2(src: bytes, dst: bytearray, width: int, height: int) -> None:
    for i in range(width * height):
        r = src[i] & 0xE0
        g = src[i] & 0x1C
        b = src[i] & 0x03
        dst[i * 4 + 0] = (b | (b << 2) | (b << 4) | (b << 6)) & 0xFF
        dst[i * 4 + 1] = (g | (g << 3) | (g << 6)) & 0xFF
        dst[i * 4 + 2] = (r | (r << 3) | (r << 6)) & 0xFF
        dst[i * 4 + 3] = 0xFF


def _process_a16r16g16b16_float(
    src: bytes, dst: bytearray, width: int, height: int
) -> None:
    for i in range(width * height):
        src_off = i * 4 * 2
        dst_off = i * 4
        for j in range(4):
            value = struct.unpack_from("<e", src, src_off + j * 2)[0]
            clamped = max(0.0, min(1.0, value))
            dst[dst_off + j] = int(clamped * 255) & 0xFF


def _process_dxt(flags: squish.SquishOptions):
    def proc(src: bytes, dst: bytearray, width: int, height: int) -> None:
        decoded = squish.decompress_image(src, width, height, flags)
        dst[: len(dst)] = decoded[: len(dst)]

    return proc


def _build_bc7_dds(data: bytes, width: int, height: int) -> bytes:
    """Wrap a BC7 payload in a minimal DX10 DDS container for Pillow."""
    blocks = ((width + 3) // 4) * ((height + 3) // 4)
    pitch = blocks * 16  # BC7 = 16 bytes per 4x4 block
    # DDS_HEADER: size, flags (CAPS|HEIGHT|WIDTH|PIXELFORMAT|LINEARSIZE),
    # height, width, pitchOrLinearSize, depth, mipMapCount, then 11 reserved.
    header = (
        struct.pack(
            "<7I", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, height, width, pitch, 0, 1
        )
        + b"\x00" * 44
    )
    # DDS_PIXELFORMAT: size, flags=FOURCC, fourCC="DX10", then 5 unused masks.
    pixelformat = struct.pack("<2I4s5I", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    # dwCaps=TEXTURE, then caps2/3/4 + reserved.
    caps = struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    # DDS_HEADER_DXT10: dxgiFormat=98 (BC7_UNORM), dimension=3 (TEXTURE2D),
    # miscFlag=0, arraySize=1, miscFlags2=0.
    dx10 = struct.pack("<5I", 98, 3, 0, 1, 0)
    return b"DDS " + header + pixelformat + caps + dx10 + bytes(data)


def _process_bc7(src: bytes, dst: bytearray, width: int, height: int) -> None:
    # BC7 has 8 modes and is impractical to decode quickly in pure Python;
    # Pillow's DDS reader has a fast native BC7 decoder, and Pillow is already
    # required for image output, so decode through it.
    import io

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise NotImplementedError(
            "BC7 texture decoding requires Pillow. Install the 'images' extra."
        ) from exc

    dds = _build_bc7_dds(src, width, height)
    image = Image.open(io.BytesIO(dds)).convert("RGBA")
    rgba = image.tobytes()  # R, G, B, A
    # Match the BGRA byte order the rest of the pipeline produces.
    dst[0::4] = rgba[2::4]  # B
    dst[1::4] = rgba[1::4]  # G
    dst[2::4] = rgba[0::4]  # R
    dst[3::4] = rgba[3::4]  # A


_PROCESSORS = {
    ImageFormat.A16R16G16B16_FLOAT: _process_a16r16g16b16_float,
    ImageFormat.A1R5G5B5: _process_a1r5g5b5,
    ImageFormat.A4R4G4B4: _process_a4r4g4b4,
    ImageFormat.A8R8G8B8_1: _process_a8r8g8b8,
    ImageFormat.A8R8G8B8_2: _process_a8r8g8b8,
    ImageFormat.A8R8G8B8_CUBE: _process_a8r8g8b8,
    ImageFormat.A8R8G8B8_4: _process_a8r8g8b8,
    ImageFormat.A8R8G8B8_5: _process_a8r8g8b8,
    ImageFormat.DXT1: _process_dxt(squish.SquishOptions.DXT1),
    ImageFormat.DXT3: _process_dxt(squish.SquishOptions.DXT3),
    ImageFormat.DXT5: _process_dxt(squish.SquishOptions.DXT5),
    ImageFormat.R3G3B2: _process_r3g3b2,
    ImageFormat.BC7: _process_bc7,
}


def convert_to_bgra(
    src: bytes, image_format: ImageFormat, width: int, height: int
) -> bytes:
    proc = _PROCESSORS.get(image_format)
    if proc is None:
        raise NotImplementedError(f"Unsupported image format {image_format!r}")
    dst = bytearray(width * height * 4)
    proc(src, dst, width, height)
    return bytes(dst)
