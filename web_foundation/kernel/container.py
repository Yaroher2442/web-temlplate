from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from web_foundation.config import GenericConfig
from web_foundation.extentions.addons.addon_loader import AddonsLoader
from web_foundation.kernel.dependency import Dependency
from web_foundation.kernel.messaging.channel import IChannel
from web_foundation.kernel.stage import ListenerRegistrator
from web_foundation.resources.files.interface import FilesResourceInterface
from web_foundation.resources.resource import Resource
from web_foundation.resources.stores.interface import DataStore
from web_foundation.utils.helpers import in_obj_classes, in_obj_subcls_of_dependencies


class DependencyContainer:
    app_config: Dependency[GenericConfig] = Dependency(instance_of=BaseModel)
    data_store: Dependency[DataStore] = Dependency(instance_of=DataStore)
    file_repository: Dependency[FilesResourceInterface] = Dependency(instance_of=FilesResourceInterface)
    addon_loader: Dependency[AddonsLoader] = Dependency(instance_of=AddonsLoader)

    def __init__(self, **kwargs):
        for dep, name in in_obj_classes(self, Dependency):
            dep_init = kwargs.get(name)
            if dep_init:
                dep.from_initialized(dep_init)

    @property
    def resources(self):
        for resource, name in in_obj_subcls_of_dependencies(self, Resource):
            if isinstance(resource, Dependency):
                resource = resource()
            yield resource

    async def before_app_run(self):
        pass

    def set_listeners(self, registrator: ListenerRegistrator):
        for dep, name in in_obj_classes(self, Dependency):
            if inited := dep():
                if hasattr(inited, "set_listeners"):
                    inited.set_listeners(registrator)

    async def init_resources(self, channel: IChannel | None = None):
        for resource in self.resources:
            await resource.init(self.app_config(), channel)

    async def shutdown_resources(self):
        for resource in self.resources:
            await resource.shutdown()

GenericDependencyContainer = TypeVar("GenericDependencyContainer", bound=DependencyContainer)
