"""Identification of a SqPack by category/expansion/number.

Port of ``SaintCoinach.IO.PackIdentifier``.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PackIdentifier"]

DEFAULT_EXPANSION = "ffxiv"

_TYPE_TO_KEY = {
    "common": 0x00,
    "bgcommon": 0x01,
    "bg": 0x02,
    "cut": 0x03,
    "chara": 0x04,
    "shader": 0x05,
    "ui": 0x06,
    "sound": 0x07,
    "vfx": 0x08,
    # "ui_script": 0x09,  # intentionally omitted, as in the C# source
    "exd": 0x0A,
    "game_script": 0x0B,
    "music": 0x0C,
    "_sqpack_test": 0x12,
    "_debug": 0x13,
}
_KEY_TO_TYPE = {v: k for k, v in _TYPE_TO_KEY.items()}

_EXPANSION_TO_KEY = {
    "ffxiv": 0x00,
    "ex1": 0x01,
    "ex2": 0x02,
    "ex3": 0x03,
    "ex4": 0x04,
    "ex5": 0x05,
}
_KEY_TO_EXPANSION = {v: k for k, v in _EXPANSION_TO_KEY.items()}


@dataclass(frozen=True)
class PackIdentifier:
    type: str
    expansion: str
    number: int

    @property
    def type_key(self) -> int:
        return _TYPE_TO_KEY[self.type]

    @property
    def expansion_key(self) -> int:
        return _EXPANSION_TO_KEY[self.expansion]

    @classmethod
    def from_keys(cls, type_key: int, expansion_key: int, number: int) -> "PackIdentifier":
        return cls(_KEY_TO_TYPE[type_key], _KEY_TO_EXPANSION[expansion_key], number)

    @classmethod
    def try_get(cls, full_path: str) -> "PackIdentifier | None":
        type_sep = full_path.find("/")
        if type_sep <= 0:
            return None
        type_name = full_path[:type_sep]
        if type_name not in _TYPE_TO_KEY:
            return None

        exp_sep = full_path.find("/", type_sep + 1)
        expansion: str | None = None
        number = 0
        if exp_sep > type_sep:
            expansion = full_path[type_sep + 1 : exp_sep]
            number_end = full_path.find("_", exp_sep)
            if number_end - exp_sep == 3:
                try:
                    number = int(full_path[exp_sep + 1 : exp_sep + 3], 16)
                except ValueError:
                    number = 0

        if expansion is None or expansion not in _EXPANSION_TO_KEY:
            expansion = DEFAULT_EXPANSION

        return cls(type_name, expansion, number)

    @classmethod
    def get(cls, full_path: str) -> "PackIdentifier":
        value = cls.try_get(full_path)
        if value is None:
            raise ValueError(f"Cannot determine pack for path '{full_path}'")
        return value

    def __str__(self) -> str:
        return f"{self.expansion}/{self.type_key:02x}{self.expansion_key:02x}{self.number:02x}"
