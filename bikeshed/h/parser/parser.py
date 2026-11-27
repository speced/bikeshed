"""Core inline stream parsing loop, top-level syntax dispatch, and open-element cleanup."""

from __future__ import annotations

import re

from ... import messages as m
from ... import t
from .. import elements
from . import autolinks, css, html, macros, markdown
from .nodes import (
    EmphDelim,
    EndTag,
    ParserNode,
    RawElement,
    RawText,
    SafeElement,
    SafeText,
    SelfClosedTag,
    StartTag,
    escapeAttr,
)
from .result import Err, Ok, isOk
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import OkT, ResultT

# This needs to be any character that can start a node,
# *or anything that can signal the end of a markup shorthand*,
# since I depend on the ends of markup shorthands being at the
# start of unconsumed text.
# (Adding more just means parseAnything will break text into
#  smaller chunks; it doesn't affect correctness.)
POSSIBLE_NODE_START_CHARS = "&<>`'~[]{}()\\—-|" + autolinks.BRACKET_AUTOLINK_CHARS
POSSIBLE_NODE_START_RE = re.compile(f"[{re.escape(POSSIBLE_NODE_START_CHARS)}]")
ACTUAL_NODE_START_CHARS = "&<>`'~[{|\\—-"
ACTUAL_NODE_START_SET = frozenset(ACTUAL_NODE_START_CHARS)
_ACTUAL_NODE_START_RE = re.compile(f"[{re.escape(ACTUAL_NODE_START_CHARS)}]")
_ACTUAL_LINE_STOP_RE = re.compile(f"[\n{re.escape(ACTUAL_NODE_START_CHARS)}]")
_PROD_NODE_START_CHARS = "".join(dict.fromkeys(ACTUAL_NODE_START_CHARS + css.PROD_GRAMMAR_START_CHARS))
_PROD_NODE_START_SET = frozenset(_PROD_NODE_START_CHARS)
_PROD_NODE_START_RE = re.compile(f"[{re.escape(_PROD_NODE_START_CHARS)}]")
_PROD_LINE_STOP_RE = re.compile(f"[\n{re.escape(_PROD_NODE_START_CHARS)}]")
_PROD_POSSIBLE_NODE_START_CHARS = "".join(dict.fromkeys(POSSIBLE_NODE_START_CHARS + css.PROD_GRAMMAR_START_CHARS))
_PROD_POSSIBLE_NODE_START_RE = re.compile(f"[{re.escape(_PROD_POSSIBLE_NODE_START_CHARS)}]")
_EMPH_NODE_START_CHARS = ACTUAL_NODE_START_CHARS + "*"
_EMPH_NODE_START_SET = frozenset(_EMPH_NODE_START_CHARS)
_EMPH_NODE_START_RE = re.compile(f"[{re.escape(_EMPH_NODE_START_CHARS)}]")
_EMPH_LINE_STOP_RE = re.compile(f"[\n{re.escape(_EMPH_NODE_START_CHARS)}]")
_EMPH_POSSIBLE_NODE_START_RE = re.compile(f"[{re.escape(POSSIBLE_NODE_START_CHARS + '*')}]")
_RAW_HTML_START_RE = re.compile(r"[&<]")
emdashRe = re.compile(r"(?:(?<!-)(—|--))\n\s*(?=\S)")


def _stripIndentAfterNewlines(text: str, indent: int, numIndents: int) -> str:
    """Strips up to `numIndents` indentation levels after each `\\n` in multi-line inline text."""
    spaces = " " * indent
    parts = text.split("\n")
    for idx in range(1, len(parts)):
        part = parts[idx]
        offset = 0
        for _ in range(numIndents):
            if offset < len(part) and part[offset] == "\t":
                offset += 1
            elif part.startswith(spaces, offset):
                offset += indent
            else:
                break
        if offset:
            parts[idx] = part[offset:]
    return "\n".join(parts)


