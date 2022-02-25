# pylint: disable=unused-import
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

import sys

from typing import (
    Any,
    DefaultDict,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    TYPE_CHECKING,
)


if TYPE_CHECKING:
    if "Spec" not in sys.modules:
        from .Spec import Spec  # pylint: disable=cyclic-import
    SpecType = Union["Spec"]
