from __future__ import annotations

import asyncio
import os
import re
import socket
from abc import ABCMeta
from dataclasses import dataclass
from enum import Enum
from importlib.abc import FileLoader
from importlib.util import spec_from_loader, module_from_spec
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Type, TypeVar, Generic, Callable, Coroutine, get_args, NewType, cast, Tuple
from typing import Union, Dict, List

import loguru
from pydantic import BaseModel

from web import settings

# --------------------------------------------------GENS TYPES---------------------------------------------------------

JSON = Union[Dict[str, Any], List[Any], int, str, float, bool, Type[None]]
TypeJSON = Union[Dict[str, 'JSON'], List['JSON'], int, str, float, bool, Type[None]]

GenAsyncCall = Callable[[Any, ...], Coroutine[Any, Any, Any]]

GenPerformCall = list[Coroutine[Any, Any, Any] | Coroutine[Any, Any, None]]

GenConfig = TypeVar("GenConfig", bound=BaseModel)

DtoType = TypeVar("DtoType", bound=BaseModel)


# --------------------------------------------------MESSAGING TYPES-----------------------------------------------------


class IMessage:
    message_type: str = "__all__"
    index: int
    inner_index: int
    sender: str
    destination: str = "__all__"
    exec_inner: bool = False
    return_event_type: Type[IMessageReturn] = None

    def __init__(self):
        self.index = 0
        self.inner_index = 0
        self.sender = "None"

    def __str__(self):
        return f"{self.__class__.__name__}({self.message_type},{self.index=},{self.inner_index=}, {self.sender=})"

    def reply(self, *args, **kwargs):
        return self.return_event_type(self, *args, **kwargs)


class IMessageReturn(IMessage):
    def __init__(self, response_to: IMessage, *args, **kwargs):
        super().__init__()
        self.inner_index = response_to.inner_index
        self.destination = response_to.sender


GenEventsType = TypeVar("GenEventsType", bound=List[Type[IMessage] | str] | Type[IMessage] | str)


class IMessageWaiter:
    result: IMessage | None
    wait_for_index: int = 0
    waiter: IChannel
    _timeout: float

    def __init__(self, waiter: IChannel, question: IMessage, timeout: float = 0):
        self.result = None
        self.waiter = waiter
        self.wait_for_index = question.inner_index
        self._timeout = timeout

    async def wait_on(self) -> IMessage | None:
        if settings.DEBUG:
            loguru.logger.debug(f"[{self}] wait for message ")
        _wait_secs = 0
        while self.result is None:
            if self._timeout != 0 and _wait_secs >= self._timeout:
                return None
            await asyncio.sleep(0.05)
            _wait_secs += 0.05
        else:
            return self.result

    def answer(self, message: IMessage):
        if settings.DEBUG:
            loguru.logger.debug(f"{self} got answer {message}")
        self.result = message

    def __eq__(self, other):
        self.wait_for_index = other.wait_for_index

    def __repr__(self):
        return f"[{self.waiter.name}::IMessageWaiter-{self.wait_for_index}]"


GenIMessage = TypeVar("GenIMessage", bound=IMessage, contravariant=True)
EventListener = Callable[[GenIMessage], Coroutine[Any, Any, Any]]


class IChannel:
    read_timeout = 0.01
    name: str
    consume_pipe: Queue
    produce_pipe: Queue
    _listeners: Dict[str, List[EventListener]]
    _response_waiters: Dict[int, IMessageWaiter]
    _inner_index: int

    def __init__(self, idx: int, isolate_name: str):
        self._inner_index = 0
        self.name = f"{isolate_name}::Channel-{idx}"
        # self.debug = debug
        self._listeners = {}
        self._response_waiters = {}
        self.consume_pipe = Queue()
        self.produce_pipe = Queue()

    def __str__(self):
        return f"IChannel({self.name})"

    async def produce(self, msg: IMessage, need_answer: bool = False, answer_timeout: float = 0) -> IMessage | None:
        raise NotImplementedError

    async def sent_to_consume(self, msg: IMessage):
        self.consume_pipe.put(msg)

    async def listen_produce(self, callback: Callable[[GenIMessage], Coroutine]):
        raise NotImplementedError

    async def listen_consume(self):
        raise NotImplementedError

    def add_event_listener(self, event_type: GenEventsType,
                           callback: EventListener, use_nested_classes: bool = False):
        raise NotImplementedError

    def set_waiter(self, waiter: IMessageWaiter):
        self._response_waiters[waiter.wait_for_index] = waiter

    def answer_to_waiters(self, answer: IMessage):
        waiter = self._response_waiters.get(answer.inner_index)
        if waiter:
            waiter.answer(message=answer)
            self._response_waiters.pop(answer.inner_index)


