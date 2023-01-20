import inspect
import re
from copy import deepcopy, copy
from functools import wraps
from typing import Callable, Type

import sanic_ext
from sanic_ext.extensions.openapi.types import Schema, Array
from tortoise import Model
from web_foundation import settings


def set_access_endpoints(access_endpoints: dict, models,
                         db_model_responses: dict[Type[Model]], get_out_struct_func: Callable,
                         get_list_out_struct_func: Callable, drop_filter_fields: list[str],
                         scope: str = None):
    params_filters = {
        "not": Schema(description="not definition", type="string"),

        "in": Array(Schema(description="any field value", type="string"),
                    description="checks if value of field is in passed list"),

        "not_in": Array(Schema(description="any field value", type="string"),
                        description="not in definition"),

        "gte": Schema(description="greater or equals than passed value", type="string"),

        "gt": Schema(description="greater than passed value", type="string"),

        "lte": Schema(description="lower or equals than passed value", type="string"),

        "lt": Schema(description="lower than passed value", type="string"),

        "range": Array(Schema(description="any field value", type="string"),
                       description="between and given two values",
                       maxItems=2, minItems=2),

        "isnull": Schema(description="field is null", type="boolean"),

        "not_isnull": Schema(description="field is not null", type="boolean"),

        "contains": Schema(description="field contains specified substring", type="string"),

        "icontains": Schema(description="case insensitive contains", type="string"),

        "startswith": Schema(description="if field starts with value", type="string"),

        "istartswith": Schema(description="case insensitive startswith", type="string"),

        "endswith": Schema(description="if field ends with value", type="string"),

        "iendswith": Schema(description="case insensitive endswith", type="string"),

        "iexact": Schema(description="case insensitive equals", type="string"),
    }

    for endpoint, versions in deepcopy(access_endpoints).items():
        for version, params in deepcopy(versions).items():
            endpoint_handler = params.get("handler")
            endpoint_protector = params.get("protector")
            endpoint_response_fabric = params.get("response_fabric")
            if scope:
                access_endpoints[endpoint][version].update({'scope': scope})
            for method_name, param in deepcopy(params).items():
                if not isinstance(param, dict):
                    continue
                target_func = param.get('handler')
                target_func = target_func if target_func else endpoint_handler
                method_protector = param.get("protector")
                method_protector = method_protector if method_protector else endpoint_protector
                if param.get('out_dto'):
                    out_struct = param.get('out_dto')
                elif not hasattr(settings, "OPENAPI") or not getattr(settings, "OPENAPI"):
                    out_struct = None
                else:
                    # get out_struct from model name (in exec_access args)
                    func_text = inspect.getsource(target_func)
                    model_name = re.findall(r"context, (\w*)", func_text)
                    if model_name:
                        model = getattr(models, model_name[0])
                        out_struct = db_model_responses.get(model)
                        if not out_struct:
                            out_struct = get_out_struct_func(model)
                        access_endpoints[endpoint][version][method_name]['out_dto'] = out_struct
                        param['out_dto'] = out_struct
                    else:
                        out_struct = None

                # add routes with <entity_id>
                if method_name in ['patch', 'delete', 'get']:
                    if method_name != 'get':
                        access_endpoints[endpoint][version].pop(method_name)
                    if not access_endpoints.get(f"{endpoint}/<entity_id:int>"):
                        access_endpoints.update({f"{endpoint}/<entity_id:int>": {}})

                    if not access_endpoints[f"{endpoint}/<entity_id:int>"].get(version):
                        access_endpoints[f"{endpoint}/<entity_id:int>"].update({
                            version: {
                                'handler': endpoint_handler,
                                'protector': endpoint_protector,
                                'response_fabric': endpoint_response_fabric
                            }
                        })
                    access_endpoints[f"{endpoint}/<entity_id:int>"][version].update({method_name: copy(param)})
                    if scope:
                        access_endpoints[f"{endpoint}/<entity_id:int>"][version]['scope'] = scope

                    if method_name == 'get' and out_struct:
                        access_endpoints[endpoint][version][method_name]['out_dto'] = get_list_out_struct_func(
                            out_struct)
                    if not access_endpoints[endpoint].get(version):
                        access_endpoints[endpoint].pop(version)

                def new_wrap(func):  # wrapper to change handler signature (need for openapi)
                    @wraps(func)
                    def wr(*args, **kwargs):
                        return func(*args, **kwargs)

                    return wr

                if method_name == 'get' and 'entity_id' not in endpoint and out_struct:
                    get_access_func = new_wrap(target_func)
                    get_access_func.__name__ = f"{get_access_func.__name__}__read"
                    for field_model in out_struct.__fields__.values():
                        if field_model.name in drop_filter_fields:
                            continue
                        for filter, schema in params_filters.items():
                            schema.type = str
                            schema.example = f"{field_model.name}__{filter}"
                            get_access_func = sanic_ext.openapi.parameter(
                                name=f"{field_model.name}__{filter}", schema=schema)(get_access_func)
                    access_endpoints[endpoint][version][method_name]['handler'] = get_access_func


def set_security_scheme(routes_dict: dict, protectors_dict: dict[Callable, dict[str, dict | list]]):
    """
    protectors_dict: {protector: {"scheme": dict, Optional("additional_parameters": list[Decorator])}
        example: {protector: {
                    "scheme": {"cookieAuth": ["user"]},
                    "additional_parameters": [sanic_ext.openapi.parameter(
                                name=f"session", schema=int, location="cookie", required=True)]
    """
    for app_route in routes_dict.get("apps"):
        secured_handlers = []
        for endpoint, versions in app_route.get("endpoints").items():
            for version, params in versions.items():
                endpoint_handler = params.get("handler", None)
                endpoint_protector = params.get("protector", None)
                for method_name, method_params in params.items():
                    if not isinstance(method_params, dict):
                        continue
                    target_func = method_params.get('handler')
                    target_func = target_func if target_func else endpoint_handler
                    protector = method_params.get("protector")
                    protector = protector if protector else endpoint_protector
                    for _protector, protector_params in protectors_dict.items():
                        if protector == _protector:
                            if secure_params := protector_params.get("additional_parameters"):
                                if target_func not in secured_handlers:
                                    for secure_param in secure_params:
                                        secure_param(target_func)
                                secured_handlers.append(target_func)
                            if scheme := protector_params.get("scheme"):
                                sanic_ext.openapi.secured(scheme)(target_func)
