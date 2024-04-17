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
    escapeHTML,
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
    node = RawText(
        line=s.line(start),
        endLine=s.line(i),
        context=s.context,
        text=s[start:i],
    )
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

    node: ParserNode | list[ParserNode] | None

    inOpaque = s.inOpaqueElement()

    if s[start] == "&":
        ch, i = parseCharRef(s, start, context=CharRefContext.NON_ATTR).vi
        if ch is not None:
            node = RawText(text=f"&#{ord(ch)};", line=s.line(start), endLine=s.line(i), context=s.context)
            return Result(node, i)

    if s[start] == "<":
        node, i = parseAngleStart(s, start).vi
        if node is not None:
            return Result(node, i)

    # This isn't quite correct to handle here,
    # but it'll have to wait until I munge
    # the markdown and HTML parsers together.
    el: ParserNode | None
    if s[start] in ("`", "~"):
        el, i = parseFencedCodeBlock(s, start).vi
        if el is not None:
            return Result(el, i)
    if s.config.markdown:
        if s[start] == "`":
            els, i = parseCodeSpan(s, start).vi
            if els is not None:
                return Result(els, i)
        if s[start : start + 2] == r"\`":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="`",
            )
            return Result(node, start + 2)
    if s.config.css and not inOpaque:
        if s[start : start + 3] == r"\''":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="''",
            )
            return Result(node, start + 3)
        elif s[start : start + 2] == r"\'":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="'",
            )
            return Result(node, start + 2)
        elif s[start : start + 2] == "''":
            maybeRes = parseCSSMaybe(s, start)
            if maybeRes.valid:
                return maybeRes
        elif s[start] == "'":
            propdescRes = parseCSSPropdesc(s, start)
            if propdescRes.valid:
                return propdescRes
    if s.config.dfn and not inOpaque:
        if s[start] == "\\" and s[start + 1] == "[" and s[start + 2] in ("=", "$"):
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="[" + s[start + 2],
            )
            return Result(node, start + 3)
        if s[start] == "[" and s[start + 1] == "=":
            dfnRes = parseAutolinkDfn(s, start)
            if dfnRes.valid:
                return dfnRes
        if s[start] == "[" and s[start + 1] == "$":
            abstractRes = parseAutolinkAbstract(s, start)
            if abstractRes.valid:
                return abstractRes
    if s.config.header and not inOpaque:
        if s[start] == "\\" and s[start + 1] == "[" and s[start + 2] == ":":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="[" + s[start + 2],
            )
            return Result(node, start + 3)
        if s[start] == "[" and s[start + 1] == ":":
            headerRes = parseAutolinkHeader(s, start)
            if headerRes.valid:
                return headerRes
    if s.config.idl and not inOpaque:
        if s[start] == "\\" and s[start + 1] == "{" and s[start + 2] == "{":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="{{",
            )
            return Result(node, start + 3)
        if s[start] == "{" and s[start + 1] == "{":
            idlRes = parseAutolinkIdl(s, start)
            if idlRes.valid:
                return idlRes
    if s.config.markup and not inOpaque:
        if s[start] == "\\" and s[start + 1] == "<" and s[start + 2] == "{":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="<{",
            )
            return Result(node, start + 3)
        if s[start] == "<" and s[start + 1] == "{":
            elementRes = parseAutolinkElement(s, start)
            if elementRes.valid:
                return elementRes
    if s.config.algorithm and not inOpaque:
        if s[start] == "\\" and s[start + 1] == "|":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                context=s.context,
                text="|",
            )
            return Result(node, start + 2)
        if s[start] == "|":
            varMatch, i = s.matchRe(start + 1, re.compile(r"(\w(?:[\w\s-]*\w)?)\|")).vi
            if varMatch:
                varStart = StartTag(
                    line=s.line(start),
                    endLine=s.line(start+1),
                    context=s.context,
                    tag="var",
                    attrs={"bs-autolink-syntax": s[start:i]},
                )
                varMiddle = RawText(
                    line=s.line(start + 1),
                    endLine=s.line(i - 2),
                    context=s.context,
                    text=varMatch[1],
                )
                varEnd = EndTag(
                    line=s.line(i - 1),
                    endLine=s.line(i),
                    context=s.context,
                    tag=varStart.tag,
                )
                return Result([varStart, varMiddle, varEnd], i)
    if s[start : start + 2] == "\\[":
        if s[start + 2].isalpha() or s[start + 2].isdigit():
            # an escaped macro, so handle it here
            text = "["
            endI = start + 2
        elif s[start + 2] == "[":
            # actually an escaped biblio, so let the
            # biblio/autolink code handle it for now.
            # FIXME when biblio shorthands are built into
            # this parser
            text = r"\[["
            endI = start + 3
        else:
            # same, but actually an an escaped autolink
            text = r"\["
            endI = start + 2
        node = RawText(
            line=s.line(start),
            endLine=s.line(start),
            context=s.context,
            text=text,
        )
        return Result(node, endI)
    if s[start] == "[" and s[start - 1] != "[":
        macroRes = parseMacro(s, start)
        if macroRes.valid:
            return macroRes
    match, i = s.matchRe(start, emdashRe).vi
    if match is not None:
        # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
        node = RawText(
            line=s.line(start),
            endLine=s.line(i),
            context=s.context,
            text="—\u200b",
        )
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
                el = RawElement(
                    line=startTag.line,
                    tag="pre",
                    startTag=startTag,
                    data=text,
                    endLine=s.line(i),
                    context=s.context,
                )
                return Result(el, i)
        if startTag.tag == "script":
            text, i = parseScriptToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement(
                line=startTag.line,
                tag="script",
                startTag=startTag,
                data=text,
                endLine=s.line(i),
                context=s.context,
            )
            return Result(el, i)
        elif startTag.tag == "style":
            text, i = parseStyleToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement(
                line=startTag.line,
                tag="style",
                startTag=startTag,
                data=text,
                endLine=s.line(i),
                context=s.context,
            )
            return Result(el, i)
        elif startTag.tag == "xmp":
            text, i = parseXmpToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            el = RawElement(
                line=startTag.line,
                tag="xmp",
                startTag=startTag,
                data=text,
                endLine=s.line(i),
                context=s.context,
            )
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

    tag = StartTag(line=s.line(start), endLine=s.line(start), context=s.context, tag=tagname)

    attr = None
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
        if attrName in tag.attrs:
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
        tag.attrs[attrName] = attrValue

    i = parseWhitespace(s, i).i

    if s[i] == "/":
        if s[i + 1] == ">" and tagname in ("br", "link", "meta"):
            tag.endLine = s.line(i + 1)
            el = SelfClosedTag.fromStartTag(tag)
            return Result(el, i + 2)
        elif s[i + 1] == ">" and preds.isXMLishTagname(tagname):
            tag.endLine = s.line(i + 1)
            el = SelfClosedTag.fromStartTag(tag)
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
        tag.endLine = s.line(i)
        if tagname in VOID_ELEMENTS:
            el = SelfClosedTag.fromStartTag(tag)
            return Result(el, i + 1)
        return Result(tag, i + 1)

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
    return Result(EndTag(line=s.line(start), endLine=s.line(i), context=s.context, tag=tagname), i)


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
                Comment(line=s.line(start), endLine=s.line(i + 2), context=s.context, data=s[dataStart:i]),
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
    node = Doctype(line=s.line(start), endLine=s.line(start + 15), context=s.context, data=s[start : start + 15])
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


