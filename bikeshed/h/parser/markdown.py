"""Inline Markdown constructs (emphasis, code spans, links, escapes) and fenced code blocks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ... import messages as m
from ... import t
from .. import elements
from .html import CharRefContext, isDatablockClass, parseCharRef, printChAsCharRef
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
    TagNodeT,
    escapeAttr,
    isInlineTag,
)
from .preds import isControl, isWhitespace
from .result import Err, Ok
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import ResultT
    from .stream import ExperimentalNodesFn

codeSpanStartRe = re.compile(r"`+")
# A few common lengths to pre-compile for speed.
codeSpanEnd1Re = re.compile(r"(.*?[^`])(`)([^`]|$)")
codeSpanEnd2Re = re.compile(r"(.*?[^`])(``)([^`]|$)")

fencedStartRe = re.compile(r"`{3,}|~{3,}")

_MARKDOWN_ESCAPE_CHARS = frozenset(r"""\!"#$%&'()*+,-./:;<=>?@[]^_`{|}~""")
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
_INLINE_EMPH_EXTRA_TAGS = frozenset({"ins", "del"})


def parseEmphasisRun(s: Stream, start: int) -> ResultT[RawText]:
    """Parse a contiguous run of `*` characters at `start`, returning an `EmphDelim` if CommonMark-flanking or plain `RawText`."""
    if s[start] != "*":
        return Err(start)
    chars = s.chars
    length = s.length
    end = start + 1
    while end < length and chars[end] == "*":
        end += 1

    beforeChar = s[start - 1]
    afterChar = s[end]
    beforeIsWs = beforeChar == "" or beforeChar.isspace()
    afterIsWs = afterChar == "" or afterChar.isspace()
    beforeIsPunct = not beforeIsWs and unicodedata.category(beforeChar)[0] in ("P", "S")
    afterIsPunct = not afterIsWs and unicodedata.category(afterChar)[0] in ("P", "S")

    # CommonMark 6.2 flanking rules for `*` (intraword emphasis is permitted for `*`).
    canOpen = not afterIsWs and (not afterIsPunct or beforeIsWs or beforeIsPunct)
    canClose = not beforeIsWs and (not beforeIsPunct or afterIsWs or afterIsPunct)
    if not canOpen and not canClose:
        return Ok(RawText.fromStream(s, start, end), end)
    return Ok(EmphDelim.fromDelim(s, start, end, canOpen=canOpen, canClose=canClose), end)


@dataclass(slots=True)
class _DelimEntry:
    """One `*` delimiter run in the CommonMark doubly-linked delimiter stack."""

    pos: int
    nodeIdx: int
    delim: EmphDelim
    count: int
    origCount: int
    canOpen: bool
    canClose: bool
    leftPos: int
    rightPos: int
    prev: _DelimEntry | None = None
    next: _DelimEntry | None = None


@dataclass(slots=True)
class _EmphFrame:
    """One open HTML element scope accumulating candidate `*` delimiters."""

    tag: str | None
    delims: list[_DelimEntry] = field(default_factory=list)


def _isInlineEmphTag(node: TagNodeT, blockElements: t.Collection[str]) -> bool:
    """Return True if `node` is an inline HTML tag that emphasis may span across."""
    return isInlineTag(node, blockElements, _INLINE_EMPH_EXTRA_TAGS)


