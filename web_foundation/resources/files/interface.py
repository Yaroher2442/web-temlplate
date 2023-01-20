from abc import ABCMeta
from typing import Any, Generic, TypeVar

class FilesResourceInterface(metaclass=ABCMeta):
    root: Any

    async def open(self, path: Any, *args, **kwargs) -> Any:
        raise NotImplementedError

    async def remove(self, path: Any, recursive: bool = False, *args, **kwargs):
        raise NotImplementedError

    async def rename(self, path: Any, new_name: str, *args, **kwargs):
        raise NotImplementedError

    async def replace(self, path: Any, new_path: str, *args, **kwargs):
        raise NotImplementedError

    async def mkdir(self, path: Any, *args, **kwargs):
        raise NotImplementedError

    async def makedirs(self, path: Any, *args, **kwargs):
        raise NotImplementedError

    async def list(self, path: Any, *args, **kwargs):
        raise NotImplementedError

    async def exists(self, path: Any) -> bool:
        raise NotImplementedError
