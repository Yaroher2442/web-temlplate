from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List
from typing import cast

from pydantic import BaseModel

try:
    import orjson
    from sanic import Sanic
except ImportError:
    raise ImportError("poetry install --with rest")

from web import settings
from web.kernel.transport import Transport
from web.kernel.types import ConfAble, AppNameAble, ISocket, IService, TransportConf
from web.trend.rest.custom import CustomRouter, CustomErrorHandler


class SanicConf(BaseModel):
    access_log: bool | None = False
    noisy_exceptions: bool | None = False
    debug: bool = False


class ServingPaths(BaseModel):
    uri: str
    path: str
    route: bool = False


class SanicExtConf(BaseModel):
    params: SanicConf | None
    serving: dict[str, list[ServingPaths]] | None


class RestTransportConfig(TransportConf):
    sanic: SanicExtConf


class RestTransport(Transport, AppNameAble, ConfAble[RestTransportConfig]):
    sanic: Sanic
    _router: CustomRouter

    def __init__(self,
                 services: List[IService],
                 routes: dict,
                 ):
        super().__init__(services)
        self.sanic = Sanic("__broken__name",
                           loads=orjson.loads,
                           dumps=orjson.dumps,
                           error_handler=CustomErrorHandler())
        self._router = CustomRouter(routes)
        self._router.ctx.app = self.sanic
        self.sanic.router = self._router

    async def run(self, socket: ISocket):
        self.sanic.name = self.app_name
        cast(CustomRouter, self.sanic.router).set_routes(self)

        # Todo: it's magick hack to start with asyncio
        @self.sanic.middleware("request")
        async def make_cors(request):
            if request and hasattr(request, "route") and request.route:
                request.route.ctx._cors = request.app.ctx.cors

        start_args = self.conf.sanic.params.dict() if self.conf else {}
        if settings.DEBUG:
            start_args["debug"] = True
        server = await self.sanic.create_server(**start_args,
                                                sock=socket,
                                                return_asyncio_server=True)
        await server.startup()
        await server.serve_forever()
