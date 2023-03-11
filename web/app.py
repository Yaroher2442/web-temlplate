from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from signal import Signals, signal, SIGINT, SIGTERM
from typing import List, Generic, Any, Coroutine, Type, cast

import loguru

from web import settings
from web.kernel.messaging.dispatcher import IDispatcher
from web.kernel.proc.manager import ProcManager
from web.kernel.transport import Transport, TransportIsolate
from web.kernel.types import ConfAble, GenConfig, AppNameAble, Environment, EnvAble, cheat, ISocket, SigAble, \
    IScheduler, ChanAble, SocketConf, TaskEvent, SharedState, SignalType, call_signals


class WebApp(Generic[GenConfig], ConfAble[GenConfig], SigAble, ChanAble, EnvAble):
    _transports: List[Transport]
    name: str
    _environment: Environment
    manager: ProcManager
    scheduler: IScheduler | None
    dispatcher: IDispatcher
    shared_state: SharedState | None

    def __init__(self, name: str,
                 config: GenConfig,
                 transports: List[Transport],
                 environment: Environment):
        self.scheduler = None
        self.shared_state = None
        self._environment = environment
        self._transports = transports
        self.manager = ProcManager()
        self.dispatcher = IDispatcher()
        cheat(self.manager, EnvAble, self._environment, nested=False)
        self.channel = self.dispatcher.set_channel(self, ext_name="MasterChannel", master=True)
        self.name = name
        self.conf = config

    def with_scheduler(self, scheduler: IScheduler = None) -> WebApp:
        if settings.SCHEDULER_ENABLE:
            if not self.shared_state:
                self.shared_state = SharedState(self.channel)
            from web.kernel.proc.scheduler import Scheduler
            self.scheduler = Scheduler() if not scheduler else scheduler
            if not self.scheduler.manager:
                self.scheduler.manager = self.manager
            if not self.scheduler.dispatcher:
                self.scheduler.dispatcher = self.dispatcher
            return self
        else:
            raise RuntimeError("apscheduler is not installed on your system. scheduler not enable")

    def with_shared_state(self) -> WebApp:
        self.shared_state = SharedState(self.channel)
        return self

    def _create_transport_isolates(self, workers: int | None = None) -> List[TransportIsolate]:
        isolates = []
        typed_transports: dict[Type[Transport], List[Transport]] = {}
        type_sockets: dict[Type[Transport], ISocket] = {}
        for transport in self._transports:
            if type(transport) not in typed_transports:
                typed_transports.update({type(transport): [transport]})
            else:
                typed_transports[type(transport)].append(transport)
        for typed, transport in typed_transports.items():
            conf = cast(SocketConf, transport[0].conf.socket)
            type_sockets.update({typed: ISocket(conf.host, conf.port)})

        if not workers:
            workers = 0
            for typed, transports in typed_transports.items():
                for num, transport in enumerate(transports):
                    isolate = TransportIsolate(f"{self.name}::{transport.__class__.__name__}-{num}",
                                               transport, type_sockets[typed])
                    self.dispatcher.set_channel(isolate)
                    isolates.append(isolate)
                    workers += 1
        else:
            if workers < len(typed_transports):
                raise Exception(f"Too many transports ({len(typed_transports)}) for this cpu ({workers})")
            workers_count: dict[Type[Transport], int] = {typed: 0 for typed in typed_transports.keys()}
            for typed in typed_transports.keys():
                workers_count.update({typed: 0})
            couter = 0
            from itertools import cycle
            type_cycle = cycle(typed_transports.keys())
            isolates_count: dict[Type[Transport], int] = {typed: 0 for typed in typed_transports.keys()}
            while couter != workers:
                typed = next(type_cycle)
                transports = typed_transports[typed]
                if len(transports) <= workers_count[typed]:
                    workers_count[typed] += 1
                else:
                    workers_count[typed] = 0
                transport = transports[workers_count[typed]]
                isolates_count[typed] += 1
                isolate = TransportIsolate(f"{self.name}::{transport.__class__.__name__}-{isolates_count[typed]}",
                                           transport,
                                           type_sockets[typed])
                self.dispatcher.set_channel(isolate)
                isolates.append(isolate)
                couter += 1
        self._worker_num = workers
        return isolates

    async def run(self, multiprocessing: bool = False,
                  fast: bool = False,
                  ) -> None:
        if not multiprocessing and fast:
            raise Exception("multiprocessing must be True if fast is True")

        cheat(self, AppNameAble, self.name)
        tasks: list[Coroutine[Any, Any, Any]] = []

        cheat(self, EnvAble, self._environment)

        cheat(self, ConfAble, self.conf)

        if multiprocessing:
            self.manager.add_isolate_list(self._create_transport_isolates(workers=os.cpu_count() if fast else None))
            # tasks.extend(self.manager.perform())
            await self.manager.run()

        if self.scheduler:
            self.channel.add_event_listener(TaskEvent.message_type, self.scheduler.add_task)
            # tasks.extend(self.scheduler.perform())
            await self.scheduler.run()

        # # TODO FIX:
        # if not multiprocessing:
        #     united_socket = ISocket(self._transports[0].conf.socket.host, self._transports[0].conf.socket.port)
        #     for transport in self._transports:
        #         tasks.extend(transport.perform(united_socket))

        tasks.extend(self.dispatcher.perform())
        tasks.append(self.channel.listen_consume())

        async def sig_handler():
            loguru.logger.info(
                f"{self.name} Received shutdown signal , exit")
            await call_signals(self, SignalType.AFTER_APP_STOP, app=self)
            self.scheduler.stop()
            self.manager.stop()
            exit(0)

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(SIGINT, lambda: asyncio.create_task(sig_handler()))
        loop.add_signal_handler(SIGTERM, lambda: asyncio.create_task(sig_handler()))

        await self.env.init()
        await call_signals(self, SignalType.BEFORE_APP_RUN, app=self)
        await asyncio.wait(tasks)
        await self._environment.shutdown()


#
# async def __return_metrics(self, event: MetricRequestEvent):
#     event = await self._metrics_store.on_metric_request(event)
#     await self._dispatcher.send_to_consume(event.sender, event)

def load_config(conf_path: Path, config_model: Type[GenConfig]) -> GenConfig:
    """
    Load environment config to user in
    :param conf_path:
    :param config_model: BaseModel to cast json file to pydantic
    :return: None
    """
    with open(conf_path, "r") as _json_file:
        conf = config_model(**json.loads(_json_file.read()))
        return conf
