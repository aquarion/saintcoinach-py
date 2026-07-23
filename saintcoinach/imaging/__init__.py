"""Image/texture decoding for SaintCoinach (Python port)."""

from __future__ import annotations

from ..io.pack import PackCollection
from .image_file import ImageFile, ImageFormat, convert_to_bgra

__all__ = ["ImageFile", "ImageFormat", "convert_to_bgra", "get_icon"]

_ICON_FORMAT = "ui/icon/{0:03d}000/{1}{2:06d}.tex"
_ICON_HR1_FORMAT = "ui/icon/{0:03d}000/{1}{2:06d}_hr1.tex"


def get_icon(
    packs: PackCollection, number: int, type: str = "", prefer_high_res: bool = False
) -> ImageFile | None:
    """Look up a UI icon by number, mirroring ``IconHelper.GetIcon``.

    ``type`` is an optional language sub-folder (e.g. ``"en"``); if a
    type-specific icon is missing the generic one is tried.
    """
    type = type or ""
    if type and not type.endswith("/"):
        type += "/"

    file = None
    if prefer_high_res:
        file = _get_icon_file(packs, _ICON_HR1_FORMAT, type, number)
    if file is None:
        file = _get_icon_file(packs, _ICON_FORMAT, type, number)
    return file if isinstance(file, ImageFile) else None


def _get_icon_file(packs: PackCollection, fmt: str, type: str, number: int):
    path = fmt.format(number // 1000, type, number)
    file = packs.try_get_file(path)
    if file is None and type:
        path = fmt.format(number // 1000, "", number)
        file = packs.try_get_file(path)
    return file
