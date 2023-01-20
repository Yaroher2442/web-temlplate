from typing import Any

from web_foundation.kernel.messaging.channel import IMessage


class StoreUpdateEvent(IMessage):
    message_type = "store_update"
    obj: bool = False

    def __init__(self, key: str, value: Any, obj: bool = False):
        super().__init__()
        self.key = key
        self.value = value
        self.obj = obj

    def __str__(self):
        return f"{self.__class__.__name__}({self.key})"
