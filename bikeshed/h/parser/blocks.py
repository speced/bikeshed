from __future__ import annotations

import re
from dataclasses import dataclass, field

from ... import messages as m
from ... import t
from .. import elements
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    RawText,
    SafeText,
    SelfClosedTag,
    StartTag,
    TagNodeT,
    escapeAttr,
    isTag,
)
from .parser import (
    ACTUAL_NODE_START_SET,
    POSSIBLE_NODE_START_CHARS,
    POSSIBLE_NODE_START_RE,
    fencedStartRe,
    parseDoctype,
    parseNode,
)
from .result import isOk
from .stream import ParseConfig, Stream

_INLINE_LINE_STOP_RE = re.compile(f"[\n{re.escape(POSSIBLE_NODE_START_CHARS)}]")
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
_RULE_RE = re.compile(r"(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_NUMBERED_START_RE = re.compile(r"(-?\d+)\.(?:[ \t]+|$)")
_BULLETED_START_RE = re.compile(r"[*+-](?:[ \t]+|$)")
_DL_START_RE = re.compile(r"(:{1,2})(?:[ \t]+|$)")
_NOTE_START_RE = re.compile(r"(note[:,])(\s*)(.*)", re.I)
_ISSUE_PAREN_START_RE = re.compile(r"issue\(([^)]+)\):(.*)", re.I)
_MIXED_INDENT_TAB_AFTER_SPACE_RE = re.compile(r"(?:\t+ +\t)|( +\t)")
_HTML_TAG_PEEK_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9._-]*)")
_BLOCK_MATH_DISPLAY_RE = re.compile(r"""(?<![\w._:-])display\s*=\s*(?:"block"|'block'|block(?:\s|>|/|$))""", re.I)


@dataclass(slots=True)
class IndentChecker:
    """Records mixed-indentation lint issues during parsing for emission afterward."""

    indentChar: str
    opaqueTags: frozenset[str]
    issues: list[tuple[str | int, str]] = field(default_factory=list)
    _lastCheckedStream: Stream | None = None
    _lastCheckedStart: int = -1

    def _checkPart(self, part: str, lineNum: str | int) -> None:
        badIndentChar = " " if self.indentChar == "\t" else "\t"
        if part[0] == badIndentChar:
            if self.indentChar == " ":
                self.issues.append((lineNum, "Line starts with tabs, but document is space-indented"))
            else:
                self.issues.append((lineNum, "Line starts with spaces, but document is tab-indented"))
        if _MIXED_INDENT_TAB_AFTER_SPACE_RE.match(part):
            self.issues.append((lineNum, "Line's indent contains tabs after spaces."))

    def checkLine(self, s: Stream, lineStart: int) -> None:
        if lineStart >= s.length:
            return
        if s is self._lastCheckedStream and lineStart <= self._lastCheckedStart:
            return
        self._lastCheckedStream = s
        self._lastCheckedStart = lineStart
        ch = s.chars[lineStart]
        if ch not in (" ", "\t"):
            return
        lineEnd = s.chars.find("\n", lineStart)
        if lineEnd == -1:
            lineEnd = s.length
        part = s.chars[lineStart:lineEnd]
        lineNo = s.line(lineStart)
        lineNum: str | int = f"{lineNo} of {s.context}" if s.context else lineNo
        self._checkPart(part, lineNum)

    def checkNodes(self, nodes: t.Sequence[ParserNode], *, atLineStart: bool = True) -> None:
        opaqueDepth = 0
        for node in nodes:
            if opaqueDepth > 0:
                if isinstance(node, StartTag) and node.tag in self.opaqueTags:
                    opaqueDepth += 1
                elif isinstance(node, EndTag) and node.tag in self.opaqueTags:
                    opaqueDepth -= 1
                atLineStart = False
                continue
            if isinstance(node, RawText):
                parts = node.text.split("\n")
                for j, part in enumerate(parts):
                    if atLineStart and part:
                        partLineNo = node.line + j
                        lineNum: str | int = f"{partLineNo} of {node.context}" if node.context else partLineNo
                        self._checkPart(part, lineNum)
                    if j < len(parts) - 1:
                        atLineStart = True
                    elif part or (j == 0 and node.start != node.end):
                        atLineStart = False
            else:
                if isinstance(node, StartTag) and node.tag in self.opaqueTags:
                    opaqueDepth += 1
                atLineStart = False

    def emit(self) -> None:
        for lineNum, msg in self.issues:
            m.lint(msg, lineNum=lineNum)


@dataclass(slots=True)
class ListStop:
    baseIndent: int
    itemTypes: tuple[str, ...]
    parent: ListStop | None = None


