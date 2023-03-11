from __future__ import annotations

import os
import sys
from abc import ABC
from abc import ABCMeta
from dataclasses import dataclass
from functools import wraps
from traceback import extract_tb
from typing import Any, Callable, Coroutine, TypeVar, Generic, cast
from typing import Dict
from typing import List
from typing import Type

import loguru
from pydantic import ValidationError as PdValidationError, BaseModel as PdModel
from sanic import Request
from sanic import Sanic, file
from sanic import json, HTTPResponse
from sanic.errorpages import exception_response, JSONRenderer
from sanic.exceptions import BadRequest
from sanic.exceptions import SanicException
from sanic.handlers import ErrorHandler
from sanic.router import Router

from web import settings
from web.errors.app import ValidationError, ApplicationError
from web.kernel.transport import Transport
from web.kernel.types import DtoType
from web.kernel.types import Plugin, GenAsyncCall, ITransport
from web.trend.rest.utils.openapi_spec import add_openapi_spec


@dataclass
class PlugRouteConf:
    route: str
    method: str

    def __post_init__(self):
        self.method = self.method.lower()


class RestPlugin(Plugin, metaclass=ABCMeta):
    routes_conf: List[PlugRouteConf]
    required_attrs = ["routes_conf"]

    async def exec(self, handler: GenAsyncCall,
                   ctx: InputContext,
                   transport: ITransport,
                   prev_plugin_result: Any = None):
        raise NotImplementedError


def validate_dto(dto_cls: Type[PdModel] | None, request: Request) -> PdModel | None:
    if not dto_cls:
        return None
    if "json" in request.content_type:
        data = request.json
    elif "form" in request.content_type:
        data = {key: value[0] for key, value in request.form.items()}
    else:
        raise BadRequest("Incorrect content type")
    try:
        dto = dto_cls(**data)
        return dto
    except PdValidationError as ex:
        failed_fields = ex.errors()
        fields = [field["loc"][-1] for field in failed_fields]
        # commment_str = "Some of essential params failed : " + ", ".join(
        #     [field["loc"][-1] + " - " + field["msg"] for field in failed_fields])
        comment_str = f"""Some essential params failed: {", ".join([f'{field["loc"][-1]} - {field["msg"]}' for field in failed_fields])}"""
        context = {
            "fields": fields,
            "comment": comment_str
        }
        raise ValidationError(message=comment_str,
                              context=context)


@dataclass
class ProtectIdentity:
    pass


ProtectIdentityType = TypeVar("ProtectIdentityType", bound=ProtectIdentity)


@dataclass
class InputContext(Generic[DtoType, ProtectIdentityType]):
    request: Request
    dto: DtoType | None
    identity: ProtectIdentity | None
    r_kwargs: Dict


Protector = Callable[[Request, Transport], Coroutine[Any, Any, ProtectIdentityType | None]]
DtoValidator = Callable[[Type[DtoType], Request], PdModel]
HandlerType = Callable[[InputContext, Transport], Coroutine[Any, Any, HTTPResponse]]


class CustomRequestHandler(ABC):
    protector: Protector | None
    in_struct: Type[PdModel] | None
    validation_fnc: DtoValidator | None
    transport: Transport
    response_fabric: Callable[[Any], HTTPResponse] | None

    def __init__(self,
                 transport: Transport,
                 protector: Protector = None,
                 in_struct: Type[PdModel] | None = None,
                 validation_fnc: DtoValidator = validate_dto,
                 response_fabric: Callable[[Any], HTTPResponse] = json):
        self.protector = protector
        self.transport = transport
        self.in_struct = in_struct
        self.validation_fnc = validation_fnc
        self.response_fabric = response_fabric

    def __find_plugins(self, req) -> List[RestPlugin]:
        find_plugins = []
        for plug in self.transport.plugins:
            if RestPlugin in plug.__class__.__mro__:
                plug = cast(RestPlugin, plug)
                for route_cfg in plug.routes_conf:
                    if route_cfg == PlugRouteConf(req.route.path, req.method):
                        find_plugins.append(plug)
        return find_plugins

    def __call__(self, target: HandlerType):
        @wraps(target)
        async def f(*args, **kwargs):
            req: Request = args[0]
            if len(args) > 1:
                kwargs['ws'] = args[1]
            prot_identity = await self.protector(req, self.transport) if self.protector else None
            if self.in_struct:
                validated = self.validation_fnc(self.in_struct, req)
            else:
                validated = None
            incoming = InputContext(req, validated, prot_identity, kwargs)
            ret_val = None
            try:
                plugins = self.__find_plugins(req)
                if plugins:
                    if settings.DEBUG:
                        loguru.logger.debug(
                            f"[{self.transport.__class__.__name__}::RequestHandler]: find plugins: {plugins}")
                    for plug in plugins:
                        if settings.DEBUG:
                            loguru.logger.debug(
                                f"[{self.transport.__class__.__name__}::RequestHandler] Call plugin {plug.name}")
                        ret_val = await plug.exec(target, incoming, self.transport, prev_plugin_result=ret_val)
            except RuntimeError as e:
                if settings.DEBUG:
                    loguru.logger.warning(f"RequestHandler{e}")
            if not ret_val:
                ret_val = await target(incoming, self.transport)
            return self.response_fabric(ret_val)

        return f


