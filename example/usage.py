import asyncio
import os
import random
from dataclasses import dataclass
from pathlib import Path

import loguru
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel

from example.models import TestModel
from example.proto import protoc
from web import settings
from web.app import WebApp
from web.env.database.database import DbConfig, DatabaseResource
from web.kernel.messaging.channel import IMessage
from web.kernel.proc.isolate import Isolate
from web.kernel.types import Environment, SocketConf, IService, SignalType, Resource, ConfAble, ISOLATE_EXEC
from web.trend.grpc.transport import GrpcTransportConfig, GrpcTransport
from web.trend.rest.custom import InputContext
from web.trend.rest.sse import SseWriter, SseRtMessage
from web.trend.rest.transport import RestTransport, RestTransportConfig, SanicExtConf, SanicConf
from web.trend.rest.ws import WsWriter, WsRtMessage
from web.utils.logger import setup_loggers


class GlConf(BaseModel):
    token: str


class IntegrationConf(BaseModel):
    gl: GlConf


class MyConf(BaseModel):
    rest: RestTransportConfig
    grpc: GrpcTransportConfig
    database: DbConfig
    integr: IntegrationConf


class TestResource(Resource, ConfAble[GlConf]):
    async def shutdown(self):
        pass

    async def init(self, *args, **kwargs) -> None:
        self.token = self.conf.token


class MyEnv(Environment):
    database = DatabaseResource(["example.models"])
    gitlab = TestResource()


class MyRESTService(IService):
    async def test(self):
        loguru.logger.warning("test")


class MyGrpcService(protoc.PackageServiceBase, IService):
    async def get_test(self, test: protoc.TestStructDto = None) -> protoc.TestStructResponse:
        loguru.logger.warning(test)
        loguru.logger.warning(self.transport.get_service(MyGrpcService))
        return protoc.TestStructResponse(test=protoc.TestStructResp(data=""))


class MyEvent(IMessage):
    message_type = "test_event"
    data: {}

    def __init__(self, data: dict):
        super().__init__()
        self.data = data


class MyTestIsolate(Isolate, ConfAble[GlConf]):
    async def work(self, *args, **kwargs) -> None:
        while True:
            loguru.logger.warning(f"[{self.channel.name}] TEST MESSAGE")
            await asyncio.sleep(10)


# ------------------------------ REST ---------------------------------

async def my_test_view(ctx: InputContext, transport: RestTransport):
    loguru.logger.warning(transport.env.database.communicator)
    await TestModel.create(name="VALENTIN PIDOR")
    loguru.logger.warning(transport.get_service(MyRESTService))
    # loguru.logger.warning(transport.plugins)
    # loguru.logger.warning(transport.shared_state)
    # loguru.logger.warning(transport.env)
    # loguru.logger.warning(transport.services)
    # await transport.get_service(MyIService).test()
    # loguru.logger.warning(transport)
    # loguru.logger.warning(transport.env)
    # loguru.logger.warning(transport.env.channel)
    # await transport.env.channel.produce(MyEvent(data={"hello": "world"}))
    return {"status": "ok"}


# ------------------------------ SSE ---------------------------------


async def my_test_post_event(ctx: InputContext, transport: RestTransport):
    await transport.channel.produce(MyEvent(data={"test": "da"}))
    return {"status": "ok"}


async def my_test_get_sse(ctx: InputContext, transport: RestTransport):
    async def my_sse_resolver(writer: SseWriter, message: MyEvent):
        loguru.logger.warning(message)
        return SseRtMessage(message.message_type)

    _response = await ctx.request.respond(content_type=SseWriter.content_type(),
                                          headers=SseWriter.default_headers())
    return await transport.new_rt(writer=SseWriter(_response, ping_enable=True),
                                  resolver=my_sse_resolver,
                                  events_type=MyEvent)


# ------------------------------ WSS ---------------------------------

async def my_test_get_wss(ctx: InputContext, transport: RestTransport):
    ws_conn = ctx.r_kwargs.get("ws")

    async def my_wss_resolver(writer: SseWriter, message: MyEvent):
        loguru.logger.warning(message)
        return WsRtMessage(msg="pidor")

    async def read_callback(writer: WsWriter, message: str):
        loguru.logger.warning(message)
        if message == "yes":
            await writer.close()

    return await transport.new_rt(writer=WsWriter(ws_conn, read_callback=read_callback),
                                  resolver=my_wss_resolver,
                                  events_type=MyEvent)


# ------------------------------ Scheduller ---------------------------------

