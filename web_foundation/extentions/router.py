import os
from dataclasses import dataclass
from typing import Dict, Any
from typing import List, Type, Callable, Generic

from pydantic import BaseModel
from sanic import Sanic, HTTPResponse, file
from sanic.router import Router

from web_foundation.extentions.addons.addon_loader import AddonsLoader
from web_foundation.extentions.openapi_spec import add_openapi_spec
from web_foundation.extentions.request_handler import Protector, HandlerType, GenericRequestHandler
from web_foundation.kernel.container import GenericDependencyContainer


@dataclass
class RouteMethodConf:
    method_name: str
    protector: Protector | None
    in_dto: Type[BaseModel] | None
    out_dto: Type[BaseModel] | None
    handler: HandlerType
    response_fabric: Callable[[Any], HTTPResponse] | None
    version_prefix: str | None
    version: str | None


@dataclass
class RouteConf:
    app_name: str
    path: str
    methods: List[RouteMethodConf]


class ExtRouter(Router, Generic[GenericRequestHandler]):
    ext_handler: GenericRequestHandler
    parsed_routes: List[RouteConf]

    def __init__(self, ext_handler: GenericRequestHandler):
        super().__init__()
        self.ext_handler = ext_handler
        self.parsed_routes = []

    def _parse(self):
        raise NotImplementedError

    def parse(self):
        self._parse()

    def apply_routes(self, app: Sanic, container: GenericDependencyContainer, *args, **kwargs):
        raise NotImplementedError


class DictRouter(ExtRouter, Generic[GenericRequestHandler]):
    _router_conf: Dict
    addon_loader: AddonsLoader | None
    versioning: bool
    open_api: bool

    def __init__(self,
                 routes_config: Dict,
                 ext_handler: GenericRequestHandler,
                 versioning: bool = True,
                 open_api: bool = False):
        super().__init__(ext_handler)
        self._router_conf = routes_config
        self.versioning = versioning
        self.open_api = open_api

    def _parse(self):
        for app_route in self._router_conf.get("apps"):
            version_prefix = app_route.get("version_prefix")
            version_prefix = version_prefix if version_prefix else "/api/v"
            if not isinstance(app_route, dict):
                continue
            for endpoint, versions in app_route.get("endpoints").items():
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
                        protector = method_params.get("protector")
                        protector = protector if protector else endpoint_protector
                        in_dto = method_params.get("in_dto")
                        out_dto = method_params.get("out_dto")
                        response_fabric = method_params.get("response_fabric")
                        response_fabric = response_fabric if response_fabric else endpoint_response_fabric

                        methods_confs.append(RouteMethodConf(method_name=method_name,
                                                             protector=protector,
                                                             in_dto=in_dto,
                                                             out_dto=out_dto,
                                                             handler=target_func,
                                                             response_fabric=response_fabric,
                                                             version_prefix=version_prefix,
                                                             version=version
                                                             ))

                    route = RouteConf(app_name=app_route.get("app_name"),
                                      path=endpoint,
                                      methods=methods_confs)
                    self.parsed_routes.append(route)

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

    def apply_routes(self, app: Sanic, container: GenericDependencyContainer = None, addon_manager: AddonsLoader = None,
                     **kwargs):
        for route_conf in self.parsed_routes:
            for method_conf in route_conf.methods:
                if method_conf.response_fabric:
                    chain = self.ext_handler(protector=method_conf.protector,
                                             in_struct=method_conf.in_dto,
                                             addon_manager=addon_manager,
                                             response_fabric=method_conf.response_fabric,
                                             container=container)(method_conf.handler)
                else:
                    chain = self.ext_handler(protector=method_conf.protector,
                                             addon_manager=addon_manager,
                                             in_struct=method_conf.in_dto,
                                             container=container)(method_conf.handler)
                if self.open_api:
                    chain = add_openapi_spec(uri=route_conf.path,
                                             method_name=method_conf.method_name,
                                             func=method_conf.handler,
                                             handler=chain,
                                             in_dto=method_conf.in_dto,
                                             out_dto=method_conf.out_dto)

                if self.versioning:
                    app.add_route(uri=route_conf.path,
                                  methods={method_conf.method_name.upper()},
                                  handler=chain,
                                  version_prefix=method_conf.version_prefix,
                                  version=method_conf.version)
                else:
                    app.add_route(uri=route_conf.path,
                                  methods={method_conf.method_name.upper()},
                                  handler=chain)
