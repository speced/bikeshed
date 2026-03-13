from __future__ import annotations

from ... import t

if t.TYPE_CHECKING:
    type OkT[ValT] = tuple[ValT, int, t.Literal[False]]
    type ErrT = tuple[None, int, t.Literal[True]]
    type ResultT[ValT] = OkT[ValT] | ErrT


def Ok[U](val: U, index: int) -> OkT[U]:
    return (val, index, False)


def Err(index: int) -> ErrT:
    return (None, index, True)


def isOk[U](res: ResultT[U]) -> t.TypeIs[OkT[U]]:
    return not res[2]


def isErr(res: ResultT[t.Any]) -> t.TypeIs[ErrT]:
    return bool(res[2])
