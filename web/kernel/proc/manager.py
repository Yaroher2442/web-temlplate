import multiprocessing
from multiprocessing import Manager
from typing import List, Coroutine, Any, Dict

import loguru

from web import settings
from web.kernel.proc.isolate import Isolate
from web.kernel.types import EnvAble, cheat, ConfAble


class ProcManager(EnvAble, ConfAble):
    _worker_num: int
    _isolates: Dict[str, Isolate]
    _manager: Manager

    def __init__(self):
        self._manager = Manager()
        self._worker_num = 0
        self._isolates = {}

    def perform(self) -> list[Coroutine[Any, Any, Any] | Coroutine[Any, Any, None]]:
        return [self.run()]

    def _add_isolate(self, isolate: Isolate, run: bool = False):
        self._isolates.update({isolate.name: isolate})
        cheat(isolate, EnvAble, self.env)
        if run:
            ctx = multiprocessing.get_context("fork")
            isolate.fork(ctx)
        if settings.DEBUG:
            loguru.logger.debug(f"[{self}] Add isolate {isolate.name}")

    def add_isolate_list(self, isolates: List[Isolate], run: bool = False):
        for i in isolates:
            self._add_isolate(i, run)

    def add_isolate(self, isolate: Isolate, run: bool = False):
        self._add_isolate(isolate, run)

    def remove_isolate(self, name: str):
        self._isolates.pop(name)

    async def run(self):
        with self._manager as manager:
            ctx = multiprocessing.get_context("fork")
            for isolate in self._isolates.values():
                if not isolate.process:
                    isolate.fork(ctx)

    def stop(self):
        for i in self._isolates.values():
            i.process.terminate()

    @property
    def isolates(self):
        return self._isolates

    def __repr__(self):
        return f"{self.__class__.__name__}"
