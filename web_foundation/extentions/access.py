import asyncio
import json as py_json
from typing import List, Type, Coroutine, Callable, Any

from sanic.exceptions import NotFound

from web_foundation.extentions.request_handler import InputContext
from web_foundation.resources.database.model_loader import ModelLoader
from web_foundation.resources.database.models import AbstractDbModel
from web_foundation.kernel.container import GenericDependencyContainer
from web_foundation.kernel.container import DependencyContainer

AccessCallback = Callable[
    [AbstractDbModel | List[AbstractDbModel] | None, InputContext, Type[ModelLoader]], Coroutine[
        Any, Any, None]]


async def exec_access(inc: InputContext,
                      model: Type[AbstractDbModel],
                      container: GenericDependencyContainer = None,
                      fetch_fields: List[str] = None,
                      drop_cols: List[str] = None,
                      full_info: bool = False,
                      middleware: Type[ModelLoader] = ModelLoader,
                      external_callback: AccessCallback = None,
                      retrieved_callback: AccessCallback = None
                      ):
    """
    Access to models
    """
    match inc.request.method:
        case "GET":
            kwargs = inc.r_kwargs
            entity_id = kwargs.pop("entity_id", None)
            if entity_id is None:
                limit = inc.request.args.get("limit")
                offset = inc.request.args.get("offset")
                limit = int(limit) if limit and limit.isdigit() else 100
                offset = int(offset) if offset and offset.isdigit() else None
                # order_by = inc.request.args.get("order_by")  # for openapi. Variable forwarded to read_all in kwargs
                for ar, val in inc.request.args.items():
                    if ar in ["limit", "offset"]:
                        continue
                    val = val[0]
                    if val.lower() == 'false':
                        val = False
                    elif val.lower() == 'true':
                        val = True
                    elif val.lower() == 'none':
                        val = None
                    elif val.isdigit():
                        val = int(val)
                    elif "." in val and val.replace('.', '').isdigit():
                        val = float(val)
                    elif val.startswith("["):
                        val = py_json.loads(val)
                    kwargs[ar] = val

                retrieved_all, total = await middleware.read_all(model, inc.identity, limit, offset,
                                                                 container=container,
                                                                 fetch_fields=fetch_fields, **kwargs)
                if external_callback:
                    asyncio.create_task(external_callback(retrieved_all, inc, middleware))
                if retrieved_callback:
                    return await retrieved_callback(retrieved_all, inc, middleware)
                res = [await model.values_dict(drop_cols=drop_cols, full_info=full_info) for model in retrieved_all]
                return res, total
            retrieved = await middleware.read(model, entity_id, inc.identity,
                                              container=container, fetch_fields=fetch_fields, **kwargs)
            if not retrieved:
                raise NotFound()

        case "POST":
            retrieved = await middleware.create(model, inc.identity, inc.dto,
                                                container=container, **inc.r_kwargs)

        case "PATCH":
            entity_id = inc.r_kwargs.pop("entity_id")
            retrieved = await middleware.update(model, entity_id, inc.identity, inc.dto,
                                                container=container, **inc.r_kwargs)

        case "DELETE":
            entity_id = inc.r_kwargs.pop("entity_id")
            retrieved = await middleware.delete(model, entity_id, inc.identity,
                                                container=container, **inc.r_kwargs)

    if external_callback:
        asyncio.create_task(external_callback(retrieved, inc, middleware))
    if retrieved_callback:
        return await retrieved_callback(retrieved, inc, middleware)
    if isinstance(retrieved, list):
        return [await i.values_dict(drop_cols=drop_cols, full_info=full_info) for i in retrieved]
    return await retrieved.values_dict(drop_cols=drop_cols, full_info=full_info)


async def exec_access_with_total(inc: InputContext,
                                 model: Type[AbstractDbModel],
                                 container: GenericDependencyContainer = None,
                                 fetch_fields: List[str] = None,
                                 drop_cols: List[str] = None,
                                 full_info: bool = False,
                                 middleware: Type[ModelLoader] = ModelLoader,
                                 external_callback: AccessCallback = None,
                                 retrieved_callback: AccessCallback = None):
    """Return from read_all dict with "items" and "total" """
    result = await exec_access(inc=inc, model=model, container=container,
                               fetch_fields=fetch_fields,
                               drop_cols=drop_cols,
                               full_info=full_info,
                               middleware=middleware,
                               external_callback=external_callback,
                               retrieved_callback=retrieved_callback)
    if inc.request.method == "GET" and isinstance(result, tuple):
        return {"items": result[0], "total": result[1]}
    return result
