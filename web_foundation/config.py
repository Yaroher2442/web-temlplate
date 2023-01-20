from pathlib import Path
from typing import TypeVar

from pydantic import BaseSettings, BaseModel


class DbConfig(BaseModel):
    host: str
    port: str
    database: str
    user: str
    password: str
    db_schema: str
    with_migrations: bool
    migrations_path: Path


class SanicConf(BaseModel):
    host: str | None
    port: int | None
    dev: bool = False
    fast: bool = False
    debug: bool = False
    verbosity: int = 0
    workers: int = 1
    access_log: bool | None
    noisy_exceptions: bool | None

    # TODO:MABY
    # auto_reload: bool | None
    # reload_dir: Optional[Union[List[str], str]] = None


class ServingPaths(BaseModel):
    uri: str
    path: str
    route: bool = False


SanicStaticServing = dict[str, list[ServingPaths]] | None


class AppConf(BaseModel):
    app_name: str
    openapi_filepath: str | None
    database: DbConfig | None
    sanic: SanicConf | None
    serving: SanicStaticServing


GenericConfig = TypeVar("GenericConfig", bound=BaseModel)
