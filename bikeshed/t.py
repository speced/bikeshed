# pylint: skip-file
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

# The only three things that should be available during runtime.
from typing import TYPE_CHECKING, cast, overload

if TYPE_CHECKING:
    from typing import (
        AbstractSet,
        Any,
        AnyStr,
        Awaitable,
        Callable,
        DefaultDict,
        Deque,
        FrozenSet,
        Generator,
        Generic,
        Iterable,
        Iterator,
        Literal,
        Mapping,
        MutableMapping,
        MutableSequence,
        NamedTuple,
        NewType,
        Protocol,
        Sequence,
        TextIO,
        TypeAlias,
        TypedDict,
        TypeGuard,
        TypeVar,
    )
    from typing_extensions import (
        Required,
        NotRequired,
    )
    from _typeshed import SupportsKeysAndGetItem

    from lxml import etree

    ElementT: TypeAlias = etree._Element
    DocumentT: TypeAlias = etree._ElementTree
    NodeT: TypeAlias = str | ElementT

    # In many places I treat lists as an "anonymous" element
    ElementishT: TypeAlias = ElementT | list[NodeT]

    # Can't actually do recursive types yet :(
    # Get as close as possible, but let lists be Any
    NodesT: TypeAlias = list[Any] | NodeT

    # Similar for JSON
    JSONT: TypeAlias = dict[str, Any]

    from types import ModuleType

    import sys

    if "Spec" not in sys.modules:
        from .Spec import Spec
    SpecT = Spec

    from .biblio import BiblioEntry
    from .retrieve import DataFileRequester
    from .metadata import MetadataManager
    from .refs import RefSource, ReferenceManager, RefWrapper, MethodVariants, MethodVariant

    BiblioStorageT: TypeAlias = DefaultDict[str, list[BiblioEntry]]

    FillContainersT: TypeAlias = DefaultDict[str, list[ElementT]]

    LinkDefaultsT: TypeAlias = DefaultDict[str, list[tuple[str, str, str | None, str | None]]]
