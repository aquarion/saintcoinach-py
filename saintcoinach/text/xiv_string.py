"""Decoder for the game's rich-text string format.

The game stores strings as UTF-8 text interspersed with binary "tags" (colour
changes, auto-translate references, conditional text, ...).  A full evaluator
is a large subsystem; this port decodes the literal UTF-8 runs and structurally
skips tags, which yields the correct plain text for the overwhelming majority
of entries -- matching the "good string for most queries" behaviour noted in
the original project's README.
"""

from __future__ import annotations

__all__ = ["decode"]

_TAG_START = 0x02
_TAG_END = 0x03


def _read_integer(data: bytes, pos: int) -> tuple[int, int]:
    """Read a tag-length integer, returning (value, new_pos)."""
    t = data[pos]
    pos += 1
    if t < 0xF0:
        return t - 1, pos
    if t == 0xF0:  # Byte
        return data[pos], pos + 1
    if t == 0xF1:  # ByteTimes256
        return data[pos] * 256, pos + 1
    if t == 0xF2:  # Int16
        return (data[pos] << 8) | data[pos + 1], pos + 2
    if t == 0xFA:  # Int24
        return (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2], pos + 3
    if t == 0xFE:  # Int32
        return (
            (data[pos] << 24) | (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3],
            pos + 4,
        )
    # Unknown marker; treat as a raw byte value.
    return t, pos


def decode(data: bytes) -> str:
    """Decode a binary game string to plain text, skipping tags."""
    parts: list[str] = []
    pending = bytearray()
    pos = 0
    length = len(data)

    while pos < length:
        v = data[pos]
        if v == _TAG_START:
            if pending:
                parts.append(pending.decode("utf-8", errors="replace"))
                pending.clear()
            pos += 1
            # tag type byte
            pos += 1
            tag_len, pos = _read_integer(data, pos)
            pos += tag_len  # skip the tag arguments
            if pos < length and data[pos] == _TAG_END:
                pos += 1
        else:
            pending.append(v)
            pos += 1

    if pending:
        parts.append(pending.decode("utf-8", errors="replace"))
    return "".join(parts)
