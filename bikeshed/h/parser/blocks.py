"""Block-level Markdown parser: headings, rules, paragraphs, blockquotes, block macros, and top-level block loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ... import messages as m
from ... import t
from .. import elements
from . import html, lists, macros, markdown
from .indents import (
    IndentChecker,
    consumeIndentAt,
    findLineEnd,
    lineLoc,
    nextLinePos,
    prefixCountAt,
    skipHws,
)
from .lists import ListStop, blankEndsList, effectivePrevNodes, parseList, shouldStopForList
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    RawText,
    SelfClosedTag,
    StartTag,
    TagStackEntry,
    isInlineTag,
    isTag,
    makeStartTag,
)
from .parser import parseInlineNodes
from .stream import ParseConfig, Stream

_EQUALS_LINE_RE = re.compile(r"={3,}[ \t]*$")
_DASH_LINE_RE = re.compile(r"-{3,}[ \t]*$")
_HEADING_START_RE = re.compile(r"(#{1,5})[ \t]+(?=\S)")
_HEADING_ID_RE = re.compile(r"\{#([^ }]+)\}$")
_HEADING_CLOSING_RES = {
    "#": re.compile(r"#\s*\{#[^ }]+\}$"),
    "##": re.compile(r"##\s*\{#[^ }]+\}$"),
    "###": re.compile(r"###\s*\{#[^ }]+\}$"),
    "####": re.compile(r"####\s*\{#[^ }]+\}$"),
    "#####": re.compile(r"#####\s*\{#[^ }]+\}$"),
}
_MULTILINE_HEADING_ID_RE = re.compile(r"\s*\{\s*#([^ }]+)\s*\}\s*$")
_NOTE_START_RE = re.compile(r"(note[:,])(\s*)(.*)", re.I)
_ISSUE_PAREN_START_RE = re.compile(r"issue\(([^)]+)\):(.*)", re.I)
_BLOCK_MATH_DISPLAY_RE = re.compile(r"""(?<![\w._:-])display\s*=\s*(?:"block"|'block'|block(?:\s|>|/|$))""", re.I)


@dataclass(slots=True)
class PendingLine:
    """Pre-parsed non-paragraph line handed back from `parseParagraph()` to `parseBlocks()` to avoid re-parsing."""

    kind: str  # "htmlblock" | "blank"
    lineNodes: list[ParserNode]
    nextI: int


@dataclass(slots=True)
class BlockState:
    """Mutable parsing state threaded across recursive block Markdown calls."""

    blockElements: set[str]
    blockquoteWarned: bool = False
    indentChecker: IndentChecker | None = None
    onMacroNodes: t.Callable[[list[ParserNode], bool], None] | None = None


@dataclass(slots=True)
class _PreparedLine:
    """Resolved indentation and slice offsets for a non-blank, non-comment block line."""

    lineStart: int
    lineEnd: int
    bodyStart: int
    cStart: int
    absIndent: int
    relIndent: int
    underIndented: bool
    wasFirstLineTrimmed: bool


@dataclass(slots=True)
class _LinePrepResult:
    """Outcome of preparing the next physical line in `parseBlocks()`."""

    nextI: int
    canStartParagraph: bool
    listContinuesUntil: int
    line: _PreparedLine | None = None
    stop: bool = False


def parseBlockStream(s: Stream, *, indentChecker: IndentChecker | None = None) -> list[ParserNode]:
    """Parse block-level Markdown and inline HTML/Bikeshed markup from `s` in one pass."""
    assert not s.config.rawHtml
    if s.blockParser is None:
        s.blockParser = parseBlockStream
    state = BlockState(
        blockElements={*s.config.blockElements, "if-wrapper", "bs-macro"},
        indentChecker=indentChecker,
        onMacroNodes=indentChecker.checkMacroNodes if indentChecker is not None else None,
    )
    nodes, _ = parseBlocks(s, 0, state, checkIndents=indentChecker is not None)
    if s.config.markdownInline:
        nodes = markdown.resolveEmphasis(nodes, state.blockElements)
    return nodes


def _reportUnderIndented(s: Stream, lineStart: int, lineEnd: int, minIndent: int) -> None:
    """Log a fatal error for a Markdown line inside a list item that lacks `minIndent` indentation levels."""
    tabs = f"{minIndent} tab{'' if minIndent == 1 else 's'}"
    totalSpaces = minIndent * s.config.indent
    spaces = f"{totalSpaces} space{'' if totalSpaces == 1 else 's'}"
    if s.config.indentChar == "\t":
        detail = tabs
    elif s.config.indentChar == " ":
        detail = spaces
    else:
        detail = f"{tabs} or {spaces}"
    m.die(
        f'Line {s.line(lineStart)} isn\'t indented enough (needs {minIndent} indent{"" if minIndent == 1 else "s"}: {detail}) to be valid Markdown:\n"{s.chars[lineStart:lineEnd]}"',
    )


def stripWsNodes(nodes: list[ParserNode]) -> list[ParserNode]:
    """Return `nodes` with leading and trailing whitespace stripped from outer RawText nodes."""
    if not nodes:
        return []
    first = nodes[0]
    last = nodes[-1]
    if not isinstance(first, RawText) and not isinstance(last, RawText):
        return nodes
    res = list(nodes)
    while res and isinstance(res[0], RawText):
        trimmed = res[0].text.lstrip()
        if not trimmed:
            res.pop(0)
        else:
            if trimmed != res[0].text:
                res[0] = RawText(s=res[0].s, start=res[0].start, end=res[0].end, text=trimmed)
            break
    while res and isinstance(res[-1], RawText):
        trimmed = res[-1].text.rstrip()
        if not trimmed:
            res.pop()
        else:
            if trimmed != res[-1].text:
                res[-1] = RawText(s=res[-1].s, start=res[-1].start, end=res[-1].end, text=trimmed)
            break
    return res


def rstripNodes(nodes: list[ParserNode]) -> None:
    """Strip trailing whitespace in-place from the end of `nodes`."""
    while nodes and isinstance(nodes[-1], RawText):
        trimmed = nodes[-1].text.rstrip()
        if not trimmed:
            nodes.pop()
        else:
            if trimmed != nodes[-1].text:
                nodes[-1] = RawText(s=nodes[-1].s, start=nodes[-1].start, end=nodes[-1].end, text=trimmed)
            break


def sliceFirstText(nodes: list[ParserNode], offset: int) -> list[ParserNode]:
    """Return a copy of `nodes` with the first `offset` characters removed from the leading RawText node."""
    if not nodes:
        return []
    first = nodes[0]
    assert isinstance(first, RawText)
    rest = first.text[offset:]
    if rest:
        return [RawText(s=first.s, start=first.start, end=first.end, text=rest), *nodes[1:]]
    return list(nodes[1:])


def isInlineStart(node: ParserNode, blockElements: set[str]) -> bool:
    """Return whether `node` is an inline tag (or non-tag) that can start a Markdown text line."""
    return not isTag(node) or isInlineTag(node, blockElements)


def matchRawBlockStart(
    s: Stream,
    cStart: int,
    lineEnd: int,
    config: ParseConfig,
) -> tuple[str | None, re.Match[str] | None]:
    """Classify a non-blank line's raw-text Markdown block opener at `cStart`."""
    chars = s.chars
    ch = chars[cStart]
    if ch == "=" and _EQUALS_LINE_RE.match(chars, cStart, lineEnd):
        return "equals-line", None
    if ch == "-" and _DASH_LINE_RE.match(chars, cStart, lineEnd):
        return "dash-line", None
    if ch == "#" and (match := _HEADING_START_RE.match(chars, cStart, lineEnd)):
        return "heading", match
    if ch in ("*", "-", "_") and lists.RULE_RE.match(chars, cStart, lineEnd):
        return "rule", None
    listKind, listMatch = lists.matchListItemStart(chars, cStart, lineEnd)
    if listKind is not None:
        return listKind, listMatch
    if config.markdownBlockquotes and ch == ">":
        return "blockquote", None
    return None, None


