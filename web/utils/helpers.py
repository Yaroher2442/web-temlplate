import asyncio
from functools import wraps, partial
from inspect import isawaitable, iscoroutine, iscoroutinefunction
from typing import Union, List, Type, Callable, Coroutine, Any


# ------------------------------------------------STR_TO---------------------------------------------------------------


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
