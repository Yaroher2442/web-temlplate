from dataclasses import dataclass, field

import loguru
from sanic.server.websockets.impl import WebsocketImplProtocol

from web.kernel.types import RtMessage, RtWriter, RtReadCallback


@dataclass
class WsRtMessage(RtMessage):
    msg: str = field(default="")

    def prepare(self, *args, **kwargs) -> str | bytes:
        return self.msg

    @classmethod
    def ping_message(cls):
        return ""


class WsWriter(RtWriter[WsRtMessage]):
    read_callback: RtReadCallback
    obj: WebsocketImplProtocol

    def __init__(self, obj: WebsocketImplProtocol, read_callback: RtReadCallback = None):
        super().__init__(obj)
        self.read_callback = read_callback

    async def write(self, message: str) -> None:
        await self.obj.send(message)

    async def freeze(self, ping_enable: bool = False, ping_timeout: int = 5):
        if self.read_callback:
            async for msg in self.obj:
                await self.read_callback(self, msg)

    async def close(self, code: int = 1000, reason: str = ""):
        await self.obj.close(code=code, reason=reason)