@dataclass(slots=True)
class PendingLine:
    kind: str  # "htmlblock" | "blank"
    lineNodes: list[ParserNode]
    nextI: int


@dataclass(slots=True)
class BlockState:
    blockElements: set[str]
    blockquoteWarned: bool = False
    indentChecker: IndentChecker | None = None


def parseBlockStream(s: Stream, *, indentChecker: IndentChecker | None = None) -> list[ParserNode]:
    """Parses block-level Markdown and inline HTML/Bikeshed markup from `s` in one pass."""
    state = BlockState(
        blockElements={*s.config.blockElements, "if-wrapper"},
        indentChecker=indentChecker,
    )
    nodes, _ = parseBlocks(s, 0, state, checkIndents=indentChecker is not None)
    return nodes


def skipHws(chars: str, pos: int, end: int) -> int:
    while pos < end and chars[pos] in (" ", "\t"):
        pos += 1
    return pos


def findLineEnd(s: Stream, pos: int) -> int:
    lineEnd = s.chars.find("\n", pos)
    return s.length if lineEnd == -1 else lineEnd


def prefixCountAt(s: Stream, lineStart: int, indent: int) -> int:
    chars = s.chars
    length = s.length
    if lineStart >= length or chars[lineStart] not in (" ", "\t"):
        return 0
    i = lineStart
    prefixLen = 0
    spaces = " " * indent
    while i < length:
        if chars[i] == "\t":
            i += 1
            prefixLen += 1
        elif chars.startswith(spaces, i):
            i += indent
            prefixLen += 1
        else:
            break
    return prefixLen


def consumeIndentAt(s: Stream, lineStart: int, indent: int, numIndents: int) -> int | None:
    if numIndents == 0:
        return lineStart
    i = lineStart
    chars = s.chars
    length = s.length
    spaces = " " * indent
    for _ in range(numIndents):
        if i < length and chars[i] == "\t":
            i += 1
        elif chars.startswith(spaces, i):
            i += indent
        else:
            return None
    return i


def stripWsNodes(nodes: list[ParserNode]) -> list[ParserNode]:
    """Returns a copy of `nodes` with leading and trailing whitespace stripped from outer RawText nodes."""
    if not nodes:
        return []
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
    """Strips trailing whitespace in-place from the end of `nodes`."""
    while nodes and isinstance(nodes[-1], RawText):
        trimmed = nodes[-1].text.rstrip()
        if not trimmed:
            nodes.pop()
        else:
            if trimmed != nodes[-1].text:
                nodes[-1] = RawText(s=nodes[-1].s, start=nodes[-1].start, end=nodes[-1].end, text=trimmed)
            break


def sliceFirstText(nodes: list[ParserNode], offset: int) -> list[ParserNode]:
    """Returns a copy of `nodes` with the first `offset` characters removed from the leading RawText node."""
    if not nodes:
        return []
    first = nodes[0]
    assert isinstance(first, RawText)
    rest = first.text[offset:]
    if rest:
        return [RawText(s=first.s, start=first.start, end=first.end, text=rest), *nodes[1:]]
    return list(nodes[1:])


def isBlockMathTag(node: TagNodeT) -> bool:
    """Returns whether `node` is a `<math display=block>` tag (or its matching `</math>`)."""
    if isinstance(node, (StartTag, SelfClosedTag)):
        attrs = node.attrs
    elif node.startTag is not None:
        attrs = node.startTag.attrs
    else:
        return False
    if not attrs:
        return False
    return attrs.get("display", "inline") == "block"


def isInlineStart(node: ParserNode, blockElements: set[str]) -> bool:
    """Returns whether `node` is an inline tag (or non-tag) that can start a Markdown text line."""
    if isTag(node):
        tagname = node.tag
        if tagname == "math":
            return tagname not in blockElements and not isBlockMathTag(node)
        if tagname in elements.INLINE_ELEMENTS:
            return True
        if "-" in tagname and tagname not in blockElements:
            return True
        return False
    return True


def makeStartTag(tagName: str, lineNumber: int, attrs: dict[str, str] | None = None) -> StartTag:
    """Creates a StartTag with `bs-line-number` and escaped attributes."""
    safeAttrs: t.SafeAttrDict = {"bs-line-number": t.SafeAttrStr(str(lineNumber))}
    if attrs:
        for k, v in attrs.items():
            safeAttrs[k] = t.SafeAttrStr(escapeAttr(v))
    return StartTag(tag=tagName, attrs=safeAttrs)


