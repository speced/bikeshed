# pylint: skip-file
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

# The only three things that should be available during runtime.
# ...except I need these too, to declare a generic class.
from typing import TYPE_CHECKING, Generic, TypeVar, cast, overload

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
        Type,
        TypeAlias,
        TypedDict,
        TypeGuard,
    )

    from _typeshed import Self, SupportsKeysAndGetItem
    from lxml import etree
    from typing_extensions import (
        NotRequired,
        Required,
    )

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

    import sys
    from types import ModuleType

    if "Spec" not in sys.modules:
        from .Spec import Spec
    SpecT = Spec

    from .biblio import BiblioEntry
    from .config.BoolSet import BoolSet
    from .metadata import MetadataManager
    from .refs import MethodVariant, MethodVariants, ReferenceManager, RefSource, RefWrapper
    from .retrieve import DataFileRequester

    BiblioStorageT: TypeAlias = DefaultDict[str, list[BiblioEntry]]

    FillContainersT: TypeAlias = DefaultDict[str, list[ElementT]]

    LinkDefaultsT: TypeAlias = DefaultDict[str, list[tuple[str, str, str | None, str | None]]]
