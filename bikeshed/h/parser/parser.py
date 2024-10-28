from __future__ import annotations

import re
from enum import Enum

from ... import constants, t
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


POSSIBLE_NODE_START_CHARS = "&<`'~[\\—-|"


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
        if res.err is None:
            return res
    i = start + 1
    end = len(s)
    while s[i] not in POSSIBLE_NODE_START_CHARS and i < end:
        i += 1
    node = RawText(
        line=s.line(start),
        endLine=s.line(i),
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

    if s[start] == "&":
        ch, i = parseCharRef(s, start, context=CharRefContext.NON_ATTR).vi
        if ch is not None:
            node = RawText(text=f"&#{ord(ch)};", line=s.line(start), endLine=s.line(i))
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
        if s[start : start + 2] == "\\`":
            node = RawText(
                line=s.line(start),
                endLine=s.line(start),
                text="`",
            )
            return Result(node, start + 2)
    if s.config.css:
        if s[start] == "'":
            el, i = parseCSSMaybe(s, start).vi
            if el is not None:
                return Result(el, i)
    if s[start : start + 2] == "[[":
        # biblio link, for now just pass it thru
        node = RawText(
            line=s.line(start),
            endLine=s.line(start),
            text="[[",
        )
        return Result(node, start + 2)
    if s[start] == "[":
        macroRes = parseMacro(s, start)
        if macroRes.err is None:
            return macroRes
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
            text=text,
        )
        return Result(node, endI)
    match, i = s.matchRe(start, emdashRe).vi
    if match is not None:
        # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
        node = RawText(
            line=s.line(start),
            endLine=s.line(i),
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
        if dtRes.err is None:
            return dtRes
        commentRes = parseComment(s, start)
        if commentRes.err is None:
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

    tag = StartTag(line=s.line(start), endLine=s.line(start), tag=tagname)

    while True:
        ws, i = parseWhitespace(s, i).vi
        if ws is None:
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
            attrValue = replaceMacrosInAttr(
                text=attrValue,
                macros=s.config.macros,
                s=s,
                start=i,
                attrName=attrName,
            )
        tag.attrs[attrName] = attrValue

    i = parseWhitespace(s, i).i

    if s[i] == "/":
        if s[i + 1] == ">" and tagname in ("br", "link", "meta"):
            tag.endLine = s.line(i + 1)
            return Result(tag, i + 2)
        elif s[i + 1] == ">" and preds.isXMLishTagname(tagname):
            tag.endLine = s.line(i + 1)
            el = SelfClosedTag.fromStartTag(tag)
            return Result(el, i + 2)
        else:
            m.die(f"Spurious / in <{tagname}>.", lineNum=s.loc(start))
            return Result.fail(start)

    if s[i] == ">":
        tag.endLine = s.line(i)
        return Result(tag, i + 1)

    if s.eof(i):
        m.die(f"Tag <{tagname}> wasn't closed at end of file.", lineNum=s.loc(start))
        return Result.fail(start)

    m.die(f"Garbage at {s.loc(i)} in <{tagname}>.", lineNum=s.loc(start))
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
    return Result(EndTag(s.line(start), s.line(i), tagname), i)


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
            return Result(Comment(s.line(start), s.line(i + 2), s[dataStart:i]), i + 3)
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
    node = Doctype(line=s.line(start), endLine=s.line(start + 15), data=s[start : start + 15])
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


def parseCSSProduction(s: Stream, start: int) -> Result[list[ParserNode]]:
    if s[start : start + 2] != "<<":
        return Result.fail(start)
    textStart = start + 2

    text, textEnd = s.skipTo(textStart, ">>").vi
    if text is None:
        m.die("Saw the start of a CSS production (like <<foo>>), but couldn't find the end.", lineNum=s.loc(start))
        return Result.fail(start)
    elif "\n" in text:
        m.die(
            "Saw the start of a CSS production (like <<foo>>), but couldn't find the end on the same line.",
            lineNum=s.loc(start),
        )
        return Result.fail(start)
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
                return Result.fail(start)
            textEnd = newTextEnd
            text = s[textStart:textEnd]
        else:
            m.die(
                "It seems like you wrote a CSS production (like <<foo>>), but there's more markup inside of it, or you didn't close it properly.",
                lineNum=s.loc(start),
            )
            return Result.fail(start)
    nodeEnd = textEnd + 2

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start),
        tag="fake-production-placeholder",
        attrs={"bs-autolink-syntax": s[start:nodeEnd], "class": "production", "bs-opaque": ""},
    ).finalize()
    contents = SafeText(
        line=s.line(textStart),
        endLine=s.line(textEnd),
        text=text,
    )
    endTag = EndTag(
        line=s.line(textEnd),
        endLine=s.line(nodeEnd),
        tag=startTag.tag,
    )
    return Result([startTag, contents, endTag], nodeEnd)