def isFencedCodeStart(s: Stream, cStart: int, lineEnd: int) -> bool:
    """Return True if `cStart` starts a valid fenced code block opener (no backticks in info string)."""
    chars = s.chars
    if cStart >= lineEnd or chars[cStart] not in ("`", "~"):
        return False
    match = markdown.fencedStartRe.match(chars, cStart, lineEnd)
    if match is None:
        return False
    return "`" not in chars[match.end() : lineEnd]


def isBlockHtmlStart(s: Stream, cStart: int, lineEnd: int, blockElements: set[str]) -> bool:
    """Read-only peek: return whether `cStart` begins with a block-level HTML tag."""
    peek = html.peekHtmlTagAt(s, cStart, lineEnd)
    if peek is None:
        return False
    isClose, tagname, afterName = peek
    chars = s.chars
    if tagname == "l":
        return False
    if tagname == "math":
        if tagname in blockElements:
            return True
        if isClose:
            entry = s.openEls.getDeepestFromTag("math")
            if entry is not None and entry.startTag.attrs.get("display", "inline").lower() == "block":
                return True
            return False
        gt = chars.find(">", afterName)
        tagSlice = chars[afterName : gt if gt != -1 else lineEnd]
        return bool(_BLOCK_MATH_DISPLAY_RE.search(tagSlice))
    if tagname in elements.INLINE_ELEMENTS:
        return False
    if "-" in tagname and tagname not in blockElements:
        return False
    return True


def peekSetextUnderline(
    s: Stream,
    start: int,
    minIndent: int,
    stopAt: ListStop | None,
) -> tuple[str, int] | None:
    """Peek past comment-only lines for a Setext underline (`===` or `---`), returning `(tagName, nextI)`."""
    chars = s.chars
    length = s.length
    j = start
    while j < length:
        if (nextAfterComment := html.trySkipCommentOrDoctypeLine(s, j, peekOnly=True)) is not None:
            j = nextAfterComment
            continue
        jEnd = findLineEnd(s, j)
        if skipHws(chars, j, jEnd) == jEnd:
            return None
        absIndent = prefixCountAt(s, j, s.config.indent)
        if shouldStopForList(s, j, jEnd, absIndent, stopAt):
            return None
        if absIndent < minIndent:
            return None
        bodyStart = consumeIndentAt(s, j, s.config.indent, minIndent)
        assert bodyStart is not None
        cStart = skipHws(chars, bodyStart, jEnd)
        if cStart >= jEnd:
            return None
        nextI = nextLinePos(jEnd, length)
        if chars[cStart] == "=" and _EQUALS_LINE_RE.match(chars, cStart, jEnd):
            return "h2", nextI
        if chars[cStart] == "-" and _DASH_LINE_RE.match(chars, cStart, jEnd):
            return "h3", nextI
        return None
    return None


def extractSingleLineHeadingId(nodes: list[ParserNode], hashes: str) -> str | None:
    """Extract a trailing `{#id}` from `nodes`, stripping closing `#`s and `{#id}` in-place when matched."""
    if not nodes or not isinstance(nodes[-1], RawText):
        return None
    lastNode = nodes[-1]
    lastText = lastNode.text
    idMatch = _HEADING_ID_RE.search(lastText)
    if not idMatch:
        return None
    headingId = idMatch.group(1)
    closingMatch = _HEADING_CLOSING_RES[hashes].search(lastText)
    if not closingMatch:
        return headingId
    prefix = lastText[: closingMatch.start()]
    if len(nodes) == 1 and not prefix.strip():
        return headingId
    if prefix:
        nodes[-1] = RawText(
            s=lastNode.s,
            start=lastNode.start,
            end=lastNode.end,
            text=prefix,
        )
    else:
        nodes.pop()
    return headingId


def buildSingleLineHeading(
    lineNum: int,
    hashes: str,
    contentNodes: list[ParserNode],
) -> list[ParserNode]:
    """Wrap ATX heading content in `<h2>`-`<h6>` (level = `len(hashes) + 1`), extracting any trailing `{#id}`."""
    headingNodes = stripWsNodes(contentNodes)
    headingId = extractSingleLineHeadingId(headingNodes, hashes)
    headingNodes = stripWsNodes(headingNodes)
    attrs: dict[str, str] = {}
    if headingId:
        attrs["id"] = headingId
    tagName = f"h{len(hashes) + 1}"
    return [
        makeStartTag(tagName, lineNum, attrs),
        *headingNodes,
        EndTag(tag=tagName),
        RawText(text="\n"),
    ]


