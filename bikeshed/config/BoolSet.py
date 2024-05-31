from __future__ import annotations

import collections.abc

from .. import t


class BoolSet(collections.abc.MutableMapping):
    """
    Implements a "boolean set",
    where keys can be explicitly set to True or False,
    but interacted with like a normal set
    (similar to Counter, but with bools).
    Can also set whether the default should consider unset values to be True or False by default.
    """

    def __init__(self, values: t.Any = None, default: bool = False) -> None:
        self._internal: dict[t.Any, bool] = {}
        if isinstance(values, collections.abc.Mapping):
            for k, v in values.items():
                self._internal[k] = bool(v)
        elif isinstance(values, collections.abc.Iterable):
            for k in values:
                self._internal[k] = True
        self.default = bool(default)

    def __missing__(self, key: t.Any) -> bool:
        return self.default

    def __contains__(self, key: t.Any) -> bool:
        if key in self._internal:
            return self._internal[key]
        else:
            return self.default

    def __getitem__(self, key: t.Any) -> bool:
        return key in self

    def __setitem__(self, key: t.Any, val: bool) -> None:
        self._internal[key] = bool(val)

    def __delitem__(self, key: t.Any) -> None:
        del self._internal[key]

    def __iter__(self) -> t.Iterator[t.Any]:
        return iter(self._internal)

    def __len__(self) -> int:
        return len(self._internal)

    def __repr__(self) -> str:
        if self.default is False:
            trueVals = [k for k, v in self._internal.items() if v is True]
            vrepr = "[" + ", ".join(repr(x) for x in trueVals) + "]"
        else:
            falseVals = [k for k, v in self._internal.items() if v is False]
            vrepr = "{" + ", ".join(repr(x) + ":False" for x in falseVals) + "}"
        return f"BoolSet({vrepr}, default={self.default})"

    def hasExplicit(self, key: t.Any) -> bool:
        return key in self._internal

    @t.overload
    def update(self, __other: t.SupportsKeysAndGetItem[t.Any, t.Any], **kwargs: bool) -> None: ...

    @t.overload
    def update(self, __other: t.Iterable[tuple[t.Any, t.Any]], **kwargs: bool) -> None: ...

    @t.overload
    def update(self, **kwargs: bool) -> None: ...

    def update(self, __other: t.Any = None, **kwargs: bool) -> None:
        # If either defaults to True, the result
        # should too, since it "contains" everything
        # by default.
        if isinstance(__other, BoolSet):
            self.default = self.default or __other.default
            self._internal.update(__other._internal)  # pylint: disable=protected-access
        elif __other is not None:
            self._internal.update(__other)
        for k, v in kwargs.items():
            self[k] = bool(v)
