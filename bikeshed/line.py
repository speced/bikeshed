import dataclasses


@dataclasses.dataclass
class Line:
    i: int
    text: str

    def __unicode__(self):
        return self.text


def rectify(lines):
    if any(isinstance(x, str) for x in lines):
        return [Line(-1, x) for x in lines]
    return lines
