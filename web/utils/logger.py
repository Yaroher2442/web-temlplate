import logging

from loguru import logger
from pydantic import BaseModel


class FileLoggerSettings(BaseModel):
    log_file: str
    rotation_trigger: str  # "500 MB"  "12:00" "1 week" "10 days"
    compression: str  # "zip"
    retention: str


class LogsHandler(logging.Handler):
    def __init__(self, file_log_settings: FileLoggerSettings | None):
        super().__init__()
        if file_log_settings:
            logger.add(file_log_settings.log_file, rotation=file_log_settings.rotation_trigger,
                       compression=file_log_settings.compression, retention=file_log_settings.retention)

    def emit(self, record):
        logger_opt = logger.opt(depth=10, exception=record.exc_info)
        try:
            logger_opt.log(record.levelname, record.getMessage())
        except Exception as exx:
            logger.warning(f"LOGGER {record.name} ERROR {exx}")
            pass


def setup_loggers(file_log_settings: FileLoggerSettings | None = None):
    handler = LogsHandler(file_log_settings)
    for logger_name, logger_obj in logging.root.manager.loggerDict.items():
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).handlers = [handler]
        # logging.basicConfig(handlers=[handler], level=0, force=True)
