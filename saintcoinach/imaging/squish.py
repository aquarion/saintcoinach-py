"""Minimal DXT1/DXT3/DXT5 decompressor.

Decompression-only port of the parts of DotSquish that SaintCoinach uses.  The
output byte order matches the original ``Squish.DecompressImage``: BGRA per
pixel (so it maps straight onto a 32bpp ARGB bitmap in memory).
"""

from __future__ import annotations

from enum import IntFlag

__all__ = ["SquishOptions", "decompress_image"]


class SquishOptions(IntFlag):
    DXT1 = 1 << 0
    DXT3 = 1 << 1
    DXT5 = 1 << 2


def _unpack_565(block: bytes, offset: int, colour: bytearray, colour_offset: int) -> int:
    value = block[offset] | (block[offset + 1] << 8)
    red = (value >> 11) & 0x1F
    green = (value >> 5) & 0x3F
    blue = value & 0x1F

    colour[colour_offset + 0] = (red << 3) | (red >> 2)
    colour[colour_offset + 1] = (green << 2) | (green >> 4)
    colour[colour_offset + 2] = (blue << 3) | (blue >> 2)
    colour[colour_offset + 3] = 255
    return value


def _decompress_colour(block: bytes, offset: int, is_dxt1: bool) -> bytearray:
    codes = bytearray(16)
    a = _unpack_565(block, offset + 0, codes, 0)
    b = _unpack_565(block, offset + 2, codes, 4)

    for i in range(3):
        c = codes[i]
        d = codes[4 + i]
        if is_dxt1 and a <= b:
            codes[8 + i] = (c + d) // 2
            codes[12 + i] = 0
        else:
            codes[8 + i] = (2 * c + d) // 3
            codes[12 + i] = (c + 2 * d) // 3

    codes[8 + 3] = 255
    codes[12 + 3] = 0 if (is_dxt1 and a <= b) else 255

    indices = bytearray(16)
    for i in range(4):
        packed = block[offset + 4 + i]
        indices[4 * i + 0] = packed & 0x3
        indices[4 * i + 1] = (packed >> 2) & 0x3
        indices[4 * i + 2] = (packed >> 4) & 0x3
        indices[4 * i + 3] = (packed >> 6) & 0x3

    rgba = bytearray(4 * 16)
    for i in range(16):
        off = 4 * indices[i]
        rgba[4 * i : 4 * i + 4] = codes[off : off + 4]
    return rgba


def _decompress_alpha_dxt3(block: bytes, offset: int, target: bytearray) -> None:
    for i in range(8):
        quant = block[offset + i]
        lo = quant & 0x0F
        hi = quant & 0xF0
        target[8 * i + 3] = lo | (lo << 4)
        target[8 * i + 7] = hi | (hi >> 4)


def _decompress_alpha_dxt5(block: bytes, offset: int, target: bytearray) -> None:
    alpha0 = block[offset + 0]
    alpha1 = block[offset + 1]

    codes = bytearray(8)
    codes[0] = alpha0
    codes[1] = alpha1
    if alpha0 <= alpha1:
        for i in range(1, 5):
            codes[1 + i] = ((5 - i) * alpha0 + i * alpha1) // 5
        codes[6] = 0
        codes[7] = 255
    else:
        for i in range(1, 7):
            codes[1 + i] = ((7 - i) * alpha0 + i * alpha1) // 7

    indices = bytearray(16)
    bl_off = 2
    ind_off = 0
    for _ in range(2):
        value = 0
        for j in range(3):
            value |= block[offset + bl_off] << (8 * j)
            bl_off += 1
        for j in range(8):
            indices[ind_off] = (value >> (3 * j)) & 0x7
            ind_off += 1

    for i in range(16):
        target[4 * i + 3] = codes[indices[i]]


def _decompress_block(block: bytes, offset: int, flags: SquishOptions) -> bytearray:
    col_off = offset
    alpha_off = offset
    if flags & (SquishOptions.DXT3 | SquishOptions.DXT5):
        col_off += 8

    rgba = _decompress_colour(block, col_off, bool(flags & SquishOptions.DXT1))

    if flags & SquishOptions.DXT3:
        _decompress_alpha_dxt3(block, alpha_off, rgba)
    elif flags & SquishOptions.DXT5:
        _decompress_alpha_dxt5(block, alpha_off, rgba)
    return rgba


def decompress_image(blocks: bytes, width: int, height: int, flags: SquishOptions) -> bytearray:
    """Decompress a DXT-compressed image into a BGRA byte buffer."""
    argb = bytearray(4 * width * height)
    bytes_per_block = 8 if (flags & SquishOptions.DXT1) else 16

    block_offset = 0
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            target_rgba = _decompress_block(blocks, block_offset, flags)

            source_pixel_offset = 0
            for py in range(4):
                for px in range(4):
                    sx = x + px
                    sy = y + py
                    if sx < width and sy < height:
                        i = 4 * ((width * sy) + sx)
                        # RGBA -> BGRA, as in the original.
                        argb[i + 0] = target_rgba[source_pixel_offset + 2]
                        argb[i + 1] = target_rgba[source_pixel_offset + 1]
                        argb[i + 2] = target_rgba[source_pixel_offset + 0]
                        argb[i + 3] = target_rgba[source_pixel_offset + 3]
                    source_pixel_offset += 4

            block_offset += bytes_per_block
    return argb
