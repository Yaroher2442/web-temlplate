from abc import abstractmethod, ABCMeta
from typing import Any, Dict, List

from web_foundation.logic.module import AbstractModule
from pydantic import BaseModel


class AbstractUseCase(metaclass=ABCMeta):
    _addictions: Dict[str, AbstractModule]
    name: str | None

    version: int
    method: str
    route: str
    in_model: BaseModel
    out_model: BaseModel

    roles: List[str]

    def raise_if_none(self, val: Any, ex: Exception = Exception("Item not found")):
        if not val:
            raise ex

    @abstractmethod
    async def execute(self, *args, **kwargs):
        pass

    @property
    def available(self):
        return all([i.available for i in self._addictions.values()])
