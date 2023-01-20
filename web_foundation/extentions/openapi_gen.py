import os, os.path
from json import dump, load

import loguru
from sanic import Request, json
from sanic_routing import Route
from sanic_ext.config import add_fallback_config
from sanic_ext.extensions.openapi.blueprint import blueprint_factory
from sanic_ext.extensions.openapi.builders import SpecificationBuilder
from sanic_ext.extensions.openapi import extension
from web_foundation import settings


def generate_openapi(app, json_filepath="openapi.json"):
    """
    Generate openapi json
    NOTE: After generation you can't start sanic app

    :param app: kernel.app.App
    :return:
    """
    settings.OPENAPI = True
    app.sanic.router.open_api = True
    app.sanic.router.parse()
    app.sanic.router.apply_routes(app.sanic, app.container)
    app.sanic.finalize()
    app.sanic.config = add_fallback_config(app.sanic)
    oas_bp = blueprint_factory(app.sanic.config)
    for listener in oas_bp._future_listeners:
        if "build_spec" == listener.listener.__name__:
            listener.listener(app.sanic, None)
    oas_json = SpecificationBuilder().build(app.sanic).serialize()
    with open(json_filepath, 'w') as f:
        dump(oas_json, f)


def add_openapi(app):
    """
    Overwrite Openapi sanic extension startup method for reading openapi json from file

    :param app: kernel.app.App
    :return:
    """
    if not app.config.openapi_filepath:
        app.sanic.router.open_api = False
        app.sanic.config.OAS = False
        return
    if not os.path.exists(app.config.openapi_filepath):
        loguru.logger.error('OPENAPI FILE NOT FOUND')
        app.sanic.router.open_api = False
        app.sanic.config.OAS = False
        return

    app.sanic.router.open_api = True
    app.sanic.config.OAS = True

    async def spec(request: Request):
        with open(app.config.openapi_filepath) as f:
            return json(load(f))

    if hasattr(app.sanic.config, "OAS_URL_PREFIX") and hasattr(app.sanic.config, "OAS_URI_TO_JSON"):
        for route_path, route in app.sanic.router.routes_all.items():
            route: Route
            if route.uri == f"{app.sanic.config.OAS_URL_PREFIX}{app.sanic.config.OAS_URI_TO_JSON}":
                route.handler = spec

    def startup(self, bootstrap) -> None:
        if self.app.config.OAS:
            self.bp = blueprint_factory(self.app.config)
            for route in self.bp._future_routes:
                if route.uri == self.app.config.OAS_URI_TO_JSON:
                    self.bp._future_routes.remove(route)
                    self.bp.add_route(spec, self.app.config.OAS_URI_TO_JSON)
                    break
            for listener in self.bp._future_listeners:
                if "build_spec" == listener.listener.__name__:
                    self.bp._future_listeners.remove(listener)
            self.app.blueprint(self.bp)
            bootstrap._openapi = SpecificationBuilder()

    extension.OpenAPIExtension.startup = startup
