"""Minimal DXT1/DXT3/DXT5 decompressor.

Decompression-only port of the parts of DotSquish that SaintCoinach uses.  The
output byte order matches the original ``Squish.DecompressImage``: BGRA per
pixel (so it maps straight onto a 32bpp ARGB bitmap in memory).

Decoding is block-parallel (each 4x4 block is independent), so when numpy is
importable ``decompress_image`` uses a vectorised path that decodes every
block in a handful of array operations instead of a per-pixel Python loop.
This matters for bulk exports (e.g. all UI icons), where the pure-Python loop
dominates runtime. Without numpy, decoding falls back to the reference
per-pixel implementation, which remains correct (if slow) for single-icon use.
"""

from __future__ import annotations

from enum import IntFlag

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised by the no-numpy test path
    np = None

__all__ = ["SquishOptions", "decompress_image"]


class SquishOptions(IntFlag):
    DXT1 = 1 << 0
    DXT3 = 1 << 1
    DXT5 = 1 << 2


# -- reference (pure Python) implementation -----------------------------------


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


def _decompress_image_python(
    blocks: bytes, width: int, height: int, flags: SquishOptions
) -> bytearray:
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


# -- vectorised (numpy) implementation ----------------------------------------


def _unpack_565_np(values):
    """Expand an array of packed RGB565 uint16 values to (r, g, b) uint8 arrays."""
    r5 = (values >> 11) & 0x1F
    g6 = (values >> 5) & 0x3F
    b5 = values & 0x1F
    r8 = (r5 << 3) | (r5 >> 2)
    g8 = (g6 << 2) | (g6 >> 4)
    b8 = (b5 << 3) | (b5 >> 2)
    return r8, g8, b8


def _decompress_colour_np(colour_bytes, is_dxt1: bool):
    """Decode the 8-byte colour sub-block for every block at once.

    ``colour_bytes`` is a ``(N, 8)`` uint8 array. Returns ``(codes, indices)``
    where ``codes`` is ``(N, 4, 4)`` uint8 (4 candidate RGBA colours per
    block) and ``indices`` is ``(N, 16)`` uint8 (per-pixel code selector,
    0-3).
    """
    n = colour_bytes.shape[0]
    color0 = colour_bytes[:, 0].astype(np.uint16) | (
        colour_bytes[:, 1].astype(np.uint16) << 8
    )
    color1 = colour_bytes[:, 2].astype(np.uint16) | (
        colour_bytes[:, 3].astype(np.uint16) << 8
    )

    r0, g0, b0 = (c.astype(np.int32) for c in _unpack_565_np(color0))
    r1, g1, b1 = (c.astype(np.int32) for c in _unpack_565_np(color1))

    use_three_colour = is_dxt1 & (color0 <= color1)

    def blend(c0, c1):
        avg = (c0 + c1) // 2
        third1 = (2 * c0 + c1) // 3
        third2 = (c0 + 2 * c1) // 3
        code2 = np.where(use_three_colour, avg, third1)
        code3 = np.where(use_three_colour, 0, third2)
        return code2, code3

    r2, r3 = blend(r0, r1)
    g2, g3 = blend(g0, g1)
    b2, b3 = blend(b0, b1)
    alpha3 = np.where(use_three_colour, 0, 255)

    codes = np.empty((n, 4, 4), dtype=np.uint8)
    codes[:, 0, 0] = r0
    codes[:, 0, 1] = g0
    codes[:, 0, 2] = b0
    codes[:, 0, 3] = 255
    codes[:, 1, 0] = r1
    codes[:, 1, 1] = g1
    codes[:, 1, 2] = b1
    codes[:, 1, 3] = 255
    codes[:, 2, 0] = r2
    codes[:, 2, 1] = g2
    codes[:, 2, 2] = b2
    codes[:, 2, 3] = 255
    codes[:, 3, 0] = r3
    codes[:, 3, 1] = g3
    codes[:, 3, 2] = b3
    codes[:, 3, 3] = alpha3

    index_bytes = colour_bytes[:, 4:8]  # (N, 4), one byte per pixel row
    indices = np.empty((n, 16), dtype=np.uint8)
    for row in range(4):
        packed = index_bytes[:, row]
        indices[:, 4 * row + 0] = packed & 0x3
        indices[:, 4 * row + 1] = (packed >> 2) & 0x3
        indices[:, 4 * row + 2] = (packed >> 4) & 0x3
        indices[:, 4 * row + 3] = (packed >> 6) & 0x3

    return codes, indices


