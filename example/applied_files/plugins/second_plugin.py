import os

import loguru


async def before(*args, **kwargs):
    loguru.logger.debug(f"BEFORE 2222222222222  FUCK {os.getpid()}")
    return


async def after(*args, **kwargs):
    loguru.logger.debug(f"AFTER 2222222222222222 FUCK ")
    return