def _resolveDelimFrame(
    delims: list[_DelimEntry],
    openTagsAfter: dict[int, list[StartTag]],
    closeTagsBefore: dict[int, list[EndTag]],
    remaining: dict[int, tuple[int, int]],
) -> None:
    """Run the CommonMark emphasis-matching algorithm on `delims`, recording tag insertions by `nodeIdx`."""
    if not delims:
        return

    for k, entry in enumerate(delims):
        entry.pos = k
        entry.prev = delims[k - 1] if k > 0 else None
        entry.next = delims[k + 1] if k + 1 < len(delims) else None

    def unlink(entry: _DelimEntry) -> None:
        """Remove `entry` from the active doubly-linked delimiter stack in O(1)."""
        if entry.prev is not None:
            entry.prev.next = entry.next
        if entry.next is not None:
            entry.next.prev = entry.prev
        entry.prev = None
        entry.next = None

    # Track the lowest unmatched search boundary per `(closer.origCount % 3, closer.canOpen)` for O(N) time.
    openersBottom: dict[tuple[int, bool], int] = {}
    closer: _DelimEntry | None = delims[0]
    while closer is not None:
        if not closer.canClose or closer.count == 0:
            closer = closer.next
            continue

        bottomKey = (closer.origCount % 3, closer.canOpen)
        bottom = openersBottom.get(bottomKey, -1)
        opener = closer.prev
        foundOpener: _DelimEntry | None = None
        while opener is not None and opener.pos > bottom:
            if opener.canOpen and opener.count > 0:
                oddMatch = (
                    (opener.canClose or closer.canOpen)
                    and closer.origCount % 3 != 0
                    and (opener.origCount + closer.origCount) % 3 == 0
                )
                if not oddMatch:
                    foundOpener = opener
                    break
            opener = opener.prev

        if foundOpener is None:
            openersBottom[bottomKey] = closer.pos - 1
            nextCloser = closer.next
            if not closer.canOpen:
                unlink(closer)
            closer = nextCloser
            continue

        useDelims = 2 if (foundOpener.count >= 2 and closer.count >= 2) else 1
        tagName = "strong" if useDelims == 2 else "em"

        openEnd = foundOpener.rightPos
        openStart = openEnd - useDelims
        foundOpener.rightPos = openStart
        foundOpener.count -= useDelims

        closeStart = closer.leftPos
        closeEnd = closeStart + useDelims
        closer.leftPos = closeEnd
        closer.count -= useDelims

        assert foundOpener.delim.s is not None and closer.delim.s is not None
        startTag = StartTag.fromStream(foundOpener.delim.s, openStart, openEnd, tagName)
        endTag = EndTag.fromStream(closer.delim.s, closeStart, closeEnd, startTag)
        openTagsAfter.setdefault(foundOpener.nodeIdx, []).append(startTag)
        closeTagsBefore.setdefault(closer.nodeIdx, []).append(endTag)

        # Drop all delimiters strictly between opener and closer in O(1).
        foundOpener.next = closer
        closer.prev = foundOpener

        if foundOpener.count == 0:
            unlink(foundOpener)
        if closer.count == 0:
            nextCloser = closer.next
            unlink(closer)
            closer = nextCloser

    for entry in delims:
        remaining[entry.nodeIdx] = (entry.leftPos, entry.rightPos)


def _autoCloseFrameTop(
    frames: list[_EmphFrame],
    closeTags: tuple[str, ...],
    flushFrame: t.Callable[[_EmphFrame], None],
    stopTags: tuple[str, ...] | None = None,
) -> None:
    """Flush and pop the top frame if its tag matches `closeTags` (without crossing `stopTags`)."""
    if len(frames) <= 1:
        return
    topTag = frames[-1].tag
    if stopTags and topTag in stopTags:
        return
    if topTag in closeTags:
        flushFrame(frames.pop())


def _autoCloseEmphFramesForStart(
    tag: str,
    frames: list[_EmphFrame],
    flushFrame: t.Callable[[_EmphFrame], None],
) -> None:
    """Apply HTML optional-end-tag auto-closing rules for opening `tag` on the emphasis frame stack."""
    if len(frames) <= 1:
        return
    if tag in elements.AUTO_CLOSE_P_START_ELEMENTS:
        _autoCloseFrameTop(frames, ("p",), flushFrame)
    if pScopes := elements.AUTO_CLOSE_P_SCOPED_START_ELEMENTS.get(tag):
        _autoCloseFrameTop(frames, ("p",), flushFrame, pScopes)
    if rules := elements.AUTO_CLOSE_START_RULES.get(tag):
        for closeTags, stopTags in rules:
            _autoCloseFrameTop(frames, closeTags, flushFrame, stopTags)


def _autoCloseEmphFramesForEnd(
    tag: str,
    frames: list[_EmphFrame],
    flushFrame: t.Callable[[_EmphFrame], None],
) -> None:
    """Apply HTML optional-end-tag auto-closing rules for closing `tag` on the emphasis frame stack."""
    if len(frames) <= 1:
        return
    if tag in elements.AUTO_CLOSE_P_END_ELEMENTS:
        _autoCloseFrameTop(frames, ("p",), flushFrame)
    if rules := elements.AUTO_CLOSE_END_RULES.get(tag):
        for closeTags, stopTags in rules:
            _autoCloseFrameTop(frames, closeTags, flushFrame, stopTags)


