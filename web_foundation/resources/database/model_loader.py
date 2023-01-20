from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Awaitable, Any
from typing import List, TypeVar, Tuple, Generic

from pydantic import BaseModel as PdModel
from tortoise.exceptions import IntegrityError, FieldError, OperationalError
from tortoise.expressions import RawSQL
from tortoise.queryset import QuerySet, MODEL

from web_foundation.errors.app.application import InconsistencyError
from web_foundation.extentions.request_handler import ProtectIdentity
from web_foundation.kernel.container import GenericDependencyContainer
from web_foundation.resources.database.models import GenericDbType, ConcurrentEntity
from web_foundation.resources.database.utils import integrity_error_format

EntityId = TypeVar("EntityId", bound=int)


async def retry_dummy(dummy: Any) -> bool:
    return False


@dataclass
class AccessProtectIdentity(Generic[GenericDbType], ProtectIdentity):
    pass


class ModelLoader(Generic[GenericDbType]):

    @classmethod
    async def fetch_related(cls, model: GenericDbType, query: QuerySet[MODEL],
                            fetch_fields: List[str] | None = None) -> QuerySet[MODEL]:
        if fetch_fields:
            for_select = {field for fk_field in model._meta.fk_fields for field in fetch_fields if
                          fk_field == field}
            for_prefetch = set(fetch_fields) - for_select
            if for_select:
                query = query.select_related(*for_select)
            if for_prefetch:
                query = query.prefetch_related(*for_prefetch)
        return query

    @staticmethod
    async def get_entity(model: GenericDbType,
                         entity_id: EntityId,
                         protection: AccessProtectIdentity = None) -> GenericDbType:  # TODO TYPED USER
        entity = await model.get_or_none(id=entity_id)
        if not entity:
            raise InconsistencyError(message=f"{model.__name__} not found")  # type: ignore
        return entity

    @classmethod
    async def create(cls, model: GenericDbType, protection: AccessProtectIdentity, dto: PdModel,
                     container: GenericDependencyContainer = None,
                     **kwargs) -> GenericDbType:
        entity_kwargs = {}
        m2m_fields = {}
        for field, value in dto.dict().items():
            if value is None:
                continue
            if field.endswith('_id') or field.endswith('_ids'):
                raw_field = field[:field.find("_id")]
                if raw_field in model._meta.m2m_fields:
                    m2m_model = model._meta.fields_map[raw_field].related_model
                    m2m_model = m2m_model if m2m_model != model else model._meta.fields_map[raw_field].model
                    if not isinstance(value, (list, set)):
                        value = [value]
                    m2m_entities = await m2m_model.filter(id__in=value)
                    if len(m2m_entities) != len(value):
                        raise InconsistencyError(message=f"Some {m2m_model.__name__} not found")
                    m2m_fields[raw_field] = m2m_entities
                else:
                    entity_kwargs[field] = value
            else:
                entity_kwargs[field] = value
        try:
            entity = await model.create(**entity_kwargs)
        except IntegrityError as exception:
            raise integrity_error_format(exception)
        except ValueError as exception:
            raise InconsistencyError(exception)

        for m2m_field, m2m_entities in m2m_fields.items():
            await getattr(entity, m2m_field).add(*m2m_entities)
        return entity

    @classmethod
    async def read(cls, model: GenericDbType, entity_id: EntityId, protection: AccessProtectIdentity,
                   container: GenericDependencyContainer = None,
                   fetch_fields: List[str] | None = None,
                   **kwargs) -> GenericDbType | None:
        query = model.filter(id=entity_id)
        if kwargs:
            query = query.filter(**kwargs)
        query = await cls.fetch_related(model, query, fetch_fields)
        try:
            entity = await query.first()
        except FieldError:
            raise InconsistencyError(message="Incorrect filter")
        except OperationalError:
            raise InconsistencyError(message="Incorrect filter value")
        return entity

    @classmethod
    async def read_all(cls, model: GenericDbType, protection: AccessProtectIdentity, limit: int = None,
                       offset: int = None,
                       container: GenericDependencyContainer = None,
                       fetch_fields: List[str] = None,
                       **kwargs) -> Tuple[List[GenericDbType], int]:
        query = model.filter()
        if kwargs:
            if "order_by" in kwargs:
                try:
                    query = query.order_by(kwargs.pop("order_by"))
                except FieldError:
                    raise InconsistencyError(message=f"Incorrect field in order_by")
            query = query.filter(**kwargs)

        if limit:
            query = query.limit(limit)
        if offset:
            query = query.offset(offset)
        query = await cls.fetch_related(model, query, fetch_fields)
        query = query.distinct()
        try:
            entities = await query
            query._limit = None
            query._offset = None
            query._orderings = []
            query = query.annotate(count=RawSQL(f'COUNT(DISTINCT "{model._meta.db_table}"."id")')).values('count')  # what if model haven't id?
            res = await query
            total = res[0].get('count')
            # ------------------------------------ #
        except FieldError:
            raise InconsistencyError(message="Incorrect filter")
        except OperationalError:
            raise InconsistencyError(message="Incorrect filter value")
        return entities, total

    @classmethod
    async def update(cls, model: GenericDbType, entity_id: EntityId, protection: AccessProtectIdentity, dto: PdModel,
                     container: GenericDependencyContainer = None,
                     **kwargs) -> GenericDbType:
        entity = await cls.get_entity(model, entity_id, protection=protection)
        m2m_fields = {}
        entity_kwargs = {field: value for field, value in dto.dict().items() if value is not None}
        for field, value in entity_kwargs.copy().items():
            if field.endswith('_id') or field.endswith('_ids'):
                raw_field = field[:field.find("_id")]
                if raw_field in model._meta.m2m_fields:
                    m2m_model = model._meta.fields_map[raw_field].related_model
                    m2m_model = m2m_model if m2m_model != model else model._meta.fields_map[raw_field].model
                    if not isinstance(value, (list, set)):
                        value = [value]
                    m2m_entities = await m2m_model.filter(id__in=value)
                    if len(m2m_entities) != len(value):
                        raise InconsistencyError(message=f"Some {m2m_model.__name__} not found")
                    m2m_fields[raw_field] = m2m_entities
                    entity_kwargs.pop(field)
                    continue
            setattr(entity, field, value)
        try:
            await entity.save(update_fields=list(entity_kwargs.keys()))
        except IntegrityError as exception:
            raise integrity_error_format(exception)
        except ValueError as exception:
            raise InconsistencyError(exception)
        for m2m_field, m2m_entities in m2m_fields.items():
            await getattr(entity, m2m_field).clear()
            await getattr(entity, m2m_field).add(*m2m_entities)
        return entity

    @classmethod
    async def delete(cls, model: GenericDbType, entity_id: EntityId, protection: AccessProtectIdentity,
                     container: GenericDependencyContainer = None,
                     **kwargs) -> GenericDbType:
        assert entity_id is not None
        entity = await cls.get_entity(model, entity_id, protection=protection)
        await entity.delete()
        return entity

    @classmethod
    async def concurrent_update(cls, query: QuerySet, should_retry: Callable[[Any], Awaitable[bool]] = retry_dummy,
                                **kwargs):
        """
            This function is designed to apply updates to database objects in concurrent manner
            and uses Read-Modify-Write Pattern (RMW).

            It's implemented in three basic steps:
            1. Read object -> acquire/own it;
            2. Modify local copy;
            3. Apply updates only if we still own it (we have it's latest version)

            Step 3 may fail in case when concurrency detected:
            some other database session modified target object
            while we were modifying our local copy, which means
            we do not 'own' the object and must refresh it
            in order to get the latest version.

            It is perceived by comparing local 'updated_at' field
            with it's actual value at step 3.
            So the typical produced query is going to look like:
            update table set value=x where updated_at=<our local updated_at value>

            'query' is required to contain some filtering expression
            'apply' must contain kwargs to be applied in case of success
            'should_retry' functor can be provided as guard who checks retry neccesarity

            NOTE: To keep database consistency regarding
            concurrently accessed objects - every code must MODIFY
            such objects only through this function.

            NOTE: requires connections to use 'read committed' policy
        """
        while True:
            entity: ConcurrentEntity = await query.first()
            if not entity:
                return None

            kwargs.update({'updated_at': datetime.now()})
            done = await query.filter(updated_at=entity.updated_at) \
                .update(**kwargs)

            if done:
                return await query.first()
            elif not await should_retry(query):
                return None
