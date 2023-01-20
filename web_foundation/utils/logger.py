import logging
import sys

from loguru import logger
from pydantic import BaseModel


class SanicLogMessage:
    def __init__(self, record):
        self.record = record
        self.msg = " ".join([record.name, record.host, record.request, str(record.status)])


class LoggerSettings(BaseModel):
    log_file: str
    rotation_trigger: str  # "500 MB"  "12:00" "1 week" "10 days"
    compression: str  # "zip"
    retention: str


class LogsHandler(logging.Handler):
    def __init__(self, settings: LoggerSettings | None):
        super().__init__()
        self.settings = settings
        self._set_loggers()

    def _set_loggers(self):
        if self.settings:
            logger.add(self.settings.log_file, rotation=self.settings.rotation_trigger,
                       compression=self.settings.compression, retention=self.settings.retention)

    def emit(self, record):
        # Retrieve context where the logging call occurred, this happens to be in the 6th frame upward
        logger_opt = logger.opt(depth=10, exception=record.exc_info)
        try:
            if record.name == "sanic.access":
                record.msg = SanicLogMessage(record).msg
            if hasattr(record, "status"):
                if record.status < 200:
                    logger_opt.debug(record.msg)
                elif (record.status >= 200) and (record.status < 400):
                    logger_opt.info(record.msg)
                elif (record.status >= 400) and (record.status < 500):
                    logger_opt.warning(record.msg)
                elif record.status >= 500:
                    logger_opt.error(record.msg)
            else:
                logger_opt.log(record.levelname, record.getMessage())
        except Exception as exx:
            logger.warning(f"LOGGER {record.name} ERROR {exx}")
            pass


def setup_loggers(settings: LoggerSettings | None = None):
    handler = LogsHandler(settings)
    for logger_name, logger_obj in logging.root.manager.loggerDict.items():
        logging.getLogger(logger_name).handlers.clear()
        logging.basicConfig(handlers=[handler], level=0, force=True)