def buildMultiLineHeading(
    lineNum: int,
    tagName: str,
    strippedNodes: list[ParserNode],
) -> list[ParserNode]:
    """Wrap Setext heading content in `<h2>`/`<h3>`, extracting and stripping any trailing `{#id}`."""
    attrs: dict[str, str] = {}
    headingNodes = list(strippedNodes)
    if headingNodes and isinstance(headingNodes[-1], RawText):
        lastText = headingNodes[-1].text
        if match := _MULTILINE_HEADING_ID_RE.search(lastText):
            attrs["id"] = match.group(1)
            prefix = lastText[: match.start()]
            if prefix:
                headingNodes[-1] = RawText(
                    s=headingNodes[-1].s,
                    start=headingNodes[-1].start,
                    end=headingNodes[-1].end,
                    text=prefix,
                )
            else:
                headingNodes.pop()
                rstripNodes(headingNodes)
    return [
        makeStartTag(tagName, lineNum, attrs),
        *headingNodes,
        EndTag(tag=tagName),
        RawText(text="\n"),
    ]


def parseParagraph(
    s: Stream,
    lineNum: int,
    firstStrippedNodes: list[ParserNode],
    *,
    initialRelIndent: int,
    startAfterLine1: int,
    state: BlockState,
    minIndent: int,
    stopAt: ListStop | None,
    stopAtTagDepth: int | None = None,
    checkIndents: bool,
) -> tuple[list[ParserNode], int, PendingLine | None]:
    """Build a `<p>` block starting with `firstStrippedNodes` and consume continuation lines."""
    firstLineNodes = list(firstStrippedNodes)
    prefixNodes: list[ParserNode]
    endTags: list[ParserNode] = [EndTag(tag="p")]

    if firstLineNodes and isinstance(firstLineNodes[0], RawText):
        firstText = firstLineNodes[0].text
        lowerFirst = firstText.lower()
        if matchNote := _NOTE_START_RE.match(firstText):
            firstLineNodes = sliceFirstText(firstLineNodes, matchNote.start(3))
            prefixNodes = [
                makeStartTag("p", lineNum, {"class": "replace-with-note-class"}),
                makeStartTag("span", lineNum, {"class": "marker"}),
                RawText(text=matchNote.group(1)),
                EndTag(tag="span"),
            ]
            if matchNote.group(2):
                prefixNodes.append(RawText(text=matchNote.group(2)))
        elif lowerFirst.startswith("issue:"):
            firstLineNodes = sliceFirstText(firstLineNodes, 6)
            prefixNodes = [makeStartTag("p", lineNum, {"class": "replace-with-issue-class"})]
        elif lowerFirst.startswith("assert:"):
            prefixNodes = [makeStartTag("p", lineNum, {"class": "replace-with-assertion-class"})]
        elif lowerFirst.startswith("advisement:"):
            firstLineNodes = sliceFirstText(firstLineNodes, 11)
            prefixNodes = [
                makeStartTag("p", lineNum),
                makeStartTag("strong", lineNum, {"class": "replace-with-advisement-class"}),
            ]
            endTags = [EndTag(tag="strong"), EndTag(tag="p")]
        elif match := _ISSUE_PAREN_START_RE.match(firstText):
            firstLineNodes = sliceFirstText(firstLineNodes, match.start(2))
            prefixNodes = [
                makeStartTag(
                    "p",
                    lineNum,
                    {"bs-remote-issue-id": match.group(1), "class": "replace-with-issue-class"},
                ),
            ]
        else:
            prefixNodes = [makeStartTag("p", lineNum)]
    else:
        prefixNodes = [makeStartTag("p", lineNum)]

    contentNodes: list[ParserNode] = list(firstLineNodes)
    i = startAfterLine1
    chars = s.chars
    length = s.length
    indent = s.config.indent
    pending: PendingLine | None = None

    while i < length:
        if stopAtTagDepth is not None and len(s.openEls.tags) <= stopAtTagDepth:
            break
        if checkIndents and state.indentChecker is not None and not s.inOpaqueElement():
            state.indentChecker.checkLine(s, i)
        lineEnd = findLineEnd(s, i)
        lineCStart = skipHws(chars, i, lineEnd)
        if lineCStart == lineEnd:
            break
        if (nextAfterComment := html.trySkipCommentOrDoctypeAt(s, lineCStart)) is not None:
            i = nextAfterComment
            continue
        absIndent = prefixCountAt(s, i, indent)
        if shouldStopForList(s, i, lineEnd, absIndent, stopAt):
            break
        underIndented = False
        if absIndent < minIndent:
            # Insufficiently indented line inside a list item; only consume if
            # initialRelIndent == 0 and it's a plain text line (otherwise let parseBlocks handle it).
            if initialRelIndent > 0:
                break
            cStart = lineCStart
            rawKind, _ = matchRawBlockStart(s, cStart, lineEnd, s.config)
            if rawKind is not None:
                break
            underIndented = True
            bodyStart = i
        else:
            relIndent = absIndent - minIndent
            if relIndent < initialRelIndent:
                break
            if minIndent == 0:
                bodyStart = i
                cStart = lineCStart
            else:
                consumed = consumeIndentAt(s, i, indent, minIndent)
                assert consumed is not None
                bodyStart = consumed
                cStart = skipHws(chars, bodyStart, lineEnd)
            rawKind, _ = matchRawBlockStart(s, cStart, lineEnd, s.config)
            if rawKind is not None:
                break

        peek = html.peekHtmlTagAt(s, cStart, lineEnd)
        if peek is not None and not peek[0] and peek[1] == "bs-macro":
            break

        lineNodes, nextI = parseInlineNodes(
            s,
            bodyStart,
            stopAtNewline=True,
            minIndent=minIndent,
            onMacroNodes=state.onMacroNodes,
        )
        stripped = stripWsNodes(lineNodes)
        if not stripped:
            pending = PendingLine(kind="blank", lineNodes=lineNodes, nextI=nextI)
            break
        if len(stripped) == 1 and isinstance(stripped[0], (Comment, Doctype)):
            i = nextI
            continue
        if underIndented:
            _reportUnderIndented(s, i, lineEnd, minIndent)
        if not isInlineStart(stripped[0], state.blockElements):
            pending = PendingLine(kind="htmlblock", lineNodes=lineNodes, nextI=nextI)
            break
        contentNodes.append(RawText(text="\n"))
        contentNodes.extend(lineNodes)
        i = nextI

    rstripNodes(contentNodes)
    return [*prefixNodes, *contentNodes, *endTags, RawText(text="\n")], i, pending


