from __future__ import annotations

import dataclasses

from . import t


@dataclasses.dataclass
class Line:
    i: int
    text: str

    def __unicode__(self) -> str:
        return self.text


def rectify(lines: list[str] | list[Line]) -> list[Line]:
    if any(isinstance(x, str) for x in lines):
        return [Line(-1, t.cast(str, x)) for x in lines]
    return t.cast("list[Line]", lines)
