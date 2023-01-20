from __future__ import annotations

import asyncio
import copy
import datetime
import os
import uuid
from dataclasses import dataclass, field
from functools import partial
from time import time_ns
from typing import Dict, Callable, Coroutine, Any, TypeVar
from web_foundation import settings
import loguru
from apscheduler.events import EVENT_JOB_SUBMITTED, JobSubmissionEvent, JobExecutionEvent, \
    EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.base import BaseExecutor
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import timezone
from web_foundation.kernel.messaging.channel import IMessage
from web_foundation.utils.helpers import is_in_base_classes

BackgroundTask = TypeVar("BackgroundTask", Callable[..., Coroutine[Any, Any, Any]], partial)


class TaskIMessage(IMessage):
    message_type = "background_task"
    task: BackgroundTask
    args: Any | None
    kwargs: Any | None
    trigger: BaseTrigger
    add_job_kw: Dict
    on_error_callback: TaskErrorCallback
    on_complete_callback: TaskCompleteCallback
    return_event: bool
    destination = "__dispatcher__"

    def __init__(self, task: BackgroundTask,
                 trigger=None,
                 args: Any = None,
                 kwargs: Any | None = None,
                 add_job_kw: Dict = None,
                 on_error_callback: TaskErrorCallback = None,
                 on_complete_callback: TaskCompleteCallback = None,
                 return_event: bool = False):
        super().__init__()
        self.task = task
        self.args = args
        self.kwargs = kwargs
        self.add_job_kw = add_job_kw if add_job_kw else {}
        self.trigger = trigger
        self.on_error_callback = on_error_callback
        self.on_complete_callback = on_complete_callback
        self.return_event = return_event


@dataclass
class Task:
    id: str
    status: str
    name: str
    scheduled_trigger: BaseTrigger
    trigger_message: TaskIMessage
    result: Any | None = field(default=None)
    scheduled_job: Job | None = field(default=None)
    on_error_callback: TaskErrorCallback = field(default=None)
    on_complete_callback: TaskCompleteCallback = field(default=None)
    next_call_time: datetime.datetime | None = field(default=None)
    execution_time: float = field(default=0)
    done_time: float = field(default=0)
    call_time: float = field(default=0)
    call_counter: int = field(default=0)
    create_time: datetime.datetime | None = field(default_factory=datetime.datetime.now)
    error: BaseException | None = field(default=None)
    return_event: bool = False
    return_task: bool = False


class TaskIMessageReturn(IMessage):
    task: Task
    message_type = "background_task_return"

    def __init__(self, task: Task):
        super().__init__()
        self.task = task
        self.destination = self.task.trigger_message.sender


TaskErrorCallback = Callable[[JobExecutionEvent, Task], Coroutine[Any, Any, None]]
TaskCompleteCallback = Callable[[JobExecutionEvent, Task], Coroutine[Any, Any, None]]
ProduceCall = Callable[[IMessage], Coroutine[Any, Any, None]]


class TaskScheduler:
    _tasks: Dict[str, Task]
    _scheduler: AsyncIOScheduler
    produce_method: ProduceCall
    state: Dict[str, Any]

    def __init__(self, executors: Dict[str, BaseExecutor] = None, job_defaults=None,
                 **kwargs):
        self._tasks = {}
        executor = {
            'default': ProcessPoolExecutor(os.cpu_count())
        }
        job_default = {
            "misfire_grace_time": 1,
            'coalesce': False,
            'max_instances': 10
        }
        self._scheduler = AsyncIOScheduler(jobstores={"default": MemoryJobStore()},
                                           executors=executors if executors else executor,
                                           job_defaults=job_defaults if job_defaults else job_default,
                                           timezone=timezone.utc)

        self._add_listeners()

    async def add_task(self, message: TaskIMessage):
        if not self._scheduler.state:
            self._scheduler.start()
        # message.task = get_callable_from_fnc(message.task)
        if isinstance(message.trigger, IntervalTrigger):
            for task_id, task in self._tasks.items():
                if task.scheduled_job.func == message.task:
                    task.trigger_message = message
                    task.scheduled_job.trigger = message.trigger
                    task.scheduled_trigger = message.trigger
                    task.scheduled_job.args = message.args
                    task.scheduled_job.kwargs = message.kwargs
                    return

        arc_task = Task(id=str(uuid.uuid4()),
                        name=message.task.__name__,
                        status="new",
                        scheduled_trigger=message.trigger,
                        on_error_callback=message.on_error_callback,
                        on_complete_callback=message.on_complete_callback,
                        return_event=message.return_event,
                        trigger_message=message)
        arc_task.scheduled_job = self._scheduler.add_job(message.task,
                                                         name=arc_task.name,
                                                         id=arc_task.id,
                                                         trigger=message.trigger,
                                                         args=message.args,
                                                         kwargs=message.kwargs,
                                                         **message.add_job_kw)
        if settings.DEBUG:
            loguru.logger.debug(f"Task scheduled {arc_task}")
        # arc_task.next_call_time = arc_task.scheduled_job.next_run_time
        self._tasks.update({arc_task.id: arc_task})

    def _add_listeners(self):
        def _on_job_submitted(event: JobSubmissionEvent):
            nonlocal self
            task = self._tasks.get(event.job_id)
            task.call_time = time_ns()
            task.call_counter += 1
            task.status = "called"

        def _on_job_exec(event: JobExecutionEvent):  # todo remove done jobs? YAROHA: NO, NEED TO STATISTICS
            nonlocal self
            task = self._tasks.get(event.job_id)
            task.done_time = time_ns()
            task.execution_time = task.done_time - task.call_time
            task.status = "done"
            task.next_call_time = task.scheduled_job.next_run_time
            task.result = event.retval
            if event.exception:
                task.error = event.exception
                task.status = 'error'
                if task.on_error_callback:
                    asyncio.create_task(task.on_error_callback(event, task))
            else:
                if task.on_complete_callback:
                    asyncio.create_task(task.on_complete_callback(event, task))
                if task.return_event:
                    if is_in_base_classes(event.retval, IMessage):
                        asyncio.create_task(self.produce_method(event.retval))
                if task.return_task:
                    ret_event = TaskIMessageReturn(task)
                    asyncio.create_task(self.produce_method(ret_event))

        self._scheduler.add_listener(_on_job_submitted, EVENT_JOB_SUBMITTED)
        self._scheduler.add_listener(_on_job_exec, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def close(self, *args, **kwargs):
        self._scheduler.shutdown()

    def perform(self):
        self._scheduler.start()
