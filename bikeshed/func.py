from __future__ import annotations

from . import t


class Functor:
    # Pointed and Co-Pointed by default;
    # override these yourself if you need to.
    def __init__(self, val: t.Any) -> None:
        self.__val__ = val

    def extract(self) -> t.Any:
        return self.__val__

    def map(self, fn: t.Any) -> t.Any:
        return self.__class__(fn(self.__val__))
