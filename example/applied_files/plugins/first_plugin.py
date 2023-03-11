import os

import loguru


async def before(*args, **kwargs):
    loguru.logger.debug(f"BEFORE 111111111  FUCK {os.getpid()}")
    return


async def after(*args, **kwargs):
    loguru.logger.debug(f"AFTER 1111111111 FUCK ")
    return
