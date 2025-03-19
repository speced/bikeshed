from __future__ import annotations

from ... import t

ResultValT_co = t.TypeVar("ResultValT_co", covariant=True)
ResultValT_contra = t.TypeVar("ResultValT_contra", contravariant=True)
OkT: t.TypeAlias = "tuple[ResultValT_co, int, t.Literal[False]]"
ErrT: t.TypeAlias = "tuple[None, int, t.Literal[True]]"
ResultT: t.TypeAlias = "OkT[ResultValT_co] | ErrT"


def Ok(val: ResultValT_contra, index: int) -> OkT[ResultValT_contra]:
    return (val, index, False)


def Err(index: int) -> ErrT:
    return (None, index, True)


def isOk(res: ResultT[ResultValT_co]) -> t.TypeIs[OkT[ResultValT_co]]:
    return not res[2]


def isErr(res: ResultT) -> t.TypeIs[ErrT]:
    return bool(res[2])
