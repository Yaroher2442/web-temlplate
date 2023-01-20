from typing import Any, TypeVar, Generic

from web_foundation.config import AppConf
from web_foundation.kernel.messaging.channel import IChannel
from web_foundation.kernel.stage import ListenerRegistrator

GenericCommunicator = TypeVar("GenericCommunicator")


class Resource(Generic[GenericCommunicator]):
    _communicator: GenericCommunicator | None
    _channel: IChannel | None
    _inited: bool
    _config: AppConf

    def __init__(self, *args, **kwargs):
        self._inited = False

    async def init(self, config: AppConf, channel: IChannel | None = None,
                   communicator: GenericCommunicator | None = None, *args,
                   **kwargs) -> None:
        self._config = config
        self._channel = channel
        self._inited = True
        self._communicator = communicator

    async def shutdown(self):
        raise NotImplementedError

    def clear(self):
        self._inited = False
        self._communicator = None
        self._channel = None

    def set_listeners(self, registrator: ListenerRegistrator):
        pass

    @property
    def ready(self):
        return self._inited

    @property
    def channel(self):
        if not self._inited:
            raise RuntimeError("Resource not inited")
        return self._channel

    @property
    def communicator(self):
        if not self._inited:
            raise RuntimeError("Resource not inited. Can't access to communicator")
        return self._communicator
