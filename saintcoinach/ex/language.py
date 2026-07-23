"""Languages available in the game data.

Port of ``SaintCoinach.Ex.Language`` and its extension helpers.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["Language"]


class Language(Enum):
    NONE = ""
    JAPANESE = "ja"
    ENGLISH = "en"
    GERMAN = "de"
    FRENCH = "fr"
    CHINESE_SIMPLIFIED = "chs"
    CHINESE_TRADITIONAL = "cht"
    KOREAN = "ko"
    TRADITIONAL_CHINESE = "tc"
    UNSUPPORTED = "?"

    @property
    def code(self) -> str:
        return self.value

    @property
    def suffix(self) -> str:
        return "_" + self.value if self.value else ""

    @classmethod
    def from_code(cls, code: str) -> "Language":
        for lang in cls:
            if lang.value.lower() == code.lower():
                return lang
        return cls.UNSUPPORTED


# Numeric ids as they appear in an EXH's language table.
LANGUAGE_MAP = {
    0: Language.NONE,
    1: Language.JAPANESE,
    2: Language.ENGLISH,
    3: Language.GERMAN,
    4: Language.FRENCH,
    5: Language.CHINESE_SIMPLIFIED,
    6: Language.CHINESE_TRADITIONAL,
    7: Language.KOREAN,
    8: Language.TRADITIONAL_CHINESE,
}