def _parseRawHtmlNodes(s: Stream, start: int) -> tuple[list[ParserNode], int]:
    """Fast-path plain-HTML parser for `rawHtml` mode, skipping Bikeshed shorthands and macros."""
    nodes: list[ParserNode] = []
    chars = s.chars
    end = s.length
    i = start
    lastRaw: RawText | None = None
    # Start offset of an accumulated plain-text run (-1 when no run is open).
    textStart = -1

    def pushRaw(node: RawText, canMerge: bool) -> None:
        nonlocal lastRaw
        if canMerge and lastRaw is not None and lastRaw.end == node.start:
            lastRaw.text += node.text
            lastRaw.end = node.end
        else:
            if lastRaw is not None:
                nodes.append(lastRaw)
            if canMerge:
                lastRaw = node
            else:
                nodes.append(node)
                lastRaw = None

    while i < end:
        ch = chars[i]
        if ch in ("&", "<"):
            res = parseNode(s, i)
            if isOk(res):
                if textStart != -1:
                    pushRaw(RawText.fromStream(s, textStart, i), canMerge=True)
                    textStart = -1
                val, i, _ = res
                assert not isinstance(val, list)
                if isinstance(val, SafeText):
                    val = RawText.fromSafeText(val)
                if isinstance(val, RawText):
                    canMerge = val.s is s and val.text.count("\n") == chars.count("\n", val.start, val.end)
                    pushRaw(val, canMerge)
                else:
                    if lastRaw is not None:
                        nodes.append(lastRaw)
                        lastRaw = None
                    s.observeNode(val)
                    nodes.append(val)
                continue
        if textStart == -1:
            textStart = i
        match = _RAW_HTML_START_RE.search(chars, i + 1)
        i = match.start() if match else end

    if textStart != -1:
        pushRaw(RawText.fromStream(s, textStart, i), canMerge=True)
    if lastRaw is not None:
        nodes.append(lastRaw)
    return nodes, i


def parseInlineNodes(
    s: Stream,
    start: int,
    *,
    stopAtNewline: bool = False,
    minIndent: int = 0,
    onMacroNodes: t.Callable[[list[ParserNode], bool], None] | None = None,
    atLineStart: bool = False,
) -> tuple[list[ParserNode], int]:
    """Parses HTML/inline Bikeshed nodes from `s` starting at `start`, applying curly
    apostrophes and merging contiguous `RawText` nodes.

    When `stopAtNewline` is True, stops at (and consumes) the first `\\n` outside any
    multi-line construct and outside any open opaque element (`s.inOpaqueElement()`).
    When `atLineStart` is True, `start` is treated as column 0 of the logical line
    (e.g. after a list marker) so leading fenced code blocks are recognized.
    """
    if s.config.rawHtml:
        assert not stopAtNewline
        return _parseRawHtmlNodes(s, start)

    nodes: list[ParserNode] = []
    # `lastNode` is always the previous emitted node (for curlifyApostrophes context);
    # when `heldLast` is True, it is an unappended RawText buffered for merging.
    lastNode: ParserNode | None = None
    heldLast = False
    heldCanMerge = False
    textStart = -1
    chars = s.chars
    end = s.length
    i = start
    openEls = s.openEls
    cssEnabled = s.config.css
    mdInline = s.config.markdownInline
    indent = s.config.indent

    inOpaque = False
    inProd = False
    inEmph = False
    startSet: frozenset[str] = ACTUAL_NODE_START_SET
    scanRe: t.Pattern = _ACTUAL_NODE_START_RE

    def refreshMode() -> None:
        nonlocal inOpaque, inProd, inEmph, startSet, scanRe
        inOpaque = openEls.inOpaqueElement()
        inProd = cssEnabled and s.inProdElement()
        inEmph = mdInline and not inOpaque and not inProd
        stopLine = stopAtNewline and not inOpaque
        if inProd:
            startSet = _PROD_NODE_START_SET
            scanRe = _PROD_LINE_STOP_RE if stopLine else _PROD_NODE_START_RE
        elif inEmph:
            startSet = _EMPH_NODE_START_SET
            scanRe = _EMPH_LINE_STOP_RE if stopLine else _EMPH_NODE_START_RE
        else:
            startSet = ACTUAL_NODE_START_SET
            scanRe = _ACTUAL_LINE_STOP_RE if stopLine else _ACTUAL_NODE_START_RE

    def emitRaw(node: RawText, canMerge: bool) -> None:
        nonlocal lastNode, heldLast, heldCanMerge
        if not inOpaque:
            if minIndent > 0 and "\n" in node.text and node.s is s:
                node.text = _stripIndentAfterNewlines(node.text, indent, minIndent)
            node.curlifyApostrophes(lastNode)
        if heldLast and heldCanMerge and canMerge and isinstance(lastNode, RawText) and lastNode.end == node.start:
            lastNode.text += node.text
            lastNode.end = node.end
        else:
            if heldLast:
                assert lastNode is not None
                nodes.append(lastNode)
            lastNode = node
            heldLast = True
            heldCanMerge = canMerge

    refreshMode()

    while i < end:
        ch = chars[i]
        if stopAtNewline and ch == "\n" and not inOpaque:
            break
        if ch in startSet:
            isAtLineStart = atLineStart and lastNode is None and (textStart == -1 or chars[textStart:i].strip() == "")
            res = parseNode(s, i, atLineStart=isAtLineStart, parseFast=True, inOpaque=inOpaque, inProd=inProd)
            if isOk(res):
                if textStart != -1:
                    emitRaw(RawText.fromStream(s, textStart, i), canMerge=True)
                    textStart = -1

                val, nextI, _ = res
                wasOpaque = inOpaque
                s.observeResult(res)
                refreshMode()
                if isinstance(val, list):
                    # Macro expansions are parsed in a child Stream, so `val[0].s is not s` identifies them.
                    if (
                        onMacroNodes is not None
                        and not wasOpaque
                        and val
                        and val[0].s is not None
                        and val[0].s is not s
                    ):
                        onMacroNodes(val, s.col(i) == 1)
                    items: t.Sequence[ParserNode] = val
                else:
                    items = (val,)

                for item in items:
                    if isinstance(item, SafeText):
                        item = RawText.fromSafeText(item)
                    if isinstance(item, RawText) and not isinstance(item, EmphDelim):
                        # Only merge RawText nodes belonging to this stream whose emitted
                        # newlines match their source line span (not line-ending em-dashes),
                        # so downstream `node.line + j` line tracking stays accurate.
                        nodeCanMerge = item.s is s and item.text.count("\n") == chars.count("\n", item.start, item.end)
                        emitRaw(item, nodeCanMerge)
                    else:
                        if heldLast:
                            assert lastNode is not None
                            nodes.append(lastNode)
                        nodes.append(item)
                        lastNode = item
                        heldLast = False
                        heldCanMerge = False
                i = nextI
                continue

        if textStart == -1:
            textStart = i
        match = scanRe.search(chars, i + 1)
        i = match.start() if match else end

    if textStart != -1:
        emitRaw(RawText.fromStream(s, textStart, i), canMerge=True)
    if heldLast:
        assert lastNode is not None
        nodes.append(lastNode)
    if stopAtNewline and i < end and chars[i] == "\n" and not inOpaque:
        i += 1
    if not stopAtNewline and mdInline:
        nodes = markdown.resolveEmphasis(nodes, s.config.blockElements)
    return nodes, i


