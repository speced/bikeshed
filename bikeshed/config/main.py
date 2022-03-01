import collections.abc
import os
import re

import lxml

from .. import messages
from .. import t


def englishFromList(items, conjunction="or"):
    # Format a list of strings into an English list.
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return "{0} {2} {1}".format(items[0], items[1], conjunction)
    return "{0}, {2} {1}".format(", ".join(items[:-1]), items[-1], conjunction)


def intersperse(iterable, delimiter):
    first = True
    for x in iterable:
        if not first:
            yield delimiter
        first = False
        yield x


def processTextNodes(nodes, regex, replacer):
    """
    Takes an array of alternating text/objects,
    and runs reSubObject on the text parts,
    splicing them into the passed-in array.
    Mutates!
    """
    for i, node in enumerate(nodes):
        # Node list always alternates between text and elements
        if i % 2 == 0:
            nodes[i : i + 1] = reSubObject(regex, node, replacer)
    return nodes


def reSubObject(pattern, string, repl=None):
    """
    like re.sub, but replacements don't have to be text;
    returns an array of alternating unmatched text and match objects instead.
    If repl is specified, it's called with each match object,
    and the result then shows up in the array instead.
    """
    lastEnd = 0
    pieces = []
    for match in pattern.finditer(string):
        pieces.append(string[lastEnd : match.start()])
        if repl:
            pieces.append(repl(match))
        else:
            pieces.append(match)
        lastEnd = match.end()
    pieces.append(string[lastEnd:])
    return pieces


def simplifyText(text):
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


def linkTextsFromElement(el):
    from ..h import find, textContent

    if el.get("data-lt") == "":
        return []
    elif el.get("data-lt"):
        rawText = el.get("data-lt")
        if rawText in ["|", "||", "|||"]:
            texts = [rawText]
        else:
            texts = [x.strip() for x in rawText.split("|")]
    else:
        if el.tag in ("dfn", "a"):
            texts = [textContent(el).strip()]
        elif el.tag in ("h2", "h3", "h4", "h5", "h6"):
            texts = [textContent(find(".content", el)).strip()]
    if el.get("data-local-lt"):
        localTexts = [x.strip() for x in el.get("data-local-lt").split("|")]
        for text in localTexts:
            if text in texts:
                # lt and local-lt both specify the same thing
                raise DuplicatedLinkText(text, texts + localTexts, el)
        texts += localTexts

    texts = [re.sub(r"\s+", " ", x) for x in texts if x != ""]
    return texts


class DuplicatedLinkText(Exception):
    def __init__(self, offendingText, allTexts, el):
        super().__init__()
        self.offendingText = offendingText
        self.allTexts = allTexts
        self.el = el

    def __unicode__(self):
        return f"<Text '{self.offendingText}' shows up in both lt and local-lt>"


def firstLinkTextFromElement(el):
    try:
        texts = linkTextsFromElement(el)
    except DuplicatedLinkText as e:
        texts = e.allTexts
    return texts[0] if len(texts) > 0 else None


def splitForValues(forValues):
    """
    Splits a string of 1+ "for" values into an array of individual value.
    Respects function args, etc.
    Currently, for values are separated by commas.
    """
    if forValues is None:
        return None
    forValues = re.sub(r"\s+", " ", forValues)
    return [value.strip() for value in re.split(r",(?![^()]*\))", forValues) if value.strip()]


def groupFromKey(key, length=2):
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


_groupFromKeyCache: t.Dict[str, str]
_groupFromKeyCache = {}


def flatten(arr):
    for el in arr:
        if isinstance(el, collections.abc.Iterable) and not isinstance(el, str) and not lxml.etree.iselement(el):
            yield from flatten(el)
        else:
            yield el


def scriptPath(*pathSegs):
    startPath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    path = os.path.join(startPath, *pathSegs)
    return path


def chrootPath(rootPath, path):
    rootPath = os.path.abspath(rootPath)
    path = os.path.abspath(path)
    if not path.startswith(rootPath):
        messages.die(
            f"Attempted to access a file ({path}) outside the source document's directory ({rootPath}). See --allow-nonlocal-files."
        )
        raise Exception()
    else:
        return path


def doEvery(s, action, lastTime=None):
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
