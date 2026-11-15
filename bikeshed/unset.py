from __future__ import annotations

from enum import Enum
from typing import Final, Literal


class _UnsetType(Enum):
    """
    A singleton (UNSET, of type UnsetT, also exported by the t module) to use when None is a valid value.
    While sentinel() was introduced in 3.15, for older versions mypy recognizes a singleton Enum as a literal type,
    so `is` expressions will type-narrow properly.
    """

    UNSET = "UNSET"

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Final = _UnsetType.UNSET
UnsetT = Literal[_UnsetType.UNSET]