class SettingsChangeEvent(IMessage):
    message_type = "__change_settings_event__"
    name: str
    value: bool

    def __init__(self, name: str, value: bool):
        super().__init__()
        self.name = name
        self.value = value

    def __str__(self):
        return f"{self.__class__.__name__}({self.name})"


# --------------------------------------------------ABLES TYPES------------------------------------------------------

class Able:
    pass


GenAble = TypeVar("GenAble", bound=Able)


class AppNameAble(Able):
    __app_name: str

    @property
    def app_name(self) -> str:
        if self.__app_name:
            return self.__app_name
        else:
            raise RuntimeError(f"__app_name not set in {self.__class__.__name__}")

    @app_name.setter
    def app_name(self, name: str):
        self.__app_name = name


class SharedStateAble(Able):
    __shared_state: SharedState | None = None

    @property
    def shared_state(self) -> SharedState:
        if self.__shared_state:
            return self.__shared_state
        else:
            raise RuntimeError(f"__shared_state not set in {self.__class__.__name__}")

    @shared_state.setter
    def shared_state(self, state: SharedState):
        self.__shared_state = state


class ChanAble(Able):
    name: str
    __chan: IChannel | None = None

    @property
    def channel(self) -> IChannel:
        if self.__chan:
            return self.__chan
        else:
            raise RuntimeError(f"__channel not set in {self.__class__.__name__}")

    @channel.setter
    def channel(self, chan: IChannel):
        self.__chan = chan


class ConfAble(Generic[GenConfig], Able):
    __conf: GenConfig | None = None

    @property
    def conf(self) -> GenConfig:
        if self.__conf:
            return self.__conf
        else:
            raise RuntimeError("__conf not set")

    @conf.setter
    def conf(self, conf: GenConfig):
        self.__conf = conf


class EnvAble(Able):
    __env: Environment | None

    @property
    def env(self) -> Environment:
        if self.__env:
            return self.__env
        else:
            raise RuntimeError(f"__env not set in {self.__class__.__name__}")

    @env.setter
    def env(self, e: Environment):
        self.__env = e


def cheat(set_to: Any, typed: Type, value: Any, nested: bool = True, self: bool = True, nested_count: int = 1):
    def _set_conf_able(obj, conf) -> bool:
        for base in obj.__orig_bases__:
            if "ConfAble" in base.__name__:
                conf_class = get_args(base)[0]
                for attr in vars(conf).values():
                    if isinstance(attr, conf_class):
                        obj.conf = attr
                        loguru.logger.success(
                            f"[CONF_ABLE::{obj.__class__.__name__}] Set {attr.__class__.__name__}")
                        return True
                    elif issubclass(attr.__class__, BaseModel):
                        if _set_conf_able(obj, attr):
                            return True
            if base == Generic[GenConfig]:
                obj.conf = value
                return True
        return False

    def set_up(target: GenAble):
        if typed == EnvAble:
            target.env = value
            return True
        elif typed == AppNameAble:
            target.app_name = value
            return True
        elif typed == ChanAble:
            target.channel = value
            return True
        elif typed == SharedStateAble:
            target.shared_state = value
            return True
        if typed == ConfAble:
            return _set_conf_able(target, value)
        return False

    def proc(_item):
        if typed in _item.__class__.__mro__:
            if settings.DEBUG:
                loguru.logger.debug(
                    f"[CYCLE::{nested_count}][OBJECT::{set_to.__class__.__name__}] "
                    f"- Set({typed.__name__},{name}:{item.__class__.__name__})")
            is_set = set_up(_item)
            if settings.DEBUG:
                if is_set:
                    loguru.logger.success(
                        f"[CYCLE::{nested_count}][OBJECT::{_item.__class__.__name__}] Set {typed.__name__}")
                else:
                    loguru.logger.error(
                        f"[CYCLE::{nested_count}][OBJECT::{_item.__class__.__name__}] NOT SET {typed.__name__}")
            if nested:
                cheat(_item, typed, value,
                      nested_count=nested_count + 1)

    if self and typed in set_to.__class__.__mro__:
        set_up(set_to)

    if hasattr(set_to, "__dict__"):
        for name, item in vars(set_to).items():
            if isinstance(item, list):
                for i in item:
                    proc(i)
            else:
                proc(item)
    else:
        loguru.logger.error(f"SKIP {set_to.__class__.__name__} have not __dict__")


