"""Markdown and mixed HTML/Markdown list parsing (`<ul>`, `<ol>`, `<dl>`) and indentation stop frames."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ... import messages as m
from ... import t
from . import html
from .indents import (
    IndentChecker,
    consumeIndentAt,
    findLineEnd,
    lineLoc,
    nextLinePos,
    prefixCountAt,
    skipHws,
)
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    RawText,
    StartTag,
    makeStartTag,
)
from .parser import parseInlineNodes
from .stream import Stream

if t.TYPE_CHECKING:

    class BlockRecurseFn(t.Protocol):
        """Callback invoking `blocks.parseBlocks()` for nested list-item bodies."""

        def __call__(
            self,
            s: Stream,
            start: int,
            *,
            minIndent: int = 0,
            minTagDepth: int = 0,
            firstLineTrimmed: bool = False,
            stopAt: ListStop | None = None,
            stopAtTagDepth: int | None = None,
            initialCanStartParagraph: bool = True,
        ) -> tuple[list[ParserNode], int]:
            """Parse nested block content inside a list item."""


RULE_RE = re.compile(r"(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_NUMBERED_START_RE = re.compile(r"(-?\d+)\.(?:[ \t]+|$)")
_BULLETED_START_RE = re.compile(r"[*+-](?:[ \t]+|$)")
_DL_START_RE = re.compile(r"(:{1,2})(?:[ \t]+|$)")

# HTML elements whose end tag is optional when their enclosing parent closes.
_AUTO_CLOSABLE_CHILD: dict[str, tuple[str, ...]] = {
    "li": ("ul", "ol"),
    "dt": ("dl",),
    "dd": ("dl",),
    "td": ("tr", "table"),
    "th": ("tr", "table"),
    "tr": ("thead", "tbody", "tfoot", "table"),
    "thead": ("table",),
    "tbody": ("table",),
    "tfoot": ("table",),
    "colgroup": ("table",),
    "caption": ("table",),
    "option": ("optgroup", "select"),
    "optgroup": ("select",),
    "rt": ("rtc", "ruby"),
    "rp": ("ruby",),
    "rb": ("ruby",),
    "rtc": ("ruby",),
}


@dataclass(slots=True)
class ListStop:
    """Linked frame describing an enclosing Markdown list so nested blocks know when to exit."""

    baseIndent: int
    itemTypes: tuple[str, ...]
    htmlItemTags: tuple[str, ...] = ()
    htmlExitTags: tuple[tuple[bool, str], ...] = ()
    htmlCloseTag: str | None = None
    hasHtmlContainer: bool = False
    tagDepth: int = 0
    parent: ListStop | None = None


def matchListItemStart(chars: str, cStart: int, lineEnd: int) -> tuple[str | None, re.Match[str] | None]:
    """Classify a Markdown list-item marker (`numbered`, `bulleted`, `dt`, `dd`) at `cStart`."""
    ch = chars[cStart]
    if ch in ("*", "-") and RULE_RE.match(chars, cStart, lineEnd):
        return None, None
    if (ch == "-" or ch.isdigit()) and (match := _NUMBERED_START_RE.match(chars, cStart, lineEnd)):
        return "numbered", match
    if ch in ("*", "+", "-") and (match := _BULLETED_START_RE.match(chars, cStart, lineEnd)):
        return "bulleted", match
    if ch == ":" and (match := _DL_START_RE.match(chars, cStart, lineEnd)):
        return ("dt" if len(match.group(1)) == 1 else "dd"), match
    return None, None


def matchLineItemType(s: Stream, lineStart: int, lineEnd: int) -> str | None:
    """Return the list-item marker type (`bulleted`, `numbered`, `dt`, `dd`) on `lineStart`, or `None`."""
    cStart = skipHws(s.chars, lineStart, lineEnd)
    if cStart >= lineEnd:
        return None
    kind, _ = matchListItemStart(s.chars, cStart, lineEnd)
    return kind


def shouldStopForList(s: Stream, lineStart: int, lineEnd: int, absIndent: int, stopAt: ListStop | None) -> bool:
    """Return True if a line at `absIndent` exits any active enclosing list frame in `stopAt`."""
    stop = stopAt
    htmlTag: tuple[bool, str] | None = None
    htmlChecked = False
    while stop is not None:
        if absIndent < stop.baseIndent:
            return True
        if absIndent == stop.baseIndent:
            openSlice = s.openEls.tags[stop.tagDepth :]
            inNestedList = any(e.startTag.tag in ("ul", "ol", "dl") for e in openSlice)
            if matchLineItemType(s, lineStart, lineEnd) in stop.itemTypes:
                if stop.htmlCloseTag is None or not inNestedList:
                    return True
            if stop.htmlItemTags or stop.htmlExitTags:
                if not htmlChecked:
                    htmlChecked = True
                    cStart = skipHws(s.chars, lineStart, lineEnd)
                    peek = html.peekHtmlTagAt(s, cStart, lineEnd)
                    htmlTag = (peek[0], peek[1]) if peek is not None else None
                if htmlTag is not None:
                    isClose, tagName = htmlTag
                    if not isClose and tagName in stop.htmlItemTags and not inNestedList:
                        return True
                    if htmlTag in stop.htmlExitTags:
                        if isClose:
                            if not any(e.startTag.tag == tagName for e in openSlice):
                                return True
                        elif not openSlice:
                            return True
        stop = stop.parent
    return False


def blankEndsList(s: Stream, blankLineEnd: int, stopAt: ListStop) -> tuple[bool, int]:
    """Return `(endsList, nextContentPos)` for the blank/comment run starting after `blankLineEnd`."""
    chars = s.chars
    length = s.length
    j = nextLinePos(blankLineEnd, length)
    while j < length:
        if (nextAfterComment := html.trySkipCommentOrDoctypeLine(s, j, peekOnly=True)) is not None:
            j = nextAfterComment
            continue
        jEnd = findLineEnd(s, j)
        jCStart = skipHws(chars, j, jEnd)
        if jCStart == jEnd:
            j = nextLinePos(jEnd, length)
            continue
        nextAbsIndent = prefixCountAt(s, j, s.config.indent)
        if nextAbsIndent < stopAt.baseIndent:
            return True, j
        if nextAbsIndent > stopAt.baseIndent:
            return False, j
        if matchLineItemType(s, j, jEnd) in stopAt.itemTypes:
            return False, j
        if (peek := html.peekHtmlTagAt(s, jCStart, jEnd)) is not None:
            isClose, tagName, _ = peek
            if stopAt.htmlCloseTag is not None and isClose and tagName == stopAt.htmlCloseTag:
                return False, j
            if isClose and any(e.startTag.tag == tagName for e in s.openEls.tags[stopAt.tagDepth :]):
                return False, j
            if not stopAt.hasHtmlContainer and not isClose and tagName in stopAt.htmlItemTags:
                return False, j
        return True, j
    return True, length


def lastNonWsNode(nodes: list[ParserNode]) -> ParserNode | None:
    """Return the last node in `nodes` that is not pure whitespace text, Comment, or Doctype."""
    for node in reversed(nodes):
        if isinstance(node, (Comment, Doctype)):
            continue
        if isinstance(node, RawText) and not node.text.strip():
            continue
        return node
    return None


def effectivePrevNodes(
    nodes: list[ParserNode],
    inheritedPrevNodes: list[ParserNode] | None,
) -> list[ParserNode]:
    """Return `nodes` if it contains any significant node, otherwise `inheritedPrevNodes` (or `[]`)."""
    return nodes if lastNonWsNode(nodes) is not None else (inheritedPrevNodes or [])


def matchHtmlListParent(
    s: Stream,
    minTagDepth: int,
    listTag: str,
    baseIndent: int,
    prevNodes: list[ParserNode],
) -> tuple[bool, tuple[tuple[bool, str], ...], list[EndTag]]:
    """Check if `s.openEls` has an open HTML list container matching `listTag` at `>= minTagDepth`.

    Returns `(matched, htmlExitTags, autoCloseEndTags)`. For a direct container match, verifies
    that the immediately preceding non-whitespace node in `prevNodes` is the container's start tag
    or a valid sibling item end tag (so an unclosed list left open far earlier in the document
    with intervening `<p>`/`<h4>` content does not swallow an unrelated Markdown list). If an
    unclosed HTML list item (`<li>`, `<dt>`, `<dd>`, optionally containing an unclosed `<p>`) is
    open at or past `baseIndent` directly inside a matching HTML list container, pops it from
    `s.openEls` and returns the corresponding `EndTag`s so the Markdown item merges as a sibling
    rather than nesting inside it.
    """
    tags = s.openEls.tags
    n = len(tags)
    if n <= minTagDepth:
        return False, (), []

    topEntry = tags[-1]
    topTag = topEntry.startTag.tag

    # Case 1: Direct enclosing explicit HTML list container (<ul>, <ol>, <dl>, or <dl> > <div>).
    if topTag == listTag:
        prev = lastNonWsNode(prevNodes)
        if listTag == "dl":
            validPrev = (isinstance(prev, StartTag) and prev.tag == "dl") or (
                isinstance(prev, EndTag) and prev.tag in ("dt", "dd", "div")
            )
            exitTags: tuple[tuple[bool, str], ...] = ((True, "dl"), (False, "div"))
        else:
            validPrev = (isinstance(prev, StartTag) and prev.tag == listTag) or (
                isinstance(prev, EndTag) and prev.tag == "li"
            )
            exitTags = ((True, listTag),)
        if validPrev:
            return True, exitTags, []
        return False, (), []
    if listTag == "dl" and n >= minTagDepth + 2 and topTag == "div" and tags[-2].startTag.tag == "dl":
        prev = lastNonWsNode(prevNodes)
        if (isinstance(prev, StartTag) and prev.tag == "div") or (
            isinstance(prev, EndTag) and prev.tag in ("dt", "dd")
        ):
            return True, ((True, "div"), (True, "dl")), []
        return False, (), []

    # Case 2: Unclosed HTML list item directly inside a matching HTML list container.
    # Only merge as a sibling when not indented deeper than the HTML item (deeper means a sublist).
    itemIdx = n - 1
    if topTag == "p" and itemIdx > minTagDepth:
        itemIdx -= 1
    itemEntry = tags[itemIdx]
    itemTag = itemEntry.startTag.tag
    validItemTags = ("dt", "dd") if listTag == "dl" else ("li",)
    if itemTag not in validItemTags or itemIdx <= minTagDepth:
        return False, (), []

    parentIdx = itemIdx - 1
    parentEntry = tags[parentIdx]
    parentTag = parentEntry.startTag.tag
    if parentTag == listTag:
        exitTags = ((True, "dl"), (False, "div")) if listTag == "dl" else ((True, listTag),)
    elif (
        listTag == "dl" and parentIdx > minTagDepth and parentTag == "div" and tags[parentIdx - 1].startTag.tag == "dl"
    ):
        exitTags = ((True, "div"), (True, "dl"))
    else:
        return False, (), []

    itemStart = itemEntry.startTag
    if itemStart.s is not s:
        return False, (), []
    itemIndent = prefixCountAt(s, s.currentLineStart(itemStart.start), s.config.indent)
    if baseIndent > itemIndent:
        return False, (), []

    endTags: list[EndTag] = []
    while len(tags) > itemIdx:
        entry = s.openEls.popEntry()
        endTags.append(EndTag(tag=entry.startTag.tag))
    return True, exitTags, endTags


def skipBlanksToNextListItem(
    s: Stream,
    start: int,
    *,
    baseIndent: int,
    itemTypes: tuple[str, ...],
    htmlItemTags: tuple[str, ...],
    indentChecker: IndentChecker | None,
) -> tuple[list[ParserNode], int] | None:
    """Skip blank/comment lines after a closed HTML item if another matching list item follows at `baseIndent`."""
    chars = s.chars
    length = s.length
    j = start
    while j < length:
        if (nextAfterComment := html.trySkipCommentOrDoctypeLine(s, j, peekOnly=True)) is not None:
            j = nextAfterComment
            continue
        jEnd = findLineEnd(s, j)
        jCStart = skipHws(chars, j, jEnd)
        if jCStart == jEnd:
            j = nextLinePos(jEnd, length)
            continue
        if prefixCountAt(s, j, s.config.indent) != baseIndent:
            return None
        if matchLineItemType(s, j, jEnd) in itemTypes:
            break
        peek = html.peekHtmlTagAt(s, jCStart, jEnd)
        if peek is not None and not peek[0] and peek[1] in htmlItemTags:
            break
        return None
    else:
        return None

    blankNodes: list[ParserNode] = []
    pos = start
    while pos < j:
        if indentChecker is not None:
            indentChecker.checkLine(s, pos)
        if (nextAfterComment := html.trySkipCommentOrDoctypeLine(s, pos)) is not None:
            pos = nextAfterComment
            continue
        posEnd = findLineEnd(s, pos)
        if pos < posEnd:
            blankNodes.append(RawText.fromStream(s, pos, posEnd))
        blankNodes.append(RawText(text="\n"))
        pos = nextLinePos(posEnd, length)
    return blankNodes, j


def closeOpenElementsToDepth(
    s: Stream,
    endPos: int,
    targetDepth: int,
    itemTag: str,
    itemLineNum: int,
) -> list[EndTag]:
    """Close any HTML elements left open on `s.openEls` above `targetDepth` when a Markdown list item ends.

    Silently closes a trailing `<p>` and HTML optional-end-tag children whose unclosed parent is also
    being closed, logging a single error for the unclosed element(s) instead of letting them leak
    onto `s.openEls` across subsequent list items.
    """
    tags = s.openEls.tags
    if len(tags) <= targetDepth:
        return []

    endTags: list[EndTag] = []
    # A trailing unclosed <p> auto-closes cleanly when </li>, </dt>, or </dd> closes.
    if tags[-1].startTag.tag == "p":
        entry = s.openEls.popEntry()
        endTags.append(EndTag.fromStream(s, endPos, endPos, entry.startTag))
    if len(tags) <= targetDepth:
        return endTags

    leaked = list(tags[targetDepth:])
    while len(tags) > targetDepth:
        entry = s.openEls.popEntry()
        endTags.append(EndTag.fromStream(s, endPos, endPos, entry.startTag))

    # Only report elements that aren't validly auto-closed by an unclosed parent being closed here.
    unclosed = []
    for idx, entry in enumerate(leaked):
        tag = entry.startTag.tag
        if idx > 0 and tag in _AUTO_CLOSABLE_CHILD and leaked[idx - 1].startTag.tag in _AUTO_CLOSABLE_CHILD[tag]:
            continue
        unclosed.append(entry)

    endLine = s.line(max(0, endPos - 1)) if endPos > 0 else itemLineNum
    itemSpan = (
        f"started on line {itemLineNum}, ended on line {endLine}" if endLine > itemLineNum else f"on line {itemLineNum}"
    )
    if len(unclosed) == 1:
        entry = unclosed[0]
        m.die(
            f"<{entry.startTag.tag}> element was still open at the end of the markdown <{itemTag}> ({itemSpan})",
            lineNum=entry.startTag.loc,
        )
    elif unclosed:
        openList = [f"{x.name} at {x.startTag.loc}" for x in unclosed]
        m.die(
            f"{len(unclosed)} elements were still open at the end of the markdown <{itemTag}> ({itemSpan}).\nOpen tags: {', '.join(openList)}",
            lineNum=unclosed[0].startTag.loc,
        )
    return endTags


def parseHtmlListItem(
    s: Stream,
    lineStart: int,
    *,
    listStartTag: StartTag,
    baseIndent: int,
    itemTypes: tuple[str, ...],
    htmlItemTags: tuple[str, ...],
    onMacroNodes: t.Callable[[list[ParserNode], bool], None] | None,
    outerStopAt: ListStop | None,
    parseSubBlocks: BlockRecurseFn,
) -> tuple[list[ParserNode], int]:
    """Parse an explicit HTML `<li>`/`<dt>`/`<dd>` item mixed into a synthetic Markdown list."""
    nodes: list[ParserNode] = []
    syntheticEntry = s.openEls.pushSynthetic(listStartTag)
    try:
        tagDepthBefore = len(s.openEls.tags)
        bodyStart = consumeIndentAt(s, lineStart, s.config.indent, baseIndent)
        assert bodyStart is not None
        lineNodes, i = parseInlineNodes(
            s,
            bodyStart,
            stopAtNewline=True,
            minIndent=baseIndent,
            onMacroNodes=onMacroNodes,
        )
        nodes.extend(lineNodes)
        if not s.inOpaqueElement():
            nodes.append(RawText(text="\n"))

        if len(s.openEls.tags) > tagDepthBefore:
            openItemTag = s.openEls.tags[tagDepthBefore].startTag.tag
            itemStop = ListStop(
                baseIndent=baseIndent,
                itemTypes=itemTypes,
                htmlItemTags=htmlItemTags,
                htmlCloseTag=openItemTag,
                tagDepth=len(s.openEls.tags),
                parent=outerStopAt,
            )
            bodyNodes, i = parseSubBlocks(
                s,
                i,
                minIndent=baseIndent,
                minTagDepth=len(s.openEls.tags),
                stopAt=itemStop,
                stopAtTagDepth=tagDepthBefore,
                initialCanStartParagraph=False,
            )
            nodes.extend(bodyNodes)

        # Close any inner unclosed tags and auto-close the HTML item itself if its end tag was omitted.
        if len(s.openEls.tags) > tagDepthBefore and s.openEls.tags[tagDepthBefore].startTag.tag in htmlItemTags:
            openItemTag = s.openEls.tags[tagDepthBefore].startTag.tag
            nodes.extend(closeOpenElementsToDepth(s, i, tagDepthBefore + 1, openItemTag, s.line(lineStart)))
            entry = s.openEls.popEntry()
            nodes.append(EndTag(tag=entry.startTag.tag))
    finally:
        s.openEls.popSynthetic(syntheticEntry)

    return nodes, i


def parseList(
    s: Stream,
    firstKind: str,
    firstMatch: re.Match[str],
    firstLineStart: int,
    *,
    baseIndent: int,
    minTagDepth: int,
    prevNodes: list[ParserNode],
    indentChecker: IndentChecker | None,
    onMacroNodes: t.Callable[[list[ParserNode], bool], None] | None,
    outerStopAt: ListStop | None,
    parseSubBlocks: BlockRecurseFn,
) -> tuple[list[ParserNode], int]:
    """Parse a bulleted, numbered, or definition list at `baseIndent` using streaming indentation frames.

    If `s.openEls` already has a matching HTML list container (`<ul>`, `<ol>`, `<dl>`, or `<dl> > <div>`),
    emits items directly into it without creating a synthetic wrapper. Inside a synthetic container,
    also accepts interleaved HTML `<li>`/`<dt>`/`<dd>` items at `baseIndent`.
    """
    if firstKind == "bulleted":
        itemTypes: tuple[str, ...] = ("bulleted",)
        htmlItemTags: tuple[str, ...] = ("li",)
        listTag = "ul"
        listAttrs: dict[str, str] = {}
    elif firstKind == "numbered":
        itemTypes = ("numbered",)
        htmlItemTags = ("li",)
        listTag = "ol"
        startNum = int(firstMatch.group(1))
        listAttrs = {} if startNum == 1 else {"start": str(startNum)}
    else:
        itemTypes = ("dt", "dd")
        htmlItemTags = ("dt", "dd")
        listTag = "dl"
        listAttrs = {}

    hasHtmlContainer, htmlExitTags, autoCloseEndTags = matchHtmlListParent(
        s,
        minTagDepth,
        listTag,
        baseIndent,
        prevNodes,
    )
    listLineNum = s.line(firstLineStart)
    nodes: list[ParserNode] = list(autoCloseEndTags)
    listStartTag: StartTag | None = None
    if not hasHtmlContainer:
        s.openEls.autoCloseStartAt(s, listTag, firstLineStart)
        s.openEls.verifyDirectParent(listTag, lineLoc(s, listLineNum))
        listStartTag = makeStartTag(listTag, listLineNum, listAttrs)
        nodes.append(listStartTag)

    listStop = ListStop(
        baseIndent=baseIndent,
        itemTypes=itemTypes,
        htmlItemTags=htmlItemTags,
        htmlExitTags=htmlExitTags,
        hasHtmlContainer=hasHtmlContainer,
        tagDepth=len(s.openEls.tags),
        parent=outerStopAt,
    )
    itemMinIndent = baseIndent + 1
    chars = s.chars
    length = s.length
    indent = s.config.indent

    curKind: str | None = firstKind
    curMatch: re.Match[str] | None = firstMatch
    curHtmlTag: str | None = None
    curLineNum = listLineNum
    i = firstLineStart

    while True:
        if curHtmlTag is not None:
            assert listStartTag is not None
            htmlItemNodes, i = parseHtmlListItem(
                s,
                i,
                listStartTag=listStartTag,
                baseIndent=baseIndent,
                itemTypes=itemTypes,
                htmlItemTags=htmlItemTags,
                onMacroNodes=onMacroNodes,
                outerStopAt=outerStopAt,
                parseSubBlocks=parseSubBlocks,
            )
            nodes.extend(htmlItemNodes)
            skipped = skipBlanksToNextListItem(
                s,
                i,
                baseIndent=baseIndent,
                itemTypes=itemTypes,
                htmlItemTags=htmlItemTags,
                indentChecker=indentChecker,
            )
            if skipped is None:
                break
            blankNodes, i = skipped
            nodes.extend(blankNodes)
        else:
            assert curKind is not None and curMatch is not None
            itemTag = "li" if curKind in ("bulleted", "numbered") else curKind
            nodes.append(makeStartTag(itemTag, curLineNum, {"data-md": ""}))
            afterMarker = curMatch.end()
            itemTagDepth = len(s.openEls.tags)
            s.openEls.pushBlockParent(itemTag)
            try:
                itemNodes, i = parseSubBlocks(
                    s,
                    afterMarker,
                    minIndent=itemMinIndent,
                    minTagDepth=itemTagDepth,
                    firstLineTrimmed=True,
                    stopAt=listStop,
                )
            finally:
                s.openEls.popBlockParent()
            nodes.extend(itemNodes)
            nodes.extend(closeOpenElementsToDepth(s, i, itemTagDepth, itemTag, curLineNum))
            nodes.append(EndTag(tag=itemTag))

        # `parseSubBlocks` returns only at EOF, a list-ending blank line, or a `shouldStopForList` line.
        if i >= length:
            break
        nextEnd = findLineEnd(s, i)
        nextCStart = skipHws(chars, i, nextEnd)
        if nextCStart == nextEnd:
            break
        nextAbsIndent = prefixCountAt(s, i, indent)
        if nextAbsIndent != baseIndent:
            break
        nextKind, nextMatch = matchListItemStart(chars, nextCStart, nextEnd)
        if nextKind in itemTypes and nextMatch is not None:
            curKind = nextKind
            curMatch = nextMatch
            curHtmlTag = None
            curLineNum = s.line(i)
            continue
        if not hasHtmlContainer:
            peek = html.peekHtmlTagAt(s, nextCStart, nextEnd)
            if peek is not None and not peek[0] and peek[1] in htmlItemTags:
                curKind = None
                curMatch = None
                curHtmlTag = peek[1]
                continue
        break

    if not hasHtmlContainer:
        nodes.append(EndTag(tag=listTag))
    return nodes, i