def matchFenceAt(s: Stream, contentStart: int, lineEnd: int) -> tuple[int, str, bool, bool] | None:
    """If `contentStart` (after stripping nested `>` markers) starts with a code fence, return `(gtDepth, fence, isOpener, isCloser)`."""
    chars = s.chars
    pos = skipHws(chars, contentStart, lineEnd)
    gtDepth = 0
    while pos < lineEnd and chars[pos] == ">":
        gtDepth += 1
        pos = skipHws(chars, pos + 1, lineEnd)
    if pos >= lineEnd or chars[pos] not in ("`", "~"):
        return None
    match = markdown.fencedStartRe.match(chars, pos, lineEnd)
    if match is None:
        return None
    isOpener = "`" not in chars[match.end() : lineEnd]
    isCloser = skipHws(chars, match.end(), lineEnd) == lineEnd
    return gtDepth, match.group(0), isOpener, isCloser


def bqLineAllowsLazyContinuation(
    s: Stream,
    contentStart: int,
    lineEnd: int,
    blockElements: set[str],
) -> bool | None:
    """Return whether a blockquote line's stripped content leaves a paragraph open for lazy continuation.

    Returns `None` for single-line standalone comments/doctypes (which are transparent).
    """
    chars = s.chars
    pos = skipHws(chars, contentStart, lineEnd)
    while pos < lineEnd and chars[pos] == ">":
        pos = skipHws(chars, pos + 1, lineEnd)
    if pos >= lineEnd:
        return False
    afterComment = html.trySkipCommentOrDoctypeLine(s, pos, peekOnly=True)
    if afterComment is not None:
        if afterComment == nextLinePos(lineEnd, s.length):
            return None
    if isFencedCodeStart(s, pos, lineEnd):
        return False
    if isBlockHtmlStart(s, pos, lineEnd, blockElements):
        return False
    rawKind, rawMatch = matchRawBlockStart(s, pos, lineEnd, s.config)
    if rawKind is None:
        return True
    if rawKind in ("bulleted", "numbered", "dt", "dd"):
        assert rawMatch is not None
        return bqLineAllowsLazyContinuation(s, rawMatch.end(), lineEnd, blockElements)
    return False


def _isLazyContinuationLine(s: Stream, cStart: int, lineEnd: int, blockElements: set[str]) -> bool:
    """Return True if a non-`>` line at `cStart` is a plain text line eligible to lazily continue a blockquote."""
    rawKind, _ = matchRawBlockStart(s, cStart, lineEnd, s.config)
    return (
        rawKind is None
        and not isFencedCodeStart(s, cStart, lineEnd)
        and not isBlockHtmlStart(s, cStart, lineEnd, blockElements)
    )


def _autoClosePreLineParagraph(
    s: Stream,
    tagName: str,
    lineStart: int,
    *,
    preLineTopP: TagStackEntry | None,
    preLineHasBuriedP: bool,
    preLineTagDepth: int,
    preLineParentContext: tuple[str | None, str | None],
) -> tuple[int, tuple[str | None, str | None]]:
    """Auto-close an HTML `<p>` that was open prior to an inline-parsed line now becoming a block (`<p>` or Setext heading)."""
    if (
        preLineTopP is not None
        and preLineTagDepth - 1 < len(s.openEls.tags)
        and s.openEls.tags[preLineTagDepth - 1] is preLineTopP
    ):
        s.openEls.popEntry(preLineTagDepth - 1)
        preLineTagDepth -= 1
        preLineParentContext = s.openEls.directParentContext(preLineTagDepth)
    elif preLineHasBuriedP and s.openEls.inTagContext("p"):
        s.openEls.autoCloseStartAt(s, tagName, lineStart)
    return preLineTagDepth, preLineParentContext


