from typing import Any, Dict

from loguru import logger

from web_foundation import settings
from web_foundation.resources.resource import Resource
from web_foundation.resources.stores.interface import DataStore


class InMemoryDictStore(Resource[dict], DataStore):
    need_sync = True
    _storage: Dict

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._storage = {}

    async def _set_item(self, key: str, value: Any):
        if settings.DEBUG:
            if self._storage.get(key):
                logger.debug(f"the key ({key}) will be overwritten")
        self._storage[key] = value

    async def get_item(self, key: str) -> Any:
        ret_val = self._storage.get(key)
        if settings.DEBUG and not ret_val:
            logger.debug(f"""Can"t find key "{key}" in store""")
        return ret_val

    async def shutdown(self):
        pass

    async def size(self):
        return len(self._storage)

    async def get_all(self):
        return self._storage.items()
