"""SqPack containers and lookup by path.

Port of ``SaintCoinach.IO.Pack``, ``PackCollection`` and ``Directory``.
"""

from __future__ import annotations

import os

from .. import crc
from .file import SqPackFile, read_file
from .index import Index
from .pack_identifier import PackIdentifier

__all__ = ["Pack", "PackCollection", "Directory"]

_INDEX_FILE_FORMAT = "{0:02x}{1:02x}{2:02x}.win32.index"
_DAT_FILE_FORMAT = "{0:02x}{1:02x}{2:02x}.win32.dat{3}"


class Directory:
    """A directory inside a SqPack, resolving file names to :class:`SqPackFile`."""

    def __init__(self, pack: "Pack", index_directory):
        self.pack = pack
        self.index = index_directory
        self.path: str | None = None
        self._files: dict[int, SqPackFile] = {}

    def file_exists(self, name: str) -> bool:
        return crc.compute(name) in self.index.files

    def get_file(self, name: str) -> SqPackFile:
        file = self._get_file_by_key(crc.compute(name))
        if file is None:
            raise FileNotFoundError(f"Pack file not found '{name}'")
        if self.path is not None:
            file.path = f"{self.path}/{name}"
        return file

    def try_get_file(self, name: str) -> SqPackFile | None:
        file = self._get_file_by_key(crc.compute(name))
        if file is not None and self.path is not None:
            file.path = f"{self.path}/{name}"
        return file

    def _get_file_by_key(self, key: int) -> SqPackFile | None:
        if key in self._files:
            return self._files[key]
        index_file = self.index.files.get(key)
        if index_file is None:
            return None
        file = read_file(self.pack, index_file)
        self._files[key] = file
        return file


class Pack:
    """A single SqPack (one ``*.index`` plus its ``*.dat*`` files)."""

    def __init__(self, data_directory: str, id: PackIdentifier, collection: "PackCollection | None" = None):
        self.data_directory = data_directory
        self.id = id
        self.collection = collection
        self._streams: dict[int, object] = {}
        self._directories: dict[int, Directory] = {}

        index_name = _INDEX_FILE_FORMAT.format(id.type_key, id.expansion_key, id.number)
        index_path = os.path.join(data_directory, id.expansion, index_name)
        if not os.path.exists(index_path):
            raise FileNotFoundError(index_path)
        self.index = Index(id, index_path)

    def get_data_stream(self, dat_file: int = 0):
        stream = self._streams.get(dat_file)
        if stream is None:
            name = _DAT_FILE_FORMAT.format(self.id.type_key, self.id.expansion_key, self.id.number, dat_file)
            path = os.path.join(self.data_directory, self.id.expansion, name)
            stream = open(path, "rb")
            self._streams[dat_file] = stream
        return stream

    def close(self) -> None:
        for stream in self._streams.values():
            stream.close()
        self._streams.clear()

    # -- lookup ---------------------------------------------------------------

    def _get_directory(self, path: str) -> Directory | None:
        key = crc.compute(path)
        directory = self._directories.get(key)
        if directory is None:
            index_dir = self.index.directories.get(key)
            if index_dir is None:
                return None
            directory = Directory(self, index_dir)
            self._directories[key] = directory
        directory.path = path
        return directory

    def file_exists(self, path: str) -> bool:
        dir_path, _, base = path.rpartition("/")
        if not _:
            raise ValueError(path)
        directory = self._get_directory(dir_path)
        return directory is not None and directory.file_exists(base)

    def get_file(self, path: str) -> SqPackFile:
        dir_path, sep, base = path.rpartition("/")
        if not sep:
            raise ValueError(path)
        directory = self._get_directory(dir_path)
        if directory is None:
            raise FileNotFoundError(path)
        return directory.get_file(base)

    def try_get_file(self, path: str) -> SqPackFile | None:
        dir_path, sep, base = path.rpartition("/")
        if not sep:
            return None
        directory = self._get_directory(dir_path)
        if directory is None:
            return None
        return directory.try_get_file(base)


class PackCollection:
    """The set of SqPacks under a game's ``sqpack`` data directory."""

    def __init__(self, data_directory: str):
        if not os.path.isdir(data_directory):
            raise NotADirectoryError(data_directory)
        self.data_directory = data_directory
        self._packs: dict[PackIdentifier, Pack] = {}

    def get_pack(self, id: PackIdentifier) -> Pack:
        pack = self._packs.get(id)
        if pack is None:
            pack = Pack(self.data_directory, id, self)
            self._packs[id] = pack
        return pack

    def try_get_pack(self, path: str) -> Pack | None:
        id = PackIdentifier.try_get(path)
        if id is None:
            return None
        try:
            return self.get_pack(id)
        except FileNotFoundError:
            return None

    def get_file(self, path: str) -> SqPackFile:
        id = PackIdentifier.get(path)
        return self.get_pack(id).get_file(path)

    def try_get_file(self, path: str) -> SqPackFile | None:
        pack = self.try_get_pack(path)
        if pack is None:
            return None
        return pack.try_get_file(path)

    def file_exists(self, path: str) -> bool:
        pack = self.try_get_pack(path)
        return pack is not None and pack.file_exists(path)

    def close(self) -> None:
        for pack in self._packs.values():
            pack.close()