def trySkipCommentOrDoctypeLine(
    s: Stream,
    lineStart: int,
    *,
    peekOnly: bool = False,
) -> int | None:
    """If `lineStart` is a standalone single Comment or Doctype line (possibly multi-line), returns the index after its trailing newline."""
    chars = s.chars
    length = s.length
    lineEnd = findLineEnd(s, lineStart)
    cStart = skipHws(chars, lineStart, lineEnd)
    if cStart >= lineEnd or chars[cStart] != "<":
        return None
    if chars.startswith("<!--", cStart):
        idx = cStart + 4
        while True:
            dashIdx = chars.find("--", idx)
            if dashIdx == -1:
                return None
            if chars.startswith("-->", dashIdx):
                afterComment = dashIdx + 3
                afterLineEnd = findLineEnd(s, afterComment)
                if skipHws(chars, afterComment, afterLineEnd) == afterLineEnd:
                    return afterLineEnd + 1 if afterLineEnd < length else length
                return None
            if chars.startswith("--!>", dashIdx):
                return None
            idx = dashIdx + 1
    if chars[cStart : cStart + 9].lower() == "<!doctype":
        gtIdx = chars.find(">", cStart + 9)
        if gtIdx == -1:
            return None
        afterDt = gtIdx + 1
        afterLineEnd = findLineEnd(s, afterDt)
        if skipHws(chars, afterDt, afterLineEnd) == afterLineEnd:
            if not peekOnly:
                parseDoctype(s, cStart)
            return afterLineEnd + 1 if afterLineEnd < length else length
    return None


def matchRawBlockStart(
    s: Stream,
    cStart: int,
    lineEnd: int,
    config: ParseConfig,
) -> tuple[str | None, re.Match[str] | None]:
    """Classifies a non-blank line's raw-text Markdown block opener at `cStart`."""
    chars = s.chars
    ch = chars[cStart]
    if config.markdownHeadings:
        if ch == "=" and _EQUALS_LINE_RE.match(chars, cStart, lineEnd):
            return "equals-line", None
        if ch == "-" and _DASH_LINE_RE.match(chars, cStart, lineEnd):
            return "dash-line", None
        if ch == "#" and (match := _HEADING_START_RE.match(chars, cStart, lineEnd)):
            return "heading", match
    if ch in ("*", "-", "_") and _RULE_RE.match(chars, cStart, lineEnd):
        return "rule", None
    if (ch == "-" or ch.isdigit()) and (match := _NUMBERED_START_RE.match(chars, cStart, lineEnd)):
        return "numbered", match
    if ch in ("*", "+", "-") and (match := _BULLETED_START_RE.match(chars, cStart, lineEnd)):
        return "bulleted", match
    if ch == ":" and (match := _DL_START_RE.match(chars, cStart, lineEnd)):
        return ("dt" if len(match.group(1)) == 1 else "dd"), match
    if config.markdownBlockquotes and ch == ">":
        return "blockquote", None
    return None, None


def matchLineItemType(s: Stream, lineStart: int, lineEnd: int, config: ParseConfig) -> str | None:
    """Returns the list-item marker type (`bulleted`, `numbered`, `dt`, `dd`) on `lineStart`, or None."""
    cStart = skipHws(s.chars, lineStart, lineEnd)
    if cStart >= lineEnd:
        return None
    kind, _ = matchRawBlockStart(s, cStart, lineEnd, config)
    if kind in ("bulleted", "numbered", "dt", "dd"):
        return kind
    return None


def isFencedCodeStart(s: Stream, cStart: int, lineEnd: int) -> bool:
    chars = s.chars
    if cStart >= lineEnd or chars[cStart] not in ("`", "~"):
        return False
    match = fencedStartRe.match(chars, cStart, lineEnd)
    if match is None:
        return False
    return "`" not in chars[match.end() : lineEnd]


def isBlockHtmlStart(s: Stream, cStart: int, lineEnd: int, blockElements: set[str]) -> bool:
    """Read-only peek: returns whether `cStart` begins with a block-level HTML tag (used for blockquote lazy continuation)."""
    chars = s.chars
    if cStart >= lineEnd or chars[cStart] != "<":
        return False
    match = _HTML_TAG_PEEK_RE.match(chars, cStart)
    if match is None:
        return False
    afterName = match.end()
    if afterName >= s.length:
        return False
    isClose = bool(match.group(1))
    nextCh = chars[afterName]
    if isClose:
        if nextCh != ">":
            return False
    else:
        if nextCh not in (" ", "\t", "\n", "\x0c", ">", "/", "["):
            return False
        # Avoid mistaking <org/repo#123> repository links for HTML tags.
        if nextCh == "/":
            gt = chars.find(">", afterName, lineEnd)
            if gt != -1 and "#" in chars[afterName:gt]:
                return False
    tagname = match.group(2).lower()
    if tagname == "l":
        return False
    if tagname == "math":
        if tagname in blockElements:
            return True
        if isClose:
            entry = s.openEls.getDeepestFromTag("math")
            if entry is not None and entry.startTag.attrs.get("display", "inline") == "block":
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