PROPDESC_RE = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")
FUNC_RE = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
ATRULE_RE = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
TYPE_RE = re.compile(
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
        failNode = SafeText(line=s.line(start), endLine=s.line(start + 2), context=s.context, text="<<")
        return Result(failNode, start + 2)
    elif "\n" in text:
        m.die(
            "Saw the start of a CSS production (like <<foo>>), but couldn't find the end on the same line.",
            lineNum=s.loc(start),
        )
        failNode = SafeText(line=s.line(start), endLine=s.line(start + 2), context=s.context, text="<<")
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
                failNode = SafeText(line=s.line(start), endLine=s.line(start + 2), context=s.context, text="<<")
                return Result(failNode, start + 2)
            textEnd = newTextEnd
            text = s[textStart:textEnd]
        else:
            m.die(
                "It seems like you wrote a CSS production (like <<foo>>), but there's more markup inside of it, or you didn't close it properly.",
                lineNum=s.loc(start),
            )
            failNode = SafeText(line=s.line(start), endLine=s.line(start + 2), context=s.context, text="<<")
            return Result(failNode, start + 2)
    nodeEnd = textEnd + 2

    attrs: dict[str, str] = {
        "bs-autolink-syntax": s[start:nodeEnd],
        "class": "production",
        "bs-opaque": "",
    }
    for _ in [1]:
        match = PROPDESC_RE.match(text)
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
                failNode = SafeText(
                    line=s.line(start),
                    endLine=s.line(nodeEnd),
                    context=s.context,
                    text=s[start:nodeEnd],
                )
                return Result(failNode, nodeEnd)
            attrs["data-link-type"] = linkType
            attrs["data-lt"] = lt
            if linkFor is not None:
                attrs["data-link-for"] = linkFor
            text = f"<'{lt}'>"
            break

        match = FUNC_RE.match(text)
        if match:
            attrs["data-link-type"] = "function"
            attrs["data-lt"] = match[2]
            if match[1] is not None:
                attrs["data-link-for"] = match[1]
            text = f"<{match[2]}>"
            break

        match = ATRULE_RE.match(text)
        if match:
            attrs["data-link-type"] = "at-rule"
            attrs["data-lt"] = match[2]
            if match[1] is not None:
                attrs["data-link-for"] = match[1]
            text = f"<{match[2]}>"
            break

        match = TYPE_RE.match(text)
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
                    failNode = SafeText(
                        line=s.line(start),
                        endLine=s.line(nodeEnd),
                        context=s.context,
                        text=s[start:nodeEnd],
                    )
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
        failNode = SafeText(line=s.line(start), endLine=s.line(nodeEnd), context=s.context, text=s[start:nodeEnd])
        return Result(failNode, nodeEnd)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(textStart),
        context=s.context,
        tag="a",
        attrs=attrs,
    ).finalize()
    contents = SafeText(
        line=s.line(textStart),
        endLine=s.line(textEnd),
        context=s.context,
        text=text,
    )
    endTag = EndTag(
        line=s.line(textEnd),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
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
    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(textStart),
        context=s.context,
        tag="css",
    )
    tagMiddle = RawText(
        line=s.line(textStart),
        endLine=s.line(textEnd),
        context=s.context,
        text=rawFromDoubleAngles(text),
    )
    endTag = EndTag(
        line=s.line(textEnd),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    return Result([startTag, tagMiddle, endTag], nodeEnd)


MAYBE_PROP_RE = re.compile(r"^(@[\w-]+/)?([\w-]+): .+")


def parseMaybeDecl(s: Stream, start: int, textStart: int, textEnd: int, nodeEnd: int) -> Result[list[ParserNode]]:
    text = s[textStart:textEnd]
    match = MAYBE_PROP_RE.match(text)
    if not match:
        return Result.fail(nodeEnd)

    for_, propdescname = match.groups()
    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(textStart),
        context=s.context,
        # Maybe autolinks are sometimes nested inside of real <a>s.
        # To avoid parsing issues, I'll turn these into a custom el first,
        # then swap them into an <a> post-parsing (in processAutolinks).
        # I can probably avoid doing this later, when I'm parsing
        # *only* with my bespoke parser, and can just emit a parsing error.
        tag="bs-link",
        attrs={
            "bs-autolink-syntax": escapeAttr(s[start:nodeEnd]),
            "class": "css",
            "data-link-type": "propdesc",
            "data-lt": escapeAttr(propdescname),
        },
    )
    if for_:
        startTag.attrs["data-link-for"] = escapeAttr(for_)
        startTag.attrs["data-link-type"] = "descriptor"
    startTag.finalize()
    tagMiddle = RawText(
        line=s.line(textStart),
        endLine=s.line(textEnd),
        context=s.context,
        text=rawFromDoubleAngles(text),
    )
    endTag = EndTag(
        line=s.line(textEnd),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
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
        startTag = StartTag(
            line=s.line(start),
            endLine=s.line(textStart),
            context=s.context,
            tag="css",
        )
        tagMiddle = SafeText(
            line=s.line(textStart),
            endLine=s.line(textEnd),
            context=s.context,
            text=valueName,
        )
        endTag = EndTag(
            line=s.line(textEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        return Result([startTag, tagMiddle, endTag], nodeEnd)

    # Probably a valid link, but *possibly* not.
    # If it looks *sufficiently like* an autolink,
    # swap the text out as if it was one
    # (has a for value and/or a type value, and the for value
    #  doesn't look like it's an end tag).
    # Otherwise, keep the text as-is, but set the intended
    # link text if it *does* succeed.
    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(textStart),
        context=s.context,
        tag="bs-link",
        attrs={
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
        tagMiddle = SafeText(
            line=s.line(textStart),
            endLine=s.line(textEnd),
            context=s.context,
            text=safeFromDoubleAngles(valueName),
        )
    else:
        startTag.attrs["bs-replace-text-on-link-success"] = escapeAttr(safeFromDoubleAngles(valueName))
        tagMiddle = RawText(
            line=s.line(textStart),
            endLine=s.line(textEnd),
            context=s.context,
            text=rawFromDoubleAngles(text),
        )

    startTag.finalize()
    endTag = EndTag(
        line=s.line(textEnd),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
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


PROPDESC_RE = re.compile(
    r"""
    '
    (?:(@[\w-]+|)/)?
    ([\w*-]+)
    (?:!!([\w-]+))?
    """,
    flags=re.X,
)


def parseCSSPropdesc(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    match, innerEnd = s.matchRe(start, PROPDESC_RE).vi
    if match is None:
        return Result.fail(start)

    linkFor, lt, linkType = match.groups()

    if s[innerEnd] == "'":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        # If you provided a for or type, you almost certainly *meant*
        # this to be a propdesc, and just left off the closing '.
        if linkFor is not None or linkType is not None:
            m.die(
                f"It appears that you meant to write a property/descriptor autolink ({s[start:innerEnd]}), but didn't finish it. Close it with a final ', or escape the initial ' character.",
                lineNum=s.loc(start),
            )
            return Result(
                SafeText(line=s.line(start), endLine=s.line(innerEnd), context=s.context, text=s[start:innerEnd]),
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
            f"Propdesc link '{s[start+1:innerEnd]}' gave its type as '{linkType}', but only 'property' or 'descriptor' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "propdesc"

    if "*" in lt or lt.startswith("--"):
        startTag = StartTag(
            line=s.line(start),
            endLine=s.line(start + 1),
            context=s.context,
            tag="css",
            attrs={
                "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 1]),
            },
        )
    else:
        startTag = StartTag(
            line=s.line(start),
            endLine=s.line(start + 1),
            context=s.context,
            tag="a",
            attrs={
                "class": "property",
                "data-link-type": linkType,
                "data-lt": escapeAttr(lt),
                "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 1]),
            },
        )
        if linkFor is not None:
            startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if not textOverride:
        nodeEnd = innerEnd + 1
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=lt,
        )
        return Result([startTag, middleText, endTag], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending '
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("Propdesc autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i] == "'":
            if s.line(res.i + 1) > s.line(start):
                m.die(
                    "Propdesc autolinks can't be spread across multiple lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 1
            break
    else:
        m.die("Propdesc autolink was opened, but was never closed.", lineNum=s.loc(start))
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 1),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])

    return Result([startTag, *innerContent, endTag], nodeEnd)


def linkInValue(val: ParserNode | list[ParserNode]) -> bool:
    if isinstance(val, list):
        return any(linkInValue(x) for x in val)
    else:
        return isinstance(val, StartTag) and val.tag in ("a", "bs-link")


AUTOLINK_DFN_RE = re.compile(r".*?(?=\||=])", flags=re.DOTALL)


def parseAutolinkDfn(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[=":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(start + 2, AUTOLINK_DFN_RE).vi
    if match is None:
        m.die(
            "Dfn autolink was opened, but no closing =] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    innerText = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context=f"[={innerText}=]",
    )
    if "/" in innerText:
        linkFor, _, lt = innerText.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
    else:
        linkFor = None
        lt = innerText
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)

    if s[innerEnd : innerEnd + 2] == "=]":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        m.die(
            "PROGRAMMING ERROR: my regex didn't correctly capture the end of the dfn autolink :(\nPlease report this to <https://github.com/speced/bikeshed>.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="a",
        attrs={
            "data-link-type": "dfn",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if not textOverride:
        nodeEnd = innerEnd + 2
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=lt,
        )
        return Result([startTag, middleText, endTag], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending braces
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("Dfn autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i : res.i + 2] == "=]":
            if s.line(res.i + 1) > s.line(innerEnd) + 2:
                m.die(
                    "Dfn autolinks can't be spread across too many lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 2
            break
    else:
        m.die(
            "Dfn autolink was opened, but no closing =] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])

    return Result([startTag, *innerContent, endTag], nodeEnd)


AUTOLINK_ABSTRACT_RE = re.compile(r".*?(?=\||\$])", flags=re.DOTALL)


def parseAutolinkAbstract(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[$":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(start + 2, AUTOLINK_ABSTRACT_RE).vi
    if match is None:
        m.die(
            "Abstract-op autolink was opened, but no closing $] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    innerText = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context=f"[${innerText}$]",
    )
    if "/" in innerText:
        linkFor, _, lt = innerText.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
    else:
        linkFor = None
        lt = innerText
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)

    if s[innerEnd : innerEnd + 2] == "$]":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        m.die(
            "PROGRAMMING ERROR: my regex didn't correctly capture the end of the Abstract-op autolink :(\nPlease report this to <https://github.com/speced/bikeshed>.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="a",
        attrs={
            "data-link-type": "abstract-op",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if not textOverride:
        nodeEnd = innerEnd + 2
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=lt,
        )
        return Result([startTag, middleText, endTag], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending braces
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("Abstract-op autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i : res.i + 2] == "$]":
            if s.line(res.i + 1) > s.line(innerEnd) + 2:
                m.die(
                    "Abstract-op autolinks can't be spread across too many lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 2
            break
    else:
        m.die(
            "Abstract-op autolink was opened, but no closing $] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])

    return Result([startTag, *innerContent, endTag], nodeEnd)


AUTOLINK_HEADER_RE = re.compile(r":?.*?(?=\||:])", flags=re.DOTALL)


def parseAutolinkHeader(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "[:":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(start + 2, AUTOLINK_HEADER_RE).vi
    if match is None:
        m.die(
            "HTTP Header autolink was opened, but no closing :] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    innerText = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context=f"[:{innerText}:]",
    )
    if "/" in innerText:
        linkFor, _, lt = innerText.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
    else:
        linkFor = None
        lt = innerText
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)

    if s[innerEnd : innerEnd + 2] == ":]":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        m.die(
            "PROGRAMMING ERROR: my regex didn't correctly capture the end of the HTTP Header autolink :(\nPlease report this to <https://github.com/speced/bikeshed>.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="a",
        attrs={
            "data-link-type": "http-header",
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startTick = RawText(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        text="`",
    )
    startCode = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="code",
    )

    if not textOverride:
        nodeEnd = innerEnd + 2
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        endCode = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startCode.tag,
        )
        endTick = RawText(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            text="`",
        )

        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=lt,
        )
        return Result([startTick, startCode, startTag, middleText, endTag, endCode, endTick], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending braces
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("HTTP Header autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i : res.i + 2] == ":]":
            if s.line(res.i + 1) > s.line(innerEnd) + 2:
                m.die(
                    "HTTP Header autolinks can't be spread across too many lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 2
            break
    else:
        m.die(
            "HTTP Header autolink was opened, but no closing :] was found. Either close your autolink, or escape the initial [ as &#91;",
            lineNum=s.loc(start),
        )
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])
    endCode = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startCode.tag,
    )
    endTick = RawText(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        text="`",
    )

    return Result([startTick, startCode, startTag, *innerContent, endTag, endCode, endTick], nodeEnd)


AUTOLINK_IDL_RE = re.compile(r".*?(?=\||}})", flags=re.DOTALL)


def parseAutolinkIdl(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "{{":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(start + 2, AUTOLINK_IDL_RE).vi
    if match is None:
        m.die(
            "IDL autolink was opened, but no closing }} was found. Either close your autolink, or escape the initial { as &#123;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    innerText = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context="{{" + innerText + "}}",
    )
    if "/" in innerText:
        linkFor, _, innerText = innerText.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
    else:
        linkFor = None
    if "!!" in innerText:
        lt, _, linkType = innerText.partition("!!")
        linkType = linkType.strip()
        if linkType in config.idlTypes:
            pass
        else:
            m.die(
                f"IDL autolink {{{{{s[start+1:innerEnd]}}}}} gave its type as '{linkType}', but only IDL types are allowed.",
                lineNum=s.loc(start),
            )
            linkType = "idl"
    else:
        lt = innerText
        linkType = "idl"
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)

    if lt.startswith("constructor(") and linkFor and linkFor != "/":
        # make {{Foo/constructor()}} output as "Foo()" so you know what it's linking to.
        if "/" in linkFor:
            _, _, name = linkFor.rpartition("/")
        else:
            name = linkFor
        visibleText = name + lt[11:]
    else:
        visibleText = lt

    if s[innerEnd : innerEnd + 2] == "}}":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        m.die(
            "PROGRAMMING ERROR: my regex didn't correctly capture the end of the IDL autolink :(\nPlease report this to <https://github.com/speced/bikeshed>.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="a",
        attrs={
            "data-link-type": linkType,
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startCode = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="code",
        attrs={"class": "idl", "nohighlight": ""},
    ).finalize()

    if not textOverride:
        nodeEnd = innerEnd + 2
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        endCode = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startCode.tag,
        )

        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=visibleText,
        )
        return Result([startCode, startTag, middleText, endTag, endCode], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending braces
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("IDL autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i : res.i + 2] == "}}":
            if s.line(res.i + 1) > s.line(innerEnd) + 2:
                m.die(
                    "IDL autolinks can't be spread across too many lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 2
            break
    else:
        m.die(
            "IDL autolink was opened, but no closing }} was found. Either close your autolink, or escape the initial { as &#123;",
            lineNum=s.loc(start),
        )
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])
    endCode = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startCode.tag,
    )

    return Result([startCode, startTag, *innerContent, endTag, endCode], nodeEnd)


AUTOLINK_ELEMENT_RE = re.compile(r".*?(?=\||}>)", flags=re.DOTALL)


def parseAutolinkElement(s: Stream, start: int) -> Result[SafeText | list[ParserNode]]:
    if s[start : start + 2] != "<{":
        return Result.fail(start)
    # Otherwise we're locked in, this opener is a very strong signal.
    match, innerEnd = s.searchRe(start + 2, AUTOLINK_ELEMENT_RE).vi
    if match is None:
        m.die(
            "Markup autolink was opened, but no closing }> was found. Either close your autolink, or escape the initial < as &lt;",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    innerText = match[0]
    innerText = replaceMacrosInText(
        text=innerText,
        macros=s.config.macros,
        s=s,
        start=start,
        context="<<" + innerText + ">>",
    )
    if "/" in innerText:
        linkFor, _, innerText = innerText.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = re.sub(r"\s+", " ", linkFor)
        if "/" in linkFor:
            linkType = "attr-value"
        else:
            # either element-state or element-attr
            linkType = "element-sub"
    else:
        linkFor = None
        linkType = "element"
    if "!!" in innerText:
        lt, _, linkType = innerText.partition("!!")
        linkType = linkType.strip()
        if linkType in config.markupTypes:
            pass
        else:
            m.die(
                f"Markup autolink <{{{s[start+1:innerEnd]}}}> gave its type as '{linkType}', but only markup types are allowed.",
                lineNum=s.loc(start),
            )
            linkType = "idl"
    else:
        lt = innerText
    lt = lt.strip()
    lt = re.sub(r"\s+", " ", lt)

    if s[innerEnd : innerEnd + 2] == "}>":
        textOverride = False
    elif s[innerEnd] == "|":
        textOverride = True
    else:
        m.die(
            "PROGRAMMING ERROR: my regex didn't correctly capture the end of the markup autolink :(\nPlease report this to <https://github.com/speced/bikeshed>.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="a",
        attrs={
            "data-link-type": linkType,
            "data-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s[start : innerEnd + 2]),
            "bs-opaque": "",
        },
    )
    if linkFor is not None:
        startTag.attrs["data-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startCode = StartTag(
        line=s.line(start),
        endLine=s.line(start + 1),
        context=s.context,
        tag="code",
        attrs={"nohighlight": ""},
    ).finalize()

    if not textOverride:
        nodeEnd = innerEnd + 2
        endTag = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startTag.tag,
        )
        endCode = EndTag(
            line=s.line(innerEnd),
            endLine=s.line(nodeEnd),
            context=s.context,
            tag=startCode.tag,
        )

        middleText = SafeText(
            line=s.line(start + 1),
            endLine=s.line(innerEnd),
            context=s.context,
            text=lt,
        )
        return Result([startCode, startTag, middleText, endTag, endCode], nodeEnd)

    # Otherwise we need to parse what's left, until we find the ending braces
    innerContent: list[ParserNode] = []
    for res in generateResults(s, innerEnd + 1):
        value = res.value
        assert value is not None
        if linkInValue(value):
            m.die("Element autolinks can't contain more links in their linktext.", lineNum=s.loc(start))
            return Result(
                SafeText(
                    line=s.line(start),
                    endLine=s.line(innerEnd + 1),
                    context=s.context,
                    text=s[start : innerEnd + 1],
                ),
                innerEnd + 1,
            )
        if isinstance(value, list):
            innerContent.extend(value)
        else:
            innerContent.append(value)
        if s[res.i : res.i + 2] == "}>":
            if s.line(res.i + 1) > s.line(innerEnd) + 2:
                m.die(
                    "Element autolinks can't be spread across too many lines. You might have forgotten to close your autolink; if not, switch to the HTML syntax to spread your link across multiple lines.",
                    lineNum=s.loc(start),
                )
                return Result(
                    SafeText(
                        line=s.line(start),
                        endLine=s.line(innerEnd + 1),
                        context=s.context,
                        text=s[start : innerEnd + 1],
                    ),
                    innerEnd + 1,
                )
            nodeEnd = res.i + 2
            break
    else:
        m.die(
            "Element autolink was opened, but no closing }> was found. Either close your autolink, or escape the initial < as &lt;",
            lineNum=s.loc(start),
        )
        return Result(
            SafeText(line=s.line(start), endLine=s.line(innerEnd + 1), context=s.context, text=s[start : innerEnd + 1]),
            innerEnd + 1,
        )

    endTag = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startTag.tag,
    )
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])
    endCode = EndTag(
        line=s.line(nodeEnd - 2),
        endLine=s.line(nodeEnd),
        context=s.context,
        tag=startCode.tag,
    )

    return Result([startCode, startTag, *innerContent, endTag, endCode], nodeEnd)


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

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(contentStart),
        context=s.context,
        tag="code",
        attrs={"bs-autolink-syntax": f"{ticks}{text}{ticks}", "bs-opaque": ""},
    )
    content = RawText(
        line=s.line(contentStart),
        endLine=s.line(contentEnd),
        context=s.context,
        text=escapeHTML(text),
    )
    endTag = EndTag(
        line=s.line(contentEnd),
        endLine=s.line(i),
        context=s.context,
        tag=startTag.tag,
    )
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
    tag = StartTag(
        line=s.line(start),
        endLine=s.line(start),
        context=s.context,
        tag="xmp",
    )
    if infoString:
        tag.attrs["bs-infostring"] = infoString
        lang = infoString.split(" ")[0]
        tag.classes.add(f"language-{lang}")
    el = RawElement(
        line=tag.line,
        tag=tag.tag,
        startTag=tag,
        data=contents,
        endLine=s.line(i),
        context=s.context,
    )
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
                RawText(
                    line=s.line(start),
                    endLine=s.line(i),
                    context=s.context,
                    text=s[start:i],
                ),
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
            RawText(
                line=s.line(start),
                endLine=s.line(i),
                context=s.context,
                text=s[start:i],
            ),
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
    el = RawElement(
        line=startTag.line,
        tag="xmp",
        startTag=startTag,
        data=contents,
        endLine=s.line(i),
        context=s.context,
    )
    return Result(el, i)


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
