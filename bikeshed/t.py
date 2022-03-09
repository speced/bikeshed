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
    cast,
    overload,
)

from lxml import etree
from typing_extensions import Literal


ElementT = etree._Element  # pylint: disable=protected-access
DocumentT = etree._ElementTree  # pylint: disable=protected-access
NodeT = Union[str, ElementT]

# Can't actually do recursive types yet :(
# Get as close as possible, but let lists be Any
NodesT = Union[NodeT, List]


if TYPE_CHECKING:
    if "Spec" not in sys.modules:
        from .Spec import Spec  # pylint: disable=cyclic-import
    SpecType = Union["Spec"]