async def test_infinite_task(env: MyEnv, *args, **kwargs):
    loguru.logger.warning(env)
    loguru.logger.warning(await TestModel.all())


async def test_task(env: MyEnv, *args, **kwargs):
    loguru.logger.warning(env)
    loguru.logger.warning(env.channel)
    loguru.logger.warning(args)
    await asyncio.sleep(5)
    # await env.channel.produce(MyEvent(data={"hello": "world"}))
    loguru.logger.warning(kwargs)
    return {"JOPA": "SLONA"}


async def my_test_scheduler(ctx: InputContext, transport: RestTransport):
    ret_event = await transport.back_task(test_task,
                                          # exec_type=ISOLATE_EXEC,
                                          args=["pidort"],
                                          kwargs={"yi": "no"},
                                          need_result=True)

    return ret_event.result


# ------------------------------ Shared state ---------------------------------
async def my_test_set_state(ctx: InputContext, transport: RestTransport):
    transport.shared_state.locally = True
    key = random.randint(1, 100)
    await transport.shared_state.set(key, [random.randint(1, 100) for _ in range(random.randint(1, 100))])
    loguru.logger.warning(transport.shared_state.forked)
    loguru.logger.warning(await transport.shared_state.get(key))
    return {"hello": "world"}


# ------------------------------ plugins state ---------------------------------
async def my_test_set_new_plugin(ctx: InputContext, transport: RestTransport):
    status, message = await transport.set_plugin(Path("plugins/new/test_add_this_plugin.py"))
    loguru.logger.info(transport.shared_state)
    return {"add": "ok"}


async def my_test_set_remove_new_plugin(ctx: InputContext, transport: RestTransport):
    for plug in transport.plugins:
        if plug.name == "TestADDPlugin":
            await transport.remove_plugin(plug.name)
    return {"remove": "ok"}


routes_dict = {
    "version_prefix": "/api/v",
    "endpoints": {
        "/test": {
            "v1": {
                "get": {"handler": my_test_view,
                        "protector": None, },
                "post": {
                    "handler": my_test_view,
                    "protector": None,
                }
            }
        },
        "/events": {
            "v1": {
                "get": {"handler": my_test_get_sse,
                        "protector": None, },
                "post": {"handler": my_test_post_event,
                         "protector": None, },
            }
        },
        "/ws": {
            "v1": {
                "websocket": {"handler": my_test_get_wss,
                              "protector": None, }
            }
        },
        "/sched": {
            "v1": {
                "post": {"handler": my_test_scheduler,
                         "protector": None, }
            }
        },
        "/state": {
            "v1": {
                "post": {"handler": my_test_set_state,
                         "protector": None, }
            }
        },
        "/plug": {
            "v1": {
                "post": {"handler": my_test_set_new_plugin,
                         "protector": None, },
                "delete": {"handler": my_test_set_remove_new_plugin,
                           "protector": None, }
            }
        },
    }
}


async def main():
    settings.DEBUG = True

    conf = MyConf(
        rest=RestTransportConfig(
            socket=SocketConf(
                host="0.0.0.0", port=8080
            ),
            sanic=SanicExtConf(params=SanicConf(access_log=True), serving=None)
        ),
        grpc=GrpcTransportConfig(socket=SocketConf(host="0.0.0.0", port=8081)),
        database=DbConfig(host="0.0.0.0",
                          port="5432",
                          database="testdb",
                          user="testuser",
                          password="Fedora132",
                          db_schema="test",
                          with_migrations=False,
                          migrations_path=Path("../applied_files/migrations")),
        integr=IntegrationConf(gl=GlConf(token="SOME_SHIT"))
    )
    env = MyEnv()
    # .with_plugins(Path("plugins/default"))
    rest_transport = RestTransport(services=[MyRESTService()],
                                   routes=routes_dict)
    grpc_transport = GrpcTransport(services=[MyGrpcService()])
    app = WebApp[MyConf]("test_app", conf, [rest_transport, grpc_transport], env).with_scheduler()
    setup_loggers()

    await rest_transport.back_task(test_infinite_task,
                                   trigger=IntervalTrigger(seconds=5),
                                   exec_type=ISOLATE_EXEC,
                                   args=["pidort"],
                                   kwargs={"yi": "no"})

    async def init_database(app: WebApp):
        await app.env.database.configure_db()

    app.on_signal(SignalType.BEFORE_APP_RUN, init_database)

    isolate = MyTestIsolate("TEST_ISOLATE")
    app.dispatcher.set_channel(isolate)
    app.manager.add_isolate(isolate)

    await app.run(multiprocessing=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        exit(0)
