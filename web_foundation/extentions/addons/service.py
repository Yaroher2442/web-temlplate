from web_foundation.extentions.addons.addon_loader import AddonsLoader
from web_foundation.kernel.service import Service


class ApiAddonsService(Service):
    addons_loader: AddonsLoader

    def __init__(self, addons_loader: AddonsLoader):
        self.addons_loader = addons_loader

    async def add_new_middleware(self, filename: str):
        await self.addons_loader.add_new_addon(filename)

    async def delete_middleware(self, filename: str):
        await self.addons_loader.delete_addon(filename)
