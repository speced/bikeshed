from __future__ import annotations

import os
import re
import time

from .. import messages, t


def englishFromList(items: t.Iterable[str], conjunction: str = "or") -> str:
    # Format a list of strings into an English list.
    items = list(items)
    assert len(items) > 0
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return "{0} {2} {1}".format(items[0], items[1], conjunction)
    return "{0}, {2} {1}".format(", ".join(items[:-1]), items[-1], conjunction)


def intersperse[IterT, DelimT](
    iterable: t.Iterable[IterT],
    delimiter: DelimT,
) -> t.Iterator[IterT | DelimT]:
    first = True
    for x in iterable:
        if not first:
            yield delimiter
        first = False
        yield x


def flatIntersperse[IterT, DelimT](
    iterable: t.Iterable[t.Iterable[IterT]],
    delimiter: t.Iterable[DelimT],
) -> t.Iterator[IterT | DelimT]:
    first = True
    for x in iterable:
        if not first:
            yield from delimiter
        first = False
        yield from x


def processTextNodes(
    nodes: t.NodeListT,
    regex: t.Pattern,
    replacer: t.Callable[[t.Match], t.NodeT],
) -> list[t.NodeT]:
    """
    Takes an array of nodes,
    and flatmaps reSubObject over the text parts.
    """
    ret: list[t.NodeT] = []
    for node in nodes:
        if isinstance(node, str):
            ret.extend(reSubObject(regex, node, replacer))
        else:
            ret.append(node)
    return ret


@t.overload
def reSubObject(
    pattern: t.Pattern,
    string: str,
    repl: None = None,
) -> list[str | t.Match]: ...


@t.overload
def reSubObject[SubT](
    pattern: t.Pattern,
    string: str,
    repl: t.Callable[[t.Match], SubT],
) -> list[str | SubT]: ...


def reSubObject[SubT](
    pattern: t.Pattern,
    string: str,
    repl: t.Callable[[t.Match], SubT] | None = None,
) -> list[str | t.Match] | list[str | SubT] | list[str | t.Match | SubT]:
    """
    like re.sub, but replacements don't have to be text;
    returns an array of alternating unmatched text and match objects instead.
    If repl is specified, it's called with each match object,
    and the result then shows up in the array instead.
    """
    lastEnd = 0
    pieces: list[str | t.Match | SubT] = []
    for match in pattern.finditer(string):
        pieces.append(string[lastEnd : match.start()])
        if repl:
            pieces.append(repl(match))
        else:
            pieces.append(match)
        lastEnd = match.end()
    pieces.append(string[lastEnd:])
    return pieces


def simplifyText(text: str) -> str:
    # Remove anything that's not a name character.
    text = text.strip().lower()
    # I convert ( to - so foo(bar) becomes foo-bar,
    # but then I have to remove () because there's nothing to separate,
    # otherwise I get a double-dash in some cases.
    text = re.sub(r"\(\)", "", text)
    text = re.sub(r"[\s/(,]+", "-", text)
    text = re.sub(r"[^a-z0-9_-]", "", text)
    text = text.rstrip("-")
    return text


@t.overload
def splitForValues(forValues: str) -> list[str]: ...


@t.overload
def splitForValues(forValues: None) -> None: ...


def splitForValues(forValues: str | None) -> list[str] | None:
    """
    Splits a string of 1+ "for" values into an array of individual value.
    Respects function args, etc.
    Currently, for values are separated by commas.
    """
    if forValues is None:
        return None
    forValues = re.sub(r"\s+", " ", forValues)
    return [value.strip() for value in re.split(r",(?![^()]*\))", forValues) if value.strip()]


def groupFromKey(key: str, length: int = 2) -> str:
    """Generates a filename-safe "group" from a key, of a specified length."""
    if key in _groupFromKeyCache:
        return _groupFromKeyCache[key]
    safeChars = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
    group = ""
    for char in key.lower():
        if len(group) == length:
            _groupFromKeyCache[key] = group
            return group
        if char in safeChars:
            group += char
    group = group.ljust(length, "_")
    _groupFromKeyCache[key] = group
    return group


_groupFromKeyCache: dict[str, str]
_groupFromKeyCache = {}


def scriptPath(*pathSegs: str) -> str:
    startPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    path = os.path.join(startPath, *pathSegs)
    return path


def docPath(doc: t.SpecT, *pathSegs: str) -> str | None:
    ret = doc.inputSource.relative(*pathSegs)
    if ret:
        return str(ret)
    return None


def chrootPath(rootPath: str, path: str) -> str:
    rootPath = os.path.abspath(rootPath)
    path = os.path.abspath(path)
    if not path.startswith(rootPath):
        messages.die(
            f"Attempted to access a file ({path}) outside the source document's directory ({rootPath}). See --allow-nonlocal-files.",
        )
        raise Exception
    else:
        return path


def doEvery(s: float, action: t.Callable[[], t.Any], lastTime: float | None = None) -> float:
    # Takes an action every N seconds.
    # Pass it the duration and the last time it took the action;
    # it returns the time it last took the action
    # (possibly just now).
    # If you want to take action on first call,
    # pass 0 as lastTime;
    # otherwise it won't take action until N seconds.
    newTime = time.time()
    if lastTime is None:
        lastTime = newTime
    if lastTime == 0 or newTime - lastTime > s:
        action()
        return newTime
    return lastTime


if t.TYPE_CHECKING:
    SafeIndexDefaultT = t.TypeVar("SafeIndexDefaultT")


@t.overload
def safeIndex[ValT](coll: t.Sequence[ValT], needle: ValT) -> int | None: ...


@t.overload
def safeIndex[ValT, DefaultT](coll: t.Sequence[ValT], needle: ValT, default: DefaultT) -> int | DefaultT: ...


def safeIndex[ValT, DefaultT](
    coll: t.Sequence[ValT],
    needle: ValT,
    default: DefaultT | None = None,
) -> int | DefaultT | None:
    try:
        return coll.index(needle)
    except ValueError:
        return default
