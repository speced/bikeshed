from __future__ import annotations

import re
from enum import Enum

from ... import config, constants, t
from ... import messages as m
from . import preds
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    RawElement,
    RawText,
    SafeText,
    SelfClosedTag,
    StartTag,
    escapeAttr,
)
from .preds import charRefs
from .stream import Result, Stream

VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "command",
    "embed",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def nodesFromStream(s: Stream, start: int) -> t.Generator[ParserNode, None, None]:
    lastNode: ParserNode | None = None
    heldLast = False
    for node in generateNodes(s, start):
        if isinstance(node, RawText):
            node.curlifyApostrophes(lastNode)
            if node.needsLCCs():
                if heldLast:
                    assert lastNode is not None
                    yield lastNode
                yield node
                lastNode = node
                heldLast = False
                continue
            if heldLast and isinstance(lastNode, RawText):
                lastNode.text += node.text
                lastNode.endLine += node.height
            else:
                lastNode = node
                heldLast = True
        else:
            if heldLast:
                assert lastNode is not None
                yield lastNode
            yield node
            lastNode = node
            heldLast = False
    if heldLast:
        assert lastNode is not None
        yield lastNode


def generateNodes(s: Stream, start: int) -> t.Generator[ParserNode, None, None]:
    i = start
    end = len(s)
    while i < end:
        nodes, i = parseAnything(s, i).vi
        if nodes is None:
            return
        elif isinstance(nodes, list):
            yield from nodes
        else:
            yield nodes


def generateResults(s: Stream, start: int) -> t.Generator[Result[ParserNode | list[ParserNode]], None, None]:
    i = start
    end = len(s)
    while i < end:
        res = parseAnything(s, i)
        if res.valid:
            yield res
            i = res.i
        else:
            return


# This needs to be any character that can start a node,
# *or anything that can signal the end of a markup shorthand*,
# since I depend on the ends of markup shorthands being at the
# start of unconsumed text.
# (Adding more just means parseAnything will break text into
#  smaller chunks; it doesn't affect correctness.)
POSSIBLE_NODE_START_CHARS = "&<>`'~[]{}\\—-|=$:"


