from __future__ import annotations

from multiprocessing.context import BaseContext
from typing import Dict, Any
from sanic.worker.manager import Worker, WorkerProcess
from sanic.worker.process import ProcessState


class ExtWorkerProcess(WorkerProcess):
    daemon: bool

    def __init__(self, factory, name, target, kwargs, worker_state, daemon=True):
        self.daemon = daemon
        super().__init__(factory, name, target, kwargs, worker_state)

    def spawn(self):
        if self.state is not ProcessState.IDLE:
            raise Exception("Cannot spawn a worker process until it is idle.")
        self._process = self.factory(
            name=self.name,
            target=self.target,
            kwargs=self.kwargs,
            daemon=self.daemon,
        )


class ExtWorker(Worker):
    def __init__(self, ident: str, serve, server_settings, context: BaseContext, worker_state: Dict[str, Any],
                 daemon=True):
        self.daemon = daemon
        super().__init__(ident, serve, server_settings, context, worker_state)

    def create_process(self) -> WorkerProcess:
        process = ExtWorkerProcess(
            factory=self.context.Process,
            name=f"Sanic-{self.ident}-{len(self.processes)}",
            target=self.serve,
            kwargs={**self.server_settings},
            worker_state=self.worker_state,
            daemon=self.daemon
        )
        self.processes.add(process)
        return process