def nodesFromStream(s: Stream, start: int) -> t.Generator[ParserNode, None, None]:
    """Consume `s` from `start` to EOF, yielding curlified and coalesced `ParserNode`s."""
    nodes, _ = parseInlineNodes(s, start)
    yield from nodes


def closeOpenElements(s: Stream, start: int | None, context: str | StartTag | t.ElementT | None) -> list[EndTag]:
    """Close any elements still open on `s.openEls` at EOF (silently for a trailing `<p>`, logging an error otherwise)."""
    nodes = []
    if start is None:
        i = len(s)
    else:
        i = start
    stopper: StartTag | None = None
    if context is None:
        containerLoc = "document"
    elif isinstance(context, str):
        containerLoc = context
    elif isinstance(context, StartTag):
        containerLoc = f"<{context.tag}> (at {context.loc})"
        stopper = context
    else:
        containerLoc = f"<{context.tag}>"
        if lineNum := context.get("bs-line-number"):
            containerLoc += f" (at {lineNum})"
    if s.openEls.tags and s.openEls.tags[-1].startTag.tag == "p":
        # A final open <p> is fine, it's meant to auto-close itself
        entry = s.openEls.popEntry()
        nodes.append(EndTag.fromStream(s, i, i, entry.startTag))
    # If there's still stuff open, tho, that's a problem
    if s.openEls.tags:
        if len(s.openEls.tags) == 1:
            entry = s.openEls.tags[0]
            if containerLoc:
                msg = f"<{entry.startTag.tag}> element was still open at the end of the {containerLoc}"
            else:
                msg = f"<{entry.startTag.tag}> element was still open at the end of your document."
            m.die(msg, lineNum=entry.startTag.loc)
        else:
            endTarget = f"the {containerLoc}" if containerLoc else "your document"
            m.die(
                f"{len(s.openEls.tags)} elements were still open at the end of {endTarget}.\nOpen tags: {', '.join(s.openEls.printOpenTags())}",
            )
        while s.openEls.tags:
            if s.openEls.tags[-1].startTag == stopper:
                break
            entry = s.openEls.popEntry()
            nodes.append(EndTag.fromStream(s, i, i, entry.startTag))
    return nodes


def debugNode(node: ParserNode | list[ParserNode]) -> str:
    """Return a compact human-readable string representation of a `ParserNode` (or list of nodes) for debugging."""
    if isinstance(node, list):
        return "".join(debugNode(x) for x in node)
    if isinstance(node, StartTag):
        return f"<{node.tag} {node.loc}>"
    if isinstance(node, EndTag):
        return f"</{node.tag} {node.loc}>"
    if isinstance(node, (RawText, SafeText)):
        return f"<{type(node).__name__} {node.loc} {node.text!r}>"
    if isinstance(node, (RawElement, SafeElement)):
        return f"<{node.tag} {node.loc}>[omitted raw content]</>"
    if isinstance(node, SelfClosedTag):
        return f"<{node.tag} {node.loc} />"
    return repr(node)


