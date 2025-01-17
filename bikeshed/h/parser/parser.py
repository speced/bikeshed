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
from .preds import charRefs, isControl, isWhitespace
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

# Characters used by the [...]-type autolinks, inside of the bracket.
BRACKET_AUTOLINK_CHARS = "=$:[]"

# This needs to be any character that can start a node,
# *or anything that can signal the end of a markup shorthand*,
# since I depend on the ends of markup shorthands being at the
# start of unconsumed text.
# (Adding more just means parseAnything will break text into
#  smaller chunks; it doesn't affect correctness.)
POSSIBLE_NODE_START_CHARS = "&<>`'~[]{}()\\—-|" + BRACKET_AUTOLINK_CHARS + constants.bqStart + constants.bqEnd


def nodesFromStream(s: Stream, start: int) -> t.Generator[ParserNode, None, None]:
    # Consumes the stream until eof, yielding ParserNodes.
    # Massages the results slightly for final consumption,
    # adding curly quotes and combining adjacent RawText nodes.
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
    # Consumes the stream until eof, yielding ParserNodes.
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


def generateResults(
    s: Stream,
    start: int,
    experimental: bool = False,
) -> t.Generator[Result[ParserNode | list[ParserNode]], None, None]:
    # Consumes the stream until eof, yielding the individual Results
    # (rather than unwrapping the Results, as generateNodes does).
    i = start
    end = len(s)
    while i < end:
        res = parseAnything(s, i, experimental=experimental)
        if res.valid:
            yield res
            i = res.i
        else:
            return


def generateExperimentalNodes(s: Stream, start: int, coll: list[ParserNode]) -> t.Generator[int, None, None]:
    """
    Does an experimental parse, collecting ParserNodes into the passed list.
    Yields the stream index it's up to.
    Intended to be used in a for-loop, where you manually break when you detect the end.
    """
    for res in generateResults(s, start, experimental=True):
        node, i, err = res.vie
        if not err:
            assert node is not None
            if isinstance(node, list):
                coll.extend(node)
            else:
                coll.append(node)
            yield i
        else:
            return