def resolveEmphasis(nodes: list[ParserNode], blockElements: t.Collection[str] = ()) -> list[ParserNode]:
    """Resolve `EmphDelim` nodes in `nodes` into balanced `<em>`/`<strong>` tags using CommonMark rules scoped per HTML element."""
    if not any(isinstance(node, EmphDelim) for node in nodes):
        return nodes

    openTagsAfter: dict[int, list[StartTag]] = {}
    closeTagsBefore: dict[int, list[EndTag]] = {}
    remaining: dict[int, tuple[int, int]] = {}

    def flushFrame(frame: _EmphFrame) -> None:
        """Resolve all accumulated delimiters in `frame` and clear its delimiter list."""
        if frame.delims:
            _resolveDelimFrame(frame.delims, openTagsAfter, closeTagsBefore, remaining)
            frame.delims.clear()

    frames: list[_EmphFrame] = [_EmphFrame(tag=None)]
    trailingNewline = False

    for idx, node in enumerate(nodes):
        if isinstance(node, EmphDelim):
            count = len(node.text)
            frames[-1].delims.append(
                _DelimEntry(
                    pos=0,
                    nodeIdx=idx,
                    delim=node,
                    count=count,
                    origCount=count,
                    canOpen=node.canOpen,
                    canClose=node.canClose,
                    leftPos=node.start,
                    rightPos=node.end,
                ),
            )
            trailingNewline = False
        elif isinstance(node, (RawText, SafeText)):
            text = node.text
            if "\n" in text:
                if _BLANK_LINE_RE.search(text) or (trailingNewline and text.split("\n", 1)[0].strip(" \t") == ""):
                    flushFrame(frames[-1])
                trailingNewline = text.rsplit("\n", 1)[1].strip(" \t") == ""
            elif text.strip(" \t") != "":
                trailingNewline = False
        elif isinstance(node, StartTag):
            _autoCloseEmphFramesForStart(node.tag, frames, flushFrame)
            if not _isInlineEmphTag(node, blockElements):
                flushFrame(frames[-1])
            frames.append(_EmphFrame(tag=node.tag))
            trailingNewline = False
        elif isinstance(node, EndTag):
            _autoCloseEmphFramesForEnd(node.tag, frames, flushFrame)
            for matchIdx in range(len(frames) - 1, 0, -1):
                if frames[matchIdx].tag == node.tag:
                    while len(frames) > matchIdx:
                        flushFrame(frames.pop())
                    break
            if not _isInlineEmphTag(node, blockElements):
                flushFrame(frames[-1])
            trailingNewline = False
        elif isinstance(node, (SelfClosedTag, RawElement, SafeElement)):
            _autoCloseEmphFramesForStart(node.tag, frames, flushFrame)
            if not _isInlineEmphTag(node, blockElements):
                flushFrame(frames[-1])
            trailingNewline = False

    while frames:
        flushFrame(frames.pop())

    out: list[ParserNode] = []
    justClosedEmph: EndTag | None = None
    for idx, node in enumerate(nodes):
        if isinstance(node, EmphDelim):
            closes = closeTagsBefore.get(idx)
            if closes:
                out.extend(closes)
            leftPos, rightPos = remaining[idx]
            opens = openTagsAfter.get(idx)
            if rightPos > leftPos:
                assert node.s is not None
                out.append(RawText.fromStream(node.s, leftPos, rightPos))
                justClosedEmph = None
            elif closes and not opens:
                justClosedEmph = closes[-1]
            else:
                justClosedEmph = None
            if opens:
                out.extend(reversed(opens))
                justClosedEmph = None
        else:
            if justClosedEmph is not None and isinstance(node, RawText) and node.text.startswith("'"):
                node.curlifyApostrophes(justClosedEmph)
            justClosedEmph = None
            out.append(node)
    return out


