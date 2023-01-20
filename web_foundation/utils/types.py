from typing import Any, Type
from typing import Union, Dict, List

JSON = Union[Dict[str, Any], List[Any], int, str, float, bool, Type[None]]
TypeJSON = Union[Dict[str, 'JSON'], List['JSON'], int, str, float, bool, Type[None]]