def parseAnything(s: Stream, start: int, experimental: bool = False) -> Result[ParserNode | list[ParserNode]]:
    """
    Either returns ParserNode(s) a la parseNode(),
    or returns a RawText node up to the next POSSIBLE_NODE_START_CHAR
    (possibly starting with such a char).
    (It does not parse the next node,
    but if the possible start char it ends at
    does not, in fact, start a node,
    it can return multiple RawTexts in a row.)

    Unlike parseNode(), this never fails to generate a result
    unless the stream is at eof.
    """
    if s.eof(start):
        return Result.fail(start)
    if s[start] in POSSIBLE_NODE_START_CHARS:
        res = parseNode(s, start)
        if not experimental:
            s.observeResult(res)
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
    Parses one or more Nodes from the start of the stream.
    Might return multiple nodes, as a list.
    Failure means the stream doesn't start with a special Node
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
    inA = s.inTagContext("a")
    inDfn = s.inTagContext("dfn")

    if first1 == constants.bqStart:
        nodes = [
            StartTag.fromStream(s, start, start + 1, "blockquote"),
            RawText.fromStream(s, start, start + 1, "\n\n"),
        ]
        return Result(nodes, start + 1)

    if first1 == constants.bqEnd:
        nodes = [RawText.fromStream(s, start, start + 1, "\n\n"), EndTag.fromStream(s, start, start + 1, "blockquote")]
        return Result(nodes, start + 1)

    if first1 == "&":
        ch, i = parseCharRef(s, start, context=CharRefContext.NonAttr).vi
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
        if first2 == r"\`":
            node = RawText.fromStream(s, start, start + 2, "`")
            return Result(node, start + 2)
        if first1 == "`":
            els, i = parseCodeSpan(s, start).vi
            if els is not None:
                return Result(els, i)
    if s.config.css and not inOpaque:
        if first2 == r"\'":
            i = start + 2
            while s[i] == "'":
                i += 1
            node = RawText.fromStream(s, start, i, s[start + 1 : i])
            return Result(node, i)
        elif first3 == "'''":
            i = start + 3
            while s[i] == "'":
                i += 1
            m.die(
                f"Saw {s[start:i]}. This is probably a typo intended to be a double apostrophe, starting a CSS maybe autolink; if not, please escape some of the apostrophes.",
                lineNum=s.loc(start),
            )
            node = RawText.fromStream(s, start, i)
            return Result(node, i)
        elif first2 == "''" and s[start - 1] != "=":
            # Temporary check to remove some error cases -
            # some weird HTML cases with an empty attr can trigger,
            maybeRes = parseCSSMaybe(s, start)
            if maybeRes.valid:
                return maybeRes
        elif first1 == "'":
            propdescRes = parseCSSPropdesc(s, start)
            if propdescRes.valid:
                if inA:
                    m.die(
                        "Parsed a CSS property autolink ('foo') inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return propdescRes
    if s.config.css:
        if first3 == "\\<<":
            node = SafeText.fromStream(s, start, start + 3, "<<")
            return Result(node, start + 3)
        elif first2 == "<<":
            if inA:
                m.die(
                    "Parsed a CSS production autolink (<<foo>>) inside of an <a> or another autolink. Either close the <a> properly, or escape the autolink.",
                    lineNum=s.loc(start),
                )
                node = SafeText.fromStream(s, start, start + 2)
                return Result(node, start + 2)
            prodRes = parseCSSProduction(s, start)
            if prodRes.valid:
                return prodRes
    if s.config.dfn and not inOpaque:
        if first3 in ("\\[=", "\\[$"):
            node = RawText.fromStream(s, start, start + 3, "[" + s[start + 2])
            return Result(node, start + 3)
        if first2 == "[=":
            dfnRes = parseAutolinkDfn(s, start)
            if dfnRes.valid:
                if inA:
                    m.die(
                        "Parsed a dfn autolink ([=...=]) inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return dfnRes
        if first2 == "[$":
            abstractRes = parseAutolinkAbstract(s, start)
            if abstractRes.valid:
                if inA:
                    m.die(
                        "Parsed an abstract-op autolink ([$...$]) inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return abstractRes
    if s.config.header and not inOpaque:
        if first3 == "\\[:":
            node = RawText.fromStream(s, start, start + 3, "[:")
            return Result(node, start + 3)
        if first2 == "[:":
            headerRes = parseAutolinkHeader(s, start)
            if headerRes.valid:
                if inA:
                    m.die(
                        "Parsed an http-header autolink ([:...:]) inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return headerRes
    if s.config.idl and not inOpaque:
        if first3 == "\\{{":
            node = RawText.fromStream(s, start, start + 3, "{{")
            return Result(node, start + 3)
        if first2 == "{{":
            idlRes = parseAutolinkIdl(s, start)
            if idlRes.valid:
                if inA:
                    m.die(
                        "Parsed an IDL autolink ({{...}}) inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return idlRes
    if s.config.markup and not inOpaque:
        if first3 == "\\<{":
            node = RawText.fromStream(s, start, start + 3, "<{")
            return Result(node, start + 3)
        if s.config.idl and first3 == "<{{":
            # Catch things like `{{Promise}}<{{Foo}}>` from being parsed as element links
            node = SafeText.fromStream(s, start, start + 1)
            return Result(node, start + 1)
        if first2 == "<{":
            elementRes = parseAutolinkElement(s, start)
            if elementRes.valid:
                if inA:
                    m.die(
                        "Parsed a markup autolink (<{...}>) inside of an <a>. Either close the <a> properly, or escape the autolink.",
                        lineNum=s.loc(start),
                    )
                return elementRes
    if s.config.algorithm and not inOpaque:
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
        if not (inA or inDfn) and first2 == "[[":
            # The WebIDL "private slot" syntax overlaps with biblio autolinks,
            # but biblios don't belong in links or dfns *anyway*. So I'll just
            # not parse biblios *at all* in those contexts, rather than throw
            # errors like the other autolinks.
            biblioRes = parseAutolinkBiblioSection(s, start)
            if biblioRes.valid:
                return biblioRes
    if s.config.markdown and not inOpaque:
        if first2 == "\\[":
            node = RawText.fromStream(s, start, start + 2, "[")
            return Result(node, start + 2)
        elif first1 == "[" and s[start - 1] != "[":
            linkRes = parseMarkdownLink(s, start)
            if linkRes.valid:
                return linkRes
    if first2 == "\\[" and isMacroStart(s, start + 2):
        # an escaped macro, so handle it here
        node = RawText.fromStream(s, start, start + 2, "[")
        return Result(node, start + 2)
    if first1 == "[" and s[start - 1] != "[" and isMacroStart(s, start + 1):
        macroRes = parseMacroToNodes(s, start)
        if macroRes.valid:
            return macroRes
    if s.config.markdownEscapes and not inOpaque:
        if first1 == "\\" and isMarkdownEscape(s, start):
            node = RawText.fromStream(s, start, start + 2, htmlifyMarkdownEscapes(s[start : start + 2]))
            return Result(node, start + 2)
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
                if "bs-macros" in startTag.attrs:
                    text = replaceMacrosInText(text, s.config.macros, s, start, context="<pre> contents")
                el = RawElement.fromStream(s, start, i, startTag, text)
                return Result(el, i)
        if startTag.tag == "script":
            text, i = parseScriptToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            if "bs-macros" in startTag.attrs:
                text = replaceMacrosInText(text, s.config.macros, s, start, context="<script> contents")
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        elif startTag.tag == "style":
            text, i = parseStyleToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            if "bs-macros" in startTag.attrs:
                text = replaceMacrosInText(text, s.config.macros, s, start, context="<style> contents")
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        elif startTag.tag == "xmp":
            text, i = parseXmpToEnd(s, i).vi
            if text is None:
                return Result.fail(start)
            if "bs-macros" in startTag.attrs:
                text = replaceMacrosInText(text, s.config.macros, s, start, context="<xmp> contents")
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Result(el, i)
        else:
            return Result(startTag, i)

    endTag, i = parseEndTag(s, start).vi
    if endTag is not None:
        return Result(endTag, i)

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

    attrs, i = parseAttributeList(s, i).vi
    if attrs is None:
        return Result.fail(start)

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


def parseAttributeList(s: Stream, start: int) -> Result[dict[str, str]]:
    i = parseWhitespace(s, start).i
    attr = None
    attrs: dict[str, str] = {}
    while True:
        if s.eof(i):
            break
        startAttr = i

        # Macros are allowed in attr list context, *if* they expand to an attribute list.
        if s[i] == "[":
            macroAttrs, i = parseMacroToAttrs(s, i).vi
            if macroAttrs is None:
                break
            macroName = s[startAttr:i]
            for k, v in macroAttrs.items():
                if k in attrs:
                    m.die(
                        f"Attribute '{k}', coming from the {macroName} macro, already exists on the element.",
                        lineNum=s.loc(startAttr),
                    )
                    continue
                attrs[k] = v
        elif preds.isAttrNameChar(s[i]):
            attr, i = parseAttribute(s, i).vi
            if attr is None:
                break
            attrName, attrValue = attr
            if attrName in attrs:
                m.die(f"Attribute '{attrName}' appears twice in the tag.", lineNum=s.loc(startAttr))
                return Result.fail(start)
            if "[" in attrValue:
                attrValue = replaceMacrosInText(
                    text=attrValue,
                    macros=s.config.macros,
                    s=s,
                    start=i,
                    context=f"attribute {attrName}='...'",
                )
            attrs[attrName] = attrValue
        else:
            break

        ws, i = parseWhitespace(s, i).vi
        if ws is None:
            # We're definitely done, just see if it should be an error nor not.
            if s.eof(i):
                # At the end of a macro, most likely
                # (or the doc ended with an unclosed tag, so I'll catch that later)
                break
            if s[i] in ("/", ">"):
                # End of a tag
                break
            m.die(
                f"Expected whitespace between attributes. ({s[startAttr:i+5]}...)",
                lineNum=s.loc(i),
            )
            break
    return Result(attrs, i)


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
            ch, i = parseCharRef(s, i, context=CharRefContext.Attr).vi
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
            ch, i = parseCharRef(s, i, context=CharRefContext.Attr).vi
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
    Attr = "Attr"
    NonAttr = "NonAttr"


def parseCharRef(s: Stream, start: int, context: CharRefContext) -> Result[str]:
    if s[start] != "&":
        return Result.fail(start)
    i = start + 1

    if preds.isASCIIAlphanum(s[i]):
        i += 1
        while preds.isASCIIAlphanum(s[i]):
            i += 1
        if s[i] == "=":
            if context is CharRefContext.Attr:
                # HTML allows you to write <a href="?foo&bar=baz">
                # without escaping the ampersand, even if it matches
                # a named charRef so long as there's an `=` after it.
                return Result.fail(start)
            elif context is CharRefContext.NonAttr:
                pass
            else:
                t.assert_never(context)
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
    if s[start : start + 2] != "''":
        return Result.fail(start)
    textStart = start + 2

    res = parseMaybeDecl(s, textStart)
    if res.valid:
        return res

    res = parseMaybeValue(s, textStart)
    if res.valid:
        return res

    return Result.fail(start)


MAYBE_DECL_RE = re.compile(r"(@[\w-]+/)?([\w-]+)$")


def parseMaybeDecl(s: Stream, textStart: int) -> Result[list[ParserNode]]:
    rawText, colonStart = s.skipTo(textStart, ":").vi
    if not rawText:
        return Result.fail(textStart)
    if s.line(textStart) != s.line(colonStart):
        return Result.fail(textStart)
    if "'" in rawText:
        return Result.fail(textStart)
    if not s[colonStart + 1].isspace():
        return Result.fail(textStart)
    colonEnd = colonStart + 1

    text = replaceMacrosInText(
        text=rawText,
        macros=s.config.macros,
        s=s,
        start=textStart,
        context=f"''{rawText}: ...''",
    )
    match = MAYBE_DECL_RE.match(text)
    if not match:
        return Result.fail(textStart)

    for_, propdescname = match.groups()

    autolinkSyntax = f"''{rawText}: ...''"
    if rawText != text:
        autolinkSyntax += f" (expands to ''{text}: ...'')"

    startTag = StartTag.fromStream(
        s,
        textStart - 2,
        textStart,
        "a",
        {
            "bs-autolink-syntax": escapeAttr(autolinkSyntax),
            "class": "css",
            "data-link-type": "propdesc",
            "data-lt": escapeAttr(propdescname),
        },
    )
    if for_:
        startTag.attrs["data-link-for"] = escapeAttr(for_)
        startTag.attrs["data-link-type"] = "descriptor"
    startTag.finalize()

    declStart = RawText.fromStream(s, textStart, colonEnd, propdescname + ":")

    rest, nodeEnd = parseLinkText(s, colonEnd, "''", "''", startTag).vi
    if rest is None:
        return Result.fail(textStart)
    return Result([startTag, declStart, *rest], nodeEnd)


MAYBE_VAL_RE = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")


def parseMaybeValue(s: Stream, textStart: int) -> Result[list[ParserNode]]:
    start = textStart - 2

    # Ugh, "maybe" autolinks might be text *or* html; we can't tell until we examine them.
    # So, do a real (but experimental) parse to the next '', holding onto the results.
    # Do some analysis on the *text* in those bounds,
    # and then, only if it looks like we need to, process the parse results.

    startLine = s.line(start)
    nodes: list[ParserNode] = []
    for i in generateExperimentalNodes(s, textStart, nodes):
        if s.line(i) > startLine + 3:
            m.die(
                "CSS-maybe autolink (''foo'') was opened, but no closing '' was found within a few lines. Either close your autolink, switch to the <css></css> element if you need the contents to stretch across that many lines, or escape the initial '' as &#39;&#39; if it wasn't intended at all.",
                lineNum=s.loc(i),
            )
            return Result.fail(textStart)
        if s[i : i + 2] == "''":
            textEnd = i
            nodeEnd = i + 2
            break

    rawText = s[textStart:textEnd]
    text = replaceMacrosInText(
        text=rawText,
        macros=s.config.macros,
        s=s,
        start=start,
        context=f"''{rawText}''",
    )
    # Do some text-based analysis of the contents first.

    match = MAYBE_VAL_RE.match(text)
    if match:
        for_, valueName, linkType = match.groups()
        probablyAutolink = (for_ is not None and not for_.endswith("<")) or match[3] is not None
    else:
        for_ = None
        valueName = text
        linkType = None
        probablyAutolink = False

    if linkType is None:
        linkType = "maybe"
    elif linkType in config.maybeTypes:
        pass
    else:
        # Looks like a maybe shorthand, just with an illegal type,
        # so format it nicely and leave it alone.
        m.die(
            f"Shorthand ''{rawText}'' gives type as '{linkType}', but only “maybe” sub-types are allowed: {config.englishFromList(config.maybeTypes)}.",
            lineNum=s.loc(start),
        )
        return Result(
            [
                StartTag.fromStream(s, start, textStart, "css"),
                SafeText.fromStream(s, textStart, textEnd, valueName),
                EndTag.fromStream(s, textEnd, nodeEnd, "css"),
            ],
            nodeEnd,
        )

    # If the text looked sufficiently like an autolink,
    # (has a for value (that doesn't look like it's from an end tag) and/or a manual type),
    # act as if the text was autolinking literal the whole time,
    # and format it nicely (just give it the valueName as contents).
    # Otherwise, use the parsed nodes as contents,
    # but set it up for autolinking based on the text,
    # and tell it what to replace itself with if it *does* succeed at linking.
    startTag = StartTag.fromStream(
        s,
        start,
        textStart,
        "bs-link",
        {
            "class": "css",
            "bs-autolink-syntax": escapeAttr(s[start:nodeEnd]),
            "data-link-type": linkType,
            "data-lt": escapeAttr(valueName),
        },
    )
    if probablyAutolink:
        if "&lt" in text or "&gt" in text:
            m.die(
                f"The autolink {s[start:nodeEnd]} is using an escaped < or > in its value; you probably just want to use a literal < and >.",
                lineNum=s.loc(start),
            )
            m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
        elif "<<" in text:
            m.die(
                f"The autolink {s[start:nodeEnd]} is using << in its value; you probably just want to use a single < and >.",
                lineNum=s.loc(start),
            )
            m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
        if for_:
            startTag.attrs["data-link-for"] = escapeAttr(for_)
    startTag.finalize()

    s.observeShorthandOpen(startTag, ("''", "''"))
    if probablyAutolink:
        # Nothing to observe, this is just text.
        nodes = [SafeText.fromStream(s, textStart, textEnd, safeFromDoubleAngles(t.cast(str, valueName)))]
    else:
        startTag.attrs["bs-replace-text-on-link-success"] = escapeAttr(safeFromDoubleAngles(text))
        s.observeNodes(nodes)
    s.observeShorthandClose(s.loc(textEnd), startTag, ("''", "''"))
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)

    return Result([startTag, *nodes, endTag], nodeEnd)


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
        return Result.fail(start)
    if s[start : start + 3] == "'-'":
        return Result.fail(start)

    innerStart = start + 1

    match, innerEnd = s.matchRe(start + 1, AUTOLINK_PROPDESC_RE).vi
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


SHORTHAND_VARIABLE_RE = re.compile(r"\|(\w(?:[\w\s-]*\w)?)\|")


def parseShorthandVariable(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    match, nodeEnd = s.matchRe(start, SHORTHAND_VARIABLE_RE).vi
    if not match:
        return Result.fail(start)

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "var",
        {"bs-autolink-syntax": escapeAttr(match[0])},
    )
    contents = RawText.fromStream(s, start + 1, nodeEnd - 1)
    endTag = EndTag.fromStream(s, nodeEnd - 1, nodeEnd, startTag)
    return Result([startTag, contents, endTag], nodeEnd)


def parseAutolinkBiblioSection(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    if s[start : start + 2] != "[[":
        return Result.fail(start)

    # A bunch of `[...]` autolink syntaxes can masquerade as biblio
    # when used in code-ish array access segments, like `foo[[=this=]].
    # So, look for one of the autolink characters, since they can't
    # be valid biblios anyway, and just fail silently.
    if s[start + 2] in BRACKET_AUTOLINK_CHARS:
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

    if re.search(r"&[\w\d#]+;", lt):
        m.die(
            "Saw an HTML escape in the literal portion of an autolink. Use raw characters, or switch to the HTML syntax.",
            lineNum=s.loc(start),
        )
        # Okay to keep going, tho, it'll just fail to link.

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

    # Even tho you no longer *need* to escape [[..]] in links
    # (used for WebIDL private slots), the parser still *allows*
    # it, and graciously/silently handles the unnecessary escape.
    # The one exception is if it's link details, since they're not
    # parsed normally, so we need to fix it right here.
    if linkFor and linkFor.startswith("\\[["):
        linkFor = linkFor[1:]
    if lt and lt.startswith("\\[["):
        lt = lt[1:]

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
    s.observeShorthandOpen(startTag, (startingSigil, endingSigil))
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
            s.observeShorthandClose(s.loc(i), startTag, (startingSigil, endingSigil))
            return Result.fail(start)
        if s[i : i + endingLength] == endingSigil:
            s.observeShorthandClose(s.loc(i), startTag, (startingSigil, endingSigil))
            endTag = EndTag.fromStream(s, i, i + endingLength, startTag)
            content.append(endTag)
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
                # Unknown modifier, that's just a failure.
                return Result.fail(innerStart)

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


class MacroContext(Enum):
    Nodes = "Nodes"
    AttrList = "AttrList"
    Text = "Text"


def parseMacro(
    s: Stream,
    start: int,
    context: MacroContext,
) -> Result[ParserNode | list[ParserNode] | dict[str, str] | str]:
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
            if context is MacroContext.Nodes:
                return Result([], i)
            elif context is MacroContext.AttrList:
                return Result({}, i)
            elif context is MacroContext.Text:
                return Result("", i)
            else:
                t.assert_never(context)
        else:
            m.die(
                f"Found unmatched text macro {s[start:i]}. Correct the macro, or escape it by replacing the opening [ with &#91;",
                lineNum=s.loc(i),
            )
            if context is MacroContext.Nodes:
                return Result(
                    RawText.fromStream(s, start, i),
                    i,
                )
            elif context is MacroContext.AttrList:
                return Result({}, i)
            elif context is MacroContext.Text:
                return Result(s[start:i], i)
            else:
                t.assert_never(context)
    macroDisplay = s[start:i]
    macroText = s.config.macros[macroName]
    streamContext = f"macro {macroDisplay}"
    try:
        newStream = s.subStream(context=streamContext, chars=macroText)
    except RecursionError:
        m.die(
            f"Macro replacement for {macroDisplay} recursed more than {s.depth} levels deep; probably your text macros are accidentally recursive.",
            lineNum=s.loc(start),
        )
        if context is MacroContext.Nodes:
            return Result(
                RawText.fromStream(s, start, i),
                i,
            )
        elif context is MacroContext.AttrList:
            return Result({}, i)
        elif context is MacroContext.Text:
            return Result(s[start:i], i)
        else:
            t.assert_never(context)

    if context is MacroContext.Nodes:
        return Result(list(nodesFromStream(newStream, 0)), i)
    elif context is MacroContext.AttrList:
        attrs, attrsEnd = parseAttributeList(newStream, 0).vi
        _, wsEnd = parseWhitespace(newStream, attrsEnd).vi
        if not newStream.eof(wsEnd):
            m.die(
                f"While parsing {macroDisplay} (on {s.loc(start)}) as an attribute list, found non-attribute content: {newStream[attrsEnd:attrsEnd+10]}...",
                lineNum=newStream.loc(attrsEnd),
            )
        return Result(attrs, i)
    elif context is MacroContext.Text:
        macroText = replaceMacrosInText(macroText, newStream.config.macros, newStream, 0, streamContext)
        return Result(macroText, i)
    else:
        t.assert_never(context)


def parseMacroToNodes(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    return t.cast("Result[ParserNode | list[ParserNode]]", parseMacro(s, start, MacroContext.Nodes))


def parseMacroToAttrs(s: Stream, start: int) -> Result[dict[str, str]]:
    return t.cast("Result[dict[str, str]]", parseMacro(s, start, MacroContext.AttrList))


def parseMacroToText(s: Stream, start: int) -> Result[str]:
    return t.cast("Result[str]", parseMacro(s, start, MacroContext.Text))


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


def parseMarkdownLink(s: Stream, start: int) -> Result[ParserNode | list[ParserNode]]:
    linkTextStart = start + 1
    startingSigil = "["
    endingSigil = "](...)"

    startTag = StartTag.fromStream(s, start, linkTextStart, "a")

    # At this point, we're still not committed to this being
    # an autolink, so it should silently fail.
    startLine = s.line(start)
    nodes: list[ParserNode] = []
    for i in generateExperimentalNodes(s, linkTextStart, nodes):
        if s.line(i) > startLine + 3:
            return Result.fail(start)
        if s[i : i + 2] == "](":
            linkTextEnd = i
            linkDestStart = i + 2
            break
        if s[i] == "]":
            return Result.fail(start)
    else:
        return Result.fail(start)
    # Now that we've seen the ](, we're committed.
    s.observeShorthandOpen(startTag, (startingSigil, endingSigil))
    s.observeNodes(nodes)
    s.observeShorthandClose(s.loc(linkTextEnd), startTag, (startingSigil, endingSigil))

    # I'm not doing bracket-checking in the link text,
    # as CommonMark requires, because I've already lost
    # the information about whether they were escaped.
    result, nodeEnd = parseMarkdownLinkDestTitle(s, linkDestStart).vi
    if result is None:
        # Return the already-parsed stuff, with the syntax
        # chars turned back into text.
        openingSquare = RawText.fromStream(s, start, start + 1)
        middleBit = RawText.fromStream(s, linkTextEnd, linkDestStart)
        return Result([openingSquare, *nodes, middleBit], linkDestStart)
    dest, title = result
    startTag.attrs["href"] = dest
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s[start:nodeEnd])
    if title:
        startTag.attrs["title"] = title
    endTag = EndTag.fromStream(s, nodeEnd - 1, nodeEnd, startTag)
    return Result([startTag, *nodes, endTag], nodeEnd)


def parseMarkdownLinkDestTitle(s: Stream, start: int) -> Result[tuple[str, str]]:
    res, i = parseMarkdownLinkWhitespace(s, start).vi
    if res is None:
        return Result.fail(start)

    TITLE_START_CHARS = ('"', "'", "(")

    dest: str | None = ""
    title: str | None = ""
    if s[i] == ")":
        # Perfectly fine to be empty.
        return Result(("", ""), i + 1)

    # Parse an optional destination
    if s[i] == "<":
        dest, i = parseMarkdownLinkAngleDest(s, i + 1).vi
        sawDest = True
    elif s[i] in TITLE_START_CHARS:
        # This indicates a title, so a skipped dest,
        # which is totally fine.
        sawDest = False
    else:
        dest, i = parseMarkdownLinkIdentDest(s, i).vi
        sawDest = True
    if dest is None:
        return Result.fail(start)

    ws, i = parseMarkdownLinkWhitespace(s, i).vi
    if ws is None:
        return Result.fail(start)
    if s[i] == ")":
        return Result((dest, ""), i + 1)

    if s[i] in TITLE_START_CHARS:
        if ws == "" and sawDest:
            # If you do have a dest, you *must* have whitespace
            # between it and the title.
            m.die("Missing required whitespace between markdown link's destination and title", lineNum=s.loc(i))
            return Result.fail(start)

        title, i = parseMarkdownLinkTitle(s, i + 1, s[i]).vi
        if title is None:
            return Result.fail(start)
    assert title is not None

    ws, i = parseMarkdownLinkWhitespace(s, i).vi
    if ws is None:
        return Result.fail(start)

    if s[i] == ")":
        return Result((dest, title), i + 1)
    else:
        m.die(
            "Tried to parse a markdown link's destination/title, but ran into some unexpected characters",
            lineNum=s.loc(i),
        )
        return Result.fail(start)


def parseMarkdownLinkWhitespace(s: Stream, start: int) -> Result[str]:
    seenLinebreak = False
    i = start
    while isWhitespace(s[i]):
        if s.eof(i):
            m.die("Hit EOF while parsing the destination/title of a markdown link", lineNum=s.line(start))
            return Result.fail(start)
        if s[i] == "\n":
            if seenLinebreak:
                m.die("The destination/title of a markdown link can't contain a blank line.", lineNum=s.line(i))
                return Result.fail(start)
            else:
                seenLinebreak = True
        i += 1
    return Result(s[start:i], i)


def parseMarkdownLinkAngleDest(s: Stream, start: int) -> Result[str]:
    i = start
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the destination of a markdown link", lineNum=s.loc(start - 1))
            return Result.fail(start)
        elif s.config.markdownEscapes and s[i] == "\\" and s[i + 1] in ("\\", ">", "<"):
            i += 2
        elif s[i] == ">":
            break
        elif s[i] == "<":
            m.die(
                "The <>-wrapped destination of a markdown link can't contain further unescaped < characters",
                lineNum=s.loc(i),
            )
            return Result.fail(start)
        elif s[i] == "\n":
            m.die("The <>-wrapped destination of a markdown link can't contain a newline", lineNum=s.loc(i))
            return Result.fail(start)
        else:
            i += 1
    dest = s[start:i]
    if s.config.markdownEscapes:
        dest = htmlifyMarkdownEscapes(dest)
    return Result(dest, i + 1)


def parseMarkdownLinkIdentDest(s: Stream, start: int) -> Result[str]:
    i = start
    parenDepth = 0
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the destination of a markdown link", lineNum=s.loc(start))
            return Result.fail(start)
        elif s.config.markdownEscapes and s[i] == "\\" and s[i + 1] in ("\\", "(", ")"):
            i += 2
        elif isControl(s[i]):
            m.die(
                f"The destination of a markdown link can't contain ASCII control characters ({hex(ord(s[i]))})",
                lineNum=s.loc(i),
            )
            return Result.fail(start)
        elif isWhitespace(s[i]):
            break
        elif s[i] == "(":
            parenDepth += 1
            i += 1
        elif s[i] == ")":
            if parenDepth == 0:
                break
            else:
                parenDepth -= 1
                i += 1
        else:
            i += 1
    dest = s[start:i]
    if s.config.markdownEscapes:
        dest = htmlifyMarkdownEscapes(dest)
    return Result(dest, i)


def parseMarkdownLinkTitle(s: Stream, start: int, startChar: str) -> Result[str]:
    i = start
    if startChar == "'":
        endChar = "'"
    elif startChar == '"':
        endChar = '"'
    elif startChar == "(":
        endChar = ")"
    else:
        assert False
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the title of a markdown link", lineNum=s.line(start))
            return Result.fail(start)
        elif s.config.markdownEscapes and s[i] == "\\" and s[i + 1] in ("\\", startChar, endChar):
            i += 2
        elif s[i] == endChar:
            break
        elif s[i] == startChar:
            m.die(
                f"The title of a markdown link can't contain the starting char ({startChar}) unless it's escaped",
                lineNum=s.loc(i),
            )
            return Result.fail(start)
        elif isWhitespace(s[i]):
            ws, i = parseMarkdownLinkWhitespace(s, i).vi
            if ws is None:
                return Result.fail(start)
        else:
            i += 1
    title = s[start:i]
    if s.config.markdownEscapes:
        title = htmlifyMarkdownEscapes(title)
    return Result(title, i + 1)


# not escaping * or _ currently, so the slash remains until after HTML parsing,
# because em/strong aren't parsed until then.
def isMarkdownEscape(s: Stream, start: int) -> bool:
    return s[start] == "\\" and s[start + 1] in (
        "\\",
        "!",
        '"',
        "#",
        "$",
        "%",
        "&",
        "'",
        "(",
        ")",
        # "*",
        "+",
        ",",
        "-",
        ".",
        "/",
        ":",
        ";",
        "<",
        "=",
        ">",
        "?",
        "@",
        "[",
        "]",
        "^",
        # "_",
        "`",
        "{",
        "|",
        "}",
        "~",
    )


MARKDOWN_ESCAPE_RE = re.compile(r"\\([\\!\"#$%&'()*+,./:;<=>?@\[\]^_`{|}~-])")


def htmlifyMarkdownEscapes(val: str) -> str:
    return re.sub(MARKDOWN_ESCAPE_RE, markdownEscapeReplacer, val)


def markdownEscapeReplacer(match: re.Match) -> str:
    return f"&#{ord(match[1])};"
