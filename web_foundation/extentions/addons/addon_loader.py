from __future__ import annotations
from copy import copy
from importlib.abc import FileLoader
from importlib.util import module_from_spec
from importlib.util import spec_from_loader
from pathlib import Path
from types import ModuleType
from typing import List

import loguru
from loguru import logger
from web_foundation import settings
from web_foundation.resources.stores.events import StoreUpdateEvent
from web_foundation.resources.files.interface import FilesResourceInterface
from web_foundation.resources.stores.interface import DataStore


class ApiAddon:
    source: str
    imported: ModuleType | None

    target: str
    name: str
    filename: str
    enabled: bool = False

    before: bool = False
    override: bool = False
    after: bool = False

    def __init__(self, filename: str, source: str, name: str = None):
        self.name = name
        self.filename = filename
        self.source = source
        self.target = ""

    def import_it(self, spec):
        try:
            imported = module_from_spec(spec)
            spec.loader.exec_module(imported)
            self.imported = imported
            if hasattr(self.imported, "before"):
                self.before = True
            if hasattr(self.imported, "after"):
                self.after = True
            if hasattr(self.imported, "override"):
                self.override = True
        except Exception as e:
            self.enabled = False
            loguru.logger.error(f"Can't import plugin \"{self.name}\". Exception: {e}")

    def drop_imported(self):
        self.imported = None
        self.before = False
        self.override = False
        self.after = False

    async def exec_before(self, context, container):
        try:
            if self.before:
                await self.imported.before(context, container)
        except Exception as e:
            loguru.logger.error(f"Can't run plugin \"{self.name}\". Exception: {e}")

    async def exec_after(self, context, container, target_result):
        try:
            if self.after:
                await self.imported.after(context, container, target_result)
        except Exception as e:
            loguru.logger.error(f"Can't run plugin \"{self.name}\". Exception: {e}")

    async def exec_override(self, context, container):
        try:
            if self.override:
                return await self.imported.override(context, container)
        except Exception as e:
            loguru.logger.error(f"Can't run plugin \"{self.name}\". Exception: {e}")

    def __repr__(self):
        return f"ApiMiddleware({self.name} on {self.target})"

    def __eq__(self, other: ApiAddon):
        return self.name == other.name


class SourceCodeLoader(FileLoader):
    def __init__(self, fullname: str, source):
        super().__init__(fullname, source)
        self.path = source

    def get_source(self, fullname: str) -> str | bytes:
        return self.path


class AddonsLoader:
    addons_path: Path
    files_repo: FilesResourceInterface = None
    store: DataStore = None

    def __init__(self, addons_dir_path: Path, files_repo: FilesResourceInterface, store: DataStore):
        self.addons_path = addons_dir_path
        self.files_repo = files_repo
        self.store = store

    async def update_store(self, middlewares, send_event=True):
        to_sent = [copy(mdw) for mdw in middlewares]
        for mdw in to_sent:
            mdw.imported = None
        await self.store.set_item("addon", to_sent, obj=True, send_event=send_event)
        # await self.store._channel.produce(StoreUpdateEvent("addon", to_sent, True))

    async def _import_addon(self, pl: ApiAddon):
        middlewares = await self.store.get_item("addon") if await self.store.get_item("addon") else []
        try:
            spec = spec_from_loader(pl.name, loader=SourceCodeLoader(pl.name, pl.source))
            pl.import_it(spec)
            if pl not in middlewares:
                middlewares.append(pl)
            await self.store.set_item("addon", middlewares, send_event=False)
        except Exception as e:
            if settings.DEBUG:
                logger.debug(f"Can't load plugin {pl.name}, cause {str(e)}")

    async def import_addons(self):
        middlewares = await self.store.get_item("addon") if await self.store.get_item("addon") else []
        for pl in middlewares:
            await self._import_addon(pl)

    async def configure_addon(self, addon: ApiAddon, *args, **kwargs) -> ApiAddon:
        """Set middleware name, target and enabled"""
        raise NotImplementedError

    async def _discover_addon(self, filename: Path, send_event=True) -> ApiAddon | None:
        async with (await self.files_repo.open(self.addons_path.joinpath(filename))) as file_:
            pl = ApiAddon(filename, await file_.read())
            pl = await self.configure_addon(pl)
            if pl.name is None:
                raise AttributeError("ApiMiddleware name must be specified")

            middlewares = await self.store.get_item("addon") if await self.store.get_item("addon") else []
            if middlewares and pl in middlewares:
                middlewares.remove(pl)
            middlewares.append(pl)
            await self.update_store(middlewares, send_event=send_event)
            return pl

    async def discover_addons(self, send_event=True):
        for filepath in await self.files_repo.list(self.addons_path):
            if filepath.is_dir():
                continue
            await self._discover_addon(filepath.name, send_event=send_event)

    async def delete_addon(self, filename: str):
        mdws = await self.store.get_item("addon")
        new_mdws: List[ApiAddon] = []
        for mdw in mdws:
            if mdw.filename != filename:
                new_mdws.append(mdw)
        await self.update_store(new_mdws)
        await self.import_addons()

    async def add_new_addon(self, filename: str):
        pl = await self._discover_addon(filename)
        if pl:
            await self._import_addon(pl)
            if settings.DEBUG:
                logger.debug(f"New plugin added {pl}")

    async def find_addon_by_target(self, target: str) -> List[ApiAddon]:
        middlewares = await self.store.get_item("addon")
        if not middlewares:
            return []
        else:
            cell_plugins: List[ApiAddon] = []
            for pl in middlewares:
                if pl.target == target and pl.enabled:
                    cell_plugins.append(pl)
            return cell_plugins

    async def find_addon_by_name(self, name: str) -> ApiAddon:
        middlewares = await self.store.get_item("addon")
        if not middlewares:
            return []
        else:
            for pl in middlewares:
                if pl.name == name and pl.enabled:
                    return pl

    async def on_store_update(self, event: StoreUpdateEvent):
        if event.key == "addon":
            await self.store.set_item("addon", event.value, send_event=False)
            await self.import_addons()

    def register_channel_middleware(self):
        self.store.channel.add_event_middleware(StoreUpdateEvent.message_type, self.on_store_update)
        self.store.channel.add_event_middleware(StoreUpdateEvent.message_type, self.on_store_sets,
                                                assign_to="before")

    async def on_store_sets(self, event: StoreUpdateEvent):
        if event.key == "addon":
            for mdw in event.value:
                mdw.imported = None

    async def first_init(self):
        await self.discover_addons(send_event=False)
        await self.import_addons()
