from __future__ import annotations

from ... import t

# Lightweight parser result tuples: (value_or_None, next_index, is_error).
if t.TYPE_CHECKING:
    type OkT[ValT] = tuple[ValT, int, t.Literal[False]]
    type ErrT = tuple[None, int, t.Literal[True]]
    type ResultT[ValT] = OkT[ValT] | ErrT


def Ok[U](val: U, index: int) -> OkT[U]:
    """Return a successful parse result carrying `val` and the next stream index."""
    return (val, index, False)


def Err(index: int) -> ErrT:
    """Return a failed parse result at `index`."""
    return (None, index, True)


def isOk[U](res: ResultT[U]) -> t.TypeIs[OkT[U]]:
    """Return True if `res` is a successful `Ok` parse result."""
    return not res[2]


def isErr(res: ResultT[t.Any]) -> t.TypeIs[ErrT]:
    """Return True if `res` is a failed `Err` parse result."""
    return bool(res[2])
