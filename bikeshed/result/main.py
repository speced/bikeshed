from __future__ import annotations

from result import Err, Ok

from .. import t


def isOk[ValT](x: t.Any) -> t.TypeIs[Ok[ValT]]:
    return isinstance(x, Ok)


def isErr[ErrT](x: t.Any) -> t.TypeIs[Err[ErrT]]:
    return isinstance(x, Err)