def parseAnything(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    """
    Either returns ParserNode(s) a la parseNode(),
    or returns a RawText node up to the next POSSIBLE_NODE_START_CHAR
    (possibly starting with such a char).
    (It does not parse the next node,
    but if the possible start char it ends at
    does not, in fact, start a node,
    it can return multiple RawTexts in a row.)
    """
    if s.eof(start):
        return Result.fail(start)
    if s[start] in POSSIBLE_NODE_START_CHARS:
        res = parseNode(s, start)
        s.observeResult(start, res)
        if res.valid:
            return res
    i = start + 1
    end = len(s)
    while s[i] not in POSSIBLE_NODE_START_CHARS and i < end:
        i += 1
    node = RawText.fromStream(s, start, i)
    return Result(node, i)


def parseNode(
    s: Stream,
    start: int,
) -> Result[ParserNode | list[ParserNode]]:
    """
    Parses one Node from the start of the stream.
    Might return multiple nodes, as a list.
    Failure means the stream doesn't start with anything special
    (it'll just be text),
    but Text *can* be validly returned sometimes as the node.
    """
    if s.eof(start):
        return Result.fail(start)

    first1 = s[start]
    first2 = s[start : start + 2]
    first3 = s[start : start + 3]

    node: ParserNode | list[ParserNode] | None

    inOpaque = s.inOpaqueElement()

    if first1 == "&":
        ch, i = parseCharRef(s, start, context=CharRefContext.NON_ATTR).vi
        if ch is not None:
            node = RawText.fromStream(s, start, i, f"&#{ord(ch)};")
            return Result(node, i)

    if first1 == "<":
        node, i = parseAngleStart(s, start).vi
        if node is not None:
            return Result(node, i)

    # This isn't quite correct to handle here,
    # but it'll have to wait until I munge
    # the markdown and HTML parsers together.
    el: ParserNode | None
    if first1 in ("`", "~"):
        el, i = parseFencedCodeBlock(s, start).vi
        if el is not None:
            return Result(el, i)
    if s.config.markdown:
        if first1 == "`":
            els, i = parseCodeSpan(s, start).vi
            if els is not None:
                return Result(els, i)
        if first2 == r"\`":
            node = RawText.fromStream(s, start, start + 2, "`")
            return Result(node, start + 2)
    if s.config.css and not inOpaque:
        if first3 == r"\''":
            node = RawText.fromStream(s, start, start + 3, "''")
            return Result(node, start + 3)
        elif first2 == r"\'":
            node = RawText.fromStream(s, start, start + 2, "'")
            return Result(node, start + 2)
        elif first2 == "''":
            maybeRes = parseCSSMaybe(s, start)
            if maybeRes.valid:
                return maybeRes
        elif first1 == "'":
            propdescRes = parseCSSPropdesc(s, start)
            if propdescRes.valid:
                return propdescRes
    if s.config.dfn and not inOpaque:
        if first3 in ("\\[=", "\\[$"):
            node = RawText.fromStream(s, start, start + 3, "[" + s[start + 2])
            return Result(node, start + 3)
        if first2 == "[=":
            dfnRes = parseAutolinkDfn(s, start)
            if dfnRes.valid:
                return dfnRes
        if first2 == "[$":
            abstractRes = parseAutolinkAbstract(s, start)
            if abstractRes.valid:
                return abstractRes
    if s.config.header and not inOpaque:
        if first3 == "\\[:":
            node = RawText.fromStream(s, start, start + 3, "[:")
            return Result(node, start + 3)
        if first2 == "[:":
            headerRes = parseAutolinkHeader(s, start)
            if headerRes.valid:
                return headerRes
    if s.config.idl and not inOpaque:
        if first3 == "\\{{":
            node = RawText.fromStream(s, start, start + 3, "{{")
            return Result(node, start + 3)
        if first2 == "{{":
            idlRes = parseAutolinkIdl(s, start)
            if idlRes.valid:
                return idlRes
    if s.config.markup and not inOpaque:
        if first3 == "\\<{":
            node = RawText.fromStream(s, start, start + 3, "<{")
            return Result(node, start + 3)
        if first2 == "<{":
            elementRes = parseAutolinkElement(s, start)
            if elementRes.valid:
                return elementRes
    if False:  # s.config.algorithm and not inOpaque:
        if first2 == "\\|":
            node = RawText.fromStream(s, start, start + 2, "|")
            return Result(node, start + 2)
        if first1 == "|":
            varRes = parseShorthandVariable(s, start)
            if varRes.valid:
                return varRes
    if s.config.biblio and not inOpaque:
        if first3 == "\\[[":
            node = RawText.fromStream(s, start, start + 3, "[[")
            return Result(node, start + 3)
        if first2 == "[[" and not s.inIDLContext():
            # To avoid lots of false positives with IDL stuff,
            # don't recognize biblios within IDL definitions,
            # or the linktext of IDL autolinks.

            biblioRes = parseAutolinkBiblioSection(s, start)
            if biblioRes.valid:
                return biblioRes
            else:
                m.die(
                    "Biblio/section autolink was opened, but its syntax wasn't recognized. If you didn't intend this to be a biblio/section autolink, escape the initial [ as &#91;",
                    lineNum=s.loc(start),
                )
                node = RawText.fromStream(s, start, start + 2, "[[")
                return Result(node, start + 2)
    if first2 == "\\[" and isMacroStart(s, start + 2):
        # an escaped macro, so handle it here
        node = RawText.fromStream(s, start, start + 2, "[")
        return Result(node, start + 2)
    if first1 == "[" and s[start - 1] != "[" and isMacroStart(s, start + 1):
        macroRes = parseMacro(s, start)
        if macroRes.valid:
            return macroRes
    if first2 == "—\n" or first3 == "--\n":
        match, i = s.matchRe(start, emdashRe).vi
        if match is not None:
            # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
            node = RawText.fromStream(s, start, i, "—\u200b")
            return Result(node, i)

    return Result.fail(start)


emdashRe = re.compile(r"(?:(?<!-)(—|--))\n\s*(?=\S)")


def parseAngleStart(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    # Assuming the stream starts with an <
    i = start + 1
    if s[i] == "!":
        dtRes = parseDoctype(s, start)
        if dtRes.valid:
            return dtRes
        commentRes = parseComment(s, start)
        if commentRes.valid:
            return commentRes
        return Result.fail(start)

    startTag, i = parseStartTag(s, start).vi
    if startTag is not None:
        if isinstance(startTag, SelfClosedTag):
            return Result(startTag, i)
        if startTag.tag == "pre":
            el, endI = parseMetadataBlock(s, start).vi
            if el is not None:
                return Result(el, endI)
            if isDatablockPre(startTag):
                text, i = parseRawPreToEnd(s, i).vi
                if text is None:
                    return Result.fail(start)
                el = RawElement.fromStream(s, start, i, startTag, text)
                return Result(el, i)
        if startTag.tag == "script":
            text, i = parseScriptToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        elif startTag.tag == "style":
            text, i = parseStyleToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        elif startTag.tag == "xmp":
            text, i = parseXmpToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        else:
            return Result(startTag, i)

    endTag, i = parseEndTag(s, start).vi
    if endTag is not None:
        return Result(endTag, i)

    if s.config.css:
        els, i = parseCSSProduction(s, start).vi
        if els is not None:
            return Result(els, i)

    return Result.fail(start)


def isDatablockPre(tag: StartTag) -> bool:
    datablockClasses = [
        "simpledef",
        "propdef",
        "descdef",
        "elementdef",
        "argumentdef",
        "railroad",
        "biblio",
        "anchors",
        "link-defaults",
        "ignored-specs",
        "info",
        "include",
        "include-code",
        "include-raw",
    ]
    tag.finalize()
    return any(x in tag.classes for x in datablockClasses)


def parseStartTag(s: Stream, start: int) -> Result[StartTag | SelfClosedTag]:
    if s[start] != "<":
        return Result.fail(start)
    else:
        i = start + 1

    tagname, i = parseTagName(s, i).vi
    if tagname is None:
        return Result.fail(start)

    # After this point we're committed to a start tag,
    # so failure will really be a parse error.

    attr = None
    attrs: dict[str, str] = {}
    while True:
        ws, i = parseWhitespace(s, i).vi
        if ws is None:
            if attr and s[i] not in ("/", ">"):
                m.die(
                    f"No whitespace after the end of an attribute in <{tagname}>. (Saw {attr[0]}={s[i-1]}{attr[1]}{s[i-1]}.) Did you forget to escape your quote character?",
                    lineNum=s.loc(i),
                )
            break
        startAttr = i
        attr, i = parseAttribute(s, i).vi
        if attr is None:
            break
        attrName, attrValue = attr
        if attrName in attrs:
            m.die(f"Attribute {attrName} appears twice in <{tagname}>.", lineNum=s.loc(startAttr))
            return Result.fail(start)
        if "[" in attrValue:
            attrValue = replaceMacrosInText(
                text=attrValue,
                macros=s.config.macros,
                s=s,
                start=i,
                context=f"<{tagname} {attrName}='...'>",
            )
        attrs[attrName] = attrValue

    i = parseWhitespace(s, i).i

    el: SelfClosedTag | StartTag
    if s[i] == "/":
        if s[i + 1] == ">" and tagname in ("br", "link", "meta"):
            el = SelfClosedTag.fromStream(s, start, i + 2, tagname, attrs)
            return Result(el, i + 2)
        elif s[i + 1] == ">" and preds.isXMLishTagname(tagname):
            el = SelfClosedTag.fromStream(s, start, i + 2, tagname, attrs)
            return Result(el, i + 2)
        elif tagname in VOID_ELEMENTS:
            m.die(f"Void element (<{tagname}>) with a spurious trailing /.", lineNum=s.loc(start))
            i += 1
            # Skip past and handle it normally
        else:
            m.die(
                f"Invalid use of self-closing syntax (trailing / on start tag) on a non-XML element (<{tagname}>).",
                lineNum=s.loc(start),
            )
            i += 1
            # Again, just skip it and keep going.

    if s[i] == ">":
        if tagname in VOID_ELEMENTS:
            el = SelfClosedTag.fromStream(s, start, i + 1, tagname, attrs)
        else:
            el = StartTag.fromStream(s, start, i + 1, tagname, attrs)
        return Result(el, i + 1)

    if s.eof(i):
        m.die(f"Tag <{tagname}> wasn't closed at end of file.", lineNum=s.loc(start))
        return Result.fail(start)

    # If I can, guess at what the 'garbage' is so I can display it.
    # Only look at next 20 chars, tho, so I don't spam the console.
    next20 = s[i : i + 20]
    if ">" in next20 or " " in next20:
        garbageEnd = min(config.safeIndex(next20, ">", 20), config.safeIndex(next20, " ", 20))
        m.die(
            f"While trying to parse a <{tagname}> start tag, ran into some unparseable stuff ({next20[:garbageEnd]}).",
            lineNum=s.loc(i),
        )
    else:
        m.die(f"While trying to parse a <{tagname}> start tag, ran into some unparseable stuff.", lineNum=s.loc(i))
    return Result.fail(start)


def parseTagName(s: Stream, start: int) -> Result[str]:
    if not preds.isASCIIAlpha(s[start]):
        return Result.fail(start)
    end = start + 1
    while preds.isTagnameChar(s[end]):
        end += 1
    return Result(s[start:end], end)


def parseAttribute(s: Stream, start: int) -> Result[tuple[str, str]]:
    i = start
    while preds.isAttrNameChar(s[i]):
        i += 1
    if i == start:
        return Result.fail(start)

    # Committed to an attribute

    attrName = s[start:i]
    endOfName = i
    i = parseWhitespace(s, i).i
    if s[i] == "=":
        i += 1
    else:
        return Result((attrName, ""), endOfName)

    # Now committed to a value too

    i = parseWhitespace(s, i).i

    if s[i] == '"' or s[i] == "'":
        attrValue, i = parseQuotedAttrValue(s, i).vi
    else:
        attrValue, i = parseUnquotedAttrValue(s, i).vi
    if attrValue is None:
        m.die(f"Garbage after {attrName}=.", lineNum=s.loc(i))
        return Result.fail(start)

    return Result((attrName, attrValue), i)


def parseQuotedAttrValue(s: Stream, start: int) -> Result[str]:
    endChar = s[start]
    i = start + 1

    # Could just append chars one-by-one,
    # but for efficiency track segments between char refs
    # and append the whole thing at once when I hit one.
    val = ""
    startSeg = i
    while s[i] != endChar:
        if s.eof(i):
            m.die("Quoted attribute was never closed", lineNum=s.loc(start))
            return Result.fail(start)
        if ord(s[i]) == 0:
            m.die("Unexpected U+0000 while parsing attribute value.", lineNum=s.loc(i))
            return Result.fail(start)
        if s[i] == "&":
            startRef = i
            ch, i = parseCharRef(s, i, context=CharRefContext.ATTR).vi
            if ch is None:
                i += 1
                continue
            val += s[startSeg:startRef] + printChAsHexRef(ch)
            startSeg = i
            continue
        i += 1
    val += s[startSeg:i]
    i += 1
    return Result(val, i)


def parseUnquotedAttrValue(s: Stream, start: int) -> Result[str]:
    i = start
    val = ""
    startSeg = i
    while not s.eof(i):
        if s[i] == ">":
            break
        if preds.isWhitespace(s[i]):
            break
        if s[i] in "\"'<`":
            m.die(f"Character {s[i]} (at {s.loc(i)}) is invalid in unquoted attribute values.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i] == "&":
            startRef = i
            ch, i = parseCharRef(s, i, context=CharRefContext.ATTR).vi
            if ch is None:
                i += 1
                continue
            val += s[startSeg:startRef] + printChAsHexRef(ch)
            startSeg = i
            continue
        i += 1
    if i == start:
        m.die("Missing attribute value.", lineNum=s.loc(start))
        return Result.fail(start)
    val += s[startSeg:i]
    return Result(val, i)


def printChAsHexRef(ch: str) -> str:
    """
    Turns a character reference value,
    aka a value from preds.charRefs,
    back into a hex char ref for normalization purposes.
    Sometimes outputs as two refs,
    since a few of the values are two characters.
    """
    return "".join(f"&#{ord(x)};" for x in ch)


class CharRefContext(Enum):
    ATTR = "attr"
    NON_ATTR = "non-attr"


def parseCharRef(s: Stream, start: int, context: CharRefContext) -> Result[str]:
    if s[start] != "&":
        return Result.fail(start)
    i = start + 1

    if preds.isASCIIAlphanum(s[i]):
        i += 1
        while preds.isASCIIAlphanum(s[i]):
            i += 1
        if s[i] == "=" and context == CharRefContext.ATTR:
            # HTML allows you to write <a href="?foo&bar=baz">
            # without escaping the ampersand, even if it matches
            # a named charRef so long as there's an `=` after it.
            return Result.fail(start)
        if s[i] != ";":
            m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
            return Result.fail(start)
        i += 1
        if s[start:i] not in charRefs:
            m.die(f"'{s[start:i]} isn't a valid character reference.", lineNum=s.loc(start))
            return Result.fail(start)
        return Result(charRefs[s[start:i]], i)
    elif s[i] == "#":
        i += 1
        if s[i] == "x" or s[i] == "X":
            i += 1
            numStart = i
            while preds.isHexDigit(s[i]):
                i += 1
            if i == numStart:
                m.die(f"Malformed numeric character reference '{s[start:i]}'.", lineNum=s.loc(start))
                return Result.fail(start)
            if s[i] != ";":
                m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
                return Result.fail(start)
            cp = int(s[numStart:i], 16)
        else:
            numStart = i
            while preds.isHexDigit(s[i]):
                i += 1
            if i == numStart:
                m.die(f"Malformed numeric character reference '{s[start:i]}'.", lineNum=s.loc(start))
                return Result.fail(start)
            if s[i] != ";":
                m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
                return Result.fail(start)
            cp = int(s[numStart:i], 10)
        i += 1
        if cp == 0:
            m.die("Char refs can't resolve to null.", lineNum=s.loc(start))
            return Result.fail(start)
        if cp > 0x10FFFF:
            m.die(f"Char ref '{s[start:i]}' is outside of Unicode.", lineNum=s.loc(start))
            return Result.fail(start)
        if 0xD800 <= cp <= 0xDFFF:
            m.die(f"Char ref '{s[start:i]}' is a lone surrogate.", lineNum=s.loc(start))
            return Result.fail(start)
        if preds.isNoncharacter(cp):
            m.die(f"Char ref '{s[start:i]}' is a non-character.", lineNum=s.loc(start))
            return Result.fail(start)
        if cp == 0xD or (preds.isControl(cp) and not preds.isWhitespace(cp)):
            m.die(f"Char ref '{s[start:i]}' is a control character.", lineNum=s.loc(start))
            return Result.fail(start)
        return Result(chr(cp), i)
    else:
        return Result.fail(start)


def parseWhitespace(s: Stream, start: int) -> Result[bool]:
    i = start
    while preds.isWhitespace(s[i]):
        i += 1
    if i != start:
        return Result(True, i)
    else:
        return Result.fail(start)


def parseEndTag(s: Stream, start: int) -> Result[EndTag]:
    if s[start : start + 2] != "</":
        return Result.fail(start)
    i = start + 2

    # committed now

    if s[i] == ">":
        m.die("Missing end tag name. (Got </>.)", lineNum=s.loc(start))
        return Result.fail(start)
    if s.eof(i):
        m.die("Hit EOF in the middle of an end tag.", lineNum=s.loc(start))
        return Result.fail(start)
    tagname, i = parseTagName(s, i).vi
    if tagname is None:
        m.die("Garbage in an end tag.", lineNum=s.loc(start))
        return Result.fail(start)
    if s.eof(i):
        m.die(f"Hit EOF in the middle of an end tag </{tagname}>.", lineNum=s.loc(start))
        return Result.fail(start)
    if s[i] != ">":
        m.die(f"Garbage after the tagname in </{tagname}>.", lineNum=s.loc(start))
        return Result.fail(start)
    i += 1
    return Result(EndTag.fromStream(s, start, i, tagname), i)


def parseComment(s: Stream, start: int) -> Result[Comment]:
    if s[start : start + 2] != "<!":
        return Result.fail(start)
    i = start + 2

    # committed
    if s[i : i + 2] != "--":
        m.die(f"Malformed HTML comment '{s[start:start+10]}'.", lineNum=s.loc(start))
        return Result.fail(start)
    i += 2

    dataStart = i

    while True:
        while s[i] != "-" and not s.eof(i):
            i += 1
        if s[i : i + 3] == "-->":
            return Result(
                Comment.fromStream(s, start, i + 3, s[dataStart:i]),
                i + 3,
            )
        if s[i : i + 4] == "--!>":
            m.die("Malformed comment - don't use a ! at the end.", lineNum=s.loc(start))
            return Result.fail(start)
        if s.eof(i):
            m.die("Hit EOF in the middle of a comment.", lineNum=s.loc(start))
            return Result.fail(start)
        i += 1
    assert False


def parseDoctype(s: Stream, start: int) -> Result[Doctype]:
    if s[start : start + 2] != "<!":
        return Result.fail(start)
    if s[start + 2 : start + 9].lower() != "doctype":
        return Result.fail(start)
    if s[start + 9 : start + 15].lower() != " html>":
        m.die("Unnecessarily complex doctype - use <!doctype html>.", lineNum=s.loc(start))
        return Result.fail(start)
    node = Doctype.fromStream(s, start, start + 15, s[start : start + 15])
    return Result(node, start + 15)


def parseScriptToEnd(s: Stream, start: int) -> Result[str]:
    # Call with s[i] after the opening <script> tag.
    # Returns with s[i] after the </script> tag,
    # with text contents in the Result.

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of a <script>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 9] == "</script>":
            return Result(s[start:i], i + 9)
        i += 1
    assert False


def parseStyleToEnd(s: Stream, start: int) -> Result[str]:
    # Identical to parseScriptToEnd

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of a <style>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 8] == "</style>":
            return Result(s[start:i], i + 8)
        i += 1
    assert False


def parseXmpToEnd(s: Stream, start: int) -> Result[str]:
    # Identical to parseScriptToEnd

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of an <xmp>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 6] == "</xmp>":
            return Result(s[start:i], i + 6)
        i += 1
    assert False