def generateResults(
    s: Stream,
    start: int,
    experimental: bool = False,
) -> t.Generator[OkT[ParserNode | list[ParserNode]], None, None]:
    """Yield raw `Ok` parse results from `parseAnything()` until EOF, stopping at every `POSSIBLE_NODE_START_CHARS` boundary."""
    i = start
    end = len(s)
    while i < end:
        res = parseAnything(s, i, experimental=experimental)
        if isOk(res):
            yield res
            _, i, _ = res
        else:
            return


def generateExperimentalNodes(s: Stream, start: int, coll: list[ParserNode]) -> t.Generator[int, None, None]:
    """
    Does an experimental parse, collecting ParserNodes into the passed list.
    Yields the stream index it's up to.
    Intended to be used in a for-loop, where you manually break when you detect the end.
    """
    for res in generateResults(s, start, experimental=True):
        node, i, _ = res
        if isinstance(node, list):
            coll.extend(node)
        else:
            coll.append(node)
        yield i


def parseAnything(s: Stream, start: int, experimental: bool = False) -> ResultT[ParserNode | list[ParserNode]]:
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
        return Err(start)
    if s.config.rawHtml:
        if s.chars[start] in ("&", "<"):
            res = parseNode(s, start)
            if isOk(res):
                return res
        match = _RAW_HTML_START_RE.search(s.chars, start + 1)
        i = match.start() if match else s.length
        node = RawText.fromStream(s, start, i)
        return Ok(node, i)
    inOpaque = s.inOpaqueElement()
    inProd = s.config.css and s.inProdElement()
    inEmph = s.config.markdownInline and not inOpaque and not inProd
    startSet = _PROD_NODE_START_SET if inProd else (_EMPH_NODE_START_SET if inEmph else ACTUAL_NODE_START_SET)
    if s.chars[start] in startSet:
        res = parseNode(s, start, parseFast=True, inOpaque=inOpaque, inProd=inProd)
        if isOk(res):
            val, i, err = res
            if not experimental:
                s.observeResult(res)
            return (val, i, err)
    possRe = (
        _PROD_POSSIBLE_NODE_START_RE if inProd else (_EMPH_POSSIBLE_NODE_START_RE if inEmph else POSSIBLE_NODE_START_RE)
    )
    match = possRe.search(s.chars, start + 1)
    i = match.start() if match else s.length
    node = RawText.fromStream(s, start, i)
    return Ok(node, i)


def _parseCharRefNode(s: Stream, start: int) -> OkT[RawText | SafeText]:
    """Parse a character reference at `start`, returning a normalized `RawText` or fallback `SafeText`."""
    ch, i, _ = html.parseCharRef(s, start, context=html.CharRefContext.NonAttr)
    if ch is not None:
        if isinstance(ch, str):
            return Ok(RawText.fromStream(s, start, i, f"&#{ord(ch)};"), i)
        return Ok(ch, i)
    return Ok(SafeText.fromStream(s, start, start + 1), start + 1)


def _checkAutolinkNotInA(inA: bool, description: str, s: Stream, start: int) -> None:
    """Log an error if an autolink shorthand was parsed inside an already-open `<a>`."""
    if inA:
        m.die(
            f"Parsed {description} inside of an <a>. Either close the <a> properly, or escape the autolink.",
            lineNum=s.loc(start),
        )


