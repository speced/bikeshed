import dataclasses

from . import t


@dataclasses.dataclass
class Line:
    i: int
    text: str

    def __unicode__(self):
        return self.text


def rectify(lines: t.Union[t.List[str], t.List[Line]]) -> t.List[Line]:
    if any(isinstance(x, str) for x in lines):
        return [Line(-1, t.cast(str, x)) for x in lines]
    return t.cast("t.Union[t.List[Line]]", lines)