def parseRawPreToEnd(s: Stream, start: int) -> Result[str]:
    # Identical to parseScriptToEnd

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of a <pre> datablock.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 6] == "</pre>":
            return Result(s[start:i], i + 6)
        i += 1
    assert False


PROD_PROPDESC_RE = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")
PROD_FUNC_RE = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
PROD_ATRULE_RE = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
PROD_TYPE_RE = re.compile(
    r"""
    ^(?:(\S*)/)?
    (\S+)
    (?:\s+
        \[\s*
        (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;))\s*
        ,\s*
        (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;))\s*
        \]\s*
    )?$
    """,
    re.X,
)

TYPEWITHARGS_RE = re.compile(
    r"""
    ^(?:(\S*)/)?
    (\S+)
    \s*\[([^\]]*)\]\s*$
    """,
    re.X,
)


def parseCSSProduction(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start : start + 2] != "<<":
        return Result.fail(start)
    textStart = start + 2

    text, textEnd = s.skipTo(textStart, ">>").vi
    if text is None:
        m.die("Saw the start of a CSS production (like <<foo>>), but couldn't find the end.", lineNum=s.loc(start))
        failNode = SafeText.fromStream(s, start, start + 2)
        return Result(failNode, start + 2)
    elif "\n" in text:
        m.die(
            "Saw the start of a CSS production (like <<foo>>), but couldn't find the end on the same line.",
            lineNum=s.loc(start),
        )
        failNode = SafeText.fromStream(s, start, start + 2)
        return Result(failNode, start + 2)
    elif "<" in text or ">" in text:
        # Allow <<boolean [<<foo>>]>>
        if "[" in text:
            endOfArg = s.skipTo(textEnd, "]").i
            newTextEnd = s.skipTo(endOfArg, ">>").i
            if endOfArg == textEnd or newTextEnd == endOfArg:  # noqa: PLR1714
                m.die(
                    "It seems like you wrote a CSS production with an argument (like <<foo [<<bar>>]>>), but either included more [] in the argument, or otherwise messed up the syntax.",
                    lineNum=s.loc(start),
                )
                failNode = SafeText.fromStream(s, start, start + 2)
                return Result(failNode, start + 2)
            textEnd = newTextEnd
            text = s[textStart:textEnd]
        else:
            m.die(
                "It seems like you wrote a CSS production (like <<foo>>), but there's more markup inside of it, or you didn't close it properly.",
                lineNum=s.loc(start),
            )
            failNode = SafeText.fromStream(s, start, start + 2)
            return Result(failNode, start + 2)
    nodeEnd = textEnd + 2

    attrs: dict[str, str] = {
        "bs-autolink-syntax": s[start:nodeEnd],
        "class": "production",
        "bs-opaque": "",
    }
    for _ in [1]:
        match = PROD_PROPDESC_RE.match(text)
        if match:
            linkFor, lt, linkType = match.groups()
            if linkFor == "":
                linkFor = "/"
            if linkType is None:
                if linkFor is None:
                    linkType = "property"
                else:
                    linkType = "propdesc"
            elif linkType in ("property", "descriptor"):
                pass
            else:
                m.die(
                    f"Shorthand <<{match[0]}>> gives type as '{match[3]}', but only 'property' and 'descriptor' are allowed.",
                    lineNum=s.loc(start),
                )
                failNode = SafeText.fromStream(s, start, nodeEnd)
                return Result(failNode, nodeEnd)
            attrs["data-link-type"] = linkType
            attrs["data-lt"] = lt
            if linkFor is not None:
                attrs["data-link-for"] = linkFor
            text = f"<'{lt}'>"
            break

        match = PROD_FUNC_RE.match(text)
        if match:
            attrs["data-link-type"] = "function"
            attrs["data-lt"] = match[2]
            if match[1] is not None:
                attrs["data-link-for"] = match[1]
            text = f"<{match[2]}>"
            break

        match = PROD_ATRULE_RE.match(text)
        if match:
            attrs["data-link-type"] = "at-rule"
            attrs["data-lt"] = match[2]
            if match[1] is not None:
                attrs["data-link-for"] = match[1]
            text = f"<{match[2]}>"
            break

        match = PROD_TYPE_RE.match(text)
        if match:
            for_, term, rangeStart, rangeEnd = match.groups()
            attrs["data-link-type"] = "type"
            attrs["data-lt"] = f"<{term}>"
            if for_ is not None:
                attrs["data-link-for"] = for_
            if rangeStart is not None:
                formattedStart, numStart = parseRangeComponent(rangeStart)
                formattedEnd, numEnd = parseRangeComponent(rangeEnd)
                if formattedStart is None or formattedEnd is None:
                    m.die(f"Shorthand <<{text}>> has an invalid range.", lineNum=s.loc(start))
                    failNode = SafeText.fromStream(s, start, nodeEnd)
                    return Result(failNode, nodeEnd)
                elif numStart >= numEnd:
                    m.die(
                        f"Shorthand <<{text}>> has a range whose start is equal or greater than its end.",
                        lineNum=s.loc(start),
                    )
                    # Getting this wrong is an error, but shouldn't stop
                    # the link from working, so continue on if you can.
                text = f"<{term} [{formattedStart},{formattedEnd}]>"
            else:
                text = f"<{term}>"
            break

            match = TYPEWITHARGS_RE.match(text)
            if match:
                for_, term, arg = match.groups()
                attrs["data-lt"] = f"<{term}>"
                attrs["data-link-type"] = "type"
                if for_ is not None:
                    attrs["data-link-for"] = for_
                if "<<" in arg:
                    arg = arg.replace("<<", "<").replace(">>", ">")
                text = f"<{term}[{arg}]>"
                break

    else:
        m.die(f"Shorthand <<{text}>> does not match any recognized shorthand grammar.", lineNum=s.loc(start))
        failNode = SafeText.fromStream(s, start, nodeEnd)
        return Result(failNode, nodeEnd)

    startTag = StartTag.fromStream(s, start, textStart, "a", attrs).finalize()
    contents = SafeText.fromStream(s, textStart, textEnd, text)
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Result([startTag, contents, endTag], nodeEnd)


