import asyncio
import signal
from abc import ABCMeta
from asyncio import CancelledError
from typing import Dict, Generic

import loguru
from sanic import Sanic
from sanic.worker.multiplexer import WorkerMultiplexer

from web_foundation.extentions.sanic_ext_worker import ExtWorker
from web_foundation.kernel.container import GenericDependencyContainer
from web_foundation.kernel.messaging.channel import IChannel


class Isolate(Generic[GenericDependencyContainer], metaclass=ABCMeta):
    name: str
    channel: IChannel | None
    container: GenericDependencyContainer
    init_kwargs: Dict

    def __init__(self, name: str, container: GenericDependencyContainer, **kwargs):
        self.name = name
        self.container = container
        self.channel = IChannel(f"Channel_{name}")
        self.init_kwargs = kwargs

    async def work(self, **kwargs) -> None:
        raise NotImplementedError

    def run_forked(self) -> None:
        async def call():
            try:
                nonlocal self
                await self.container.init_resources(self.channel)
                asyncio.create_task(self.channel.listen_consume())
                await self.work(**self.init_kwargs)
                await self.container.shutdown_resources()
            except CancelledError:
                await self.container.shutdown_resources()
                self.close()

        def signal_handler(sig, frame):
            for task in asyncio.all_tasks():
                task.cancel()

        signal.signal(signal.SIGINT, signal_handler)

        try:
            asyncio.run(call())
        except KeyboardInterrupt:
            asyncio.run(self.container.shutdown_resources())
            self.close()

    def close(self):
        pass
