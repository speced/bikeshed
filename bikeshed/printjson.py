from __future__ import annotations

from . import h, t
from . import messages as m


def printjson(x: t.Any, indent: str | int = 2, level: int = 0) -> str:
    if isinstance(indent, int):
        # Convert into a number of spaces.
        indent = " " * indent
    x = getjson(x)
    if isinstance(x, dict):
        ret = printjsonobject(x, indent, level)
    elif isinstance(x, list):
        if len(x) > 0 and isinstance(getjson(x[0]), dict):
            ret = printjsonobjectarray(x, indent, level)
        else:
            ret = printjsonsimplearray(x, indent, level)
    else:
        ret = printjsonprimitive(x)
    if level == 0 and ret.startswith("\n"):
        ret = ret[1:]
    return ret
    # return json.dumps(obj, indent=2, default=lambda x:x.__json__())


def getjson(x: t.Any) -> t.Any:
    try:
        return x.__json__()
    except AttributeError:
        return x


def printjsonobject(x: t.Any, indent: str, level: int) -> str:
    x = getjson(x)
    ret = ""
    maxKeyLength = 0
    for k in x:
        maxKeyLength = max(maxKeyLength, len(k))
    for k, v in x.items():
        ret += (
            "\n"
            + (indent * level)
            + m.printColor((k + ": ").ljust(maxKeyLength + 2), "cyan")
            + printjson(v, indent, level + 1)
        )
    return ret


def printjsonobjectarray(x: list[dict[str, t.Any]], indent: str, level: int) -> str:
    # Prints an array of objects
    x = getjson(x)
    ret = ""
    for i, v in enumerate(x):
        if i != 0:
            ret += "\n" + (indent * level) + m.printColor("=" * 10, "blue")
        ret += printjsonobject(v, indent, level)
    return ret


def printjsonsimplearray(x: list, indent: str, level: int) -> str:  # pylint: disable=unused-argument
    x = getjson(x)
    ret = m.printColor("[", "blue")
    for i, v in enumerate(x):
        if i != 0:
            ret += m.printColor(", ", "blue")
        ret += printjsonprimitive(v)
    ret += m.printColor("]", "blue")
    return ret


def printjsonprimitive(x: t.Any) -> str:
    x = getjson(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return str(x)
    if x is None:
        return "null"
    if h.isElement(x):
        return repr(x) + ":" + h.outerHTML(x)
    msg = f"Could not print value: {x}"
    raise ValueError(msg)
