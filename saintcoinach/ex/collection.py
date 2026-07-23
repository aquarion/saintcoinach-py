"""The collection of all EX sheets in a game installation.

Port of ``SaintCoinach.Ex.ExCollection``.
"""

from __future__ import annotations

import io as _io

from .header import Header
from .language import Language
from .sheet import DataSheet, MultiSheet

__all__ = ["ExCollection"]


class ExCollection:
    def __init__(self, packs):
        self.packs = packs
        self.active_language = Language.ENGLISH
        self._sheet_identifiers: dict[int, str] = {}
        self._available_sheets: set[str] = set()
        self._headers: dict[str, Header] = {}
        self._sheets: dict[str, object] = {}
        self._build_index()

    def _build_index(self) -> None:
        root = self.packs.get_file("exd/root.exl")
        text = root.get_data().decode("ascii", errors="replace")
        reader = _io.StringIO(text)
        reader.readline()  # EXLT,<version>
        for line in reader:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 2:
                continue
            name, id_str = parts
            self._available_sheets.add(name)
            try:
                id_value = int(id_str)
            except ValueError:
                continue
            if id_value >= 0:
                self._sheet_identifiers[id_value] = name

    @property
    def available_sheets(self) -> set[str]:
        return self._available_sheets

    def sheet_exists(self, name: str) -> bool:
        return name in self._available_sheets

    def fix_name(self, name: str) -> str:
        for candidate in self._available_sheets:
            if candidate.lower() == name.lower():
                return candidate
        return name

    def get_header(self, name: str) -> Header:
        header = self._headers.get(name)
        if header is None:
            exh = self.packs.get_file(f"exd/{name}.exh")
            header = Header(self, name, exh)
            self._headers[name] = header
        return header

    def get_sheet(self, name: str):
        if name in self._sheets:
            return self._sheets[name]
        if name not in self._available_sheets:
            raise KeyError(f"Unknown sheet '{name}'")

        header = self.get_header(name)
        if header.available_languages_count >= 1:
            sheet: object = MultiSheet(self, header)
        else:
            language = header.available_languages[0]
            sheet = DataSheet(self, header, language)
        self._sheets[name] = sheet
        return sheet
