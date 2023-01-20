from __future__ import annotations
from dataclasses import dataclass, field

import asyncio
from asyncio import Task
from typing import Generic, Any, Callable, Coroutine

from loguru import logger

from web_foundation import settings
from web_foundation.extentions.request_handler import InputContext
from web_foundation.kernel.messaging.channel import GenericIMessage


@dataclass
class RtMessage:
    event_id: str | None = field(default=None)

    def _prepare(self, *args, **kwargs) -> str | bytes:
        raise NotImplementedError

    @property
    def to_sent(self) -> str | bytes:
        return self._prepare()

    @classmethod
    def ping_message(cls):
        raise NotImplementedError


class WriteableObj:
    obj: Any

    def __init__(self, obj: Any):
        self.obj = obj

    async def write(self, message: Any) -> None:
        pass


class RtConnection(Generic[GenericIMessage]):
    ping_timeout: float
    listen_timeout: float
    writeable: WriteableObj
    input_ctx: InputContext
    _last_event_id: int
    _ping_task: Task
    ping_enable: bool
    resolve_callback: RtEventCallback
    _on_disconnect: Callable[[], Coroutine]

    def __init__(self, input_ctx: InputContext, writeable: WriteableObj,
                 resolve_callback: RtEventCallback,
                 ping_enable: bool = False,
                 ping_timeout=None,
                 listen_timeout=None):
        if not resolve_callback:
            raise AttributeError("Resolve Callback can't bee none")
        self.writeable = writeable
        self.resolve_callback = resolve_callback
        self.input_ctx = input_ctx
        self.ping_enable = ping_enable
        self.ping_timeout = ping_timeout if ping_timeout else 5
        self.listen_timeout = listen_timeout if listen_timeout else 0.1
        self._last_event_id = 0

    def _ping_msg(self) -> str | bytes:
        raise NotImplementedError

    async def _ping(self):
        while True:
            if self.ping_enable:
                await self.writeable.write(self._ping_msg())
                # if settings.DEBUG:
                #     real_ip = self.input_ctx.request.headers.get("x-real-ip")
                #     logger.debug(f"Sent ping to {real_ip if real_ip else self.input_ctx.request.ip}")
            await asyncio.sleep(self.ping_timeout)

    async def freeze_request(self, on_disconnect: Callable[[], Coroutine]):
        self._on_disconnect = on_disconnect
        await self._ping()

    async def send_after_call(self, event: GenericIMessage):
        msg = await self.resolve_callback(self, event)
        if msg:
            self._last_event_id += 1
            msg.event_id = self._last_event_id
            await self.writeable.write(msg.to_sent)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._on_disconnect()
        if settings.DEBUG:
            real_ip = self.input_ctx.request.headers.get("x-real-ip")
            logger.debug(
                f"RtConnection({self.__class__.__name__}) on {real_ip if real_ip else self.input_ctx.request.ip} disconnected, ping task canceled")

    def _close_condition(self) -> bool:
        raise NotImplementedError

    @classmethod
    async def accept_connection(cls, input_ctx: InputContext,
                                resolve_callback: RtEventCallback = None,
                                ping_enable: bool = True,
                                ping_timeout=None,
                                listen_timeout=None) -> RtConnection:
        raise NotImplementedError

    @classmethod
    async def _construct_writable(cls, input_ctx: InputContext, *args, **kwargs) -> WriteableObj:
        raise NotImplementedError

    @property
    def last_event_num(self):
        return self._last_event_id


RtEventCallback = Callable[[RtConnection, GenericIMessage], Coroutine[Any, Any, RtMessage | None]]