class CustomRouter(Router):
    _router_conf: Dict
    open_api: bool

    def __init__(self,
                 routes_config: Dict,
                 open_api: bool = False):
        super().__init__()
        self._router_conf = routes_config
        self.open_api = open_api

    @classmethod
    def set_serving_config(cls, sanic: Sanic, config, root_path="applied_files"):
        """Configure serving static files"""
        if not hasattr(config, 'serving') or not config.serving:
            return
        for dir_name, serv in config.serving.items():
            target = os.path.join(root_path, dir_name)
            if not os.path.exists(target):
                os.makedirs(target, exist_ok=True)
            for serv_path in serv:
                if serv_path.path:
                    serv_path_target = os.path.join(target, serv_path.path)
                else:
                    serv_path_target = target
                if serv_path.route:
                    if not os.path.isfile(serv_path_target):
                        raise Exception("Serve static as route is possible only for one file")
                    else:
                        def get_static_route(path: str):
                            def static_route(r, *args, **kwargs):
                                return file(path)

                            return static_route

                        sanic.add_route(get_static_route(serv_path_target), serv_path.uri)
                else:
                    if not os.path.exists(serv_path_target):
                        os.makedirs(serv_path_target, exist_ok=True)
                    sanic.static(serv_path.uri, file_or_directory=serv_path_target)

    def set_routes(self, transport: Transport):
        version_prefix = self._router_conf.get("version_prefix")
        version_prefix = version_prefix if version_prefix else "/api/v"
        for endpoint, versions in self._router_conf.get("endpoints").items():
            if not isinstance(versions, dict):
                continue
            for version, params in versions.items():
                if not isinstance(params, dict):
                    continue
                methods_confs = []
                endpoint_handler = params.pop("handler", None)
                endpoint_protector = params.pop("protector", None)
                endpoint_response_fabric = params.pop("response_fabric", None)
                for method_name, method_params in params.items():
                    if not isinstance(method_params, dict):
                        continue
                    target_func = method_params.get('handler')
                    target_func = target_func if target_func else endpoint_handler
                    # TODO: avoid deprecation in sanic
                    target_func.__name__ = method_name + target_func.__name__
                    protector = method_params.get("protector")
                    protector = protector if protector else endpoint_protector
                    in_dto = method_params.get("in_dto")
                    out_dto = method_params.get("out_dto")
                    response_fabric = method_params.get("response_fabric")
                    response_fabric = response_fabric if response_fabric else endpoint_response_fabric

                    # handler = self.__find_handler_by_name(services, method_conf.handler, prefix=method_prefix)
                    if response_fabric:
                        chain = CustomRequestHandler(transport,
                                                     protector=protector,
                                                     in_struct=in_dto,
                                                     response_fabric=response_fabric)(target_func)
                    else:
                        chain = CustomRequestHandler(transport,
                                                     protector=protector,
                                                     in_struct=in_dto)(target_func)
                    if self.open_api:
                        chain = add_openapi_spec(uri=endpoint,
                                                 method_name=method_name,
                                                 func=target_func,
                                                 handler=chain,
                                                 in_dto=in_dto,
                                                 out_dto=out_dto)
                    if method_name.lower() == 'websocket':
                        self.ctx.app.add_websocket_route(
                            handler=chain,
                            uri=endpoint,
                            version=version,
                            version_prefix=version_prefix
                        )
                    else:
                        self.ctx.app.add_route(
                            uri=endpoint,
                            methods={method_name.upper()},
                            handler=chain,
                            version=version,
                            version_prefix=version_prefix
                        )


class StatusCodes:
    APPLICATION_CODE = 409
    REPORT_CODE = 501


class CustomJSONRenderer(JSONRenderer):
    def _generate_output(self, *, full):
        output = {
            "description": self.title,
            "status": self.status,
            # "message": self.text,
            "error": getattr(self.exception, "context", {})
        }
        if not output['error'].get('type'):
            output['error']['type'] = getattr(self.exception, "error_type", "C")

        if not output['error'].get('class'):
            output['error']['class'] = getattr(self.exception, "default_class", 999)

        if not output['error'].get('subclass'):
            output['error']['subclass'] = getattr(self.exception, "default_subclass", 999)

        if not output['error'].get('code'):
            output['error'][
                'code'] = f"{output['error']['type']}-{output['error']['class']}-{output['error']['subclass']}"

        if self.text:
            if output.get('error'):
                if not output['error'].get('comment'):
                    output['error'].update({"comment": self.text})
            else:
                output['error'] = {"comment": self.text}

        if full:
            _, exc_value, __ = sys.exc_info()
            exceptions = []

            while exc_value:
                exceptions.append(
                    {
                        "type": exc_value.__class__.__name__,
                        "exception": str(exc_value),
                        "frames": [
                            {
                                "file": frame.filename,
                                "line": frame.lineno,
                                "name": frame.name,
                                "src": frame.line,
                            }
                            for frame in extract_tb(exc_value.__traceback__)
                        ],
                    }
                )
                exc_value = exc_value.__cause__

            output["path"] = self.request.path
            output["args"] = self.request.args
            output["exceptions"] = exceptions[::-1]

        return output


class CustomErrorHandler(ErrorHandler):
    def default(self, request, exception):
        """Convert ApplicationError to SanicException"""
        renderer = None
        if isinstance(exception, ApplicationError):
            if not isinstance(exception, SanicException):
                exception = type(exception.__class__.__name__,
                                 (SanicException,),
                                 {"message": exception.message if exception.message else "",
                                  "status_code": StatusCodes.APPLICATION_CODE,
                                  "error_type": exception.error_type,
                                  "default_class": exception.default_class,
                                  "default_subclass": exception.default_subclass, })(context=exception.context)
            renderer = CustomJSONRenderer
        else:
            self.log(request, exception)
        fallback = request.app.config.FALLBACK_ERROR_FORMAT
        return exception_response(
            request,
            exception,
            debug=settings.DEBUG,
            base=self.base,
            fallback=fallback,
            renderer=renderer
        )