def parseBlockquote(
    s: Stream,
    lineStart: int,
    cStart: int,
    lineEnd: int,
    *,
    bqAbsIndent: int,
    state: BlockState,
    stopAt: ListStop | None,
    checkIndents: bool,
) -> tuple[list[ParserNode], int]:
    """Collect consecutive `>`-prefixed (and lazy-continuation) lines and parse them recursively in a child Stream."""
    chars = s.chars
    length = s.length
    indent = s.config.indent
    lineNum = s.line(lineStart)
    s.openEls.autoCloseStartAt(s, "blockquote", lineStart)
    s.openEls.verifyDirectParent("blockquote", lineLoc(s, lineNum))

    if not state.blockquoteWarned and not s.config.markdownBlockquotesExplicit:
        state.blockquoteWarned = True
        m.warn(
            f"Line {lineNum} looks like the start of a markdown blockquote.\nIf this is intended, please set `Markup Shorthands: markdown-blockquotes yes`; if not, set it to `no`.\nSee https://speced.github.io/bikeshed/#md-blockquote for details.",
        )

    # Tracks an open fenced code block as (nested `>` depth, fence char, fence length)
    # so lazy continuation is disabled until a matching closer at the same depth appears.
    openFence: tuple[int, str, int] | None = None
    canLazyContinue = False
    subLines: list[str] = []
    # Track stripped prefix widths per line so errors inside the child stream report accurate columns.
    colOffsets: list[int] = []

    def observeBqContent(contentStart: int, contentEnd: int) -> None:
        """Update open-fence and lazy-continuation eligibility after consuming a blockquote line."""
        nonlocal openFence, canLazyContinue
        fence = matchFenceAt(s, contentStart, contentEnd)
        if openFence is not None:
            if (
                fence is not None
                and fence[0] == openFence[0]
                and fence[1][0] == openFence[1]
                and len(fence[1]) >= openFence[2]
                and fence[3]
            ):
                openFence = None
            canLazyContinue = False
            return
        if fence is not None and fence[2]:
            openFence = (fence[0], fence[1][0], len(fence[1]))
            canLazyContinue = False
            return
        allows = bqLineAllowsLazyContinuation(s, contentStart, contentEnd, state.blockElements)
        if allows is not None:
            canLazyContinue = allows

    def consumeQuotedLine(physStart: int, gtPos: int, endPos: int) -> None:
        """Strip one `>` prefix (and optional space/tab), record line content and column offset, and update state."""
        afterGt = gtPos + 1
        if afterGt < endPos and chars[afterGt] in (" ", "\t"):
            afterGt += 1
        subLines.append(chars[afterGt:endPos])
        colOffsets.append((afterGt - physStart) + s.colOffset(s.lineIndex(gtPos)))
        observeBqContent(afterGt, endPos)

    consumeQuotedLine(s.currentLineStart(cStart), cStart, lineEnd)

    i = nextLinePos(lineEnd, length)
    while i < length:
        curLineStart = i
        curLineEnd = findLineEnd(s, curLineStart)
        curCStart = skipHws(chars, curLineStart, curLineEnd)

        # Blank line without `>` always terminates the blockquote.
        if curCStart == curLineEnd:
            break

        # Handle comment-only lines without `>` inside a blockquote: preserve their line count
        # if the blockquote continues afterward, otherwise stop before them.
        if chars[curCStart] != ">" and (
            afterComment := html.trySkipCommentOrDoctypeLine(s, curLineStart, peekOnly=True)
        ):
            # Peek past consecutive comment-only lines to see if the blockquote continues.
            peekI = afterComment
            while peekI < length:
                if (nextC := html.trySkipCommentOrDoctypeLine(s, peekI, peekOnly=True)) is not None:
                    peekI = nextC
                    continue
                break
            continues = False
            if peekI < length:
                pEnd = findLineEnd(s, peekI)
                pCStart = skipHws(chars, peekI, pEnd)
                if pCStart < pEnd:
                    pAbsIndent = prefixCountAt(s, peekI, indent)
                    if pAbsIndent >= bqAbsIndent and not shouldStopForList(s, peekI, pEnd, pAbsIndent, stopAt):
                        if chars[pCStart] == ">":
                            continues = True
                        elif canLazyContinue and _isLazyContinuationLine(s, pCStart, pEnd, state.blockElements):
                            continues = True
            if not continues:
                break
            curCommentI = curLineStart
            while curCommentI < peekI:
                if checkIndents and state.indentChecker is not None:
                    state.indentChecker.checkLine(s, curCommentI)
                nextCommentI = html.trySkipCommentOrDoctypeLine(s, curCommentI, peekOnly=True)
                assert nextCommentI is not None
                # Preserve exact physical lines of the comment so child stream line numbers stay 1:1.
                commentSlice = chars[curCommentI:nextCommentI]
                if commentSlice.endswith("\n"):
                    commentSlice = commentSlice[:-1]
                commentStartIdx = s.lineIndex(curCommentI)
                for offsetIdx, commentLine in enumerate(commentSlice.split("\n")):
                    subLines.append(commentLine)
                    colOffsets.append(s.colOffset(commentStartIdx + offsetIdx))
                curCommentI = nextCommentI
            i = peekI
            continue

        curAbsIndent = prefixCountAt(s, curLineStart, indent)
        if curAbsIndent < bqAbsIndent:
            break
        if shouldStopForList(s, curLineStart, curLineEnd, curAbsIndent, stopAt):
            break

        if chars[curCStart] == ">":
            if checkIndents and state.indentChecker is not None:
                state.indentChecker.checkLine(s, curLineStart)
            consumeQuotedLine(curLineStart, curCStart, curLineEnd)
            i = nextLinePos(curLineEnd, length)
            continue

        # Potential lazy continuation line: only allowed after an open paragraph
        # (CommonMark §5.1) and only if it's a plain text line.
        if not canLazyContinue or not _isLazyContinuationLine(s, curCStart, curLineEnd, state.blockElements):
            break

        if checkIndents and state.indentChecker is not None:
            state.indentChecker.checkLine(s, curLineStart)
        subLines.append(chars[curCStart:curLineEnd])
        colOffsets.append((curCStart - curLineStart) + s.colOffset(s.lineIndex(curLineStart)))
        i = nextLinePos(curLineEnd, length)

    # Preserve a trailing newline so inline constructs that inspect `s[self.end] == "\n"`
    # (like trailing possessive `|var|'`) behave identically inside blockquotes.
    hadTrailingNewline = i > lineStart and chars[i - 1] == "\n"
    subChars = "\n".join(subLines)
    if hadTrailingNewline:
        subChars += "\n"
        colOffsets.append(0)
    subStream = s.subStream(
        context=s.config.context,
        chars=subChars,
        startLine=lineNum,
        colOffsets=colOffsets,
        openEls=s.openEls,
        depth=s.depth,
    )
    s.openEls.pushBlockParent("blockquote")
    try:
        innerNodes, _ = parseBlocks(
            subStream,
            0,
            state,
            minTagDepth=len(s.openEls.tags),
            checkIndents=False,
        )
    finally:
        s.openEls.popBlockParent()
    return [
        makeStartTag("blockquote", lineNum),
        *innerNodes,
        EndTag(tag="blockquote"),
        RawText(text="\n"),
    ], i