def parseNode(
    s: Stream,
    start: int,
    *,
    atLineStart: bool = False,
    parseFast: bool = False,
    inOpaque: bool = False,
    inProd: bool = False,
) -> ResultT[ParserNode | list[ParserNode]]:
    """
    Parses one or more Nodes from the start of the stream.
    Might return multiple nodes, as a list.
    Failure means the stream doesn't start with a special Node
    (it'll just be text),
    but Text *can* be validly returned sometimes as the node.

    When `parseFast` is True, the caller guarantees that:
    - `start < s.length` (not at EOF),
    - `s.config.rawHtml` is False,
    - `s.chars[start]` is already in the active candidate start set
      (`_PROD_NODE_START_SET`, `_EMPH_NODE_START_SET`, or `ACTUAL_NODE_START_SET`), and
    - `inOpaque` and `inProd` reflect the current `Stream` / `TagStack` state.
    Hot-path callers (`parseInlineNodes()`, `parseAnything()`) pass `parseFast=True`
    to skip redundant EOF, `rawHtml`, `startSet`, and tag-stack checks.
    """
    node: ParserNode | list[ParserNode] | None
    if not parseFast:
        if s.eof(start):
            return Err(start)
        first1 = s.chars[start]
        if s.config.rawHtml:
            if first1 == "&":
                return _parseCharRefNode(s, start)
            if first1 == "<":
                node, i, _ = parseAngleStart(s, start)
                if node is not None:
                    return Ok(node, i)
                return Ok(SafeText.fromStream(s, start, start + 1), start + 1)
            return Err(start)

        inOpaque = s.inOpaqueElement()
        inProd = s.config.css and s.inProdElement()
        inEmph = s.config.markdownInline and not inOpaque and not inProd
        startSet = _PROD_NODE_START_SET if inProd else (_EMPH_NODE_START_SET if inEmph else ACTUAL_NODE_START_SET)
        if first1 not in startSet:
            return Err(start)
    else:
        first1 = s.chars[start]

    if first1 in ("-", "—"):
        if (first1 == "-" and s.slice(start, start + 3) == "--\n") or (
            first1 == "—" and s.slice(start, start + 2) == "—\n"
        ):
            match, i, _ = s.matchRe(start, emdashRe)
            if match is not None:
                return Ok(RawText.fromStream(s, start, i, "—\u200b"), i)
        return Err(start)

    if first1 == "&":
        if inProd and not s.inTagContext("a"):
            grammarRes = css.parseCSSProductionGrammar(s, start)
            if isOk(grammarRes):
                return grammarRes
        return _parseCharRefNode(s, start)

    if first1 == "<":
        node, i, _ = parseAngleStart(s, start)
        if node is not None:
            return Ok(node, i)
        # Only fall through for `<<` (CSS production) and `<{` (markup autolink);
        # any other unrecognized `<` is escaped immediately as SafeText.
        if s[start + 1] not in ("<", "{"):
            return Ok(SafeText.fromStream(s, start, start + 1), start + 1)

    first2 = s.slice(start, start + 2)
    first3 = s.slice(start, start + 3)

    inA = s.inTagContext("a")
    inDfn = s.inTagContext("dfn")

    el: ParserNode | None
    if first1 in ("`", "~"):
        el, i, _ = markdown.parseFencedCodeBlock(s, start, atLineStart=atLineStart)
        if el is not None:
            if blockType := html.isDatablock(el.startTag, s.loc(i)):
                el.startTag.attrs["bs-datablock-type"] = escapeAttr(blockType)
                return Ok(el, i)
            if s.config.css and "prod" in el.startTag.classes:
                bodyNodes = css.parseCSSProductionGrammarInText(s, s.nextLineStart(start), el.data)
                return Ok([el.startTag, *bodyNodes, EndTag.fromStream(s, i, i, el.startTag)], i)
            return Ok(el, i)
    if s.config.markdownInline:
        if first2 == r"\`":
            node = RawText.fromStream(s, start, start + 2, "`")
            return Ok(node, start + 2)
        if first1 == "`":
            els, i, _ = markdown.parseCodeSpan(s, start)
            if els is not None:
                return Ok(els, i)
    if s.config.css and not inOpaque:
        if first2 == r"\'":
            i = start + 2
            while s[i] == "'":
                i += 1
            node = RawText.fromStream(s, start, i, s.slice(start + 1, i))
            return Ok(node, i)
        elif first3 == "'''":
            i = start + 3
            while s[i] == "'":
                i += 1
            m.die(
                f"Saw {s.slice(start, i)}. This is probably a typo intended to be a double apostrophe, starting a CSS maybe autolink; if not, please escape some of the apostrophes.",
                lineNum=s.loc(start),
            )
            node = RawText.fromStream(s, start, i)
            return Ok(node, i)
        elif first2 == "''" and s[start - 1] != "=":
            # Temporary check to remove some error cases -
            # some weird HTML cases with an empty attr can trigger,
            maybeRes = css.parseCSSMaybe(s, start, generateResults, generateExperimentalNodes)
            if isOk(maybeRes):
                return maybeRes
        elif first1 == "'":
            propdescRes = css.parseCSSPropdesc(s, start)
            if isOk(propdescRes):
                _checkAutolinkNotInA(inA, "a CSS property autolink ('foo')", s, start)
                return propdescRes
    if s.config.css:
        if first3 == "\\<<":
            node = SafeText.fromStream(s, start, start + 3, "<<")
            return Ok(node, start + 3)
        elif first2 == "<<":
            if inA:
                m.die(
                    "Parsed a CSS production autolink (<<foo>>) inside of an <a> or another autolink. Either close the <a> properly, or escape the autolink.",
                    lineNum=s.loc(start),
                )
                node = SafeText.fromStream(s, start, start + 2)
                return Ok(node, start + 2)
            prodRes = css.parseCSSProduction(s, start)
            if isOk(prodRes):
                return prodRes
    if inProd and not inA and first1 in css.PROD_GRAMMAR_START_SET:
        grammarRes = css.parseCSSProductionGrammar(s, start)
        if isOk(grammarRes):
            return grammarRes
    if s.config.dfn and not inOpaque:
        if first3 in ("\\[=", "\\[$"):
            node = RawText.fromStream(s, start, start + 3, "[" + s[start + 2])
            return Ok(node, start + 3)
        if first2 == "[=":
            dfnRes = autolinks.parseAutolinkDfn(s, start, generateResults)
            if isOk(dfnRes):
                _checkAutolinkNotInA(inA, "a dfn autolink ([=...=])", s, start)
                return dfnRes
        if first2 == "[$":
            abstractRes = autolinks.parseAutolinkAbstract(s, start, generateResults)
            if isOk(abstractRes):
                _checkAutolinkNotInA(inA, "an abstract-op autolink ([$...$])", s, start)
                return abstractRes
    if s.config.header and not inOpaque:
        if first3 == "\\[:":
            node = RawText.fromStream(s, start, start + 3, "[:")
            return Ok(node, start + 3)
        if first2 == "[:":
            headerRes = autolinks.parseAutolinkHeader(s, start, generateResults)
            if isOk(headerRes):
                _checkAutolinkNotInA(inA, "an http-header autolink ([:...:])", s, start)
                return headerRes
    if s.config.idl and not inOpaque:
        if first3 == "\\{{":
            node = RawText.fromStream(s, start, start + 3, "{{")
            return Ok(node, start + 3)
        if first2 == "{{":
            idlRes = autolinks.parseAutolinkIdl(s, start, generateResults)
            if isOk(idlRes):
                _checkAutolinkNotInA(inA, "an IDL autolink ({{...}})", s, start)
                return idlRes
    if s.config.cddl and not inOpaque:
        if first3 == "\\{^":
            node = RawText.fromStream(s, start, start + 3, "{^")
            return Ok(node, start + 3)
        if first2 == "{^":
            cddlRes = autolinks.parseAutolinkCddl(s, start, generateResults)
            if isOk(cddlRes):
                _checkAutolinkNotInA(inA, "a CDDL autolink ({^...^})", s, start)
                return cddlRes
    if s.config.markup and not inOpaque:
        if first3 == "\\<{":
            node = SafeText.fromStream(s, start, start + 3, "<{")
            return Ok(node, start + 3)
        if s.config.idl and first3 == "<{{":
            # Catch things like `{{Promise}}<{{Foo}}>` from being parsed as element links
            node = SafeText.fromStream(s, start, start + 1)
            return Ok(node, start + 1)
        if first2 == "<{":
            elementRes = autolinks.parseAutolinkElement(s, start, generateResults)
            if isOk(elementRes):
                _checkAutolinkNotInA(inA, "a markup autolink (<{...}>)", s, start)
                return elementRes
    if s.config.algorithm and not inOpaque:
        if first2 == "\\|":
            node = RawText.fromStream(s, start, start + 2, "|")
            return Ok(node, start + 2)
        if first1 == "|":
            varRes = autolinks.parseShorthandVariable(s, start)
            if isOk(varRes):
                return varRes
    if s.config.biblio and not inOpaque:
        if first3 == "\\[[":
            node = RawText.fromStream(s, start, start + 3, "[[")
            return Ok(node, start + 3)
        if not (inA or inDfn) and first2 == "[[":
            # The WebIDL "private slot" syntax overlaps with biblio autolinks,
            # but biblios don't belong in links or dfns *anyway*. So I'll just
            # not parse biblios *at all* in those contexts, rather than throw
            # errors like the other autolinks.
            biblioRes = autolinks.parseAutolinkBiblioSection(s, start, generateResults)
            if isOk(biblioRes):
                return biblioRes
    if s.config.markdownInline and not inOpaque:
        if first2 == "\\[":
            node = RawText.fromStream(s, start, start + 2, "[")
            return Ok(node, start + 2)
        if first2 == "\\*":
            node = RawText.fromStream(s, start, start + 2, "*")
            return Ok(node, start + 2)
        if first1 == "*":
            return markdown.parseEmphasisRun(s, start)
        if first1 == "[" and s[start - 1] != "[":
            linkRes = markdown.parseMarkdownLink(s, start, generateExperimentalNodes)
            if isOk(linkRes):
                return linkRes
    if first2 == "\\[" and macros.isMacroStart(s, start + 2):
        # an escaped macro, so handle it here
        node = RawText.fromStream(s, start, start + 2, "[")
        return Ok(node, start + 2)
    if first1 == "[" and s[start - 1] != "[" and macros.isMacroStart(s, start + 1):
        macroRes = macros.parseMacroToNodes(s, start, nodesFromStream)
        if isOk(macroRes):
            return macroRes
    if s.config.markdownEscapes and not inOpaque:
        if first1 == "\\" and markdown.isMarkdownEscape(s, start):
            node = RawText.fromStream(s, start, start + 2, f"&#{ord(s[start + 1])};")
            return Ok(node, start + 2)

    if first1 == "<":
        # Wasn't a tag or a shortcut, so catch it at the end.
        return Ok(SafeText.fromStream(s, start, start + 1), start + 1)

    return Err(start)


