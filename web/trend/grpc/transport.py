from web.kernel.transport import Transport
from web.kernel.types import ConfAble, ISocket, TransportConf, AppNameAble

try:
    from grpclib.server import Server
    from grpclib.utils import graceful_exit
    from betterproto.grpc.grpclib_server import ServiceBase
except ImportError:
    raise ImportError("poetry install --with grpc")


class GrpcTransportConfig(TransportConf):
    pass


class GrpcTransport(Transport, AppNameAble, ConfAble[GrpcTransportConfig]):
    async def run(self, socket: ISocket):
        for service in self.services:
            if ServiceBase not in service.__class__.__mro__:
                raise RuntimeError(ServiceBase)
        server = Server(self.services)
        with graceful_exit([server]):
            await server.start(sock=socket)
            await server.wait_closed()
