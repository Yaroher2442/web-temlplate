from typing import Any, Dict, Mapping

from pydantic import BaseModel
from tortoise import Model


class CDto(BaseModel, Mapping):
    _dd: Dict[str, Any] = {}

    def __len__(self):
        return len(self.dict())

    def __getitem__(self, k):
        return self.dict().get(k)

    def __iter__(self):
        return iter(self.dict())


class ExportedModel(Model):
    pass
