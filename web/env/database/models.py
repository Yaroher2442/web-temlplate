from enum import Enum
from ipaddress import IPv4Address
from typing import TypeVar, List, Any, Dict
from uuid import UUID

from tortoise import fields
from tortoise.fields import ReverseRelation
from tortoise.models import Model
from tortoise.queryset import QuerySet

from .utils import string_from_db_date


class AbstractDbModel(Model):
    app_name: str = ""
    id = fields.IntField(pk=True)

    async def values_dict(self, m2m_fields: bool = False, fk_fields: bool = False, backward_fk_fields=False,
                          drop_cols: List[str] = None, iso_date_format=True,
                          all_fetched=True, full_info=False) -> Dict[str, Any]:
        def _field_in_drop(field: str):
            if not full_info and drop_cols and field in drop_cols:
                return True
            return False

        t_d = {}
        for k, v in self.__dict__.items():
            if _field_in_drop(k):
                continue
            v = string_from_db_date(v, iso_date_format)
            if isinstance(v, UUID):
                v = str(v)
            if isinstance(v, IPv4Address):
                v = str(v)
            if isinstance(v, Enum):
                v = v.value
            if not k.startswith('_'):
                t_d.update({k: v})
        if fk_fields or all_fetched:
            for field in self._meta.fk_fields:
                if _field_in_drop(field):
                    continue
                model = getattr(self, field)
                if isinstance(model, QuerySet):
                    if not fk_fields and all_fetched:
                        continue
                    model = await model
                if model:
                    t_d.update({field: await model.values_dict()})
        if m2m_fields or all_fetched:
            for field in self._meta.m2m_fields:
                if _field_in_drop(field):
                    continue
                models = getattr(self, field)
                if not models._fetched:
                    if not m2m_fields and all_fetched:
                        continue
                    models = await models
                t_d.update({field: [await i.values_dict() for i in models if i]})
        if backward_fk_fields or all_fetched:
            for field in self._meta.backward_fk_fields:
                if _field_in_drop(field):
                    continue
                model = getattr(self, field)
                if isinstance(model, ReverseRelation) and not model._fetched:
                    if not backward_fk_fields and all_fetched:
                        continue
                    model = await model.all()
                if model:
                    t_d.update({field: [await i.values_dict() for i in model if i]})
        return t_d

    @classmethod
    def relate(cls, model_str: str):
        return f"{cls.app_name}.{model_str}"

    class Meta:
        abstract = True


GenericDbType = TypeVar("GenericDbType", bound=AbstractDbModel, contravariant=True)


class ConcurrentEntity(AbstractDbModel):
    updated_at = fields.DatetimeField(null=False)