def parseCodeSpan(s: Stream, start: int) -> ResultT[list[ParserNode]]:
    """Parse an inline Markdown backtick code span (`` `code` ``) into an opaque `<code>` element."""
    if s[start - 1] == "`" and s.slice(start - 2, start) != "\\`":
        return Err(start)
    if s[start] != "`":
        return Err(start)
    match, i, _ = s.matchRe(start, codeSpanStartRe)
    assert match is not None
    ticks = match[0]
    contentStart = i

    if len(ticks) == 1:
        endRe = codeSpanEnd1Re
    elif len(ticks) == 2:
        endRe = codeSpanEnd2Re
    else:
        endRe = re.compile(r"([^`])(" + ticks + ")([^`]|$)")
    match, _, _ = s.searchRe(i, endRe)
    if match is None:
        # Allowed to be unmatched, they're just ticks then.
        return Err(start)
    contentEnd = match.end(1)
    i = match.end(2)

    text = s.slice(contentStart, contentEnd).replace("\n", " ")
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
        {"bs-autolink-syntax": escapeAttr(f"{ticks}{text}{ticks}"), "bs-opaque": ""},
    )
    content = SafeText.fromStream(s, contentStart, contentEnd, text)
    endTag = EndTag.fromStream(s, contentEnd, i, startTag)
    return Ok([startTag, content, endTag], i)


def parseFencedCodeBlock(s: Stream, start: int, *, atLineStart: bool = False) -> ResultT[SafeElement]:
    """Parse a Markdown fenced code block (```` ``` ```` or `~~~`) into a `<pre>` `SafeElement`."""
    if not atLineStart and s.precedingTextOnLine(start).strip() != "":
        return Err(start)

    match, i, _ = s.matchRe(start, fencedStartRe)
    if match is None:
        return Err(start)
    openingFence = match.group(0)

    infoString, i, _ = s.skipToNextLine(i)
    assert infoString is not None
    infoString = infoString.strip()
    if "`" in infoString:
        # This isn't allowed, because it collides with inline code spans.
        return Err(start)

    contents = ""
    while True:
        # Ending fence has to use same character and be
        # at least as long, so just search for the opening
        # fence itself, as a start.

        text, i, _ = s.skipTo(i, openingFence)

        # No ending fence in the rest of the document
        if text is None:
            m.die("Hit EOF while parsing fenced code block.", lineNum=s.loc(start))
            contents += s.slice(i, None)
            i = len(s)
            break

        # Found a possible ending fence, put preceding text
        # into the contents string.
        contents += text

        # Ending fence needs only whitespace preceding it (tolerating minor indent differences per CommonMark).
        if s.precedingTextOnLine(i).strip() == "":
            # Consume the whole fence, since it can be longer.
            _, i, _ = s.matchRe(i, fencedStartRe)
            break

        # Otherwise I just hit a line that happens to have
        # a fence lookalike- on it, but not closing this one.
        # Skip the fence and continue.

        match, i, _ = s.matchRe(i, fencedStartRe)
        assert match is not None
        contents += match.group(0)

    # At this point i is past the end of the code block.
    tag = StartTag.fromStream(s, start, start, "pre")
    if infoString:
        tag.attrs["bs-infostring"] = escapeAttr(infoString)
        lang = infoString.split(" ")[0]
        if isDatablockClass(lang) or lang == "prod":
            tag.classes.add(lang)
        else:
            tag.classes.add(f"language-{lang}")
    el = SafeElement.fromStream(s, start, i, tag, contents)
    return Ok(el, i)