def shouldStopForList(s: Stream, lineStart: int, lineEnd: int, absIndent: int, stopAt: ListStop | None) -> bool:
    stop = stopAt
    while stop is not None:
        if absIndent < stop.baseIndent:
            return True
        if absIndent == stop.baseIndent:
            if matchLineItemType(s, lineStart, lineEnd, s.config) in stop.itemTypes:
                return True
        stop = stop.parent
    return False


def blankEndsList(s: Stream, blankLineEnd: int, stopAt: ListStop) -> bool:
    """Returns whether the blank line ending at `blankLineEnd` terminates `stopAt`."""
    chars = s.chars
    length = s.length
    j = blankLineEnd + 1 if blankLineEnd < length else length
    while j < length:
        if (nextAfterComment := trySkipCommentOrDoctypeLine(s, j, peekOnly=True)) is not None:
            j = nextAfterComment
            continue
        jEnd = findLineEnd(s, j)
        if skipHws(chars, j, jEnd) == jEnd:
            j = jEnd + 1 if jEnd < length else length
            continue
        nextAbsIndent = prefixCountAt(s, j, s.config.indent)
        if nextAbsIndent < stopAt.baseIndent:
            return True
        if nextAbsIndent > stopAt.baseIndent:
            return False
        itemType = matchLineItemType(s, j, jEnd, s.config)
        return itemType not in stopAt.itemTypes
    return True


def peekSetextUnderline(
    s: Stream,
    start: int,
    minIndent: int,
    stopAt: ListStop | None,
) -> tuple[str, int] | None:
    """Peeks past comment-only lines for a Setext underline (`===` or `---`), returning `(tagName, nextI)`."""
    if not s.config.markdownHeadings:
        return None
    chars = s.chars
    length = s.length
    j = start
    while j < length:
        if (nextAfterComment := trySkipCommentOrDoctypeLine(s, j, peekOnly=True)) is not None:
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
        nextI = jEnd + 1 if jEnd < length else length
        if chars[cStart] == "=" and _EQUALS_LINE_RE.match(chars, cStart, jEnd):
            return "h2", nextI
        if chars[cStart] == "-" and _DASH_LINE_RE.match(chars, cStart, jEnd):
            return "h3", nextI
        return None
    return None


def stripIndentAfterNewlines(text: str, indent: int, numIndents: int) -> str:
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


def parseInlineLine(
    s: Stream,
    start: int,
    state: BlockState,
    *,
    minIndent: int = 0,
) -> tuple[list[ParserNode], int]:
    """Parses one logical line of HTML/inline Bikeshed markup starting at `start`.

    Stops at (and consumes) the first `\\n` encountered outside any multi-line
    construct (tags, comments, autolinks, code spans, fenced blocks, em-dashes)
    and outside any open opaque element (`s.inOpaqueElement()`).
    """
    nodes: list[ParserNode] = []
    lastNode: ParserNode | None = None
    heldLast = False
    heldCanMerge = False

    def emitOne(node: ParserNode) -> None:
        nonlocal lastNode, heldLast, heldCanMerge
        if isinstance(node, SafeText):
            node = RawText.fromSafeText(node)
        if isinstance(node, RawText):
            if minIndent > 0 and "\n" in node.text and node.s is s and not s.inOpaqueElement():
                node.text = stripIndentAfterNewlines(node.text, s.config.indent, minIndent)
            if not s.config.rawHtml and not s.inOpaqueElement():
                node.curlifyApostrophes(lastNode)
            nodeCanMerge = node.s is s and node.text.count("\n") == node.height
            if (
                heldLast
                and heldCanMerge
                and nodeCanMerge
                and isinstance(lastNode, RawText)
                and lastNode.end == node.start
            ):
                lastNode.text += node.text
                lastNode.end = node.end
            else:
                if heldLast:
                    assert lastNode is not None
                    nodes.append(lastNode)
                lastNode = node
                heldLast = True
                heldCanMerge = nodeCanMerge
        else:
            if heldLast:
                assert lastNode is not None
                nodes.append(lastNode)
            nodes.append(node)
            lastNode = node
            heldLast = False
            heldCanMerge = False

    i = start
    end = s.length
    chars = s.chars
    while i < end:
        ch = chars[i]
        if ch == "\n" and not s.inOpaqueElement():
            i += 1
            break
        if ch in ACTUAL_NODE_START_SET:
            res = parseNode(s, i)
            if isOk(res):
                val, nextI, _ = res
                wasOpaque = s.inOpaqueElement()
                s.observeResult(res)
                if isinstance(val, list):
                    if (
                        state.indentChecker is not None
                        and not wasOpaque
                        and val
                        and val[0].s is not None
                        and val[0].s is not s
                    ):
                        state.indentChecker.checkNodes(
                            val,
                            atLineStart=(s.col(i) == 1),
                        )
                    for subNode in val:
                        emitOne(subNode)
                else:
                    emitOne(val)
                i = nextI
                continue
        if s.inOpaqueElement():
            match = POSSIBLE_NODE_START_RE.search(chars, i + 1)
        else:
            match = _INLINE_LINE_STOP_RE.search(chars, i + 1)
        nextI = match.start() if match else end
        emitOne(RawText.fromStream(s, i, nextI))
        i = nextI

    if heldLast:
        assert lastNode is not None
        nodes.append(lastNode)
    return nodes, i