def parseCSSMaybe(s: Stream, start: int) -> Result[RawElement]:
    # Maybes can cause parser issues,
    # like ''<length>/px'',
    # but also can contain other markup that would split the text,
    # which used to be a problem.
    if s[start : start + 2] != "''":
        return Result.fail(start)
    i = start + 2

    text, i = s.skipTo(i, "''").vi
    if text is None:
        return Result.fail(start)
    if "\n" in text:
        return Result.fail(start)
    i += 2

    # A lot of maybes have <<foo>> links in them.
    # They break in interesting ways sometimes, but
    # also if it actually produces a link
    # (like ''width: <<length>>'' linking to 'width')
    # it'll be broken anyway.
    # So we'll hack this in - << gets turned into &lt;
    # within a maybe.
    # No chance of a link, but won't misparse in weird ways.

    if "<<" in text:
        rawContents = text.replace("<<", "&lt;").replace(">>", "&gt;")
    else:
        rawContents = text

    startTag = StartTag(
        line=s.line(start),
        endLine=s.line(start),
        tag="fake-maybe-placeholder",
        attrs={"bs-autolink-syntax": s[start:i], "bs-original-contents": escapeAttr(text)},
    ).finalize()
    el = RawElement(
        line=startTag.line,
        tag=startTag.tag,
        startTag=startTag,
        data=rawContents,
        endLine=s.line(i),
    )
    return Result(el, i)


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
        tag="code",
        attrs={"bs-autolink-syntax": f"{ticks}{text}{ticks}", "bs-opaque": ""},
    )
    content = RawText(
        line=s.line(contentStart),
        endLine=s.line(contentEnd),
        text=escapeHTML(text),
    )
    endTag = EndTag(
        line=s.line(contentEnd),
        endLine=s.line(i),
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
            m.die("Hit EOF while parsing fenced code block.", lineNum=s.line(start))
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
    )
    return Result(el, i)


macroRe = re.compile(r"([\[\\]?)\[([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]")


def parseMacro(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    # Macros all look like `[FOO]` or `[FOO?]`:
    # uppercase ASCII, possibly with a ? suffix,
    # tightly wrapped by square brackets.

    if s[start] != "[":
        return Result.fail(start)
    match, i = s.matchRe(start, macroRe).vi
    if match is None:
        return Result.fail(start)
    macroName = match[2].lower()
    optional = match[3] == "?"
    if macroName not in s.config.macros:
        if optional:
            return Result([], i)
        else:
            m.die(
                f"Found unmatched text macro {match[0]}. Correct the macro, or escape it by replacing the opening [ with &#91;",
                lineNum=s.loc(i),
            )
            return Result(
                RawText(
                    line=s.line(start),
                    endLine=s.line(i),
                    text=match[0],
                ),
                i,
            )
    macroText = s.config.macros[macroName]
    context = f"macro {match[0]}"
    try:
        newStream = s.subStream(context=context, chars=macroText)
    except RecursionError:
        m.die(
            f"Macro replacement for {match[0]} recursed more than {s.depth} levels deep; probably your text macros are accidentally recursive.",
            lineNum=s.loc(start),
        )
        return Result(
            RawText(
                line=s.line(start),
                endLine=s.line(i),
                text=match[0],
            ),
            i,
        )
    nodes = list(nodesFromStream(newStream, 0))
    return Result(nodes, i)


def replaceMacrosInAttr(text: str, macros: dict[str, str], s: Stream, start: int, attrName: str) -> str:
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
            f"Found unmatched text macro {match[0]} in {attrName}='...'. Correct the macro, or escape it by replacing the opening [ with &#91;.",
            lineNum=s.loc(start),
        )
        return msc + "&#91;" + t.cast("str", match[0][1:-1]) + "&#93;" + mec

    text, count = macroRe.subn(doRep, text)
    if count > 0:
        loops = 1
        while True:
            if loops > 10:
                m.die(
                    f"Macro replacement in {attrName}='...' recursed more than 10 levels deep; probably your text macros are accidentally recursive.",
                    lineNum=s.loc(start),
                )
                break
            if "[" not in text:
                break
            newText = macroRe.sub(doRep, text)
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
        m.die("Significant text on the same line as the metadata start tag isn't allowed.", lineNum=s.line(start))
    contents = line
    endPattern = metadataPreEndRe if startTag.tag == "pre" else metadataXmpEndRe
    while True:
        if s.eof(i):
            m.die("Hit EOF while trying to parse a metadata block.", lineNum=s.line(start))
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
            m.die("Significant text on the same line as the metadata end tag isn't allowed.", lineNum=s.line(i))
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
