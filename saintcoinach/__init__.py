"""SaintCoinach - Python port of the FFXIV data extraction library.

This port covers the data-reading pipeline of the original .NET library:
SqPack extraction, EXH/EXD sheet parsing, game-string decoding and texture
(``*.tex``) decoding to PNG.  The WPF/DirectX 3D viewer is intentionally out of
scope.
"""

from __future__ import annotations

from .ex.language import Language
from .realm import GameData

__all__ = ["GameData", "Language"]

__version__ = "0.1.0"
