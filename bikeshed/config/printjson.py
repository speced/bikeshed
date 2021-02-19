from ..h import isElement, outerHTML
from ..messages import printColor


def printjson(x, indent=2, level=0):
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


def getjson(x):
    try:
        return x.__json__()
    except AttributeError:
        return x


def printjsonobject(x, indent, level):
    x = getjson(x)
    ret = ""
    maxKeyLength = 0
    for k in x.keys():
        maxKeyLength = max(maxKeyLength, len(k))
    for k, v in x.items():
        ret += (
            "\n"
            + (indent * level)
            + printColor((k + ": ").ljust(maxKeyLength + 2), "cyan")
            + printjson(v, indent, level + 1)
        )
    return ret


def printjsonobjectarray(x, indent, level):
    # Prints an array of objects
    x = getjson(x)
    ret = ""
    for i, v in enumerate(x):
        if i != 0:
            ret += "\n" + (indent * level) + printColor("=" * 10, "blue")
        ret += printjsonobject(v, indent, level)
    return ret


def printjsonsimplearray(x, indent, level):  # pylint: disable=unused-argument
    x = getjson(x)
    ret = printColor("[", "blue")
    for i, v in enumerate(x):
        if i != 0:
            ret += printColor(", ", "blue")
        ret += printjsonprimitive(v)
    ret += printColor("]", "blue")
    return ret


def printjsonprimitive(x):
    x = getjson(x)
    if isinstance(x, int):
        return str(x)
    if isinstance(x, str):
        return x
    if isinstance(x, bool):
        return str(x)
    if x is None:
        return "null"
    if isElement(x):
        return repr(x) + ":" + outerHTML(x)
    raise ValueError(f"Could not print value: {x}")