def parseRangeComponent(val: str) -> tuple[str | None, float | int]:
    sign = ""
    signVal = 1
    num: float | int
    val = val.strip()
    if val[0] in ["-", "−"]:
        sign = "-"
        signVal = -1
        val = val[1:]

    if val.lower() == "infinity":
        val = "∞"
    if val.lower() == "&infin;":
        val = "∞"
    if val == "∞":
        return sign + val, signVal * float("inf")

    match = re.match(r"(\d+)([\w-]*)", val)
    if match is None:
        return None, 0
    (digits, unit) = match.groups()
    num = int(digits) * signVal
    val = str(num)

    return val + unit, num


def parseCSSMaybe(s: Stream, start: int) -> Result[list[ParserNode]]:
    # Maybes can cause parser issues,
    # like ''<length>/px'',
    # but also can contain other markup that would split the text,
    # which used to be a problem.
    if s[start : start + 2] != "''":
        return Result.fail(start)
    i = start + 2

    textStart = i

    text, i = s.skipTo(i, "''").vi
    if text is None:
        return Result.fail(start)
    if "\n" in text:
        return Result.fail(start)
    textEnd = i
    nodeEnd = i + 2

    # A lot of maybes have <<foo>> links in them.
    # They break in interesting ways sometimes, but
    # also if it actually produces a link
    # (like ''width: <<length>>'' linking to 'width')
    # it'll be broken anyway.
    # So we'll hack this in - << gets turned into &lt;
    # within a maybe.
    # No chance of a link, but won't misparse in weird ways.

    # This syntax does double duty as both a linking syntax
    # and just a "style as CSS code" syntax.
    # So, you have to be careful that something that might *look* like
    # an autolink, but actually wasn't intended as such and thus fails
    # to link, doesn't have its text mangled as a result.
    # * text like `foo: ...` is probably a propdesc link,
    #   with the same text as what's written,
    #   so it's safe
    # * text like `foo` is probably a maybe link,
    #   with the same text as what's written,
    #   so it's safe too
    # * text like `foo/bar` might be a maybe link;
    #   if it is, its text is `bar`, but if not it should
    #   stay as `foo/bar`.
    #   So it's not safe, and we need to guard against this.
    # * anything else isn't a link, should just keep its text as-is.
    # In all cases,
    res = parseMaybeDecl(s, start, textStart, textEnd, nodeEnd)
    if res.valid:
        return res

    res = parseMaybeValue(s, start, textStart, textEnd, nodeEnd)
    if res.valid:
        return res

    # Doesn't look like a maybe link, so it's just CSS text.
    startTag = StartTag.fromStream(s, start, textStart, "css")
    tagMiddle = RawText.fromStream(s, textStart, textEnd, rawFromDoubleAngles(text))
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Result([startTag, tagMiddle, endTag], nodeEnd)


