from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from typing import Any
from typing import Dict

from sanic.response import BaseHTTPResponse

from web_foundation.extentions.realtime.connection import RtMessage, WriteableObj, RtConnection,RtEventCallback
from web_foundation.extentions.request_handler import InputContext


@dataclass
class SseRtMessage(RtMessage):
    _SEPARATOR = "\r\n"
    event_name: str = field(default="")
    data: Dict | None = field(default=None)
    retry: int | None = field(default=None)

    def _prepare(self, *args, **kwargs) -> str | bytes:
        buffer = io.StringIO()
        buffer.write('event: ' + self.event_name + self._SEPARATOR)
        if self.event_id:
            buffer.write('id: ' + str(self.event_id) + self._SEPARATOR)
        if self.retry:
            buffer.write('retry: ' + str(self.retry) + self._SEPARATOR)
        else:
            buffer.write("retry: " + "0" + self._SEPARATOR)
        if self.data:
            buffer.write('data: ' + json.dumps(self.data))
        else:
            buffer.write('data: {}')
        buffer.write("\r\n\r\n")
        return buffer.getvalue()

    @classmethod
    def ping_message(cls):
        return cls(event_id="0", event_name="ping").to_sent


class WriteableSse(WriteableObj):
    obj: BaseHTTPResponse

    def __init__(self, obj: BaseHTTPResponse):
        super().__init__(obj)

    async def write(self, message: Any) -> None:
        await self.obj.send(message)


class SseRtConnection(RtConnection):
    writeable: WriteableSse

    def _ping_msg(self) -> str | bytes:
        return SseRtMessage.ping_message()

    @classmethod
    async def accept_connection(cls, input_ctx: InputContext,
                                resolve_callback: RtEventCallback = None,
                                headers=None,
                                ping_enable: bool = True, ping_timeout=None,
                                listen_timeout=None):
        async with cls(
                input_ctx=input_ctx,
                writeable=await cls._construct_writable(input_ctx, headers=headers),
                resolve_callback=resolve_callback,
                ping_enable=ping_enable,
                ping_timeout=ping_timeout,
                listen_timeout=listen_timeout
        ) as connection:
            await input_ctx.request.app.ctx.rt_broadcaster.accept_rt_connection(
                conn=connection
            )

    @classmethod
    async def _construct_writable(cls, input_ctx: InputContext, headers=None, *args, **kwargs) -> WriteableSse:
        if not headers:
            headers = {}
        headers.update({"X-Accel-Buffering": "no"})
        _response = await input_ctx.request.respond(content_type="text/event-stream; charset=utf-8",
                                                    headers=headers)
        return WriteableSse(_response)

    def _close_condition(self) -> bool:
        if not self.writeable.obj.stream:
            return True
        else:
            return False
