from __future__ import annotations
from __future__ import annotations

import asyncio
import datetime
import uuid
from dataclasses import dataclass, field
from datetime import timezone
from typing import Callable, Coroutine, Any, List
from typing import Dict

import loguru

from web import settings
from web.kernel.messaging.dispatcher import IDispatcher
from web.kernel.proc.isolate import Isolate
from web.kernel.proc.manager import ProcManager
from web.kernel.types import IScheduler, EnvAble, ISOLATE_EXEC, TaskEvent

if settings.SCHEDULER_ENABLE:
    from apscheduler.events import EVENT_JOB_SUBMITTED, JobSubmissionEvent, EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
    from apscheduler.events import JobExecutionEvent
    from apscheduler.executors.asyncio import AsyncIOExecutor
    from apscheduler.executors.base import BaseExecutor
    from apscheduler.schedulers.base import BaseScheduler
    from apscheduler.jobstores.memory import MemoryJobStore
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger


@dataclass
class Task:
    id: str
    status: str
    trigger_event: TaskEvent
    call_time: datetime.datetime | None = field(default=None)
    done_time: datetime.datetime | None = field(default=None)
    execution_time: datetime.timedelta | None = field(default=None)

    error: BaseException | None = field(default=None)
    create_time: datetime.datetime | None = field(default_factory=datetime.datetime.now)

    call_counter: int = field(default=0)

    on_error_callback: TaskErrorCallback = field(default=None)
    on_complete_callback: TaskCompleteCallback = field(default=None)

    def __eq__(self, other: Task):
        if self.trigger_event.target.__name__ == other.trigger_event.target.__name__:
            return True
        return False

    def __repr__(self):
        return self.trigger_event.target.__name__


TaskErrorCallback = Callable[[JobExecutionEvent, Task], Coroutine[Any, Any, None]]
TaskCompleteCallback = Callable[[JobExecutionEvent, Task], Coroutine[Any, Any, None]]


class BackGroundIsolate(Isolate):
    def __init__(self, name: str, *args, coro_stop_condition: str = asyncio.FIRST_EXCEPTION, **kwargs):
        super().__init__(name, *args, coro_stop_condition=coro_stop_condition, **kwargs)

    def forked(self, *args, **kwargs) -> None:
        try:
            asyncio.run(self.env.shutdown())
        except Exception:
            pass
        super().forked(*args, **kwargs)

    async def work(self, *args, **kwargs) -> None:
        await args[0](self.env, *args[1:], **kwargs)


class Scheduler(IScheduler, EnvAble):
    _tasks_info: Dict[str, Task]
    _scheduler: BaseScheduler
    _executors: Dict[str, BaseExecutor]
    manager: ProcManager | None
    dispatcher: IDispatcher | None

    def __init__(self, scheduler: BaseScheduler = None):
        self.manager = None
        self.dispatcher = None
        self._tasks_info = {}
        self._scheduler = scheduler if scheduler else self._default_scheduler()

    def _default_scheduler(self) -> AsyncIOScheduler:
        scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()},
                                     executors={
                                         'default': AsyncIOExecutor(),
                                     },
                                     job_defaults={
                                         "misfire_grace_time": 1,
                                         'coalesce': False,
                                         'max_instances': 10
                                     },
                                     timezone=timezone.utc)

        def _on_job_submitted(event: JobSubmissionEvent):
            nonlocal self
            task = self._tasks_info.get(event.job_id)
            task.call_time = datetime.datetime.now().astimezone()
            task.status = "called"

        def _on_job_exec(event: JobExecutionEvent):  # todo remove done jobs? YAROHA: NO, NEED TO STATISTICS
            task = self._tasks_info.get(event.job_id)
            task.done_time = datetime.datetime.now().astimezone()
            task.execution_time = task.done_time - task.call_time
            task.status = "done"
            if event.exception:
                task.error = event.exception
                task.status = 'error'
                if settings.DEBUG:
                    loguru.logger.error(
                        f"[Scheduler::Task::{task.id}] Job Errored in {task.execution_time} with {event.exception}")
                if task.on_error_callback:
                    asyncio.create_task(task.on_error_callback(event, task))
                # self.manager.remove_isolate(task.name)
            else:
                if settings.DEBUG:
                    loguru.logger.success(f"[Scheduler::Task::{task.id}] Job {task} executed in {task.execution_time}")
                if task.on_complete_callback:
                    asyncio.create_task(task.on_complete_callback(event, task))
            asyncio.create_task(
                self.env.channel.produce(task.trigger_event.reply(event.retval, event.exception)))

        scheduler.add_listener(_on_job_submitted, EVENT_JOB_SUBMITTED)
        scheduler.add_listener(_on_job_exec, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        return scheduler

    async def add_task(self, message: TaskEvent):
        arc_task = Task(id=str(uuid.uuid4()),
                        status="new",
                        trigger_event=message)

        if message.exec_type == ISOLATE_EXEC:
            if not self.manager:
                raise ValueError("manager not set, process call unavailable")

            async def run_in_process(*args, **kwargs):
                isolate = BackGroundIsolate(arc_task.id,
                                            *args,
                                            coro_stop_condition=asyncio.FIRST_COMPLETED,
                                            **kwargs)
                isolate.channel = self.env.channel
                self.dispatcher.set_channel(isolate)
                self.manager.add_isolate(isolate, run=True)
                while isolate.process.is_alive():
                    await asyncio.sleep(0.1)
                isolate.process.terminate()
                self.manager.remove_isolate(isolate.name)
                return

            message.args = (message.target, *message.args)
            run_in_process.__name__ = message.target.__name__
            message.target = run_in_process
        else:
            message.args = (self.env, *message.args)
        if isinstance(message.trigger, IntervalTrigger):
            for task in self._tasks_info.values():
                if task == arc_task:
                    task.trigger_event = message
                    job = self._scheduler.get_job(task.id)
                    job.func = message.target
                    job.trigger = message.trigger
                    job.args = message.args
                    job.kwargs = message.kwargs
                    return

        job = self._scheduler.add_job(message.target,
                                      id=arc_task.id,
                                      name=arc_task.id,
                                      trigger=message.trigger,
                                      args=message.args,
                                      kwargs=message.kwargs)
        if settings.DEBUG:
            loguru.logger.debug(f"[Scheduler::Task::{arc_task.id}] Job {arc_task} queued")
        self._tasks_info.update({job.id: arc_task})

    def stop(self, *args, **kwargs):
        self._scheduler.shutdown()

    async def run(self):
        self._scheduler.start()

    def perform(self) -> List[Coroutine[Any, Any, Any] | Coroutine[Any, Any, None]]:
        self._scheduler.start()

        async def call():
            self._scheduler.start()

        return [call()]