MAYBE_PROP_RE = re.compile(r"^(@[\w-]+/)?([\w-]+): .+")


def parseMaybeDecl(s: Stream, start: int, textStart: int, textEnd: int, nodeEnd: int) -> Result[list[ParserNode]]:
    text = s[textStart:textEnd]
    match = MAYBE_PROP_RE.match(text)
    if not match:
        return Result.fail(nodeEnd)

    for_, propdescname = match.groups()
    startTag = StartTag.fromStream(
        s,
        start,
        textStart,
        "bs-link",
        {
            "bs-autolink-syntax": escapeAttr(s[start:nodeEnd]),
            "class": "css",
            "data-link-type": "propdesc",
            "data-lt": escapeAttr(propdescname),
        },
    )
    # Maybe autolinks are sometimes nested inside of real <a>s.
    # To avoid parsing issues, I'll turn these into a custom el first,
    # then swap them into an <a> post-parsing (in processAutolinks).
    # I can probably avoid doing this later, when I'm parsing
    # *only* with my bespoke parser, and can just emit a parsing error.
    # FIXME
    if for_:
        startTag.attrs["data-link-for"] = escapeAttr(for_)
        startTag.attrs["data-link-type"] = "descriptor"
    startTag.finalize()
    tagMiddle = RawText.fromStream(s, textStart, textEnd, rawFromDoubleAngles(text))
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Result([startTag, tagMiddle, endTag], nodeEnd)


MAYBE_VAL_RE = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")


def parseMaybeValue(s: Stream, start: int, textStart: int, textEnd: int, nodeEnd: int) -> Result[list[ParserNode]]:
    text = s[textStart:textEnd]
    match = MAYBE_VAL_RE.match(text)
    if not match:
        return Result.fail(nodeEnd)

    tagMiddle: RawText | SafeText
    for_, valueName, linkType = match.groups()
    if linkType is None:
        linkType = "maybe"
    elif linkType in config.maybeTypes:
        pass
    else:
        m.die(
            f"Shorthand ''{text}'' gives type as '{linkType}', but only “maybe” sub-types are allowed: {config.englishFromList(config.maybeTypes)}.",
            lineNum=s.loc(start),
        )
        startTag = StartTag.fromStream(s, start, textStart, "css")
        tagMiddle = SafeText.fromStream(s, textStart, textEnd, valueName)
        endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
        return Result([startTag, tagMiddle, endTag], nodeEnd)

    # Probably a valid link, but *possibly* not.
    # If it looks *sufficiently like* an autolink,
    # swap the text out as if it was one
    # (has a for value and/or a type value, and the for value
    #  doesn't look like it's an end tag).
    # Otherwise, keep the text as-is, but set the intended
    # link text if it *does* succeed.
    startTag = StartTag.fromStream(
        s,
        start,
        textStart,
        "bs-link",
        {
            "bs-autolink-syntax": escapeAttr(s[start:nodeEnd]),
            "class": "css",
            "data-link-type": linkType,
            "data-lt": escapeAttr(valueName),
        },
    )
    if "&lt;" in valueName:
        m.die(
            f"The autolink {s[start:nodeEnd]} is using an HTML escape (or <<) in its value; you probably don't want to escape things there.",
            lineNum=s.loc(start),
        )
        m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
    elif "<<" in valueName:
        m.die(
            f"The autolink {s[start:nodeEnd]} is using << in its value; you probably just want to use a single < and >.",
            lineNum=s.loc(start),
        )
        m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
    if for_:
        if "&lt;" in for_ or "<<" in for_:
            m.die(
                f"The autolink {s[start:nodeEnd]} is using an HTML escape (or <<) in its for value; you probably don't want to escape things there.",
                lineNum=s.loc(start),
            )
            m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
        startTag.attrs["data-link-for"] = escapeAttr(for_)
    if (for_ is not None and not for_.endswith("<")) or match[3] is not None:
        tagMiddle = SafeText.fromStream(s, textStart, textEnd, safeFromDoubleAngles(valueName))
    else:
        startTag.attrs["bs-replace-text-on-link-success"] = escapeAttr(safeFromDoubleAngles(valueName))
        tagMiddle = RawText.fromStream(s, textStart, textEnd, rawFromDoubleAngles(text))

    startTag.finalize()
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Result([startTag, tagMiddle, endTag], nodeEnd)


def rawFromDoubleAngles(text: str) -> str:
    # <<foo>> is used a lot in maybe autolinks, but it's never
    # actually meant to be a link. Generally, I just want to
    # turn them into single angles as text.
    text = re.sub(r"<<", "&lt;", text)
    text = re.sub(r">>", ">", text)
    return text


def safeFromDoubleAngles(text: str) -> str:
    text = re.sub(r"<<", "<", text)
    text = re.sub(r">>", ">", text)
    return text


AUTOLINK_PROPDESC_RE = re.compile(
    r"""
    (?:(@[\w-]+|)/)?
    ([\w*-]+)
    (?:!!([\w-]+))?
    """,
    flags=re.X,
)


