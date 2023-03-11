import asyncio

from grpclib.client import Channel

from example.proto import protoc


class TestStub(protoc.PackageServiceStub):
    pass


async def main():
    async with Channel('0.0.0.0', 8081) as channel:
        greeter = TestStub(channel)

        reply = await greeter.get_test(test=protoc.TestStructDto())
        print(reply.test)


if __name__ == '__main__':
    asyncio.run(main())