def parseMarkdownLink(
    s: Stream,
    start: int,
    generateExperimentalNodes: ExperimentalNodesFn,
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse an inline Markdown `[text](dest "title")` link into an `<a>` element."""
    linkTextStart = start + 1
    startingSigil = "["
    endingSigil = "](...)"

    startTag = StartTag.fromStream(s, start, linkTextStart, "a")

    # At this point, we're still not committed to this being
    # an autolink, so it should silently fail.
    nodes: list[ParserNode] = []
    for i in generateExperimentalNodes(s, linkTextStart, nodes):
        if s.chars.count("\n", start, i) > 3:
            return Err(start)
        if s.slice(i, i + 2) == "](":
            linkTextEnd = i
            linkDestStart = i + 2
            break
        if s[i] == "]":
            return Err(start)
    else:
        return Err(start)
    # Now that we've seen the ](, we're committed.
    s.observeShorthandOpen(startTag, (startingSigil, endingSigil))
    s.observeNodes(nodes)
    virtualEndTags = s.observeShorthandClose(linkTextEnd, startTag, (startingSigil, endingSigil))

    # I'm not doing bracket-checking in the link text,
    # as CommonMark requires, because I've already lost
    # the information about whether they were escaped.
    result, nodeEnd, _ = parseMarkdownLinkDestTitle(s, linkDestStart)
    if result is None:
        # Return the already-parsed stuff, with the syntax
        # chars turned back into text.
        openingSquare = RawText.fromStream(s, start, start + 1)
        middleBit = RawText.fromStream(s, linkTextEnd, linkDestStart)
        return Ok([openingSquare, *nodes, middleBit], linkDestStart)
    dest, title = result
    startTag.attrs["href"] = escapeAttr(dest)
    startTag.attrs["bs-autolink-syntax"] = escapeAttr(s.slice(start, nodeEnd))
    if title:
        startTag.attrs["title"] = escapeAttr(title)
    endTag = EndTag.fromStream(s, nodeEnd - 1, nodeEnd, startTag)
    return Ok([startTag, *nodes, *virtualEndTags, endTag], nodeEnd)


def parseMarkdownLinkDestTitle(s: Stream, start: int) -> ResultT[tuple[str, str]]:
    """Parse the `(dest "title")` tail of a Markdown link starting after `(`, returning `(dest, title)`."""
    res, i, _ = parseMarkdownLinkWhitespace(s, start)
    if res is None:
        return Err(start)

    TITLE_START_CHARS = ('"', "'", "(")

    dest: str | None = ""
    title: str | None = ""
    if s[i] == ")":
        # Perfectly fine to be empty.
        return Ok(("", ""), i + 1)

    # Parse an optional destination
    if s[i] == "<":
        dest, i, _ = parseMarkdownLinkAngleDest(s, i + 1)
        sawDest = True
    elif s[i] in TITLE_START_CHARS:
        # This indicates a title, so a skipped dest,
        # which is totally fine.
        sawDest = False
    else:
        dest, i, _ = parseMarkdownLinkIdentDest(s, i)
        sawDest = True
    if dest is None:
        return Err(start)

    ws, i, _ = parseMarkdownLinkWhitespace(s, i)
    if ws is None:
        return Err(start)
    if s[i] == ")":
        return Ok((dest, ""), i + 1)

    if s[i] in TITLE_START_CHARS:
        if ws == "" and sawDest:
            # If you do have a dest, you *must* have whitespace
            # between it and the title.
            m.die("Missing required whitespace between markdown link's destination and title", lineNum=s.loc(i))
            return Err(start)

        title, i, _ = parseMarkdownLinkTitle(s, i + 1, s[i])
        if title is None:
            return Err(start)
    assert title is not None

    ws, i, _ = parseMarkdownLinkWhitespace(s, i)
    if ws is None:
        return Err(start)

    if s[i] == ")":
        return Ok((dest, title), i + 1)
    else:
        m.die(
            "Tried to parse a markdown link's destination/title, but ran into some unexpected characters",
            lineNum=s.loc(i),
        )
        return Err(start)


def parseMarkdownLinkWhitespace(s: Stream, start: int) -> ResultT[str]:
    """Consume whitespace inside a Markdown link's destination/title, disallowing blank lines and EOF."""
    seenLinebreak = False
    i = start
    while isWhitespace(s[i]):
        if s[i] == "\n":
            if seenLinebreak:
                m.die("The destination/title of a markdown link can't contain a blank line.", lineNum=s.loc(start))
                return Err(start)
            else:
                seenLinebreak = True
        i += 1
    if s.eof(i):
        m.die("Hit EOF while parsing the destination/title of a markdown link", lineNum=s.loc(start))
        return Err(start)
    return Ok(s.slice(start, i), i)


def parseMarkdownLinkAngleDest(s: Stream, start: int) -> ResultT[str]:
    """Parse an angle-bracketed `<url>` Markdown link destination starting after `<`."""
    i = start
    val = ""
    startSeg = i
    ch: str | SafeText | None
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the destination of a markdown link", lineNum=s.loc(start - 1))
            return Err(start)
        elif s.config.markdownEscapes and s[i] == "\\":
            startEscape = i
            ch, i, _ = parseMarkdownEscape(s, i)
            if ch is None:
                i += 1
                continue
            val += s.slice(startSeg, startEscape) + ch
            startSeg = i
            continue
        elif s[i] == "&":
            startRef = i
            ch, i, _ = parseCharRef(s, i, context=CharRefContext.Attr)
            if ch is None:
                i += 1
                continue
            if isinstance(ch, SafeText):
                ch = ch.text
            val += s.slice(startSeg, startRef) + ch
            startSeg = i
            continue
        elif s[i] == ">":
            break
        elif s[i] == "<":
            m.die(
                "The <>-wrapped destination of a markdown link can't contain further unescaped < characters",
                lineNum=s.loc(i),
            )
            return Err(start)
        elif s[i] == "\n":
            m.die("The <>-wrapped destination of a markdown link can't contain a newline", lineNum=s.loc(start))
            return Err(start)
        else:
            i += 1
    val += s.slice(startSeg, i)
    i += 1
    return Ok(val, i)


def parseMarkdownLinkIdentDest(s: Stream, start: int) -> ResultT[str]:
    """Parse a bare (non-angle-bracketed) Markdown link destination, allowing balanced parentheses."""
    i = start
    parenDepth = 0
    val = ""
    startSeg = i
    ch: str | SafeText | None
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the destination of a markdown link", lineNum=s.loc(start))
            return Err(start)
        elif s.config.markdownEscapes and s[i] == "\\":
            startEscape = i
            ch, i, _ = parseMarkdownEscape(s, i)
            if ch is None:
                i += 1
                continue
            val += s.slice(startSeg, startEscape) + ch
            startSeg = i
            continue
        elif s[i] == "&":
            startRef = i
            ch, i, _ = parseCharRef(s, i, context=CharRefContext.Attr)
            if ch is None:
                i += 1
                continue
            if isinstance(ch, SafeText):
                ch = ch.text
            val += s.slice(startSeg, startRef) + ch
            startSeg = i
            continue
        elif isControl(s[i]):
            m.die(
                f"The destination of a markdown link can't contain ASCII control characters ({hex(ord(s[i]))})",
                lineNum=s.loc(i),
            )
            return Err(start)
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
    val += s.slice(startSeg, i)
    # no ending character so no bumping the i
    return Ok(val, i)


def parseMarkdownLinkTitle(s: Stream, start: int, startChar: str) -> ResultT[str]:
    """Parse a `'...'`, `"..."`, or `(...)` Markdown link title starting after its opening delimiter."""
    i = start
    if startChar == "'":
        endChar = "'"
    elif startChar == '"':
        endChar = '"'
    elif startChar == "(":
        endChar = ")"
    else:
        assert False, "unreachable"
    val = ""
    startSeg = i
    ch: str | SafeText | None
    while True:
        if s.eof(i):
            m.die("Hit EOF while parsing the title of a markdown link", lineNum=s.loc(start))
            return Err(start)
        elif s.config.markdownEscapes and s[i] == "\\":
            startEscape = i
            ch, i, _ = parseMarkdownEscape(s, i)
            if ch is None:
                i += 1
                continue
            val += s.slice(startSeg, startEscape) + printChAsCharRef(ch)
            startSeg = i
            continue
        elif s[i] == "&":
            startRef = i
            ch, i, _ = parseCharRef(s, i, context=CharRefContext.Attr)
            if ch is None:
                i += 1
                continue
            val += s.slice(startSeg, startRef) + printChAsCharRef(ch)
            startSeg = i
            continue
        elif s[i] == endChar:
            break
        elif s[i] == startChar:
            m.die(
                f"The title of a markdown link can't contain the starting char ({startChar}) unless it's escaped",
                lineNum=s.loc(i),
            )
            return Err(start)
        elif isWhitespace(s[i]):
            ws, i, _ = parseMarkdownLinkWhitespace(s, i)
            if ws is None:
                return Err(start)
        else:
            i += 1
    val += s.slice(startSeg, i)
    i += 1
    return Ok(val, i)


def parseMarkdownEscape(s: Stream, start: int) -> ResultT[str]:
    """Parse a Markdown backslash escape at `start`, returning the unescaped character."""
    if isMarkdownEscape(s, start):
        return Ok(s[start + 1], start + 2)
    return Err(start)


def isMarkdownEscape(s: Stream, start: int) -> bool:
    """Return True if `s[start:start+2]` is a handled Markdown backslash escape."""
    return s[start] == "\\" and s[start + 1] in _MARKDOWN_ESCAPE_CHARS