def parseAngleStart(s: Stream, start: int) -> ResultT[ParserNode | list[ParserNode]]:
    """Dispatch constructs starting with `<`: doctypes, comments, tags, raw elements, metadata blocks, and repo links."""
    if s.metadataSpans and (metaEnd := s.metadataSpans.get(start)) is not None:
        return Ok(RawText.fromStream(s, start, metaEnd, ""), metaEnd)
    i = start + 1
    if s[i] == "!":
        dtRes = html.parseDoctype(s, start)
        if isOk(dtRes):
            return dtRes
        commentRes = html.parseComment(s, start)
        if isOk(commentRes):
            return commentRes
        return Err(start)

    if s[i] == "?":
        # XML PI, definitely invalid.
        m.die("XML Processing Instructions are invalid in HTML.", lineNum=s.loc(start))
        return Err(start)

    if s[i] == "/":
        endTag, i, _ = html.parseEndTag(s, start)
        if endTag is not None:
            if not s.config.rawHtml and endTag.tag == "l":
                # Should have been caught by parseLToEnd().
                # Since it wasn't, that means there was a parse error.
                endTag.tag = "span"
            return Ok(endTag, i)
        return Err(start)

    startTag, i, _ = html.parseStartTag(s, start, parseRepoLink=autolinks.parseRepositoryLink)
    if startTag is not None:
        if isinstance(startTag, (SelfClosedTag, list)):
            return Ok(startTag, i)
        if s.config.rawHtml:
            if startTag.tag in elements.RAW_ELEMENTS:
                text, i, _ = html.parseRawElementToEnd(s, i, startTag.tag)
                return Ok(RawElement.fromStream(s, start, i, startTag, text), i)
            return Ok(startTag, i)
        if startTag.tag == "l":
            nodes, i, _ = parseLToEnd(s, i, startTag)
            if nodes is not None:
                return Ok(nodes, i)
            else:
                startTag.tag = "span"
                if "data-link-type" in startTag.attrs:
                    startTag.attrs["bs-link-type"] = startTag.attrs.pop("data-link-type")
        if startTag.tag == "bs-macro" and not s.inOpaqueElement():
            return parseBsMacro(s, startTag, i)
        el: ParserNode | None
        if startTag.tag == "title" and not s.openEls.inTagContext("svg"):
            # Stash the HTML `<title>` text in an attribute so later pipeline stages can inspect it cleanly.
            text, endI, _ = html.parseTitleToEnd(s, i)
            if text is not None:
                startTag.attrs["bs-title-contents"] = escapeAttr(text)
                el = RawElement.fromStream(s, start, endI, startTag, "")
                return Ok(el, endI)
            else:
                # <title> was never closed. Go ahead and close it empty.
                # parseTitleToEnd() already emitted an error message.
                els = [startTag, EndTag.fromStream(s, i, i, startTag)]
                return Ok(els, i)
        elif (
            html.isMetadataBlock(startTag)
            and not s.inOpaqueElement()
            and start == s.currentLineStart(start)
            and s.col(start) == 1
        ):
            el, endI, _ = html.parseMetadataBlockToEnd(s, start, startTag, i)
            if el is not None:
                if s.metadataSpans is not None:
                    m.die(
                        "Found a metadata block too far down in the document; please move all metadata blocks near the top of the document.",
                        lineNum=s.loc(start),
                    )
                # Just remove it from the doc.
                rawText = RawText.fromStream(s, start, endI, "")
                return Ok(rawText, endI)
        elif startTag.tag == "pre":
            if blockType := html.isDatablock(startTag, s.loc(i)):
                text, i, _ = html.parseDatablockPreToEnd(s, i)
                if text is None:
                    return Err(start)
                if "bs-macros" in startTag.attrs:
                    text = macros.replaceMacrosInText(text, s.config.macros, s, start, context="<pre> contents")
                startTag.attrs["bs-datablock-type"] = escapeAttr(blockType)
                el = SafeElement.fromStream(s, start, i, startTag, text)
                return Ok(el, i)
            else:
                return Ok(startTag, i)
        elif startTag.tag in ("script", "style"):
            text, i, _ = html.parseRawElementToEnd(s, i, startTag.tag)
            if "bs-macros" in startTag.attrs:
                text = macros.replaceMacrosInText(
                    text,
                    s.config.macros,
                    s,
                    start,
                    context=f"<{startTag.tag}> contents",
                )
            if blockType := html.isDatablock(startTag, s.loc(i)):
                startTag.attrs["bs-datablock-type"] = escapeAttr(blockType)
            el = RawElement.fromStream(s, start, i, startTag, text)
            return Ok(el, i)
        elif startTag.tag == "xmp":
            # Rewrite deprecated `<xmp>` to `<pre bs-was-xmp>` with HTML-escaped body.
            startTag.tag = "pre"
            startTag.attrs["bs-was-xmp"] = ""
            bodyStart = i
            text, i, _ = html.parseRawElementToEnd(s, i, "xmp")
            hasMacros = "bs-macros" in startTag.attrs
            if hasMacros:
                text = macros.replaceMacrosInText(text, s.config.macros, s, start, context="<xmp> contents")
            if blockType := html.isDatablock(startTag, s.loc(i)):
                startTag.attrs["bs-datablock-type"] = escapeAttr(blockType)
            elif s.config.css and "prod" in startTag.classes:
                bodyNodes = css.parseCSSProductionGrammarInText(s, bodyStart, text, exactOffsets=not hasMacros)
                return Ok([startTag, *bodyNodes, EndTag.fromStream(s, i, i, startTag)], i)
            el = SafeElement.fromStream(s, start, i, startTag, text)
            return Ok(el, i)
        else:
            return Ok(startTag, i)

    # `<org/repo#123>` is handled inside parseStartTag(); this catches tagless `<#123>` links.
    if s.config.repositoryLinks:
        repolink, i, _ = autolinks.parseRepositoryLink(s, start)
        if repolink is not None:
            return Ok(repolink, i)

    return Err(start)


