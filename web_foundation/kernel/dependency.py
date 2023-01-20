from __future__ import annotations

from typing import Generic, TypeVar
from typing import Type

T = TypeVar("T")


class Dependency(Generic[T]):  # type: ignore
    _initialized: T | None = None
    default: T | None
    instance_of: Type[T] | None

    def __init__(self, instance_of: Type[T] = None, default: T = None, **kwargs):
        self.instance_of = instance_of
        self.default = default
        self._initialized = self._initialized

    def __call__(self, *args, **kwargs) -> T:
        # if not self._initialized and not self.default:
        #     raise AttributeError("Dependency must me initialized with from_initialized() or with default kwarg")
        if not self._initialized:
            return self.default
        return self._initialized

    def from_initialized(self, obj) -> Dependency[T]:
        if not isinstance(obj, self.instance_of) or not issubclass(obj.__class__, self.instance_of):
            raise AttributeError("Dependency must init with same instance as instance_of or nested cls")
        self._initialized = obj
        return self

    @property
    def initialized(self) -> T:
        return self._initialized
