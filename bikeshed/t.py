# pylint: skip-file
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

import sys

# The only things that should be available during runtime.
from typing import TYPE_CHECKING, Generic, TypeVar, cast, overload

# Only available in 3.11, so stub them out for earlier versions
if sys.version_info >= (3, 11):
    from typing import assert_never, assert_type
else:
    from typing_extensions import assert_never, assert_type


if TYPE_CHECKING:
    from typing import (
        AbstractSet,
        Any,
        AnyStr,
        Awaitable,
        Callable,
        Collection,
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

    from _typeshed import SupportsKeysAndGetItem
    from lxml import etree
    from typing_extensions import (
        NotRequired,
        Required,
        Self,
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