def parseCSSPropdesc(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start] != "'":
        Result.fail(start)
    innerStart = start + 1

    match, innerEnd = s.matchRe(start+1, AUTOLINK_PROPDESC_RE).vi
    if match is None:
        return Result.fail(start)

    innerText = match[0]
    linkFor, lt, linkType = match.groups()

    if s[innerEnd] != "'":
        # If you provided a for or type, you almost certainly *meant*
        # this to be a propdesc, and just left off the closing '.
        if linkFor is not None or linkType is not None:
            m.die(
                f"It appears that you meant to write a property/descriptor autolink ({s[start:innerEnd]}), but didn't finish it. Close it with a final ', or escape the initial ' character.",
                lineNum=s.loc(start),
            )
            return Result(
                SafeText.fromStream(s, start, innerEnd),
                innerEnd,
            )
        else:
            # Otherwise this is likely just an innocent apostrophe
            # used for other purposes, and should just fail to parse.
            return Result.fail(start)

    if linkType is None:
        if linkFor is None:
            linkType = "property"
        else:
            linkType = "propdesc"
    elif linkType in ("property", "descriptor"):
        pass
    else:
        m.die(
            f"Propdesc link '{innerText}' gave its type as '{linkType}', but only 'property' or 'descriptor' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "propdesc"

    if "*" in lt or lt.startswith("--"):
        startTag = StartTag.fromStream(
            s,
            start,
            start + 1,
            "css",
            {
                "bs-autolink-syntax": escapeAttr("'" + innerText + "'"),
            },
        )
    else:
        startTag = StartTag.fromStream(
            s,
            start,
            start + 1,
            "a",
            {
                "class": "property",
                "data-link-type": linkType,
                "data-lt": escapeAttr(lt),
                "bs-autolink-syntax": escapeAttr("'" + innerText + "'"),
            },
        )
        if linkFor is not None:
            startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    nodeEnd = innerEnd + 1
    middleText = RawText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Result([startTag, middleText, endTag], nodeEnd)


AUTOLINK_DFN_RE = re.compile(r".*?(?=\||=])", flags=re.DOTALL)


def parseAutolinkDfn(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[=":
        return Result.fail(start)
    innerStart = start + 2

    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(innerStart, AUTOLINK_DFN_RE).vi
    if match is None:
        m.die(
            "Dfn autolink was opened, but no closing =] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    lt, linkFor, linkType = parseLinkInfo(s, innerStart, innerText, "[=", "=]")
    if linkType == "dfn":
        pass
    elif linkType is None:
        linkType = "dfn"
    else:
        m.die(
            f"Autolink [={innerText}=] gave its type as '{linkType}', but only 'dfn' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "dfn"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": "dfn",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[=" + innerText + "=]"),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "[=", "=]", startTag).vi
        if rest is not None:
            return Result([startTag, *rest], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Result([startTag, middleText, endTag], nodeEnd)


AUTOLINK_ABSTRACT_RE = re.compile(r".*?(?=\||\$])", flags=re.DOTALL)


def parseAutolinkAbstract(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[$":
        return Result.fail(start)
    innerStart = start + 2
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(innerStart, AUTOLINK_ABSTRACT_RE).vi
    if match is None:
        m.die(
            "Abstract-op autolink was opened, but no closing $] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    lt, linkFor, linkType = parseLinkInfo(s, innerStart, innerText, "[$", "$]")
    if linkType == "abstract-op":
        pass
    elif linkType is None:
        linkType = "abstract-op"
    else:
        m.die(
            f"Autolink [${innerText}$] gave its type as '{linkType}', but only 'abstract-op' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "abstract-op"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": "abstract-op",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[$" + innerText + "$]"),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "[$", "$]", startTag).vi
        if rest is not None:
            return Result([startTag, *rest], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Result([startTag, middleText, endTag], nodeEnd)


AUTOLINK_HEADER_RE = re.compile(r":?.*?(?=\||:])", flags=re.DOTALL)


def parseAutolinkHeader(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[:":
        return Result.fail(start)
    innerStart = start + 2
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(innerStart, AUTOLINK_HEADER_RE).vi
    if match is None:
        m.die(
            "HTTP Header autolink was opened, but no closing :] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    lt, linkFor, linkType = parseLinkInfo(s, innerStart, innerText, "[:", ":]")
    if linkType == "http-header":
        pass
    elif linkType is None:
        linkType = "http-header"
    else:
        m.die(
            f"Autolink [:{innerText}:] gave its type as '{linkType}', but only 'http-header' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "http-header"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 2,
        "a",
        {
            "data-link-type": "http-header",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[:" + innerText + ":]"),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startTick = RawText.fromStream(s, start, start, "`")
    startCode = StartTag.fromStream(s, start, start, "code")

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "[:", ":]", startTag).vi
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            endTick = RawText.fromStream(s, nodeEnd, nodeEnd, "`")
            return Result([startTick, startCode, startTag, *rest, endCode, endTick], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    endTick = RawText.fromStream(s, nodeEnd, nodeEnd, "`")
    return Result([startTick, startCode, startTag, middleText, endTag, endCode, endTick], nodeEnd)


AUTOLINK_IDL_RE = re.compile(r".*?(?=\||}})", flags=re.DOTALL)


def parseAutolinkIdl(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start : start + 2] != "{{":
        return Result.fail(start)
    innerStart = start + 2

    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(innerStart, AUTOLINK_IDL_RE).vi
    if match is None:
        m.die(
            "IDL autolink was opened, but no closing }} was found. Either close your autolink, or escape the initial { as &#123;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    lt, linkFor, linkType = parseLinkInfo(s, innerStart, innerText, "{{", "}}")
    if linkType in config.idlTypes:
        pass
    elif linkType is None:
        linkType = "idl"
    else:
        m.die(
            f"IDL autolink {{{{{s[start+1:innerEnd]}}}}} gave its type as '{linkType}', but only IDL types are allowed.",
            lineNum=s.loc(start),
        )
        linkType = "idl"

    if lt.startswith("constructor(") and linkFor and linkFor != "/":
        # make {{Foo/constructor()}} output as "Foo()" so you know what it's linking to.
        if "/" in linkFor:
            _, _, name = linkFor.rpartition("/")
        else:
            name = linkFor
        visibleText = name + lt[11:]
    else:
        visibleText = lt

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": linkType,
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startCode = StartTag.fromStream(
        s,
        start + 1,
        start + 1,
        "code",
        {"class": "idl", "nohighlight": ""},
    ).finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "{{", "}}", startTag).vi
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            return Result([startCode, startTag, *rest, endCode], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, visibleText)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    return Result([startCode, startTag, middleText, endTag, endCode], nodeEnd)


AUTOLINK_ELEMENT_RE = re.compile(r".*?(?=\||}>)", flags=re.DOTALL)


def parseAutolinkElement(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start : start + 2] != "<{":
        return Result.fail(start)
    innerStart = start + 2

    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(innerStart, AUTOLINK_ELEMENT_RE).vi
    if match is None:
        m.die(
            "Markup autolink was opened, but no closing }> was found. Either close your autolink, or escape the initial < as &lt;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    lt, linkFor, linkType = parseLinkInfo(s, innerStart, innerText, "<{", "}>")
    if linkType is None:
        if linkFor is None:
            linkType = "element"
        elif "/" in linkFor:
            linkType = "attr-value"
        else:
            # either element-state or element-attr
            linkType = "element-sub"
    if linkType in config.markupTypes:
        pass
    else:
        m.die(
            f"Markup autolink <{{{innerText}}}> gave its type as '{linkType}', but only markup types are allowed.",
            lineNum=s.loc(start),
        )
        linkType = "element"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 2,
        "a",
        {
            "data-link-type": linkType,
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("<{" + innerText + "}>"),
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()
    startCode = StartTag.fromStream(s, start, start, "code", {"nohighlight": ""})

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "<{", "}>", startTag).vi
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            return Result([startCode, startTag, *rest, endCode], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    return Result([startCode, startTag, middleText, endTag, endCode], nodeEnd)


def parseShorthandVariable(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start] != "|" or s[start + 1] in (" ", "\n"):
        return Result.fail(start)
    startLine = s.line(start)
    innerContent: list[ParserNode] = []
    for res in generateResults(s, start + 1):
        value = res.value
        assert value is not None
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s.line(res.i + 1) > startLine + 2:
            m.die(
                f"It looks like a variable shorthand (like |foo bar|) was started on line {startLine}, but not closed within a few lines. If you didn't mean to write a variable shorthand, escape the | like &#124;. If you did mean to write a variable across that many lines, use <var> instead.",
                lineNum=s.loc(start),
            )
            return Result(
                SafeText.fromStream(s, start, start + 1, "|"),
                start + 1,
            )
        if s[res.i] == "|":
            nodeEnd = res.i + 1
            break
    else:
        m.die(
            f"It looks like a variable shorthand (like |foo bar|) was started on line {startLine}, but never closed. If you didn't mean to write a variable shorthand, escape the | like &#124;.",
            lineNum=s.loc(start),
        )
        return Result(
            RawText.fromStream(s, start, start + 1, "|"),
            start + 1,
        )

    varStart = StartTag.fromStream(
        s,
        start,
        start + 1,
        "var",
        {"bs-autolink-syntax": s[start:nodeEnd]},
    )
    varEnd = EndTag.fromStream(s, nodeEnd - 1, nodeEnd, varStart)
    return Result([varStart, *innerContent, varEnd], nodeEnd)


def parseAutolinkBiblioSection(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start : start + 2] != "[[":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    innerStart = start + 2

    innerResult = parseBiblioInner(s, innerStart)
    if not innerResult.valid:
        innerResult = parseSectionInner(s, innerStart)
        if not innerResult.valid:
            m.die(
                "Saw a [[ opening a biblio or section autolink, but couldn't parse the following contents. If you didn't intend this to be a biblio autolink, escape the initial [ as &#91;",
                lineNum=s.loc(start),
            )
            return Result(
                RawText.fromStream(s, start, innerStart, "[["),
                innerStart,
            )
    parseOutcome, innerEnd = innerResult.vi
    assert parseOutcome is not None
    startTag, visibleText = parseOutcome

    if s[innerEnd] == "|":
        rest, nodeEnd = parseLinkText(s, innerEnd + 1, "[[", "]]", startTag).vi
        if rest is not None:
            return Result([startTag, *rest], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, visibleText)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Result([startTag, middleText, endTag], nodeEnd)


def parseLinkInfo(
    s: Stream,
    start: int,
    innerText: str,
    startSigil: str,
    endSigil: str,
) -> tuple[str, str | None, str | None]:
    lt = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context=startSigil + innerText + endSigil,
    )
    linkFor = None
    linkType = None
    if "/" in lt:
        linkFor, _, lt = lt.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
    if "!!" in lt:
        lt, _, linkType = lt.partition("!!")
        linkType = linkType.strip()
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)
    return lt, linkFor, linkType


def parseLinkText(
    s: Stream,
    start: int,
    startingSigil: str,
    endingSigil: str,
    startTag: StartTag,
) -> Result[list[ParserNode]]:
    endingLength = len(endingSigil)
    startLine = s.line(start)
    content: list[ParserNode] = []
    for res in generateResults(s, start):
        value, i = res.vi
        assert value is not None
        if isinstance(value, list):
            content.extend(value)
        else:
            content.append(value)
        if s.line(i) > startLine + 3:
            m.die(
                f"{startingSigil}...{endingSigil} autolink opened at {startTag.loc} wasn't closed within 3 lines. You might have forgotten to close it; if not, switch to the HTML syntax to spread your link across that many lines.",
                lineNum=startTag.loc,
            )
            return Result.fail(start)
        if s[i : i + endingLength] == endingSigil:
            content.append(EndTag.fromStream(s, i, i + endingLength, startTag))
            return Result(content, i + endingLength)
    m.die(
        f"{startingSigil}...{endingSigil} autolink was opened at {startTag.loc}, and used | to indicate it was providing explicit linktext, but never closed. Either close your autolink, or escape the initial characters that triggered autolink parsing.",
        lineNum=startTag.loc,
    )
    return Result.fail(start)


AUTOLINK_BIBLIO_RE = re.compile(r"(!?)([\w.+-]+)((?:\s+\w+)*)(?=\||\]\])")
AUTOLINK_BIBLIO_KEYWORDS = ["current", "snapshot", "inline", "index", "direct", "obsolete"]


def parseBiblioInner(s: Stream, innerStart: int) -> Result[tuple[StartTag, str]]:
    nodeStart = innerStart - 2
    match, innerEnd = s.matchRe(innerStart, AUTOLINK_BIBLIO_RE).vi
    if not match:
        return Result.fail(nodeStart)

    normative = match[1] == "!"
    lt = match[2]
    modifierSequence = match[3].strip()
    attrs = {
        "data-lt": lt,
        "data-link-type": "biblio",
        "data-biblio-type": "normative" if normative else "informative",
        "bs-autolink-syntax": s[nodeStart:innerEnd] + "]]",
    }

    failureStart = StartTag.fromStream(s, nodeStart, innerStart, "span")
    failureResult = Result(
        (failureStart, f"&#91;{lt}]"),
        innerEnd,
    )

    if modifierSequence != "":
        for modifier in re.split(r"\s+", modifierSequence):
            if modifier in ("current", "snapshot"):
                if "data-biblio-status" not in attrs:
                    attrs["data-biblio-status"] = modifier
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple current/snapshot keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            elif modifier in ("inline", "index", "direct"):
                if "data-biblio-display" not in attrs:
                    attrs["data-biblio-display"] = modifier
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple inline/index/direct keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            elif modifier == "obsolete":
                if "data-biblio-obsolete" not in attrs:
                    attrs["data-biblio-obsolete"] = ""
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple 'obsolete' keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            else:
                m.die(
                    f"Biblio shorthand [{lt} ...] has an unknown/invalid keyword ({modifier}). Allowed keywords are {config.englishFromList(AUTOLINK_BIBLIO_KEYWORDS)}. If this isn't meant to be a biblio autolink at all, escape the initial [ as &#91;",
                    lineNum=s.loc(nodeStart),
                )
                return failureResult

    startTag = StartTag.fromStream(s, nodeStart, innerStart, "a", attrs).finalize()
    return Result(
        (startTag, f"&#91;{lt}]"),
        innerEnd,
    )


AUTOLINK_SECTION_RE = re.compile(
    r"""
    ([\w.+-]+)?                           # optional spec name
    (?:
        ((?:\/[\w.+-]*)?(?:\#[\w.+-]+)) | # /page#heading
        (\/[\w.+-]+)                      # /page only
    )
    (?=\||\]\])
    """,
    re.X,
)


def parseSectionInner(s: Stream, innerStart: int) -> Result[tuple[StartTag, str]]:
    nodeStart = innerStart - 2
    match, innerEnd = s.matchRe(innerStart, AUTOLINK_SECTION_RE).vi
    if not match:
        return Result.fail(innerStart)

    spec, section, justPage = match.groups()
    if spec is None:
        # local section link
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "a",
            {
                "section": "",
                "href": section,
                "bs-autolink-syntax": f"[[{match[0]}]]",
            },
        )
    elif justPage is not None:
        # foreign link, to an actual page from a multipage spec
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "span",
            {
                "spec-section": justPage + "#",
                "spec": spec,
                "bs-autolink-syntax": f"[[{match[0]}]]",
            },
        )
    else:
        # foreign link
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "span",
            {
                "spec-section": section,
                "spec": spec,
                "bs-autolink-syntax": f"[[{match[0]}]]",
            },
        )
    return Result((startTag, ""), innerEnd)


codeSpanStartRe = re.compile(r"`+")
# A few common lengths to pre-compile for speed.
codeSpanEnd1Re = re.compile(r"(.*?[^`])(`)([^`]|$)")
codeSpanEnd2Re = re.compile(r"(.*?[^`])(``)([^`]|$)")


def parseCodeSpan(s: Stream, start: int) -> Result[list[ParserNode]]:
    if s[start - 1] == "`" and s[start - 2 : start] != "\\`":
        return Result.fail(start)
    if s[start] != "`":
        return Result.fail(start)
    match, i = s.matchRe(start, codeSpanStartRe).vi
    assert match is not None
    ticks = match[0]
    contentStart = i

    if len(ticks) == 1:
        endRe = codeSpanEnd1Re
    elif len(ticks) == 2:
        endRe = codeSpanEnd2Re
    else:
        endRe = re.compile(r"([^`])(" + ticks + ")([^`]|$)")
    match, _ = s.searchRe(i, endRe).vi
    if match is None:
        # Allowed to be unmatched, they're just ticks then.
        return Result.fail(start)
    contentEnd = match.end(1)
    i = match.end(2)

    text = s[contentStart:contentEnd].replace("\n", " ")
    if text.startswith(" ") and text.endswith(" ") and text.strip() != "":
        # If you start and end with spaces, but aren't *all* spaces,
        # strip one space off.
        # (So you can put ticks at the start/end of your code span.)
        text = text[1:-1]

    startTag = StartTag.fromStream(
        s,
        start,
        contentStart,
        "code",
        {"bs-autolink-syntax": f"{ticks}{text}{ticks}", "bs-opaque": ""},
    )
    content = SafeText.fromStream(s, contentStart, contentEnd, text)
    endTag = EndTag.fromStream(s, contentEnd, i, startTag)
    return Result([startTag, content, endTag], i)


fencedStartRe = re.compile(r"`{3,}|~{3,}")


def parseFencedCodeBlock(s: Stream, start: int) -> Result[RawElement]:
    if s.precedingTextOnLine(start).strip() != "":
        return Result.fail(start)

    match, i = s.matchRe(start, fencedStartRe).vi
    if match is None:
        return Result.fail(start)
    openingFence = match.group(0)

    infoString, i = s.skipToNextLine(i).vi
    assert infoString is not None
    infoString = infoString.strip()
    if "`" in infoString:
        # This isn't allowed, because it collides with inline code spans.
        return Result.fail(start)

    contents = "\n"
    while True:
        # Ending fence has to use same character and be
        # at least as long, so just search for the opening
        # fence itself, as a start.

        text, i = s.skipTo(i, openingFence).vi

        # No ending fence in the rest of the document
        if text is None:
            m.die("Hit EOF while parsing fenced code block.", lineNum=s.loc(start))
            contents += s[i:]
            i = len(s)
            break

        # Found a possible ending fence, put preceding text
        # into the contents string.
        contents += text

        # Ending fence has to have only whitespace preceding it.
        if s.precedingTextOnLine(i).strip() == "":
            # Currently this doesn't enforce that the ending fence
            # needs to be indented to the same level as the opening
            # fence. I'll fix this better when I munge the HTML
            # and markdown parsers.

            # Consume the whole fence, since it can be longer.
            i = s.matchRe(i, fencedStartRe).i
            break

        # Otherwise I just hit a line that happens to have
        # a fence lookalike- on it, but not closing this one.
        # Skip the fence and continue.

        match, i = s.matchRe(i, fencedStartRe).vi
        assert match is not None
        contents += match.group(0)

    # At this point i is past the end of the code block.
    tag = StartTag.fromStream(s, start, start, "xmp")
    if infoString:
        tag.attrs["bs-infostring"] = infoString
        lang = infoString.split(" ")[0]
        tag.classes.add(f"language-{lang}")
    el = RawElement.fromStream(s, start, i, tag, contents)
    return Result(el, i)


MACRO_RE = re.compile(r"([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]")


def parseMacro(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    # Macros all look like `[FOO]` or `[FOO?]`:
    # uppercase ASCII, possibly with a ? suffix,
    # tightly wrapped by square brackets.

    if s[start] != "[":
        return Result.fail(start)
    match, i = s.matchRe(start + 1, MACRO_RE).vi
    if match is None:
        return Result.fail(start)
    macroName = match[1].lower()
    optional = match[2] == "?"
    if macroName not in s.config.macros:
        if optional:
            return Result([], i)
        else:
            m.die(
                f"Found unmatched text macro {s[start:i]}. Correct the macro, or escape it by replacing the opening [ with &#91;",
                lineNum=s.loc(i),
            )
            return Result(
                RawText.fromStream(s, start, i),
                i,
            )
    macroText = s.config.macros[macroName]
    context = f"macro {s[start:i]}"
    try:
        newStream = s.subStream(context=context, chars=macroText)
    except RecursionError:
        m.die(
            f"Macro replacement for {s[start:i]} recursed more than {s.depth} levels deep; probably your text macros are accidentally recursive.",
            lineNum=s.loc(start),
        )
        return Result(
            RawText.fromStream(s, start, i),
            i,
        )
    nodes = list(nodesFromStream(newStream, 0))
    return Result(nodes, i)


# Treat [ as an escape character, too, so [[RFC2119]]/etc won't
# get accidentally recognized as a macro.
MACRO_ATTRIBUTE_RE = re.compile(r"([\[\\]?)\[([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]")


def replaceMacrosInText(text: str, macros: dict[str, str], s: Stream, start: int, context: str) -> str:
    # Since I just loop over the substituted text,
    # rather than recursing as I go like I do for content macros,
    # I need to protect against accidentally replacing something
    # that wasn't originally a macro. So:
    # * if I see an escaped macro or leave a sub failure in,
    #   turn their brackets into HTML escapes.
    # * wrap every substitution in magic chars, so adjacent
    #   substitutions can't combine to form a macro,
    #   like `[F` next to `OO]`. They're removed at the end.

    msc = constants.macroStartChar
    mec = constants.macroEndChar

    def doRep(match: re.Match) -> str:
        escaped = match[1] == "\\"
        biblio = match[1] == "["
        macroName = match[2].lower()
        optional = match[3] == "?"
        if escaped:
            return msc + "&#91;" + t.cast("str", match[0][2:-1]) + "&#93;" + mec
        if biblio:
            return msc + "&#91;&#91;" + t.cast("str", match[0][2:-1]) + "&#93;" + mec
        if macroName in macros:
            return msc + macros[macroName] + mec
        if optional:
            return msc + mec
        m.die(
            f"Found unmatched text macro {match[0]} in {context}. Correct the macro, or escape it by replacing the opening [ with &#91;.",
            lineNum=s.loc(start),
        )
        return msc + "&#91;" + t.cast("str", match[0][1:-1]) + "&#93;" + mec

    text, count = MACRO_ATTRIBUTE_RE.subn(doRep, text)
    if count > 0:
        loops = 1
        while True:
            if loops > 10:
                m.die(
                    f"Macro replacement in {context} recursed more than 10 levels deep; probably your text macros are accidentally recursive.",
                    lineNum=s.loc(start),
                )
                break
            if "[" not in text:
                break
            newText = MACRO_ATTRIBUTE_RE.sub(doRep, text)
            if text == newText:
                break
            text = newText
            loops += 1
    return text.replace(msc, "").replace(mec, "")


metadataPreEndRe = re.compile(r"</pre>(.*)")
metadataXmpEndRe = re.compile(r"</xmp>(.*)")


def parseMetadataBlock(s: Stream, start: int) -> Result[RawElement]:
    # Metadata blocks aren't actually HTML elements,
    # they're line-based BSF-Markdown constructs
    # and contain unparsed text.

    if start != s.currentLineStart(start):
        # Metadata blocks must have their start/end tags
        # on the left margin, completely unindented.
        return Result.fail(start)
    startTag, i = parseStartTag(s, start).vi
    if startTag is None:
        return Result.fail(start)
    if isinstance(startTag, SelfClosedTag):
        return Result.fail(start)
    if startTag.tag not in ("pre", "xmp"):
        return Result.fail(start)
    startTag.finalize()
    if "metadata" not in startTag.classes:
        return Result.fail(start)
    startTag.tag = startTag.tag.lower()

    # Definitely in a metadata block now
    line, i = s.skipToNextLine(i).vi
    assert line is not None
    if line.strip() != "":
        m.die("Significant text on the same line as the metadata start tag isn't allowed.", lineNum=s.loc(start))
    contents = line
    endPattern = metadataPreEndRe if startTag.tag == "pre" else metadataXmpEndRe
    while True:
        if s.eof(i):
            m.die("Hit EOF while trying to parse a metadata block.", lineNum=s.loc(start))
            break
        line, i = s.skipToNextLine(i).vi
        assert line is not None
        match = endPattern.match(line)
        if not match:
            contents += line
            continue
        # Hit the end tag
        # Back up one char so we're actually ending at the end
        # of the construct, rather than on the next line.
        i -= 1
        if match.group(1).strip() != "":
            m.die("Significant text on the same line as the metadata end tag isn't allowed.", lineNum=s.loc(i))
        break

    # Since the internals aren't parsed, call it an <xmp>
    # so it'll survive later parses if necessary.
    startTag.tag = "xmp"
    el = RawElement.fromStream(s, start, i, startTag, contents)
    return Result(el, i)


def isMacroStart(s: Stream, start: int) -> bool:
    ch = s[start]
    return ch.isalpha() or ch.isdigit() or ch == "-"


########################
# Markdown
########################

"""
def parseMarkdownLink(s: Stream, start: int) -> Result[ParserNode]:
    if s[start] != "[":
        return Result.fail(start)
    if s[start - 1] == "[":
        return Result.fail(start)

    i = start + 1

    nodes, i = parseUntil(s, i, markdownLinkStopper).vi
    if nodes is None:
        return Result.fail(start)
    return Result.fail(start)


def markdownLinkStopper(s: Stream, start: int) -> bool:
    return True
"""
