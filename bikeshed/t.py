# pylint: skip-file
# Module for holding types, for easy importing into the rest of the codebase
from __future__ import annotations

# The only things that should be available during runtime.
from typing import TYPE_CHECKING, Generic, NewType, TypedDict, TypeVar, assert_never, assert_type, cast, overload

# Representing a string that has been escaped so it's safe to be emitted raw in an attr value.
SafeAttrStr = NewType("SafeAttrStr", str)

# Representing HTML that's guaranteed to be safe for the SimpleParser.
# Being passed through EarlyParser is sufficient, but raw HTML from the outside world isn't.
EarlyParsedHtmlStr = NewType("EarlyParsedHtmlStr", str)

if TYPE_CHECKING:
    from types import ModuleType
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
        LiteralString,
        Mapping,
        MutableMapping,
        MutableSequence,
        NamedTuple,
        Protocol,
        Sequence,
        TextIO,
        Type,
        TypeAlias,
        TypeGuard,
    )

    from _typeshed import SupportsKeysAndGetItem
    from lxml import etree
    from typing_extensions import (
        NotRequired,
        Required,
        Self,
        TypeIs,
    )

    type ElementT = etree._Element
    type NodeT = str | ElementT
    type NodeListT = Sequence[NodeT]

    type SafeAttrDict = dict[str, SafeAttrStr | Literal[""]]
    type EmptyLiteralStr = Literal[""]

    type SafeHtmlStr = LiteralString | EarlyParsedHtmlStr

    type JSONObject = dict[str, JSONContainer | JSONPrimitive]
    type JSONArray = list[JSONContainer | JSONPrimitive]
    type JSONContainer = JSONObject | JSONArray
    type JSONPrimitive = str | int | float | bool | None

    # I basically never regex over bytes
    import re

    type Match = re.Match[str]
    type Pattern = re.Pattern[str]

    import sys

    if "Spec" not in sys.modules:
        from .Spec import Spec
    type SpecT = Spec

    from .biblio import BiblioEntry
    from .config.BoolSet import BoolSet
    from .metadata import MetadataManager
    from .refs import MethodVariant, MethodVariants, ReferenceManager, RefSource, RefWrapper
    from .retrieve import DataFileRequester

    type BiblioStorageT = DefaultDict[str, list[BiblioEntry]]
    type FillContainersT = DefaultDict[str, list[ElementT]]
    type LinkDefaultsT = DefaultDict[str, list[tuple[str, str, str | None, str | None]]]
