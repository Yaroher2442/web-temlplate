import asyncio
import os
import random
import sys
from datetime import datetime as dt
from pathlib import Path

import loguru
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel
from sanic import json, Sanic, Request
from sanic.models.protocol_types import Range
from sanic_ext.config import add_fallback_config
from sanic_ext.extensions.openapi.blueprint import blueprint_factory
from sanic_ext.extensions.openapi.builders import SpecificationBuilder
from sanic_ext.extensions.openapi.extension import OpenAPIExtension
from tortoise import fields
from json import dump, load

from web_foundation import settings
from web_foundation.config import DbConfig, AppConf
from web_foundation.extentions.addons.addon_loader import AddonsLoader, ApiAddon
from web_foundation.extentions.metrics.exporter import JsonExporter
from web_foundation.extentions.metrics.metric import CounterMetric
from web_foundation.extentions.metrics.events import NewMetricEvent
from web_foundation.extentions.metrics.service import MetricsService
from web_foundation.extentions.openapi_gen import generate_openapi
from web_foundation.extentions.realtime.sse import SseRtMessage, SseRtConnection
from web_foundation.extentions.request_handler import ChainRequestHandler, InputContext
from web_foundation.extentions.router import DictRouter
from web_foundation.extentions.schedulle.scheduller import TaskScheduler
from web_foundation.kernel.dependency import Dependency
from web_foundation.kernel.messaging.channel import IMessage
from web_foundation.kernel.messaging.dispatcher import IDispatcher

from web_foundation.kernel.app import App
from web_foundation.kernel.container import DependencyContainer
from web_foundation.kernel.isolate import Isolate
from web_foundation.kernel.service import Service
from web_foundation.resources.database.database import DatabaseResource
from web_foundation.resources.database.models import AbstractDbModel
from web_foundation.resources.files.os import OsFilesResource
from web_foundation.resources.resource import Resource
from web_foundation.resources.stores.memory_dict import InMemoryDictStore
from web_foundation.settings_event import SettingsChangeEvent
from web_foundation.utils.helpers import load_config
from sanic.response import file_stream


class AnyModel(AbstractDbModel):
    some_data = fields.TextField()


class TicketService(MetricsService):
    pass


class AnyContainer(DependencyContainer):
    database = Dependency(instance_of=DatabaseResource, default=DatabaseResource(modules=[__name__]))
    ticket_service = TicketService()
    file_repository: Dependency[OsFilesResource] = Dependency(instance_of=Resource,
                                                              default=OsFilesResource(Path("applied_files")))
    data_store: Dependency[InMemoryDictStore] = Dependency(instance_of=Resource, default=InMemoryDictStore())


class TestAddonLoader(AddonsLoader):
    async def configure_addon(self, addon: ApiAddon, *args, **kwargs) -> ApiAddon:
        addon.enabled = True
        addon.name = 'lskdjflkjsdlfkjsdlkfjlsdfj'
        addon.target = "test"
        return addon


class SomeDto(BaseModel):
    name: str


if __name__ == '__main__':
    settings.DEBUG = True
    settings.METRICS_ENABLE = True
    app_config = load_config(Path("applied_files/config/config.json"), AppConf)
    file_repo = OsFilesResource(Path("applied_files"))
    store = InMemoryDictStore()
    addon_loader = TestAddonLoader(addons_dir_path=Path("plugins"), files_repo=file_repo, store=store)
    container: AnyContainer = AnyContainer(app_config=app_config, data_store=store, file_repository=file_repo,
                                           addon_loader=addon_loader)
    scheduler = TaskScheduler(executors={"default": AsyncIOExecutor()})
    dispatcher = IDispatcher(scheduler=scheduler)
    app = App(dependency_container=container, dispatcher=dispatcher)


    # app.sanic.config.HEALTH = True
    # app.sanic.config.HEALTH_ENDPOINT = True
    async def check_add(s_app, *args, **kwargs):
        add_loader: TestAddonLoader = s_app.ctx.container.addon_loader()
        pl = await add_loader.find_addon_by_name("lskdjflkjsdlfkjsdlkfjlsdfj")
        loguru.logger.warning(f"on {os.getpid()} plugin {pl}")


    app.sanic.before_server_stop(check_add)


class TestEvent(IMessage):
    message_type = "test_event"
    exec_inner = True