# --------------------------------------------------SIGNALS TYPES-------------------------------------------------------

class SignalType(Enum):
    BEFORE_APP_RUN = "BEFORE_APP_RUN"
    AFTER_APP_STOP = "AFTER_APP_STOP"


class SigAble:
    signals: Dict[SignalType, List[GenAsyncCall]] | None = None

    def on_signal(self, typed: SignalType, func: GenAsyncCall):
        if not self.signals:
            self.signals = {}
        if not self.signals.get(typed):
            self.signals[typed] = []
        self.signals[typed].append(func)


async def call_signals(obj: SigAble, typed: SignalType, *args, nested: bool = False, **kwargs):
    if hasattr(obj, "signals") and obj.signals and obj.signals.get(typed):
        for signal in obj.signals[typed]:
            await signal(*args, **kwargs)
        if nested:
            for item in vars(obj).values():
                if SigAble in type(item).__mro__:
                    await call_signals(item, typed, *args, nested=True, **kwargs)


# --------------------------------------------------PROC TYPES---------------------------------------------------------


class SetStateEvent(IMessage):
    message_type = "__set_state__"
    key: Any
    value: Any
    destination = "__master__"
    exec_inner = False

    def __init__(self, key: Any, value: Any):
        super().__init__()
        self.key = key
        self.value = value


class GetStateReturnEvent(IMessageReturn):
    message_type = "__get_state_return__"
    exec_inner = False
    value: Any

    def __init__(self, ret_to: GetStateEvent, value: Any):
        super().__init__(ret_to)
        self.value = value


class GetStateEvent(IMessage):
    message_type = "__get_state__"
    key: Any
    destination = "__master__"
    exec_inner = False
    return_event_type = GetStateReturnEvent

    def __init__(self, key: Any):
        super().__init__()
        self.key = key


class RemoveStateEvent(IMessage):
    message_type = "__remove_state__"
    key: Any
    destination = "__master__"
    exec_inner = False

    def __init__(self, key: Any):
        super().__init__()
        self.key = key


class SharedState(ChanAble):
    _state: Dict[str, Any]
    locally: bool
    sync: asyncio.Lock
    forked: bool
    set_event_type: Type[IMessage] = SetStateEvent
    get_event_type: Type[IMessage] = GetStateEvent
    remove_event_type: Type[IMessage] = RemoveStateEvent

    def __init__(self, channel: IChannel,
                 forked=False,
                 locally: bool = False):
        self._state = {}
        self.channel = channel
        self.locally = locally
        self.forked = forked
        self.sync = asyncio.Lock()
        if not forked:
            if settings.DEBUG:
                loguru.logger.debug(f"{self} Set events listeners")
            self.channel.add_event_listener(self.set_event_type, self._set)
            self.channel.add_event_listener(self.get_event_type, self._get)
            self.channel.add_event_listener(self.remove_event_type, self._remove)

    async def _remove(self, event: RemoveStateEvent):
        async with self.sync:
            if settings.DEBUG:
                loguru.logger.debug(f"{self} Remove state Key: {event.key}")
            self._state.pop(event.key)

    async def _set(self, event: SetStateEvent):
        async with self.sync:
            if settings.DEBUG:
                loguru.logger.debug(f"{self} Set state Key: {event.key} Value: {event}")
            self._state[event.key] = event.value

    async def _get(self, event: GetStateEvent):
        async with self.sync:
            if settings.DEBUG:
                loguru.logger.debug(f"{self} Get state Key: {event.key}")
            await self.channel.produce(event.reply(self._state.get(event.key)))

    async def set(self, key: Any, value: Any) -> None:
        if self.locally:
            self._state[key] = value
        await self.channel.produce(self.set_event_type(key, value))

    async def get(self, key: Any):
        if self.locally and key in self._state:
            return self._state[key]
        response = cast(GetStateReturnEvent, await self.channel.produce(self.get_event_type(key), need_answer=True))
        return response.value

    async def remove(self, key: Any):
        if self.locally and key in self._state:
            self._state.pop(key)
        await self.channel.produce(self.remove_event_type(key))

    def __repr__(self):
        return f"[{self.__class__.__name__}::{self.channel.name}]"

    @property
    def local_store(self) -> Dict[str, Any]:
        if self.locally:
            return self._state
        else:
            raise RuntimeError(f"{self} Local store unavailable, locally is false")


