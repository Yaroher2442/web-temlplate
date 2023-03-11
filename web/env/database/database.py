import importlib
import os
from pathlib import Path
from typing import List

from loguru import logger
from pydantic import BaseModel
from tortoise import Tortoise, BaseDBAsyncClient, connections

from web.kernel.types import ConfAble, Resource


class DbConfig(BaseModel):
    host: str
    port: str
    database: str
    user: str
    password: str
    db_schema: str
    with_migrations: bool
    migrations_path: Path


class DatabaseResource(Resource, ConfAble[DbConfig]):
    communicator: BaseDBAsyncClient
    _modules: List[str]
    _engine: str

    def __init__(self, modules: List[str], engine: str = 'tortoise.backends.asyncpg', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._engine = engine
        self._modules = modules

    def _get_connection_setting(self) -> dict:
        if self.conf.with_migrations and "aerich.models" not in self._modules:
            self._modules.append("aerich.models")
        to_discover = [importlib.import_module(i) for i in self._modules]
        return {
            'connections': {
                # Dict format for connection
                f'{self.app_name}_default': {
                    'engine': self._engine,
                    'credentials': {
                        'host': self.conf.host,
                        'port': self.conf.port,
                        'user': self.conf.user,
                        'password': self.conf.password,
                        'database': self.conf.database,
                        'schema': self.conf.db_schema,
                        'minsize': 1,
                        'maxsize': 5,
                    }
                }
            },
            'apps': {
                f'{self.app_name}': {
                    'models': to_discover,
                    'default_connection': f'{self.app_name}_default',
                }
            },
            'use_tz': False,
            'timezone': 'UTC'
        }

    async def fill_db_data(self):
        pass

    async def init(self, **kwargs):
        await Tortoise.init(config=self._get_connection_setting())
        self.communicator = Tortoise.get_connection(f'{self.app_name}_default')

    async def shutdown(self) -> None:
        await connections.close_all()

    async def _migrations(self, schema_exists: bool, command):
        path_exists = os.path.exists(os.path.join(os.getcwd(), self.conf.migrations_path)) and os.listdir(
            os.path.join(os.getcwd(), self.conf.migrations_path))

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
        logger.info(f"Apply migrations from {self.conf.migrations_path}")
        await command.migrate()
        await command.upgrade()

    async def configure_db(self):
        scheme_name = self.conf.db_schema
        row_count, rows = await self.communicator.execute_query(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = $1", [scheme_name])
        schema_exists = True if row_count else False
        if self.conf.with_migrations:
            if not self.conf.migrations_path:
                raise ValueError("Migration Path not set can't migrate")
            try:
                from aerich import Command
            except ImportError:
                raise ImportError("To use migration need to install aerich, (web-foundation[aerich])")
            command = Command(tortoise_config=self._get_connection_setting(), app=self.app_name,
                              location=self.conf.migrations_path)
            await self._migrations(schema_exists, command)
        if not schema_exists:
            await self._create_schema()
            await self.fill_db_data()

    async def _create_schema(self, generate_schemas: bool = True):
        await self.communicator.execute_script(f"CREATE SCHEMA IF NOT EXISTS {self.conf.db_schema};")
        if generate_schemas:
            await Tortoise.generate_schemas()
