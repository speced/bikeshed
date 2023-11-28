from __future__ import annotations

import hashlib
import itertools
import re

from . import datablocks, h, markdown, t
from . import messages as m


def processInclusions(doc: t.SpecT) -> None:
    iters = 0
    while True:
        # Loop because an include can contain more includes.
        iters += 1
        if iters > 1000:
            m.die("Looked for include-blocks more than 1000 times, something is wrong.")
            return
        els = h.findAll("pre.include", doc)
        if not els:
            break
        for el in els:
            handleBikeshedInclude(el, doc)
    for el in h.findAll("pre.include-code", doc):
        handleCodeInclude(el, doc)
    for el in h.findAll("pre.include-raw", doc):
        handleRawInclude(el, doc)


def handleBikeshedInclude(el: t.ElementT, doc: t.SpecT) -> None:
    macros = {}
    for i in itertools.count(0):
        macroLine = el.get("macro-" + str(i))
        if macroLine is None:
            break
        k, _, v = macroLine.partition(" ")
        macros[k.lower()] = v
    if el.get("path"):
        path = el.get("path")
        assert path is not None
        includedInputSource = doc.inputSource.relative(path)
        if includedInputSource is None:
            m.die(f"Tried to include a file at '{path}', but the current input type can't resolve relative paths.")
            h.removeNode(el)
            return
        doc.recordDependencies(includedInputSource)
        try:
            lines = includedInputSource.read().rawLines
        except FileNotFoundError:
            m.die(f"Couldn't find include file '{path}'.", el=el)
            h.removeNode(el)
            return
        except Exception as err:
            m.die(f"Couldn't find include file '{path}'. Error was:\n{err}", el=el)
            h.removeNode(el)
            return
        # hash the content + path together for identity
        # can't use just path, because they're relative; including "foo/bar.txt" might use "foo/bar.txt" further nested
        # can't use just content, because then you can't do the same thing twice.
        # combined does a good job unless you purposely pervert it
        hash = hashlib.md5((path + "".join(lines)).encode("ascii", "xmlcharrefreplace")).hexdigest()
        if el.get("hash"):
            hashAttr = el.get("hash")
            assert hashAttr is not None
            # This came from another included file, check if it's a loop-include
            if hash in hashAttr:
                # WHOOPS
                m.die(f"Include loop detected - “{path}” is included in itself.", el=el)
                h.removeNode(el)
                return
            hash += " " + hashAttr
        depth = int(el.get("depth") or "0")
        if depth > 100:
            # Just in case you slip past the nesting restriction
            m.die("Nesting depth > 100, literally wtf are you doing.", el=el)
            h.removeNode(el)
            return
        parseConfig = h.ParseConfig.fromSpec(doc)
        parseConfig.macros = {**parseConfig.macros, **macros}
        lines = h.parseLines(lines, parseConfig)
        lines = datablocks.transformDataBlocks(doc, lines)
        lines = markdown.parse(lines, doc.md.indent, opaqueElements=doc.md.opaqueElements)
        text = "".join(lines)
        subtree = h.parseHTML(text)
        for childInclude in h.findAll("pre.include", h.E.div({}, *subtree)):
            childInclude.set("hash", hash)
            childInclude.set("depth", str(depth + 1))
        h.replaceNode(el, *subtree)
    else:
        m.die(
            "Whoops, an include block didn't get parsed correctly, so I can't include anything.",
            el=el,
        )
        h.removeNode(el)
        return


def handleCodeInclude(el: t.ElementT, doc: t.SpecT) -> None:
    if not el.get("path"):
        m.die(
            "Whoops, an include-code block didn't get parsed correctly, so I can't include anything.",
            el=el,
        )
        h.removeNode(el)
        return
    path = el.get("path")
    assert path is not None
    includedInputSource = doc.inputSource.relative(path)
    if includedInputSource is None:
        m.die(f"Tried to include a file at '{path}', but the current input type can't resolve relative paths.")
        h.removeNode(el)
        return
    doc.recordDependencies(includedInputSource)
    try:
        lines = includedInputSource.read().rawLines
    except FileNotFoundError:
        m.die(f"Couldn't find include-code file '{path}'.", el=el)
        h.removeNode(el)
        return
    except Exception as err:
        m.die(f"Couldn't find include-code file '{path}'. Error was:\n{err}", el=el)
        h.removeNode(el)
        return
    if el.get("data-code-show"):
        codeShow = el.get("data-code-show")
        assert codeShow is not None
        showLines = parseRangeString(codeShow)
        if len(showLines) == 0:
            pass
        elif len(showLines) >= 2:
            m.die(f"Can only have one include-code 'show' segment, got '{codeShow}'.", el=el)
            return
        else:
            start, end = showLines[0]
            if end:
                lines = lines[:end]
            if start:
                lines = lines[start - 1 :]
                if not el.get("line-start"):
                    # If manually overridden, leave it alone,
                    # but otherwise DWIM.
                    el.set("line-start", str(start))
    h.appendChild(el, *lines, allowEmpty=True)


def handleRawInclude(el: t.ElementT, doc: t.SpecT) -> None:
    if not el.get("path"):
        m.die(
            "Whoops, an include-raw block didn't get parsed correctly, so I can't include anything.",
            el=el,
        )
        h.removeNode(el)
        return
    path = el.get("path", "")
    includedInputSource = doc.inputSource.relative(path)
    if includedInputSource is None:
        m.die(f"Tried to include a file at '{path}', but the current input type can't resolve relative paths.")
        h.removeNode(el)
        return
    doc.recordDependencies(includedInputSource)
    try:
        content = includedInputSource.read().content
    except FileNotFoundError:
        m.die(f"Couldn't find include-raw file '{path}'.", el=el)
        h.removeNode(el)
        return
    except Exception as err:
        m.die(f"Couldn't find include-raw file '{path}'. Error was:\n{err}", el=el)
        h.removeNode(el)
        return
    subtree = h.parseHTML(content)
    h.replaceNode(el, *subtree)


if t.TYPE_CHECKING:
    RangeItem: t.TypeAlias = list[int | None]
    # UGH I DON'T UNDERSTAND THE ERROR HERE
    # fuck it, replace this with a tiny dataclass anyway


def parseRangeString(rangeStr: str) -> list[RangeItem]:
    rangeStr = re.sub(r"\s*", "", rangeStr)
    return [_f for _f in (parseSingleRange(x) for x in rangeStr.split(",")) if _f is not None]


def parseSingleRange(item: str) -> RangeItem | None:
    if "-" in item:
        # Range, format of DDD-DDD
        low: int | None
        high: int | None
        lowStr, _, highStr = item.partition("-")
        if lowStr == "*":
            low = None
        else:
            try:
                low = int(lowStr)
            except ValueError:
                m.die(f"Error parsing include-code 'show' range '{item}' - must be `int-int`.")
                return None
        if highStr == "*":
            high = None
        else:
            try:
                high = int(highStr)
            except ValueError:
                m.die(f"Error parsing include-code 'show' range '{item}' - must be `int-int`.")
                return None
        if low is not None and high is not None and low >= high:
            m.die(f"include-code 'show' ranges must be well-formed lo-hi - got '{item}'.")
            return None
        return [low, high]
    if item == "*":
        return None
    try:
        val = int(item)
        return [val, val]
    except ValueError:
        m.die(f"Error parsing include-code 'show' value '{item}' - must be an int or *.")
        return None