class NewIsolate(Isolate):

    async def reaction(self, event: SettingsChangeEvent):
        loguru.logger.warning(f"REACTION FROM {self.name},{event}")

    async def work(self, **kwargs) -> None:
        self.channel.add_event_listener(SettingsChangeEvent, self.reaction)

        # pass

        while True:
            await asyncio.sleep(1)
            loguru.logger.warning(os.getpid())


async def some_background_task(some_data: int):
    loguru.logger.warning(f"back task execute {some_data}")
    loguru.logger.warning(id(asyncio.get_event_loop()))
    model = await AnyModel.first()
    loguru.logger.warning(await model.values_dict())
    return NewMetricEvent(CounterMetric("new_metric"))


async def test(ctx: InputContext, container: AnyContainer):
    match ctx.request.method:
        case "POST":
            # await container.ticket_service.run_background(some_background_task,
            #                                               return_event=True)
            # await AnyModel.create(some_data="asasgasgasgasgasgsag")
            # await container.ticket_service.run_background(some_background_task, random.randint(0, 100),
            #                                               trigger=IntervalTrigger(seconds=2),
            #                                               return_event=True)
            await container.ticket_service.give_metric(CounterMetric("SomeCounter"), kind="some_kind")
            return {'asdf': 234}
        case "GET":
            # loguru.logger.warning(ctx.request.app.router.routes)
            loguru.logger.warning(dir(ctx.request.app.router.routes_all.get(('api', 'v1', 'test'))))
            loguru.logger.warning(ctx.request.app.router.routes_all.get(('api', 'v1', 'test')).handler.__closure__)
            loguru.logger.warning(
                dir(ctx.request.app.router.routes_all.get(('api', 'v1', 'test')).handler.__closure__[0]))
            loguru.logger.warning(ctx.request.app.router.routes_all.get(('api', 'v1', 'test')).handler.__closure__[
                                      0].cell_contents.in_struct)
            ctx.request.app.router.routes_all.get(('api', 'v1', 'test')).handler.__closure__[
                0].cell_contents.in_struct = SomeDto
            return await container.ticket_service.collect_metrics(JsonExporter(), kind="some_kind")
    return json({"ok": "ok"})


async def resolve_sse(conn, msg):
    loguru.logger.warning("sse resolver")
    return SseRtMessage(event_name='some event', data={'asdf': 1234124})


async def sse_test(ctx, container):
    loguru.logger.warning(f"start sse {os.getpid()=}")
    await SseRtConnection.accept_connection(ctx, resolve_sse)


async def emmit_sse_event(ctx, container):
    loguru.logger.warning(f"{os.getpid()=}")
    data = TestEvent()
    await ctx.request.app.ctx.channel.produce(data)
    return json({"ok": "ok"})


class MyRange(Range):
    @property
    def start(self) -> int:
        return 1024

    @property
    def size(self) -> int:
        return 1024

    @property
    def end(self) -> int:
        return 1024

    @property
    def total(self) -> int:
        return 1024


async def give_file(ctx, container):
    return await file_stream(
        location="test.json",
        chunk_size=1024,
        _range=MyRange())


if __name__ == '__main__':
    routes_dict = {
        "apps": [
            {
                "app_name": "ae_app",
                "version_prefix": "/api/v",
                "endpoints": {
                    "/test": {
                        "v1": {
                            "get": {"handler": test,
                                    "protector": None, },
                            "post": {
                                "handler": test,
                                "protector": None,
                            }
                        }
                    },
                    "/test/<kk:int>": {
                        "v1": {
                            "get": {"handler": test,
                                    "protector": None, },
                            "post": {
                                "handler": test,
                                "protector": None,
                            }
                        }
                    },
                    "/test_sse": {
                        "v1": {
                            "get": {"handler": sse_test,
                                    "protector": None, },
                            "post": {
                                "handler": emmit_sse_event,
                                "protector": None,
                            }
                        }
                    },
                    "/test_file": {
                        "v1": {
                            "get": {"handler": give_file,
                                    "protector": None, },
                        }
                    },
                }
            }
        ]
    }
    router = DictRouter[ChainRequestHandler](routes_dict, ChainRequestHandler, open_api=True)
    app.add_custom_router(router)

    if "generate_openapi" in sys.argv:
        generate_openapi(app, json_filepath=app.config.openapi_filepath)
        sys.exit()

    # app.add_isolate("AAAA", NewIsolate, app=app)
    app.subscribe_worker(TestEvent, resolve_callback=resolve_sse)
    app.run()