def parseBlockBsMacro(
    s: Stream,
    lineStart: int,
    cStart: int,
    lineEnd: int,
    *,
    state: BlockState,
    minIndent: int,
    minTagDepth: int,
    prevNodes: list[ParserNode],
    underIndented: bool,
    checkIndents: bool,
) -> tuple[list[ParserNode], int, bool]:
    """Parse a block-level `<bs-macro>` starting at `cStart` and expand the macro or its fallback via `parseBlocks()`."""
    startTag, afterStart, _ = html.parseStartTag(s, cStart)
    if not isinstance(startTag, StartTag) or startTag.tag != "bs-macro":
        restNodes, nextI = parseInlineNodes(
            s,
            cStart + 1,
            stopAtNewline=True,
            minIndent=minIndent,
            onMacroNodes=state.onMacroNodes,
        )
        fallbackOut: list[ParserNode] = [RawText.fromStream(s, cStart, cStart + 1, "&#60;"), *restNodes]
        if not s.inOpaqueElement():
            fallbackOut.append(RawText(text="\n"))
        return fallbackOut, nextI, True

    fallbackText, afterClose, _ = html.parseBsMacroToEnd(s, afterStart, startTag)
    if fallbackText is None:
        return [], s.length, False

    resolved = macros.resolveBsMacro(s, startTag, fallbackText, afterStart, openEls=s.openEls)
    expandedNodes: list[ParserNode] = []
    if resolved.stream is not None:
        expandedNodes, _ = parseBlocks(
            resolved.stream,
            0,
            state,
            minTagDepth=minTagDepth,
            inheritedPrevNodes=prevNodes,
            checkIndents=checkIndents and resolved.kind == "fallback",
        )
        if resolved.stream.config.markdownInline and expandedNodes:
            expandedNodes = markdown.resolveEmphasis(expandedNodes, state.blockElements)
        if resolved.kind == "macro" and state.onMacroNodes is not None and expandedNodes:
            state.onMacroNodes(expandedNodes, True)

    afterLineEnd = findLineEnd(s, afterClose)
    if skipHws(s.chars, afterClose, afterLineEnd) == afterLineEnd:
        nextI = nextLinePos(afterLineEnd, s.length)
        tailNodes: list[ParserNode] = []
    else:
        tailNodes, nextI = parseInlineNodes(
            s,
            afterClose,
            stopAtNewline=True,
            minIndent=minIndent,
            onMacroNodes=state.onMacroNodes,
        )

    producedContent = bool(stripWsNodes(expandedNodes)) or bool(stripWsNodes(tailNodes))
    if underIndented and producedContent:
        _reportUnderIndented(s, lineStart, lineEnd, minIndent)

    outNodes: list[ParserNode] = []
    if expandedNodes:
        outNodes.extend(expandedNodes)
        if not tailNodes and not s.inOpaqueElement():
            last = outNodes[-1]
            if not (isinstance(last, RawText) and last.text.endswith("\n")):
                outNodes.append(RawText(text="\n"))
    if tailNodes:
        outNodes.extend(tailNodes)
        if not s.inOpaqueElement():
            outNodes.append(RawText(text="\n"))
    elif not expandedNodes:
        outNodes.append(RawText(text="\n"))
    return outNodes, nextI, producedContent


