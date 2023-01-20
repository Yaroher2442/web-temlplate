from abc import ABCMeta


class AbstractModule(metaclass=ABCMeta):
    _available: bool

    def __init__(self, available: bool):
        self._available = available

    async def emit(self):
        print("event_emitted")

    @property
    def available(self):
        return self._available