def _decompress_alpha_dxt3_np(alpha_bytes):
    """``alpha_bytes``: ``(N, 8)`` uint8 -> ``(N, 16)`` uint8 alpha values."""
    lo = alpha_bytes & 0x0F
    hi = alpha_bytes & 0xF0
    even = lo | (lo << 4)
    odd = hi | (hi >> 4)
    n = alpha_bytes.shape[0]
    alpha = np.empty((n, 16), dtype=np.uint8)
    alpha[:, 0::2] = even
    alpha[:, 1::2] = odd
    return alpha


def _decompress_alpha_dxt5_np(alpha_bytes):
    """``alpha_bytes``: ``(N, 8)`` uint8 -> ``(N, 16)`` uint8 alpha values."""
    n = alpha_bytes.shape[0]
    alpha0 = alpha_bytes[:, 0].astype(np.int32)
    alpha1 = alpha_bytes[:, 1].astype(np.int32)
    cond = alpha0 <= alpha1

    codes = np.empty((n, 8), dtype=np.uint8)
    codes[:, 0] = alpha0
    codes[:, 1] = alpha1
    for k in range(2, 6):
        five_step = ((6 - k) * alpha0 + (k - 1) * alpha1) // 5
        seven_step = ((8 - k) * alpha0 + (k - 1) * alpha1) // 7
        codes[:, k] = np.where(cond, five_step, seven_step)
    seven_step_6 = ((8 - 6) * alpha0 + 5 * alpha1) // 7
    seven_step_7 = ((8 - 7) * alpha0 + 6 * alpha1) // 7
    codes[:, 6] = np.where(cond, 0, seven_step_6)
    codes[:, 7] = np.where(cond, 255, seven_step_7)

    indices = np.empty((n, 16), dtype=np.uint8)
    for half in range(2):
        chunk = alpha_bytes[:, 2 + 3 * half : 5 + 3 * half].astype(np.uint32)
        value = chunk[:, 0] | (chunk[:, 1] << 8) | (chunk[:, 2] << 16)
        for j in range(8):
            indices[:, 8 * half + j] = (value >> (3 * j)) & 0x7

    row_index = np.arange(n)[:, None]
    return codes[row_index, indices]


def _decompress_image_numpy(
    blocks: bytes, width: int, height: int, flags: SquishOptions
) -> bytearray:
    is_dxt1 = bool(flags & SquishOptions.DXT1)
    is_dxt3 = bool(flags & SquishOptions.DXT3)
    is_dxt5 = bool(flags & SquishOptions.DXT5)
    bytes_per_block = 8 if is_dxt1 else 16

    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    num_blocks = blocks_x * blocks_y

    raw = np.frombuffer(blocks, dtype=np.uint8, count=num_blocks * bytes_per_block)
    raw = raw.reshape(num_blocks, bytes_per_block)

    colour_bytes = raw[:, 8:16] if (is_dxt3 or is_dxt5) else raw[:, 0:8]
    codes, indices = _decompress_colour_np(colour_bytes, is_dxt1)

    row_index = np.arange(num_blocks)[:, None]
    rgba = codes[row_index, indices]  # (num_blocks, 16, 4)

    if is_dxt3:
        rgba[:, :, 3] = _decompress_alpha_dxt3_np(raw[:, 0:8])
    elif is_dxt5:
        rgba[:, :, 3] = _decompress_alpha_dxt5_np(raw[:, 0:8])

    # Reassemble blocks (row-major, each block row-major) into a full,
    # 4-aligned image, then crop and swap RGBA -> BGRA.
    padded = rgba.reshape(blocks_y, blocks_x, 4, 4, 4)
    padded = padded.transpose(0, 2, 1, 3, 4).reshape(blocks_y * 4, blocks_x * 4, 4)
    cropped = padded[:height, :width, :]
    bgra = cropped[:, :, [2, 1, 0, 3]]
    return bytearray(np.ascontiguousarray(bgra).tobytes())


def decompress_image(blocks: bytes, width: int, height: int, flags: SquishOptions) -> bytearray:
    """Decompress a DXT-compressed image into a BGRA byte buffer.

    Uses a vectorised numpy implementation when numpy is installed (fast
    enough for bulk exports); otherwise falls back to a pure-Python,
    per-pixel reference implementation.
    """
    if np is not None:
        return _decompress_image_numpy(blocks, width, height, flags)
    return _decompress_image_python(blocks, width, height, flags)