def extractSingleLineHeadingId(nodes: list[ParserNode], hashes: str) -> str | None:
    """Extracts a trailing `{#id}` from `nodes`, stripping closing `#`s and `{#id}` in-place when matched."""
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
    checkIndents: bool,
) -> tuple[list[ParserNode], int, PendingLine | None]:
    """Builds a `<p>` block starting with `firstStrippedNodes` and consumes continuation lines."""
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
        if checkIndents and state.indentChecker is not None and not s.inOpaqueElement():
            state.indentChecker.checkLine(s, i)
        if (nextAfterComment := trySkipCommentOrDoctypeLine(s, i)) is not None:
            i = nextAfterComment
            continue
        lineEnd = findLineEnd(s, i)
        if skipHws(chars, i, lineEnd) == lineEnd:
            break
        absIndent = prefixCountAt(s, i, indent)
        if shouldStopForList(s, i, lineEnd, absIndent, stopAt):
            break
        underIndented = False
        if absIndent < minIndent:
            # Insufficiently indented line inside a list item; only consume if
            # initialRelIndent == 0 and it's a plain text line (otherwise let parseBlocks handle it).
            if initialRelIndent > 0:
                break
            cStart = skipHws(chars, i, lineEnd)
            rawKind, _ = matchRawBlockStart(s, cStart, lineEnd, s.config)
            if rawKind is not None:
                break
            underIndented = True
            bodyStart = i
        else:
            relIndent = absIndent - minIndent
            if relIndent < initialRelIndent:
                break
            consumed = consumeIndentAt(s, i, indent, minIndent)
            assert consumed is not None
            bodyStart = consumed
            cStart = skipHws(chars, bodyStart, lineEnd)
            rawKind, _ = matchRawBlockStart(s, cStart, lineEnd, s.config)
            if rawKind is not None:
                break

        lineNodes, nextI = parseInlineLine(s, bodyStart, state, minIndent=minIndent)
        stripped = stripWsNodes(lineNodes)
        if not stripped:
            pending = PendingLine(kind="blank", lineNodes=lineNodes, nextI=nextI)
            break
        if len(stripped) == 1 and isinstance(stripped[0], (Comment, Doctype)):
            i = nextI
            continue
        if underIndented:
            m.die(
                f'Line {s.line(i)} isn\'t indented enough (needs {minIndent} indent{"" if minIndent == 1 else "s"}) to be valid Markdown:\n"{chars[i:lineEnd]}"',
            )
        if not isInlineStart(stripped[0], state.blockElements):
            pending = PendingLine(kind="htmlblock", lineNodes=lineNodes, nextI=nextI)
            break
        contentNodes.append(RawText(text="\n"))
        contentNodes.extend(lineNodes)
        i = nextI

    rstripNodes(contentNodes)
    return [*prefixNodes, *contentNodes, *endTags, RawText(text="\n")], i, pending


