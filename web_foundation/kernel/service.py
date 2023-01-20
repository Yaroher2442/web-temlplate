from typing import TypeVar, Dict, Generic

from apscheduler.triggers.base import BaseTrigger

from web_foundation.extentions.schedulle.scheduller import TaskIMessage, BackgroundTask, TaskErrorCallback, \
    TaskCompleteCallback
from web_foundation.kernel.container import GenericDependencyContainer
from web_foundation.kernel.messaging.channel import IMessage, IChannel


class Service(Generic[GenericDependencyContainer]):
    channel: IChannel
    container: GenericDependencyContainer

    async def run_background(self, task: BackgroundTask,
                             *args,
                             trigger: BaseTrigger = None,
                             on_error_callback: TaskErrorCallback = None,
                             on_complete_callback: TaskCompleteCallback = None,
                             add_job_kw: Dict = None, return_event: bool = False, **kwargs,
                             ):
        await self.emmit_event(
            TaskIMessage(task,
                         trigger,
                         on_error_callback=on_error_callback,
                         on_complete_callback=on_complete_callback,
                         add_job_kw=add_job_kw,
                         args=args,
                         kwargs=kwargs,
                         return_event=return_event))

    async def wait_for_response(self, msg: IMessage):
        return await self.channel.produce_for_response(msg)

    async def emmit_event(self, event: IMessage):
        await self.channel.produce(event)


GenericService = TypeVar("GenericService", bound=Service)
