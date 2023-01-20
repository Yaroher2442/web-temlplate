from abc import ABCMeta
from copy import copy
from typing import Any

from orjson import dumps, loads

from web_foundation.config import GenericConfig
from web_foundation.resources.stores.events import StoreUpdateEvent
from web_foundation.kernel.messaging.channel import IChannel
from web_foundation.resources.resource import Resource
from web_foundation.utils.types import TypeJSON


class DataStore(metaclass=ABCMeta):
    need_sync: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_store_update(self, event: StoreUpdateEvent):
        if not event.obj:
            event.value = self._load(event.value)
        await self.set_item(event.key, event.value, send_event=False)

    async def get_item(self, key: str) -> Any:
        raise NotImplementedError

    async def _set_item(self, key: str, value: TypeJSON):
        raise NotImplementedError

    async def set_item(self, key: str, value: Any, obj: bool = False, send_event: bool = True):
        await self._set_item(key, value)
        if self.need_sync and send_event:
            data = value if obj else self._serialize(value)
            await self._channel.produce(StoreUpdateEvent(key, copy(data), obj))

    async def get_all(self):
        raise NotImplementedError

    async def size(self):
        raise NotImplementedError

    async def init(self, config: GenericConfig, channel: IChannel, **kwargs):
        await super(DataStore, self).init(config, channel)
        self._channel.add_event_listener(StoreUpdateEvent, self.on_store_update)

    def _load(self, value: str):
        return loads(value)

    def _serialize(self, value: TypeJSON):
        return dumps(value)
