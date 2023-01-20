import asyncio
from typing import Callable, Any

from web_foundation.kernel.messaging.channel import GenericIMessage
from web_foundation.extentions.realtime.connection import RtEventCallback, RtConnection


class RtBroadcaster:
    """
    Broadcast messages to sse connections of one worker
    """
    rt_connections: list

    def __init__(self):
        self.rt_connections = []

    async def broadcast(self, message: GenericIMessage, resolve_callback: RtEventCallback = None):
        await asyncio.gather(*[
            conn.send_after_call(message)
            for conn in self.rt_connections if
            conn.resolve_callback.__name__ == resolve_callback.__name__
        ])

    async def accept_rt_connection(self, conn: RtConnection,
                                   on_disconnect_callback: Callable[[RtConnection], Any] | None = None):
        self.rt_connections.append(conn)

        async def _on_rt_close():
            nonlocal self
            nonlocal conn
            nonlocal on_disconnect_callback
            self.rt_connections.remove(conn)
            if on_disconnect_callback:
                await on_disconnect_callback(self, conn)

        await conn.freeze_request(_on_rt_close)
