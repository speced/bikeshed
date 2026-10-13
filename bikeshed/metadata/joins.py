from __future__ import annotations

from collections import defaultdict

from .. import config, t

if t.TYPE_CHECKING:
    JoinA = t.TypeVar("JoinA")
    JoinB = t.TypeVar("JoinB")


def joinValue(a: JoinA, b: JoinB) -> JoinB:  # pylint: disable=unused-argument
    return b


def joinList(a: t.Sequence[JoinA], b: t.Sequence[JoinB]) -> t.Sequence[JoinA | JoinB]:
    return a + b  # type: ignore[operator, no-any-return]


def joinDict(a: t.Mapping[str, JoinA], b: t.Mapping[str, JoinB]) -> dict[str, JoinA | JoinB]:
    x: dict[str, JoinA | JoinB] = {}
    x.update(a)
    x.update(b)
    return x


def joinBoolSet(a: config.BoolSet, b: config.BoolSet) -> config.BoolSet:
    x = config.BoolSet()
    x.update(a)
    x.update(b)
    return x


def joinDdList(
    a: defaultdict[str, list[JoinA]],
    b: defaultdict[str, list[JoinB]],
) -> defaultdict[str, list[JoinA | JoinB]]:
    x: defaultdict[str, list[JoinA | JoinB]] = defaultdict(list)
    x.update(a)  # type: ignore[arg-type]
    x.update(b)  # type: ignore[arg-type]
    return x
