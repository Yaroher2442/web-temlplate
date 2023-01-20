from enum import Enum
from typing import Callable, Coroutine, Any


class AppStage(Enum):
    BEFORE_APP_RUN = 0
    BEFORE_SERVER_START = 1


StageListener = Callable[[AppStage, 'GenericDependencyContainer'], Coroutine[Any, Any, None]]
ListenerRegistrator = Callable[[AppStage, StageListener], None]
