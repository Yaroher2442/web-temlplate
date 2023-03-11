import asyncio
import sys

import aiohttp
from loguru import logger

BASE_URL = "http://0.0.0.0:8080/api/v1"
# BASE_URL = "http://192.168.4.191:8000/api/v1"

USERS_EXAMPLE = [
    {'username': "root", 'password': "123456"},
]


async def auth(session, base_url, user_num, user):
    async with session.post(url=base_url + "/auth", json=user) as resp:
        resp_json = await resp.json()
        if resp.status != 200:
            logger.warning((resp, resp_json))
            logger.warning(resp.cookies)
            sys.exit(1)
        else:
            logger.warning((resp, resp_json))
            logger.warning(resp.cookies)
            session.cookie_jar.update_cookies(resp.cookies)
            logger.info(f"user {user_num} login")


async def get_events(session, base_url):
    async with session.get(url=base_url + f"/events", timeout=9999999) as resp:
        try:
            chunks_iterator = resp.content.iter_chunks()
            async for cc in chunks_iterator:
                yield cc[0]
            # while True:
            #     yield await resp.content.readchunk()
            #     await asyncio.sleep(0.3)
        except BaseException:
            resp.close()
            raise


async def listen_events(user):
    async with aiohttp.ClientSession() as session:
        # await auth(session, BASE_URL, 1, user)
        tasks = []
        ping_msg_count = 0
        while True:
            async for event in get_events(session, BASE_URL):
                if 'ping' in str(event):
                    ping_msg_count += 1
                    print(f"\r Pings: {ping_msg_count}", end="", flush=True)
                    continue
                print(end="\r")
                logger.warning(event)


async def main():
    await listen_events(USERS_EXAMPLE[0])


if __name__ == '__main__':
    asyncio.run(main())
