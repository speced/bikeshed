import attr


@attr.s(slots=True)
class Line:
    i = attr.ib(validator=[attr.validators.instance_of(int)])
    text = attr.ib(validator=[attr.validators.instance_of(str)])

    def __unicode__(self):
        return self.text


def rectify(lines):
    if any(isinstance(x, str) for x in lines):
        return [Line(-1, x) for x in lines]
    return lines
