# pylint: skip-file
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

import sys
from collections import defaultdict

from typing import (
    AbstractSet,
    Any,
    AnyStr,
    Awaitable,
    cast,
    Callable,
    DefaultDict,
    Deque,
    Dict,
    Generator,
    Generic,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    NewType,
    Optional,
    overload,
    Protocol,
    Sequence,
    MutableSequence,
    Set,
    TextIO,
    Tuple,
    TYPE_CHECKING,
    TypeVar,
    Union,
)

from typing_extensions import (
    Required,
    NotRequired,
)

if sys.version_info >= (3, 8):
    from typing import Literal, Protocol, TypedDict
else:
    from typing_extensions import Literal, Protocol, TypedDict

if sys.version_info >= (3, 10):
    from typing import TypeAlias, TypeGuard
else:
    from typing_extensions import TypeAlias, TypeGuard


from lxml import etree

ElementT: TypeAlias = etree._Element
DocumentT: TypeAlias = etree._ElementTree
NodeT: TypeAlias = Union[str, ElementT]

# Can't actually do recursive types yet :(
# Get as close as possible, but let lists be Any
NodesT: TypeAlias = Union[NodeT, List]

# Similar for JSON
JSONT: TypeAlias = Dict[str, Any]


if TYPE_CHECKING:

    from types import ModuleType

    if "Spec" not in sys.modules:
        from .Spec import Spec
    SpecT = Spec

    from . import biblio
    from .retrieve import DataFileRequester
    from .metadata import MetadataManager
    from .refs import RefSource, ReferenceManager, RefWrapper, MethodVariants, MethodVariant

    BiblioStorageT: TypeAlias = DefaultDict[str, List[biblio.BiblioEntry]]

    FillContainersT: TypeAlias = DefaultDict[str, List[ElementT]]

    LinkDefaultsT: TypeAlias = defaultdict[str, list[tuple[str, str, str | None, str | None]]]