# --------------------------------------------------PLUGINS TYPES ------------------------------------------------------


class Plugin(AppNameAble, EnvAble, SigAble, SharedStateAble, metaclass=ABCMeta):
    name: str
    enabled: bool
    required_attrs: List[str] = []

    async def exec(self, *args, **kwargs):
        raise NotImplementedError

    def __repr__(self):
        return f"{self.__class__.__name__}"


class PluginContainer:
    _REGEX = re.compile(r"PLUGIN_NAME\s?=\s?[\"|'](.*)[\"|']")
    file_path: Path
    code: str
    plugin: Plugin | None

    class SourceCodeLoader(FileLoader):
        def __init__(self, fullname: str, source):
            super().__init__(fullname, source)
            self.path = source

        def get_source(self, fullname: str) -> str | bytes:
            return self.path

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.plugin = None

    def import_plugin(self) -> Tuple[str, str | Exception]:
        if not self.file_path.exists():
            return "error", FileExistsError(f"{self.file_path} does not exist")
        with open(self.file_path) as file:
            self.code = file.read()
            match = self._REGEX.findall(self.code)
            if match:
                try:
                    plugin_name = match[0]
                    spec = spec_from_loader(self.file_path.name,
                                            loader=self.SourceCodeLoader(plugin_name, self.code))
                    module = module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.plugin = getattr(module, plugin_name)()
                    if Plugin not in self.plugin.__class__.__mro__:
                        return "warning", f"{plugin_name} is not child on Plugin"
                    self.plugin.name = plugin_name
                    for at in self.plugin.required_attrs:
                        if not hasattr(self.plugin, at) and not getattr(self.plugin, at):
                            return "warning", f"{at} not found in {self.plugin.name}"
                    return "success", f"Import plugin"
                except Exception as e:
                    return "exception", e
            return "warning", f"No plugin name found in {self.file_path} {match}"

    def __repr__(self):
        return f"{self.__class__.__name__}::{self.plugin}"

    def __getstate__(self):
        self.plugin = None
        return self.__dict__


class SetPluginEvent(SetStateEvent):
    message_type = "__set_plugin_state__"
    key: str
    destination: str = "__all__"
    value: PluginContainer
    exec_inner = True

    def __init__(self, key: str, value: PluginContainer):
        super().__init__(key, value)


class RemovePluginEvent(RemoveStateEvent):
    message_type = "__remove_plugin_state__"
    destination: str = "__all__"
    exec_inner = True