def matchFenceAt(s: Stream, contentStart: int, lineEnd: int) -> tuple[int, str, bool, bool] | None:
    """If `contentStart` (after stripping nested `>` markers) starts with a code fence, returns `(gtDepth, fence, isOpener, isCloser)`."""
    chars = s.chars
    pos = skipHws(chars, contentStart, lineEnd)
    gtDepth = 0
    while pos < lineEnd and chars[pos] == ">":
        gtDepth += 1
        pos = skipHws(chars, pos + 1, lineEnd)
    if pos >= lineEnd or chars[pos] not in ("`", "~"):
        return None
    match = fencedStartRe.match(chars, pos, lineEnd)
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
    """Returns whether a blockquote line's stripped content leaves a paragraph open for lazy continuation.

    Returns `None` for single-line standalone comments/doctypes (which are transparent).
    """
    chars = s.chars
    pos = skipHws(chars, contentStart, lineEnd)
    while pos < lineEnd and chars[pos] == ">":
        pos = skipHws(chars, pos + 1, lineEnd)
    if pos >= lineEnd:
        return False
    afterComment = trySkipCommentOrDoctypeLine(s, pos, peekOnly=True)
    if afterComment is not None:
        lineNext = lineEnd + 1 if lineEnd < s.length else s.length
        if afterComment == lineNext:
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
    """Collects consecutive `>`-prefixed (and lazy-continuation) lines and parses them recursively in a child Stream."""
    chars = s.chars
    length = s.length
    indent = s.config.indent
    lineNum = s.line(lineStart)

    if not state.blockquoteWarned and not s.config.markdownBlockquotesExplicit:
        state.blockquoteWarned = True
        m.warn(
            f"Line {lineNum} looks like the start of a markdown blockquote.\nIf this is intended, please set `Markup Shorthands: markdown-blockquotes yes`; if not, set it to `no`.\nSee https://speced.github.io/bikeshed/#md-blockquote for details.",
        )

    openFence: tuple[int, str, int] | None = None
    canLazyContinue = False

    def observeBqContent(contentStart: int, contentEnd: int) -> None:
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

    afterGt = cStart + 1
    if afterGt < lineEnd and chars[afterGt] in (" ", "\t"):
        afterGt += 1
    physLineStart = s.currentLineStart(cStart)
    subLines: list[str] = [chars[afterGt:lineEnd]]
    colOffsets: list[int] = [(afterGt - physLineStart) + s.colOffset(s.lineIndex(cStart))]
    observeBqContent(afterGt, lineEnd)

    i = lineEnd + 1 if lineEnd < length else length
    while i < length:
        curLineStart = i
        curLineEnd = findLineEnd(s, curLineStart)
        curCStart = skipHws(chars, curLineStart, curLineEnd)

        # Blank line without `>` always terminates the blockquote.
        if curCStart == curLineEnd:
            break

        # Handle comment-only lines without `>` inside a blockquote: preserve their line count
        # if the blockquote continues afterward, otherwise stop before them.
        if chars[curCStart] != ">" and (afterComment := trySkipCommentOrDoctypeLine(s, curLineStart, peekOnly=True)):
            # Peek past consecutive comment-only lines to see if the blockquote continues.
            peekI = afterComment
            while peekI < length:
                if (nextC := trySkipCommentOrDoctypeLine(s, peekI, peekOnly=True)) is not None:
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
                        elif canLazyContinue:
                            pKind, _ = matchRawBlockStart(s, pCStart, pEnd, s.config)
                            if (
                                pKind is None
                                and not isFencedCodeStart(s, pCStart, pEnd)
                                and not isBlockHtmlStart(s, pCStart, pEnd, state.blockElements)
                            ):
                                continues = True
            if not continues:
                break
            curCommentI = curLineStart
            while curCommentI < peekI:
                if checkIndents and state.indentChecker is not None:
                    state.indentChecker.checkLine(s, curCommentI)
                nextCommentI = trySkipCommentOrDoctypeLine(s, curCommentI, peekOnly=True)
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
            afterGt = curCStart + 1
            if afterGt < curLineEnd and chars[afterGt] in (" ", "\t"):
                afterGt += 1
            subLines.append(chars[afterGt:curLineEnd])
            colOffsets.append((afterGt - curLineStart) + s.colOffset(s.lineIndex(curLineStart)))
            observeBqContent(afterGt, curLineEnd)
            i = curLineEnd + 1 if curLineEnd < length else length
            continue

        # Potential lazy continuation line: only allowed after an open paragraph
        # (CommonMark §5.1) and only if it's a plain text line.
        if not canLazyContinue:
            break
        rawKind, _ = matchRawBlockStart(s, curCStart, curLineEnd, s.config)
        if rawKind is not None:
            break
        if isFencedCodeStart(s, curCStart, curLineEnd):
            break
        if isBlockHtmlStart(s, curCStart, curLineEnd, state.blockElements):
            break

        if checkIndents and state.indentChecker is not None:
            state.indentChecker.checkLine(s, curLineStart)
        subLines.append(chars[curCStart:curLineEnd])
        colOffsets.append((curCStart - curLineStart) + s.colOffset(s.lineIndex(curLineStart)))
        i = curLineEnd + 1 if curLineEnd < length else length

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
    innerNodes, _ = parseBlocks(subStream, 0, state, checkIndents=False)
    return [
        makeStartTag("blockquote", lineNum),
        *innerNodes,
        EndTag(tag="blockquote"),
        RawText(text="\n"),
    ], i


