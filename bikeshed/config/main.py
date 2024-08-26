from __future__ import annotations

import collections.abc
import os
import re

import lxml

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


if t.TYPE_CHECKING:
    IntersperseU = t.TypeVar("IntersperseU")
    IntersperseV = t.TypeVar("IntersperseV")


def intersperse(
    iterable: t.Iterable[IntersperseU],
    delimiter: IntersperseV,
) -> t.Generator[IntersperseU | IntersperseV, None, None]:
    first = True
    for x in iterable:
        if not first:
            yield delimiter
        first = False
        yield x


if t.TYPE_CHECKING:
    ProcessTextNodesU = t.TypeVar("ProcessTextNodesU")


def processTextNodes(nodes: list[t.NodeT], regex: re.Pattern, replacer: t.Callable) -> list[t.NodeT]:
    """
    Takes an array of text/objects,
    and flatmaps reSubObject over the text parts.
    """
    ret: list[t.NodeT] = []
    for node in nodes:
        if isinstance(node, str):
            ret.extend(reSubObject(regex, node, replacer))
        else:
            ret.append(node)
    return ret


if t.TYPE_CHECKING:
    ReSubObjectU = t.TypeVar("ReSubObjectU")


@t.overload
def reSubObject(pattern: re.Pattern, string: str, repl: None) -> list[str | re.Match]: ...


@t.overload
def reSubObject(
    pattern: re.Pattern,
    string: str,
    repl: t.Callable[[re.Match], ReSubObjectU],
) -> list[str | ReSubObjectU]: ...


def reSubObject(
    pattern: re.Pattern,
    string: str,
    repl: t.Callable[[re.Match], ReSubObjectU] | None = None,
) -> list[str | re.Match] | list[str | ReSubObjectU] | list[str | re.Match | ReSubObjectU]:
    """
    like re.sub, but replacements don't have to be text;
    returns an array of alternating unmatched text and match objects instead.
    If repl is specified, it's called with each match object,
    and the result then shows up in the array instead.
    """
    lastEnd = 0
    pieces: list[str | re.Match | ReSubObjectU] = []
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


def flatten(arr: t.Iterable) -> t.Generator:
    for el in arr:
        if isinstance(el, collections.abc.Iterable) and not isinstance(el, str) and not lxml.etree.iselement(el):
            yield from flatten(el)
        else:
            yield el


def scriptPath(*pathSegs: str) -> str:
    startPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    path = os.path.join(startPath, *pathSegs)
    return path


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


def doEvery(s: float, action: t.Callable, lastTime: float | None = None) -> float:
    # Takes an action every N seconds.
    # Pass it the duration and the last time it took the action;
    # it returns the time it last took the action
    # (possibly just now).
    # If you want to take action on first call,
    # pass 0 as lastTime;
    # otherwise it won't take action until N seconds.
    import time

    newTime = time.time()
    if lastTime is None:
        lastTime = newTime
    if lastTime == 0 or newTime - lastTime > s:
        action()
        return newTime
    return lastTime