class PluginsStore(SharedState, EnvAble):
    _state: Dict[str, PluginContainer]
    dir_path: Path
    set_event_type: Type[IMessage] = SetPluginEvent
    remove_event_type: Type[IMessage] = RemovePluginEvent

    def __init__(self, dir_path: Path, channel: IChannel, *args, **kwargs):
        self.dir_path = dir_path
        super().__init__(channel, *args, locally=True, forked=True, **kwargs)
        self.channel.add_event_listener(self.set_event_type, self._set)
        self.channel.add_event_listener(self.remove_event_type, self._remove)

    def import_plugins(self):
        for filename in os.listdir(self.dir_path):
            plugin_path = self.dir_path.joinpath(str(filename))
            container = PluginContainer(plugin_path)
            msg_type, message = container.import_plugin()
            if settings.DEBUG:
                getattr(loguru.logger, msg_type)(f"[{self}::{container}] {message}")
            if msg_type == "success":
                self._state.update({container.plugin.name: container})

    async def _set(self, event: SetPluginEvent):
        await super()._set(event)
        status, message = event.value.import_plugin()
        if settings.DEBUG:
            getattr(loguru.logger, status)(f"[{self}::{event.value}] {message}")

    async def get(self, key: str) -> PluginContainer:
        return cast(PluginContainer, await super().get(key))

    async def set(self, key: Any, value: Any) -> None:
        await super().set(key, value)

    def __repr__(self):
        return f"{self.__class__.__name__}({os.getpid()})"

    @property
    def local_store(self) -> Dict[str, PluginContainer]:
        return super().local_store


# --------------------------------------------------SPECIAL TYPES------------------------------------------------------

class SocketConf(BaseModel):
    host: str | None
    port: int | None


class ISocket(socket.socket):
    host: int
    port: int
    backlog: int

    def __init__(self, host, port, backlog: int = 100):
        """Create TCP server socket.
        :param host: IPv4
        :param port: TCP port number
        :param backlog: Maximum number of connections to queue
        """
        super().__init__()
        self.host = host
        self.port = port
        self.backlog = backlog
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind((self.host, self.port))
        self.listen(self.backlog)
        self.set_inheritable(True)

    def __repr__(self):
        return f"{self.host}:{self.port}"


GenISocket = TypeVar("GenISocket", bound=ISocket)

# --------------------------------------------------MAIN TYPES---------------------------------------------------------

GenCommunicator = TypeVar("GenCommunicator")


class TransportConf(BaseModel):
    socket: SocketConf


class ITransport(ConfAble[TransportConf], ChanAble, EnvAble, SharedStateAble, metaclass=ABCMeta):
    services: List[GenService]
    rt_writers: Dict[Type[RtWriter], List[RtWriter]]
    plugins_dir: Path | None
    _plugins_store: PluginsStore | None

    def __init__(self, services: List[GenService]):
        EnvAble.__init__(self)
        self.services = services
        for service in self.services:
            service.transport = self
        self.rt_writers = {}
        self._plugins_store = None
        self.plugins_dir = None

    def get_service(self, typed: Type[GenService]) -> GenService | None:
        for service in self.services:
            if isinstance(service, typed):
                return service

    def with_plugins(self, plugins_dir: Path):
        if not plugins_dir.exists():
            raise FileNotFoundError(f"{plugins_dir} does not exist")
        self.plugins_dir = plugins_dir
        return self

    async def set_settings(self, name: str, value: Any):
        await self.channel.produce(SettingsChangeEvent(name, value))

    def init_plugins(self):
        if self.plugins_dir:
            self._plugins_store = PluginsStore(self.plugins_dir, self.channel)
            self._plugins_store.import_plugins()

    def perform(self, sock: ISocket) -> GenPerformCall:
        self.init_plugins()
        return [self.run(sock)]

    async def back_task(self,
                        target: BackTaskTarget,
                        args: List[Any] = [],
                        kwargs: Dict[str, Any] = {},
                        trigger: BackTaskTrigger = None,
                        exec_type: str = "default",
                        on_error: BackTaskCallback = None,
                        on_complete: BackTaskCallback = None,
                        need_result: bool = False
                        ) -> TaskReturnEvent | None:
        raise NotImplementedError

    async def new_rt(self, writer: RtWriter,
                     events_type: GenEventsType,
                     resolver: RtResolver,
                     use_nested_events: bool = False):
        raise NotImplementedError

    async def run(self, sock: ISocket):
        raise NotImplementedError

    @property
    def plugins(self):
        if not self._plugins_store:
            return []
        return [container.plugin for container in self._plugins_store.local_store.values()]