def parseList(
    s: Stream,
    firstKind: str,
    firstMatch: re.Match[str],
    firstLineStart: int,
    *,
    baseIndent: int,
    state: BlockState,
    outerStopAt: ListStop | None,
    checkIndents: bool,
) -> tuple[list[ParserNode], int]:
    """Parses a bulleted, numbered, or definition list at `baseIndent` using streaming indentation frames."""
    if firstKind == "bulleted":
        itemTypes: tuple[str, ...] = ("bulleted",)
        listTag = "ul"
        listAttrs: dict[str, str] = {"bs-md-list": ""}
    elif firstKind == "numbered":
        itemTypes = ("numbered",)
        listTag = "ol"
        startNum = int(firstMatch.group(1))
        listAttrs = {"bs-md-list": ""} if startNum == 1 else {"bs-md-list": "", "start": str(startNum)}
    else:
        itemTypes = ("dt", "dd")
        listTag = "dl"
        listAttrs = {"bs-md-list": ""}

    listLineNum = s.line(firstLineStart)
    nodes: list[ParserNode] = [makeStartTag(listTag, listLineNum, listAttrs)]
    listStop = ListStop(baseIndent=baseIndent, itemTypes=itemTypes, parent=outerStopAt)
    itemMinIndent = baseIndent + 1
    chars = s.chars
    length = s.length
    indent = s.config.indent

    curKind: str | None = firstKind
    curMatch: re.Match[str] | None = firstMatch
    curLineNum = listLineNum
    i = firstLineStart

    while True:
        assert curKind is not None and curMatch is not None
        itemTag = "li" if curKind in ("bulleted", "numbered") else curKind
        nodes.append(makeStartTag(itemTag, curLineNum, {"data-md": ""}))
        afterMarker = curMatch.end()
        itemNodes, i = parseBlocks(
            s,
            afterMarker,
            state,
            minIndent=itemMinIndent,
            firstLineTrimmed=True,
            stopAt=listStop,
            checkIndents=checkIndents,
        )
        nodes.extend(itemNodes)
        if curKind != "bulleted":
            nodes.append(EndTag(tag=itemTag))

        # `parseBlocks` returns only at EOF, a list-ending blank line, or a `shouldStopForList` line.
        if i >= length:
            break
        nextEnd = findLineEnd(s, i)
        nextCStart = skipHws(chars, i, nextEnd)
        if nextCStart == nextEnd:
            break
        nextAbsIndent = prefixCountAt(s, i, indent)
        if nextAbsIndent != baseIndent:
            break
        nextKind, nextMatch = matchRawBlockStart(s, nextCStart, nextEnd, s.config)
        if nextKind not in itemTypes or nextMatch is None:
            break
        curKind = nextKind
        curMatch = nextMatch
        curLineNum = s.line(i)

    nodes.append(EndTag(tag=listTag))
    return nodes, i


