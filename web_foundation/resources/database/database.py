import importlib
import os
from typing import List, Generic

from loguru import logger
from tortoise import Tortoise, BaseDBAsyncClient, connections

from web_foundation.config import GenericConfig, DbConfig
from web_foundation.kernel.container import GenericDependencyContainer
from web_foundation.kernel.messaging.channel import IChannel
from web_foundation.kernel.stage import ListenerRegistrator, AppStage
from web_foundation.resources.resource import Resource


class DatabaseResource(Resource[BaseDBAsyncClient], Generic[GenericConfig]):
    communicator: BaseDBAsyncClient
    _app_name: str
    _modules: List[str]
    _engine: str
    db_conf: DbConfig

    def __init__(self, modules: List[str], engine: str = 'tortoise.backends.asyncpg', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._engine = engine
        self._modules = modules

    def _get_connection_setting(self) -> dict:
        if self.db_conf.with_migrations and "aerich.models" not in self._modules:
            self._modules.append("aerich.models")
        to_discover = [importlib.import_module(i) for i in self._modules]
        return {
            'connections': {
                # Dict format for connection
                f'{self._app_name}_default': {
                    'engine': self._engine,
                    'credentials': {
                        'host': self.db_conf.host,
                        'port': self.db_conf.port,
                        'user': self.db_conf.user,
                        'password': self.db_conf.password,
                        'database': self.db_conf.database,
                        'schema': self.db_conf.db_schema,
                        'minsize': 1,
                        'maxsize': 5,
                    }
                }
            },
            'apps': {
                f'{self._app_name}': {
                    'models': to_discover,
                    'default_connection': f'{self._app_name}_default',
                }
            },
            'use_tz': False,
            'timezone': 'UTC'
        }

    async def fill_db_data(self):
        pass

    async def init(self, config: GenericConfig, channel: IChannel | None = None, **kwargs):
        self._app_name = config.app_name
        self.db_conf = config.database
        await Tortoise.init(config=self._get_connection_setting())
        await super(DatabaseResource, self).init(config, channel,
                                                 communicator=Tortoise.get_connection(f'{self._app_name}_default'))

    async def shutdown(self) -> None:
        await connections.close_all()
        self.clear()

    def set_listeners(self, registrator: ListenerRegistrator, *args, **kwargs):
        async def before_app_run(stage: AppStage, container: GenericDependencyContainer):
            if not (config := container.app_config()):
                raise Exception("Config not in kwargs of set_listeners() ")
            if config.database.with_migrations:
                await self.init(config)
                await self.configure_db()
                await self.shutdown()

        registrator(AppStage.BEFORE_APP_RUN, before_app_run)

    async def _migrations(self, schema_exists: bool, command):
        path_exists = os.path.exists(os.path.join(os.getcwd(), self.db_conf.migrations_path)) and os.listdir(
            os.path.join(os.getcwd(), self.db_conf.migrations_path))

        if not path_exists and not schema_exists:
            await self._create_schema(False)
            await command.init()
            await command.init_db(safe=True)
        elif not schema_exists:
            await self._create_schema(False)
            await command.init()
            await command.upgrade()
        elif not path_exists:
            await command.init()
            await command.init_db(safe=True)  # TODO check - need to drop aerich table in db?
        await command.init()
        logger.info(f"Apply migrations from {self.db_conf.migrations_path}")
        await command.migrate()
        await command.upgrade()

    async def configure_db(self):
        scheme_name = self.db_conf.db_schema
        row_count, rows = await self.communicator.execute_query(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = $1", [scheme_name])
        schema_exists = True if row_count else False
        if self.db_conf.with_migrations:
            if not self.db_conf.migrations_path:
                raise ValueError("Migration Path not set can't migrate")
            try:
                from aerich import Command
            except ImportError:
                raise ImportError("To use migration need to install aerich, (web-foundation[aerich])")
            command = Command(tortoise_config=self._get_connection_setting(), app=self._app_name,
                              location=self.db_conf.migrations_path)
            await self._migrations(schema_exists, command)
        if not schema_exists:
            await self._create_schema()
            await self.fill_db_data()

    async def _create_schema(self, generate_schemas: bool = True):
        await self.communicator.execute_script(f"CREATE SCHEMA IF NOT EXISTS {self.db_conf.db_schema};")
        if generate_schemas:
            await Tortoise.generate_schemas()
