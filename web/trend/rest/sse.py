from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass, field
from typing import Dict, Any

from sanic.response import BaseHTTPResponse

from web.kernel.types import RtWriter, RtMessage


@dataclass
class SseRtMessage(RtMessage):
    _SEPARATOR = "\r\n"
    event_name: str = field(default="")
    data: Dict | None = field(default=None)
    retry: int | None = field(default=None)

    def prepare(self, idx: int = 0, *args, **kwargs) -> str | bytes:
        buffer = io.StringIO()
        buffer.write('event: ' + self.event_name + self._SEPARATOR)
        if idx:
            buffer.write('id: ' + str(idx) + self._SEPARATOR)
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
        return cls(event_name="ping").prepare()


class SseWriter(RtWriter):
    message_class = SseRtMessage
    obj: BaseHTTPResponse
    ping_enable: bool
    ping_timeout: int

    def __init__(self, obj: BaseHTTPResponse,
                 ping_enable: bool = False,
                 ping_timeout: int = 5):
        super().__init__(obj)
        self.ping_enable = ping_enable
        self.ping_timeout = ping_timeout

    async def write(self, message: Any) -> None:
        await self.obj.send(message)
        self.last_index += 1

    async def freeze(self, ):
        while True:
            if self.ping_enable:
                await self.write(self.message_class.ping_message())
            await asyncio.sleep(self.ping_timeout)

    @staticmethod
    def content_type() -> str:
        return "text/event-stream; charset=utf-8"

    @staticmethod
    def default_headers() -> dict:
        return {"X-Accel-Buffering": "no"}