def parseBlocks(
    s: Stream,
    start: int,
    state: BlockState,
    *,
    minIndent: int = 0,
    firstLineTrimmed: bool = False,
    stopAt: ListStop | None = None,
    checkIndents: bool = False,
) -> tuple[list[ParserNode], int]:
    """Parses block-level Markdown + HTML/inline Bikeshed markup from `s` starting at `start`."""
    nodes: list[ParserNode] = []
    i = start
    chars = s.chars
    length = s.length
    indent = s.config.indent
    canStartParagraph = True
    pending: PendingLine | None = None

    while i < length or pending is not None:
        if pending is not None:
            p = pending
            pending = None
            i = p.nextI
            nodes.extend(p.lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = p.kind == "blank"
            continue

        if s.inOpaqueElement():
            # An unclosed opaque element (e.g., opened inside a blockquote) must not
            # trigger Markdown block constructs until its closing tag is encountered.
            if firstLineTrimmed:
                firstLineTrimmed = False
            lineNodes, nextI = parseInlineLine(s, i, state, minIndent=minIndent)
            nodes.extend(lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = nextI
            continue

        underIndented = False
        if firstLineTrimmed:
            firstLineTrimmed = False
            lineStart = i
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
                canStartParagraph = True
                i = lineEnd + 1 if lineEnd < length else length
                continue
            if (nextAfterComment := trySkipCommentOrDoctypeLine(s, bodyStart)) is not None:
                i = nextAfterComment
                continue
        else:
            lineStart = i
            if checkIndents and state.indentChecker is not None:
                state.indentChecker.checkLine(s, lineStart)
            if (nextAfterComment := trySkipCommentOrDoctypeLine(s, lineStart)) is not None:
                i = nextAfterComment
                continue
            lineEnd = findLineEnd(s, lineStart)
            if skipHws(chars, lineStart, lineEnd) == lineEnd:
                if stopAt is not None and blankEndsList(s, lineEnd, stopAt):
                    break
                if lineStart < lineEnd:
                    nodes.append(RawText.fromStream(s, lineStart, lineEnd))
                nodes.append(RawText(text="\n"))
                canStartParagraph = True
                i = lineEnd + 1 if lineEnd < length else length
                continue
            absIndent = prefixCountAt(s, lineStart, indent)
            if shouldStopForList(s, lineStart, lineEnd, absIndent, stopAt):
                break
            if absIndent < minIndent:
                underIndented = True
                bodyStart = lineStart
                relIndent = 0
            else:
                consumed = consumeIndentAt(s, lineStart, indent, minIndent)
                assert consumed is not None
                bodyStart = consumed
                relIndent = absIndent - minIndent
            cStart = skipHws(chars, bodyStart, lineEnd)

        rawKind, rawMatch = matchRawBlockStart(s, cStart, lineEnd, s.config)
        if underIndented and rawKind is not None:
            m.die(
                f'Line {s.line(lineStart)} isn\'t indented enough (needs {minIndent} indent{"" if minIndent == 1 else "s"}) to be valid Markdown:\n"{chars[lineStart:lineEnd]}"',
            )
        if rawKind == "heading":
            assert rawMatch is not None
            headingLineNum = s.line(lineStart)
            headingContent, i = parseInlineLine(
                s,
                rawMatch.end(),
                state,
                minIndent=minIndent,
            )
            nodes.extend(buildSingleLineHeading(headingLineNum, rawMatch.group(1), headingContent))
            canStartParagraph = False
            continue
        if rawKind in ("rule", "dash-line"):
            nodes.append(SelfClosedTag(tag="hr"))
            nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = lineEnd + 1 if lineEnd < length else length
            continue
        if rawKind == "equals-line":
            # Orphan `===` with no preceding text line is emitted bare.
            nodes.append(RawText.fromStream(s, bodyStart, lineEnd))
            nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = lineEnd + 1 if lineEnd < length else length
            continue
        if rawKind in ("bulleted", "numbered", "dt", "dd"):
            assert rawMatch is not None
            listNodes, i = parseList(
                s,
                rawKind,
                rawMatch,
                lineStart,
                baseIndent=absIndent,
                state=state,
                outerStopAt=stopAt,
                checkIndents=checkIndents,
            )
            nodes.extend(listNodes)
            canStartParagraph = False
            continue
        if rawKind == "blockquote":
            bqNodes, i = parseBlockquote(
                s,
                lineStart,
                cStart,
                lineEnd,
                bqAbsIndent=absIndent,
                state=state,
                stopAt=stopAt,
                checkIndents=checkIndents,
            )
            nodes.extend(bqNodes)
            canStartParagraph = False
            continue

        # Not a raw Markdown block opener: parse the logical line in HTML/inline mode.
        lineNum = s.line(lineStart)
        lineNodes, nextI = parseInlineLine(s, bodyStart, state, minIndent=minIndent)
        stripped = stripWsNodes(lineNodes)
        if not stripped:
            # e.g. <pre class=metadata> stripped to empty, or empty optional macro.
            nodes.extend(lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = True
            i = nextI
            continue
        if len(stripped) == 1 and isinstance(stripped[0], (Comment, Doctype)):
            i = nextI
            continue
        if underIndented:
            m.die(
                f'Line {s.line(lineStart)} isn\'t indented enough (needs {minIndent} indent{"" if minIndent == 1 else "s"}) to be valid Markdown:\n"{chars[lineStart:lineEnd]}"',
            )
        if not isInlineStart(stripped[0], state.blockElements):
            nodes.extend(lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = nextI
            continue

        # Plain text line: check Setext heading first, then paragraph vs bare text.
        if (setext := peekSetextUnderline(s, nextI, minIndent, stopAt)) is not None:
            headingTag, afterUnderline = setext
            # Skip/validate any intervening comment/doctype lines and check indent on underline.
            scanI = nextI
            while scanI < afterUnderline:
                if checkIndents and state.indentChecker is not None and not s.inOpaqueElement():
                    state.indentChecker.checkLine(s, scanI)
                if (afterC := trySkipCommentOrDoctypeLine(s, scanI)) is not None:
                    scanI = afterC
                    continue
                break
            nodes.extend(buildMultiLineHeading(lineNum, headingTag, stripped))
            canStartParagraph = False
            i = afterUnderline
            continue

        if canStartParagraph:
            paraNodes, i, pending = parseParagraph(
                s,
                lineNum,
                stripped,
                initialRelIndent=relIndent,
                startAfterLine1=nextI,
                state=state,
                minIndent=minIndent,
                stopAt=stopAt,
                checkIndents=checkIndents,
            )
            nodes.extend(paraNodes)
            canStartParagraph = False
        else:
            nodes.extend(lineNodes)
            if not s.inOpaqueElement():
                nodes.append(RawText(text="\n"))
            canStartParagraph = False
            i = nextI

    return nodes, i
