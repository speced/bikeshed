# pylint: disable=unused-import
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

import sys
from collections import defaultdict

from typing import (
    AbstractSet,
    Any,
    cast,
    Callable,
    DefaultDict,
    Deque,
    Dict,
    Generator,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    overload,
    Sequence,
    Set,
    TextIO,
    Tuple,
    TYPE_CHECKING,
    TypeVar,
    Union,
)

if sys.version_info >= (3, 8):
    from typing import Literal, Protocol
else:
    from typing_extensions import Literal, Protocol

if sys.version_info >= (3, 10):
    from typing import TypeAlias, TypeGuard
else:
    from typing_extensions import TypeAlias, TypeGuard


from lxml import etree  # pylint: disable=wrong-import-position

ElementT: TypeAlias = etree._Element  # pylint: disable=protected-access
DocumentT: TypeAlias = etree._ElementTree  # pylint: disable=protected-access
NodeT: TypeAlias = Union[str, ElementT]

# Can't actually do recursive types yet :(
# Get as close as possible, but let lists be Any
NodesT: TypeAlias = Union[NodeT, List]

# Similar for JSON
JSONT: TypeAlias = Dict[str, Any]


if TYPE_CHECKING:
    if "Spec" not in sys.modules:
        from .Spec import Spec  # pylint: disable=cyclic-import
    SpecT = Spec

    from . import biblio  # pylint: disable=cyclic-import
    from .retrieve import DataFileRequester  # pylint: disable=cyclic-import

    BiblioStorageT: TypeAlias = DefaultDict[str, List[biblio.BiblioEntry]]

    FillContainersT: TypeAlias = DefaultDict[str, List[ElementT]]

    LinkDefaultsT: TypeAlias = defaultdict[str, list[tuple[str, str, str | None, str | None]]]