def _makeListBodyParser(state: BlockState, *, checkIndents: bool) -> lists.BlockRecurseFn:
    """Bind `state` and `checkIndents` into a `BlockRecurseFn` callback for `lists.parseList()`."""

    def _recurse(
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
        return parseBlocks(
            s,
            start,
            state,
            minIndent=minIndent,
            minTagDepth=minTagDepth,
            firstLineTrimmed=firstLineTrimmed,
            stopAt=stopAt,
            stopAtTagDepth=stopAtTagDepth,
            initialCanStartParagraph=initialCanStartParagraph,
            checkIndents=checkIndents,
        )

    return _recurse


def _prepareBlockLine(
    s: Stream,
    lineStart: int,
    nodes: list[ParserNode],
    *,
    state: BlockState,
    minIndent: int,
    wasFirstLineTrimmed: bool,
    stopAt: ListStop | None,
    canStartParagraph: bool,
    listContinuesUntil: int,
    checkIndents: bool,
) -> _LinePrepResult:
    """Prepare the physical line at `lineStart`: handle metadata spans, blanks, comments, list exits, and indent."""
    chars = s.chars
    length = s.length
    indent = s.config.indent

    if wasFirstLineTrimmed:
        # First line of a list item: the list marker (and its leading indent) were already
        # consumed by parseList(), so `lineStart` starts at the item's effective `minIndent`.
        lineEnd = findLineEnd(s, lineStart)
        bodyStart = lineStart
        relIndent = prefixCountAt(s, bodyStart, indent)
        absIndent = minIndent + relIndent
        cStart = skipHws(chars, bodyStart, lineEnd)
        if cStart == lineEnd:
            # Empty remainder on a list item's opening line (e.g. `*\n`).
            if bodyStart < lineEnd:
                nodes.append(RawText.fromStream(s, bodyStart, lineEnd))
            nodes.append(RawText(text="\n"))
            return _LinePrepResult(
                nextI=nextLinePos(lineEnd, length),
                canStartParagraph=True,
                listContinuesUntil=listContinuesUntil,
            )
        if (nextAfterComment := html.trySkipCommentOrDoctypeAt(s, cStart)) is not None:
            return _LinePrepResult(
                nextI=nextAfterComment,
                canStartParagraph=canStartParagraph,
                listContinuesUntil=listContinuesUntil,
            )
        return _LinePrepResult(
            nextI=lineStart,
            canStartParagraph=canStartParagraph,
            listContinuesUntil=listContinuesUntil,
            line=_PreparedLine(
                lineStart=lineStart,
                lineEnd=lineEnd,
                bodyStart=bodyStart,
                cStart=cStart,
                absIndent=absIndent,
                relIndent=relIndent,
                underIndented=False,
                wasFirstLineTrimmed=True,
            ),
        )

    if s.metadataSpans and (metaEnd := s.metadataSpans.get(lineStart)) is not None:
        nodes.append(RawText(text="\n"))
        nextI = metaEnd + 1 if metaEnd < length and chars[metaEnd] == "\n" else metaEnd
        return _LinePrepResult(nextI=nextI, canStartParagraph=True, listContinuesUntil=listContinuesUntil)

    if checkIndents and state.indentChecker is not None:
        state.indentChecker.checkLine(s, lineStart)
    lineEnd = findLineEnd(s, lineStart)
    lineCStart = skipHws(chars, lineStart, lineEnd)
    if lineCStart == lineEnd:
        if stopAt is not None and lineStart >= listContinuesUntil:
            endsList, nextContentPos = blankEndsList(s, lineEnd, stopAt)
            if endsList:
                return _LinePrepResult(
                    nextI=lineStart,
                    canStartParagraph=canStartParagraph,
                    listContinuesUntil=listContinuesUntil,
                    stop=True,
                )
            listContinuesUntil = nextContentPos
        if lineStart < lineEnd:
            nodes.append(RawText.fromStream(s, lineStart, lineEnd))
        nodes.append(RawText(text="\n"))
        return _LinePrepResult(
            nextI=nextLinePos(lineEnd, length),
            canStartParagraph=True,
            listContinuesUntil=listContinuesUntil,
        )

    if (nextAfterComment := html.trySkipCommentOrDoctypeAt(s, lineCStart)) is not None:
        return _LinePrepResult(
            nextI=nextAfterComment,
            canStartParagraph=canStartParagraph,
            listContinuesUntil=listContinuesUntil,
        )

    absIndent = prefixCountAt(s, lineStart, indent)
    if shouldStopForList(s, lineStart, lineEnd, absIndent, stopAt):
        return _LinePrepResult(
            nextI=lineStart,
            canStartParagraph=canStartParagraph,
            listContinuesUntil=listContinuesUntil,
            stop=True,
        )

    underIndented = False
    if absIndent < minIndent:
        underIndented = True
        bodyStart = lineStart
        relIndent = 0
        cStart = lineCStart
    elif minIndent == 0:
        bodyStart = lineStart
        relIndent = absIndent
        cStart = lineCStart
    else:
        consumed = consumeIndentAt(s, lineStart, indent, minIndent)
        assert consumed is not None
        bodyStart = consumed
        relIndent = absIndent - minIndent
        cStart = skipHws(chars, bodyStart, lineEnd)

    return _LinePrepResult(
        nextI=lineStart,
        canStartParagraph=canStartParagraph,
        listContinuesUntil=listContinuesUntil,
        line=_PreparedLine(
            lineStart=lineStart,
            lineEnd=lineEnd,
            bodyStart=bodyStart,
            cStart=cStart,
            absIndent=absIndent,
            relIndent=relIndent,
            underIndented=underIndented,
            wasFirstLineTrimmed=False,
        ),
    )


def _parseInlineBlockLine(
    s: Stream,
    line: _PreparedLine,
    nodes: list[ParserNode],
    *,
    state: BlockState,
    minIndent: int,
    stopAt: ListStop | None,
    stopAtTagDepth: int | None,
    canStartParagraph: bool,
    checkIndents: bool,
) -> tuple[int, bool, PendingLine | None]:
    """Parse a non-opener logical line in inline/HTML mode and resolve Setext headings, paragraphs, or bare text."""
    preLineTagDepth = len(s.openEls.tags)
    preLineTopP = s.openEls.tags[-1] if s.openEls.tags and s.openEls.tags[-1].startTag.tag == "p" else None
    preLineHasBuriedP = preLineTopP is None and s.openEls.inTagContext("p")
    preLineParentContext = s.openEls.directParentContext()
    # When a line will be wrapped in a Markdown `<p>` or Setext heading, push a temporary
    # `"p"` block parent so inline tags on line 1 (e.g. `<b>`, `<dfn>`) don't trigger
    # duplicate direct-child errors on an enclosing `<ul>`/`<ol>`/`<dl>` alongside `<p>`.
    willWrapLine = (
        canStartParagraph
        and not isBlockHtmlStart(s, line.cStart, line.lineEnd, state.blockElements)
        and not isFencedCodeStart(s, line.cStart, line.lineEnd)
        and not (s.chars[line.cStart] == "[" and macros.isMacroStart(s, line.cStart + 1))
    )
    if willWrapLine:
        s.openEls.pushBlockParent("p", tagDepth=preLineTagDepth)
    try:
        lineNodes, nextI = parseInlineNodes(
            s,
            line.bodyStart,
            stopAtNewline=True,
            minIndent=minIndent,
            onMacroNodes=state.onMacroNodes,
            atLineStart=line.wasFirstLineTrimmed,
        )
    finally:
        if willWrapLine:
            s.openEls.popBlockParent()

    stripped = stripWsNodes(lineNodes)
    if not stripped:
        # e.g. <pre class=metadata> stripped to empty, or empty optional macro.
        nodes.extend(lineNodes)
        if not s.inOpaqueElement():
            nodes.append(RawText(text="\n"))
        return nextI, True, None
    if len(stripped) == 1 and isinstance(stripped[0], (Comment, Doctype)):
        return nextI, canStartParagraph, None
    if line.underIndented:
        # Deferred until after inline parsing so stripped metadata blocks or empty optional
        # macros inside a list item do not falsely trigger under-indentation errors.
        _reportUnderIndented(s, line.lineStart, line.lineEnd, minIndent)
    if not isInlineStart(stripped[0], state.blockElements):
        nodes.extend(lineNodes)
        if not s.inOpaqueElement():
            nodes.append(RawText(text="\n"))
        return nextI, False, None

    # Plain text line: check Setext heading first, then paragraph vs bare text.
    if (setext := peekSetextUnderline(s, nextI, minIndent, stopAt)) is not None:
        headingTag, afterUnderline = setext
        preLineTagDepth, preLineParentContext = _autoClosePreLineParagraph(
            s,
            headingTag,
            line.lineStart,
            preLineTopP=preLineTopP,
            preLineHasBuriedP=preLineHasBuriedP,
            preLineTagDepth=preLineTagDepth,
            preLineParentContext=preLineParentContext,
        )
        s.openEls.verifyDirectParent(headingTag, lineLoc(s, s.line(line.lineStart)), parentContext=preLineParentContext)
        # Skip/validate any intervening comment/doctype lines and check indent on underline.
        scanI = nextI
        while scanI < afterUnderline:
            if checkIndents and state.indentChecker is not None and not s.inOpaqueElement():
                state.indentChecker.checkLine(s, scanI)
            if (afterC := html.trySkipCommentOrDoctypeLine(s, scanI)) is not None:
                scanI = afterC
                continue
            break
        nodes.extend(buildMultiLineHeading(s.line(line.lineStart), headingTag, stripped))
        return afterUnderline, False, None

    if canStartParagraph:
        preLineTagDepth, preLineParentContext = _autoClosePreLineParagraph(
            s,
            "p",
            line.lineStart,
            preLineTopP=preLineTopP,
            preLineHasBuriedP=preLineHasBuriedP,
            preLineTagDepth=preLineTagDepth,
            preLineParentContext=preLineParentContext,
        )
        s.openEls.verifyDirectParent("p", lineLoc(s, s.line(line.lineStart)), parentContext=preLineParentContext)
        s.openEls.pushBlockParent("p", tagDepth=preLineTagDepth)
        try:
            paraNodes, afterParaI, pending = parseParagraph(
                s,
                s.line(line.lineStart),
                stripped,
                initialRelIndent=line.relIndent,
                startAfterLine1=nextI,
                state=state,
                minIndent=minIndent,
                stopAt=stopAt,
                stopAtTagDepth=stopAtTagDepth,
                checkIndents=checkIndents,
            )
        finally:
            s.openEls.popBlockParent()
        nodes.extend(paraNodes)
        return afterParaI, False, pending

    nodes.extend(lineNodes)
    if not s.inOpaqueElement():
        nodes.append(RawText(text="\n"))
    return nextI, False, None


def parseBlocks(
    s: Stream,
    start: int,
    state: BlockState,
    *,
    minIndent: int = 0,
    minTagDepth: int = 0,
    firstLineTrimmed: bool = False,
    stopAt: ListStop | None = None,
    stopAtTagDepth: int | None = None,
    initialCanStartParagraph: bool = True,
    inheritedPrevNodes: list[ParserNode] | None = None,
    checkIndents: bool = False,
) -> tuple[list[ParserNode], int]:
    """Parse block-level Markdown + HTML/inline Bikeshed markup from `s` starting at `start`."""
    nodes: list[ParserNode] = []
    i = start
    length = s.length
    canStartParagraph = initialCanStartParagraph
    pending: PendingLine | None = None
    # Tracks the first non-blank line after a verified non-ending blank run inside a list to avoid O(K^2) lookahead.
    listContinuesUntil = -1

    while i < length or pending is not None:
        if pending is not None:
            p = pending
            pending = None
            i = p.nextI
            nodes.extend(p.lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = p.kind == "blank"
            if stopAtTagDepth is not None and len(s.openEls.tags) <= stopAtTagDepth:
                break
            continue

        if stopAtTagDepth is not None and len(s.openEls.tags) <= stopAtTagDepth:
            break

        if s.inOpaqueElement():
            # An unclosed opaque element (e.g., opened inside a blockquote) must not
            # trigger Markdown block constructs until its closing tag is encountered.
            firstLineTrimmed = False
            lineNodes, i = parseInlineNodes(
                s,
                i,
                stopAtNewline=True,
                minIndent=minIndent,
                onMacroNodes=state.onMacroNodes,
            )
            nodes.extend(lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = False
            continue

        wasFirstLineTrimmed = firstLineTrimmed
        firstLineTrimmed = False
        prep = _prepareBlockLine(
            s,
            i,
            nodes,
            state=state,
            minIndent=minIndent,
            wasFirstLineTrimmed=wasFirstLineTrimmed,
            stopAt=stopAt,
            canStartParagraph=canStartParagraph,
            listContinuesUntil=listContinuesUntil,
            checkIndents=checkIndents,
        )
        listContinuesUntil = prep.listContinuesUntil
        canStartParagraph = prep.canStartParagraph
        if prep.stop:
            break
        if prep.line is None:
            i = prep.nextI
            continue
        line = prep.line

        rawKind, rawMatch = matchRawBlockStart(s, line.cStart, line.lineEnd, s.config)
        if line.underIndented and rawKind is not None:
            _reportUnderIndented(s, line.lineStart, line.lineEnd, minIndent)
        if rawKind == "heading":
            assert rawMatch is not None
            headingLineNum = s.line(line.lineStart)
            headingTag = f"h{len(rawMatch.group(1)) + 1}"
            s.openEls.autoCloseStartAt(s, headingTag, line.lineStart)
            s.openEls.verifyDirectParent(headingTag, lineLoc(s, headingLineNum))
            s.openEls.pushBlockParent(headingTag)
            try:
                headingContent, i = parseInlineNodes(
                    s,
                    rawMatch.end(),
                    stopAtNewline=True,
                    minIndent=minIndent,
                    onMacroNodes=state.onMacroNodes,
                )
            finally:
                s.openEls.popBlockParent()
            nodes.extend(buildSingleLineHeading(headingLineNum, rawMatch.group(1), headingContent))
            canStartParagraph = False
            continue
        if rawKind in ("rule", "dash-line"):
            s.openEls.autoCloseStartAt(s, "hr", line.lineStart)
            s.openEls.verifyDirectParent("hr", lineLoc(s, s.line(line.lineStart)))
            nodes.append(SelfClosedTag(tag="hr"))
            nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = nextLinePos(line.lineEnd, length)
            continue
        if rawKind == "equals-line":
            # Orphan `===` with no preceding text line is emitted bare.
            nodes.append(RawText.fromStream(s, line.bodyStart, line.lineEnd))
            nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = nextLinePos(line.lineEnd, length)
            continue
        if rawKind in ("bulleted", "numbered", "dt", "dd"):
            assert rawMatch is not None
            listNodes, i = parseList(
                s,
                rawKind,
                rawMatch,
                line.lineStart,
                baseIndent=line.absIndent,
                minTagDepth=minTagDepth,
                prevNodes=effectivePrevNodes(nodes, inheritedPrevNodes),
                indentChecker=state.indentChecker if checkIndents else None,
                onMacroNodes=state.onMacroNodes,
                outerStopAt=stopAt,
                parseSubBlocks=_makeListBodyParser(state, checkIndents=checkIndents),
            )
            nodes.extend(listNodes)
            canStartParagraph = False
            continue
        if rawKind == "blockquote":
            bqNodes, i = parseBlockquote(
                s,
                line.lineStart,
                line.cStart,
                line.lineEnd,
                bqAbsIndent=line.absIndent,
                state=state,
                stopAt=stopAt,
                checkIndents=checkIndents,
            )
            nodes.extend(bqNodes)
            canStartParagraph = False
            continue

        peek = html.peekHtmlTagAt(s, line.cStart, line.lineEnd)
        if peek is not None and not peek[0] and peek[1] == "bs-macro":
            macroNodes, i, producedContent = parseBlockBsMacro(
                s,
                line.lineStart,
                line.cStart,
                line.lineEnd,
                state=state,
                minIndent=minIndent,
                minTagDepth=minTagDepth,
                prevNodes=effectivePrevNodes(nodes, inheritedPrevNodes),
                underIndented=line.underIndented,
                checkIndents=checkIndents,
            )
            nodes.extend(macroNodes)
            canStartParagraph = not producedContent
            continue

        i, canStartParagraph, pending = _parseInlineBlockLine(
            s,
            line,
            nodes,
            state=state,
            minIndent=minIndent,
            stopAt=stopAt,
            stopAtTagDepth=stopAtTagDepth,
            canStartParagraph=canStartParagraph,
            checkIndents=checkIndents,
        )

    return nodes, i