class Resource(AppNameAble, ConfAble, ChanAble, metaclass=ABCMeta):
    __communicator: GenCommunicator | None

    def __init__(self, communicator: GenCommunicator | None = None):
        self.__communicator = communicator

    async def init(self, *args, **kwargs) -> None:
        raise NotImplementedError

    async def shutdown(self):
        raise NotImplementedError

    @property
    def communicator(self):
        if not self.__communicator:
            raise RuntimeError(f"__communicator not set in {self.__class__.__name__}")
        return self.__communicator

    @communicator.setter
    def communicator(self, comm: GenCommunicator):
        self.__communicator = comm


class Environment(ConfAble, AppNameAble, ChanAble, SharedStateAble):
    _resources: List[Resource]

    def __init__(self):
        self._resources = []
        for res in self.__class__.__dict__.values():
            if Resource in res.__class__.__mro__:
                self._resources.append(res)

    async def init(self):
        # TODO CHEAT IS NEED?
        # cheat(self, AppNameAble, self.app_name)
        # cheat(self, ConfAble, self.conf)
        # cheat(self, EnvAble, self)
        for res in self._resources:
            cheat(res, AppNameAble, self.app_name)
            cheat(res, ConfAble, self.conf)
            await res.init()

    async def shutdown(self):
        for resource in self._resources:
            await resource.shutdown()


class IService:
    transport: ITransport


GenService = TypeVar("GenService", bound=IService)


# --------------------------------------------------RT TYPES -----------------------------------------------------------


@dataclass
class RtMessage:
    def prepare(self, idx: int = 0, *args, **kwargs) -> str | bytes:
        raise NotImplementedError

    @classmethod
    def ping_message(cls):
        raise NotImplementedError


GenRtMessage = TypeVar("GenRtMessage", bound=RtMessage)


class RtWriter(Generic[GenRtMessage]):
    message_class: GenRtMessage
    last_index: int = 0
    obj: Any

    def __init__(self, obj: Any):
        self.obj = obj

    async def write(self, message: GenIMessage) -> None:
        raise NotImplementedError

    async def freeze(self):
        raise NotImplementedError

    async def run(self, on_disconnect: Callable):
        await self.freeze()
        await on_disconnect()

    async def close(self, *args, **kwargs):
        raise NotImplementedError


RtResolver = NewType("RtResolver", Callable[[RtWriter, GenIMessage], Coroutine[Any, Any, RtMessage | None]])
RtReadCallback = NewType("RtReadCallback", Callable[[RtWriter, Any], Coroutine[Any, Any, RtMessage | None]])

# --------------------------------------------------BACK TYPES ---------------------------------------------------------


BackTaskTarget = NewType("BackTaskTarget", Callable[[Environment, ...], Coroutine[Any, Any, Any]])
BackTaskTrigger = TypeVar("BackTaskTrigger")
BackTaskCallback = TypeVar("BackTaskCallback")

ISOLATE_EXEC = "isolate_exec"


class TaskReturnEvent(IMessageReturn):
    message_type = "__task_return__"
    result: Any
    ex: Exception

    def __init__(self, ret_to: TaskEvent, result: Any, ex: Exception = None):
        super().__init__(ret_to)
        self.result = result
        self.ex = ex


class TaskEvent(IMessage):
    message_type = "__task__"
    destination = "__master__"
    target: BackTaskTarget
    trigger: BackTaskTrigger
    exec_type: str
    args: List[Any]
    kwargs: Dict[str, Any]
    on_error: BackTaskCallback
    on_complete: BackTaskCallback
    return_event_type = TaskReturnEvent

    def __init__(self, target: BackTaskTarget,
                 trigger: BackTaskTrigger = None,
                 args: List[Any] = None,
                 exec_type: str = "default",
                 kwargs: Any | None = None,
                 on_error: BackTaskCallback = None,
                 on_complete: BackTaskCallback = None):
        super().__init__()
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.trigger = trigger
        self.exec_type = exec_type
        self.on_error = on_error
        self.on_complete = on_complete


class IScheduler:
    _tasks_info: Dict[str, BackTaskTarget]
    state: Dict[str, Any]

    async def add_task(self, message: GenIMessage):
        raise NotImplementedError

    def stop(self, *args, **kwargs):
        raise NotImplementedError

    def perform(self) -> List[Coroutine[Any, Any, Any] | Coroutine[Any, Any, None]]:
        raise NotImplementedError
