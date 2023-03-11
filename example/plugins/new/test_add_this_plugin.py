import os
from typing import Any

import loguru

from web.kernel.types import GenAsyncCall
from web.trend.rest.custom import InputContext, RestPlugin, PlugRouteConf
from web.trend.rest.transport import RestTransport

PLUGIN_NAME = "TestADDPlugin"


class TestADDPlugin(RestPlugin):
    routes_conf = [PlugRouteConf("api/v1/test", "get")]

    async def exec(self, handler: GenAsyncCall,
                   ctx: InputContext,
                   transport: RestTransport,
                   prev_plugin_result: Any = None):
        loguru.logger.warning(f"{self} EXEC ADDED PLUGIN {os.getpid()}")
        loguru.logger.warning(prev_plugin_result)
        return {"posh": "nahuy", "pid": os.getpid()}
