import asyncio
import os
from abc import ABCMeta
from multiprocessing.context import BaseContext
from multiprocessing.process import BaseProcess
from signal import SIGINT, SIGTERM
from typing import Dict, Any, Coroutine, Tuple

import loguru

from web import settings
from web.kernel.types import ChanAble, cheat, EnvAble, SharedStateAble, SharedState, ConfAble


class Isolate(ChanAble, EnvAble, SharedStateAble, metaclass=ABCMeta):
    name: str
    init_args: Tuple[Any]
    init_kwargs: Dict[str, Any]
    process: BaseProcess | None
    _coro_stop_condition: str

    def __init__(self, name: str, *args, coro_stop_condition: str = asyncio.FIRST_EXCEPTION, **kwargs):
        self._coro_stop_condition = coro_stop_condition
        self.name = name
        self.init_args = args
        self.init_kwargs = kwargs
        self.process = None

    async def work(self, *args, **kwargs) -> None:
        raise NotImplementedError

    def fork(self, ctx: BaseContext, *args, daemon: bool = True, **kwargs):
        self.process = ctx.Process(target=self.forked, args=args, daemon=daemon, **kwargs)
        self.process.start()
        return self.process

    async def stop(self, ex: Exception = None):
        await self.env.shutdown()
        if settings.DEBUG:
            if ex:
                loguru.logger.exception(ex)
            else:
                loguru.logger.debug(
                    f"{self.name}::Isolate(pid={os.getgid()}) Received terminate signal. Shutting down.")
        exit(0)

    def forked(self, *args, **kwargs) -> None:
        try:

            async def _start():
                loop = asyncio.get_event_loop()
                loop.add_signal_handler(SIGINT, lambda: asyncio.create_task(self.stop()))
                loop.add_signal_handler(SIGTERM, lambda: asyncio.create_task(self.stop()))
                done_tasks, pending_tasks = await asyncio.wait(self.perform(), return_when=self._coro_stop_condition)
                for task in done_tasks:
                    if ex := task.exception():
                        loguru.logger.error(f"[{self.name}::Exception]  {ex}")
                        raise ex

            self.shared_state = SharedState(self.channel, forked=True)
            cheat(self, ChanAble, self.channel)
            cheat(self, SharedStateAble, self.shared_state)
            cheat(self, ConfAble, self.env.conf)
            asyncio.run(self.env.init())
            asyncio.run(_start())
        except Exception as e:
            loguru.logger.exception(e)
            exit(-1)

    def perform(self) -> list[Coroutine[Any, Any, Any] | Coroutine[Any, Any, None]]:
        return [
            self.channel.listen_consume(),
            self.work(*self.init_args, **self.init_kwargs)
        ]

    def __repr__(self):
        return f"{self.name}::Isolate"
