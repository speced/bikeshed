# -*- coding: utf-8 -*-


import hashlib
import itertools
import io
import re

from . import config
from . import datablocks
from . import markdown
from .h import *
from .messages import *

def processInclusions(doc):
    iters = 0
    while True:
        # Loop because an include can contain more includes.
        iters += 1
        if iters > 1000:
            die("Looked for include-blocks more than 1000 times, something is wrong.")
            return
        els = findAll("pre.include", doc)
        if not els:
            break
        for el in els:
            handleBikeshedInclude(el, doc)
    for el in findAll("pre.include-code", doc):
        handleCodeInclude(el, doc)
    for el in findAll("pre.include-raw", doc):
        handleRawInclude(el, doc)

def handleBikeshedInclude(el, doc):
    macros = {}
    for i in itertools.count(0):
        m = el.get("macro-" + str(i))
        if m is None:
            break
        k,_,v = m.partition(" ")
        macros[k.lower()] = v
    if el.get("path"):
        path = el.get("path")
        includedInputSource = doc.inputSource.relative(path)
        doc.recordDependencies(includedInputSource)
        try:
            lines = includedInputSource.read().rawLines
        except Exception as err:
            die("Couldn't find include file '{0}'. Error was:\n{1}", path, err, el=el)
            removeNode(el)
            return
        # hash the content + path together for identity
        # can't use just path, because they're relative; including "foo/bar.txt" might use "foo/bar.txt" further nested
        # can't use just content, because then you can't do the same thing twice.
        # combined does a good job unless you purposely pervert it
        hash = hashlib.md5((path + ''.join(lines)).encode("ascii", "xmlcharrefreplace")).hexdigest()
        if el.get('hash'):
            # This came from another included file, check if it's a loop-include
            if hash in el.get('hash'):
                # WHOOPS
                die("Include loop detected - “{0}” is included in itself.", path, el=el)
                removeNode(el)
                return
            hash += " " + el.get('hash')
        depth = int(el.get('depth')) if el.get('depth') is not None else 0
        if depth > 100:
            # Just in case you slip past the nesting restriction
            die("Nesting depth > 100, literally wtf are you doing.", el=el)
            removeNode(el)
            return
        lines = datablocks.transformDataBlocks(doc, lines)
        lines = markdown.parse(lines, doc.md.indent, opaqueElements=doc.md.opaqueElements)
        text = ''.join(lines)
        text = doc.fixText(text, moreMacros=macros)
        subtree = parseHTML(text)
        for childInclude in findAll("pre.include", E.div({}, *subtree)):
            childInclude.set("hash", hash)
            childInclude.set("depth", str(depth + 1))
        replaceNode(el, *subtree)
    else:
        die("Whoops, an include block didn't get parsed correctly, so I can't include anything.", el=el)
        removeNode(el)
        return

def handleCodeInclude(el, doc):
    if not el.get("path"):
        die("Whoops, an include-code block didn't get parsed correctly, so I can't include anything.", el=el)
        removeNode(el)
        return
    path = el.get("path")
    includedInputSource = doc.inputSource.relative(path)
    doc.recordDependencies(includedInputSource)
    try:
        lines = includedInputSource.read().rawLines
    except Exception as err:
        die("Couldn't find include-code file '{0}'. Error was:\n{1}", path, err, el=el)
        removeNode(el)
        return
    if el.get("data-code-show"):
        showLines = parseRangeString(el.get("data-code-show"))
        if len(showLines) == 0:
            pass
        elif len(showLines) >= 2:
            die("Can only have one include-code 'show' segment, got '{0}'.", el.get("data-code-show"), el=el)
            return
        else:
            start, end = showLines[0]
            if end:
                lines = lines[:end]
            if start:
                lines = lines[start-1:]
                if not el.get("line-start"):
                    # If manually overridden, leave it alone,
                    # but otherwise DWIM.
                    el.set("line-start", str(start))
    appendChild(el, *lines)


def handleRawInclude(el, doc):
    if not el.get("path"):
        die("Whoops, an include-raw block didn't get parsed correctly, so I can't include anything.", el=el)
        removeNode(el)
        return
    path = el.get("path")
    includedInputSource = doc.inputSource.relative(path)
    doc.recordDependencies(includedInputSource)
    try:
        content = includedInputSource.read().content
    except Exception as err:
        die("Couldn't find include-raw file '{0}'. Error was:\n{1}", path, err, el=el)
        removeNode(el)
        return
    subtree = parseHTML(content)
    replaceNode(el, *subtree)

def parseRangeString(rangeStr):
    rangeStr = re.sub(r"\s*", "", rangeStr)
    return [_f for _f in (parseSingleRange(x) for x in rangeStr.split(",")) if _f]

def parseSingleRange(item):
    if "-" in item:
        # Range, format of DDD-DDD
        low,_,high = item.partition("-")
        if low == "*":
            low = None
        else:
            try:
                low = int(low)
            except ValueError:
                die("Error parsing include-code 'show' range '{0}' - must be `int-int`.", item, el=el)
                return
        if high == "*":
            high = None
        else:
            try:
                high = int(high)
            except ValueError:
                die("Error parsing include-code 'show' range '{0}' - must be `int-int`.", item, el=el)
                return
        if low >= high:
            die("include-code 'show' ranges must be well-formed lo-hi - got '{0}'.", item, el=el)
            return
        return [low, high]
    else:
        if item == "*":
            return None
        else:
            try:
                val = int(item)
                return [val, val]
            except ValueError:
                die("Error parsing include-code 'show' value '{0}' - must be an int or *.", item, el=el)
