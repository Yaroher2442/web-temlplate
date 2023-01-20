import asyncio
import json
import re
from datetime import datetime
from datetime import time as DTime
from functools import wraps, partial
from inspect import isawaitable, iscoroutine, iscoroutinefunction
from pathlib import Path
from typing import Union, List, Type, Callable, Coroutine, Any

import loguru

from web_foundation.config import GenericConfig
from web_foundation.errors.app.application import InconsistencyError

# ------------------------------------------------STR_TO---------------------------------------------------------------
from web_foundation.kernel.dependency import Dependency


def str_to_list(string: str) -> Union[List[str], None]:
    if not ",":
        return None
    return string.split(",")


def str_to_bool(string: str) -> Union[bool, None]:
    try:
        if string.lower() == "false":
            return False
        elif string.lower() == "true":
            return True
        else:
            return None
    except Exception as e:
        return None


# ------------------------------------------------VALIDATE--------------------------------------------------------------


def validate_date(date: str, check_gt_now=True) -> str:
    try:
        if "." in date:
            _date = datetime.strptime(date, "%d.%m.%Y")
            date = _date.isoformat()
        else:
            _date = datetime.fromisoformat(date)
    except ValueError as exception:
        raise InconsistencyError(exception)
    if check_gt_now and datetime.now() > _date:
        raise InconsistencyError(message="Incorrect date")
    return date


def validate_time(str_time: str) -> str:
    try:
        t = DTime.fromisoformat(str_time)
    except ValueError as exception:
        raise InconsistencyError(exception)
    return str_time


def validate_datetime(date_time: str, check_gt_now=False) -> str:  # TODO add timezones
    format_types = ["%d", "%m", "%Y", "%H", "%M", "%S"]
    try:
        if "." in date_time and date_time.count(".") > 1:
            date_nums = [ddd for ddd in re.findall(r"(\d*)", date_time) if ddd]
            _date = datetime.strptime(' '.join(date_nums), ' '.join(format_types[:len(date_nums)]))
        else:
            _date = datetime.fromisoformat(date_time)
        date = _date.astimezone().isoformat()
    except ValueError as exception:
        raise InconsistencyError(exception)
    if check_gt_now and datetime.now() > _date:
        raise InconsistencyError(message="Incorrect datetime")
    return date


# ------------------------------------ OS ----------------------------------------

def load_config(conf_path: Path, config_model: Type[GenericConfig]) -> GenericConfig:
    """
    Load environment config to user in
    :param conf_path:
    :param config_model: BaseModel to cast json file to pydantic
    :return: None
    """
    with open(conf_path, "r") as _json_file:
        conf = config_model(**json.loads(_json_file.read()))
        return conf


# ----------------------------------------------SOME-------------------------------

def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])


def in_obj_subclasses(obj: object | Type, target_cls: Type):
    try:
        for i in dir(obj):
            if not i.startswith("__"):
                item = getattr(obj, i)
                if item.__class__ in all_subclasses(target_cls):
                    yield item, i
    except Exception as e:
        raise e


def is_in_base_classes(obj: object | Type, target_cls: Type) -> bool:
    try:
        if obj.__class__ == target_cls:
            return True
        return target_cls in obj.__class__.__mro__
    except Exception as e:
        raise e


def in_obj_subcls_of_dependencies(obj: object | Type, target_cls: Type):
    try:
        for i in dir(obj):
            if not i.startswith("__"):
                item = getattr(obj, i)
                if isinstance(item, Dependency):
                    test = item
                    item = item()
                if item.__class__ in all_subclasses(target_cls):
                    yield item, i
    except Exception as e:
        raise e


def in_obj_classes(obj: object | Type, target_cls: Type):
    try:
        for i in dir(obj):
            item = getattr(obj, i)
            if item.__class__ == target_cls:
                yield item, i
    except Exception as e:
        raise e


def in_obj_cls_items(obj: object | Type, target_cls: Type):
    try:
        for i in dir(obj):
            print()
            item = getattr(obj, i)
            cls = getattr(obj, i).__class__
            if item.__class__ == target_cls or cls in all_subclasses(target_cls):
                yield item, i
    except Exception as e:
        raise e


def get_callable_from_fnc(fnc: Callable[..., Coroutine[Any, Any, Any]] | partial):
    caller = fnc
    if iscoroutine(fnc) or isawaitable(fnc):
        @wraps(fnc)
        def __call(*args, **kwargs):
            asyncio.run(fnc(*args, **kwargs))

        caller = __call

    elif iscoroutinefunction(fnc):
        @wraps(fnc)
        def __call(*args, **kwargs):
            asyncio.run(fnc(*args, **kwargs))

        caller = __call

    return caller
