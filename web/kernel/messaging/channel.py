import asyncio
from typing import Coroutine, Callable

from loguru import logger

from web import settings
from web.kernel.types import GenIMessage, IChannel, IMessage, IMessageWaiter, EventListener, GenEventsType, \
    IMessageReturn


class Channel(IChannel):
    async def produce(self, msg: IMessage | IMessageReturn, need_answer: bool = False,
                      answer_timeout: float = 0) -> IMessage | None:
        if IMessageReturn not in msg.__class__.__mro__:
            self._inner_index += 1
            msg.inner_index = self._inner_index
        msg.sender = self.name
        if msg.exec_inner:
            if listeners := self._listeners.get(msg.message_type):
                for listener in listeners:
                    asyncio.create_task(listener(msg))
        self.produce_pipe.put(msg)
        if need_answer:
            waiter = IMessageWaiter(self, msg, timeout=answer_timeout)
            self.set_waiter(waiter)
            return await waiter.wait_on()

    async def sent_to_consume(self, msg: IMessage):
        self.consume_pipe.put(msg)

    async def listen_produce(self, callback: Callable[[GenIMessage], Coroutine]):
        while True:
            while self.produce_pipe.empty():
                await asyncio.sleep(0.01)
            r: GenIMessage = self.produce_pipe.get()
            if settings.DEBUG:
                logger.debug(
                    f"[{self.name}] Send: {r.message_type}")
            await callback(r)

    async def listen_consume(self):
        while True:
            while self.consume_pipe.empty():
                await asyncio.sleep(0.01)
            r: IMessage = self.consume_pipe.get()
            if settings.DEBUG:
                logger.debug(
                    f"[{self.name}] Receive: {r.message_type}")
            self.answer_to_waiters(r)
            callbacks = self._listeners.get(r.message_type)
            if not callbacks:
                continue
            for callback in callbacks:
                asyncio.create_task(callback(r))

    def add_event_listener(self, event_type: GenEventsType,
                           callback: EventListener, use_nested_classes: bool = False):
        def add():
            nonlocal self, event_type, callback, use_nested_classes
            if use_nested_classes and isinstance(event_type, str):
                raise AttributeError("Can't add_event_listener with use_nested_classes")

            def _add(event_name: str):
                nonlocal self
                nonlocal callback
                if event_name not in self._listeners:
                    self._listeners[event_name] = []
                self._listeners[event_name].append(callback)

            if isinstance(event_type, str):
                _add(event_type)
            else:
                def _raise(cls_type):
                    if not hasattr(cls_type, "message_type"):
                        raise AttributeError("Can't register listener cause message_type not found")

                if use_nested_classes:
                    for cls in event_type.__subclasses__():
                        _raise(cls)
                        _add(cls.message_type)
                else:
                    _raise(event_type)
                    _add(event_type.message_type)

        if isinstance(event_type, list):
            for i in event_type:
                add()
        else:
            add()