def parseLToEnd(s: Stream, start: int, lTag: StartTag) -> ResultT[ParserNode | list[ParserNode]]:
    """
    Parses the contents of an <l>, which should be a bikeshed inline shorthand of some kind.
    This is done without checking for opaqueness (as it's an explicit request)
    and without even checking which autolink syntaxes are turned on
    (again, it's an explicit request, so there's no possibility of accidents).

    Call with s[i] after the opening <l> tag.
    Returns with s[i] after the </l> tag,
    with the shorthand element in the Result.
    """
    if s.eof(start):
        return Err(start)

    first1 = s[start]
    first2 = s.slice(start, start + 2)

    # First, parse an autolink
    nodes: ParserNode | list[ParserNode] | None
    if first2 == "''":
        nodes, i, _ = css.parseCSSMaybe(s, start, generateResults, generateExperimentalNodes)
    elif first1 == "'":
        nodes, i, _ = css.parseCSSPropdesc(s, start)
    elif first2 == "<<":
        nodes, i, _ = css.parseCSSProduction(s, start)
    elif first2 == "[=":
        nodes, i, _ = autolinks.parseAutolinkDfn(s, start, generateResults)
    elif first2 == "[$":
        nodes, i, _ = autolinks.parseAutolinkAbstract(s, start, generateResults)
    elif first2 == "[:":
        nodes, i, _ = autolinks.parseAutolinkHeader(s, start, generateResults)
    elif first2 == "{{":
        nodes, i, _ = autolinks.parseAutolinkIdl(s, start, generateResults)
    elif first2 == "{^":
        nodes, i, _ = autolinks.parseAutolinkCddl(s, start, generateResults)
    elif first2 == "<{":
        nodes, i, _ = autolinks.parseAutolinkElement(s, start, generateResults)
    elif first2 == "[[":
        nodes, i, _ = autolinks.parseAutolinkBiblioSection(s, start, generateResults)
    else:
        # No recognized syntax
        nodes, i = None, start
    if nodes is None:
        m.die("<l> element didn't contain a recognized autolink syntax", lineNum=s.loc(start))
        return Err(start)
    assert isinstance(nodes, list)

    # Then, parse a </l>
    endTag, i, _ = html.parseEndTag(s, i)
    if endTag is None:
        m.die("<l> element had unrecognized syntax after the autolink", lineNum=s.loc(i))
        return Err(start)
    elif endTag.tag != "l":
        m.die("<l> element wasn't closed by a </l>", lineNum=s.loc(i))
        return Err(start)

    # Find the <a> start tag in the results
    for node in nodes:
        if isinstance(node, StartTag) and node.tag in ("a", "bs-link"):
            realStart = node
            break
    else:
        m.die(
            "Programming error - successfully parsed an autolink, but couldn't find the <a> in the parsed results. Please report this!",
            lineNum=s.loc(start),
        )
        return Err(start)

    # Transfer any <l> attributes to the autolink start tag
    for k, v in lTag.attrs.items():
        realStart.attrs[k] = v

    # Now just return the autolink, but with cursor set past the </l>
    return Ok(nodes, i)


def parseBsMacro(s: Stream, startTag: StartTag, bodyStart: int) -> ResultT[list[ParserNode]]:
    """Consume a `<bs-macro>` body through `</bs-macro>` and expand the macro or its fallback into nodes."""
    fallbackText, endI, _ = html.parseBsMacroToEnd(s, bodyStart, startTag)
    if fallbackText is None:
        return Ok([], s.length)
    resolved = macros.resolveBsMacro(s, startTag, fallbackText, bodyStart)
    if resolved.stream is None:
        return Ok([], endI)
    if s.config.markdownBlock and s.blockParser is not None:
        return Ok(s.blockParser(resolved.stream), endI)
    return Ok(list(nodesFromStream(resolved.stream, 0)), endI)
