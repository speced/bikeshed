from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .. import constants, h, t
from .. import messages as m

_EQUALS_LINE_RE = re.compile(r"={3,}$")
_DASH_LINE_RE = re.compile(r"-{3,}$")
_HEADING_START_RE = re.compile(r"(#{1,5})\s+(.*)")
_HEADING_ID_RE = re.compile(r"\{#([^ }]+)\}$")
_HEADING_CLOSING_RES = {
    "#": re.compile(r"#\s*\{#[^ }]+\}$"),
    "##": re.compile(r"##\s*\{#[^ }]+\}$"),
    "###": re.compile(r"###\s*\{#[^ }]+\}$"),
    "####": re.compile(r"####\s*\{#[^ }]+\}$"),
    "#####": re.compile(r"#####\s*\{#[^ }]+\}$"),
}
_MULTILINE_HEADING_ID_RE = re.compile(r"\s*\{\s*#([^ }]+)\s*\}\s*$")
_RULE_RE = re.compile(r"(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_NUMBERED_START_RE = re.compile(r"(-?\d+)\.\s+(.*)")
_NUMBERED_EMPTY_RE = re.compile(r"(-?\d+)\.$")
_BULLETED_START_RE = re.compile(r"[*+-]\s+(.*)")
_BULLETED_EMPTY_RE = re.compile(r"[*+-]$")
_DL_START_RE = re.compile(r"(:{1,2})\s+(.*)")
_DL_EMPTY_RE = re.compile(r"(:{1,2})$")
_BQ_START_RE = re.compile(f"[>{constants.bqChar}]\\s?(.*)")
_BQ_INNER_LINE_RE = re.compile(r"\n[ \t]*> ?")
_BQ_LINE_START_RE = re.compile(r"[ \t]*> ?")
_NOTE_START_RE = re.compile(r"(note[:,])(\s*)(.*)", re.I)
_ISSUE_PAREN_START_RE = re.compile(r"issue\(([^)]+)\):(.*)", re.I)


@dataclass(slots=True)
class MarkdownConfig:
    indent: int
    headings: bool = True
    blockquotes: bool = True
    explicitBlockquotes: bool = True
    blockElements: list[str] = field(default_factory=list)
    opaqueElements: frozenset[str] = h.DEFAULT_OPAQUE_ELEMENTS

    @staticmethod
    def fromSpec(doc: t.SpecT) -> MarkdownConfig:
        return MarkdownConfig(
            indent=doc.md.indent,
            headings=True,
            blockquotes=not doc.md.markupShorthands.explicitFalse("markdown-blockquotes"),
            explicitBlockquotes=doc.md.markupShorthands.explicitTrue("markdown-blockquotes"),
            blockElements=doc.md.blockElements + doc.md.opaqueElements,
            opaqueElements=h.DEFAULT_OPAQUE_ELEMENTS | frozenset(doc.md.opaqueElements),
        )


@dataclass(slots=True)
class NodeLine:
    i: int
    nodes: list[h.ParserNode]


@dataclass(slots=True)
class Token:
    type: str
    prefixlen: int | float = 0
    line: NodeLine = field(default_factory=lambda: NodeLine(-1, []))
    nodes: list[h.ParserNode] = field(default_factory=list)
    level: int = 0
    id: str | None = None
    num: int = 1


def parse(
    nodes: t.Iterable[h.ParserNode],
    config: MarkdownConfig,
) -> list[h.ParserNode]:
    """Parses block-level Markdown constructs in a stream of ParserNodes."""
    lines = splitNodesIntoLines(nodes, config.opaqueElements)
    return parseLines(lines, config)


def parseLines(
    lines: t.Iterable[NodeLine],
    config: MarkdownConfig,
) -> list[h.ParserNode]:
    """Tokenizes and parses an iterable of NodeLines into block-level ParserNodes."""
    tokens = tokenizeLines(lines, config)
    return parseTokens(tokens, config)


def splitNodesIntoLines(
    nodes: t.Iterable[h.ParserNode],
    opaqueElements: t.Collection[str] = h.DEFAULT_OPAQUE_ELEMENTS,
) -> t.Generator[NodeLine, None, None]:
    """Splits a flat stream of ParserNodes on newlines, yielding per-line NodeLines with source line numbers."""
    curNodes: list[h.ParserNode] = []
    lineNo = 1
    lineStartNo = 1
    hadNodes = False
    opaqueDepth = 0
    for node in nodes:
        hadNodes = True
        isRootStream = node.s is not None and node.s.depth == 1
        if opaqueDepth > 0:
            if isinstance(node, h.StartTag) and node.tag in opaqueElements:
                opaqueDepth += 1
            elif isinstance(node, h.EndTag) and node.tag in opaqueElements:
                opaqueDepth -= 1
            curNodes.append(node)
            if isRootStream:
                lineNo = node.endLine
            continue
        if isinstance(node, h.RawText):
            if "\n" not in node.text:
                if node.text:
                    if not curNodes and isRootStream:
                        lineStartNo = node.line
                    if curNodes and isinstance(curNodes[-1], h.RawText):
                        curNodes[-1].text += node.text
                    else:
                        curNodes.append(
                            h.RawText(s=node.s, start=node.start, end=node.end, text=node.text),
                        )
                if isRootStream:
                    lineNo = node.endLine
                    if not curNodes:
                        lineStartNo = lineNo
            else:
                parts = node.text.split("\n")
                for j, part in enumerate(parts):
                    if part:
                        if not curNodes and isRootStream:
                            lineStartNo = node.line + j
                        if curNodes and isinstance(curNodes[-1], h.RawText):
                            curNodes[-1].text += part
                        else:
                            curNodes.append(
                                h.RawText(s=node.s, start=node.start, end=node.end, text=part),
                            )
                    if j < len(parts) - 1:
                        if not curNodes and isRootStream:
                            lineStartNo = node.line + j
                        yield NodeLine(lineStartNo, curNodes)
                        curNodes = []
                        if isRootStream:
                            lineNo = node.line + j + 1
                        elif node.s is None:
                            lineNo += 1
                        lineStartNo = lineNo
                if isRootStream:
                    lineNo = node.endLine
                    if not curNodes:
                        lineStartNo = lineNo
        else:
            # Non-text nodes (tags, comments, datablocks) and opaque elements stay intact
            # on the current NodeLine even if they span multiple lines; lineStartNo keeps
            # the current line's starting line number while lineNo advances to node.endLine.
            if not curNodes and isRootStream:
                lineStartNo = node.line
            if isinstance(node, h.StartTag) and node.tag in opaqueElements:
                opaqueDepth += 1
            curNodes.append(node)
            if isRootStream:
                lineNo = node.endLine
    if hadNodes:
        yield NodeLine(lineStartNo, curNodes)


def stripWsNodes(nodes: list[h.ParserNode]) -> list[h.ParserNode]:
    """Returns a copy of `nodes` with leading and trailing whitespace stripped from outer RawText nodes."""
    if not nodes:
        return []
    res = list(nodes)
    while res and isinstance(res[0], h.RawText):
        s = res[0].text.lstrip()
        if not s:
            res.pop(0)
        else:
            if s != res[0].text:
                res[0] = h.RawText(s=res[0].s, start=res[0].start, end=res[0].end, text=s)
            break
    while res and isinstance(res[-1], h.RawText):
        s = res[-1].text.rstrip()
        if not s:
            res.pop()
        else:
            if s != res[-1].text:
                res[-1] = h.RawText(s=res[-1].s, start=res[-1].start, end=res[-1].end, text=s)
            break
    return res


def rstripNodes(nodes: list[h.ParserNode]) -> None:
    """Strips trailing whitespace in-place from the end of `nodes`."""
    while nodes and isinstance(nodes[-1], h.RawText):
        s = nodes[-1].text.rstrip()
        if not s:
            nodes.pop()
        else:
            if s != nodes[-1].text:
                nodes[-1] = h.RawText(s=nodes[-1].s, start=nodes[-1].start, end=nodes[-1].end, text=s)
            break


def sliceFirstText(nodes: list[h.ParserNode], offset: int) -> list[h.ParserNode]:
    """Returns a copy of `nodes` with the first `offset` characters removed from the leading RawText node."""
    if not nodes:
        return []
    first = nodes[0]
    assert isinstance(first, h.RawText)
    rest = first.text[offset:]
    if rest:
        return [h.RawText(s=first.s, start=first.start, end=first.end, text=rest), *nodes[1:]]
    return list(nodes[1:])


def isBlockMathTag(node: h.TagNodeT) -> bool:
    """Returns whether `node` is a `<math display=block>` tag (or its matching `</math>`)."""
    if isinstance(node, (h.StartTag, h.SelfClosedTag)):
        attrs = node.attrs
    elif node.startTag is not None:
        attrs = node.startTag.attrs
    else:
        return False
    if not attrs:
        return False
    return attrs.get("display", "inline") == "block"


def isInlineStart(node: h.ParserNode, blockElements: set[str]) -> bool:
    """Returns whether `node` is an inline tag (or non-tag) that can start a Markdown text line."""
    # Custom elements are assumed to be inline, unless they're passed in config.blockElements.
    # Non-custom elements are assumed to be block, unless they're on h.INLINE_ELEMENTS.
    # <math> is inline by default (and when display=inline), but block when display=block.
    # Inline elements are allowed to start a "normal" line of text, so will trigger paragraphs/etc.
    # Block elements will instead be an HTML line and will close paragraphs, etc.
    if h.isTag(node):
        tagname = node.tag
        if tagname == "math":
            return tagname not in blockElements and not isBlockMathTag(node)
        if tagname in h.INLINE_ELEMENTS:
            return True
        if "-" in tagname and tagname not in blockElements:
            return True
        return False
    return True


def parseSingleLineHeadingNodes(
    strippedNodes: list[h.ParserNode],
    match: re.Match[str],
) -> tuple[list[h.ParserNode], str | None]:
    """Extracts the heading content nodes and optional `{#id}` from a single-line `#` heading."""
    hashes = match.group(1)
    nodes = sliceFirstText(strippedNodes, match.start(2))
    headingId = extractSingleLineHeadingId(nodes, hashes)
    return stripWsNodes(nodes), headingId


def extractSingleLineHeadingId(nodes: list[h.ParserNode], hashes: str) -> str | None:
    """Extracts a trailing `{#id}` from `nodes`, stripping closing `#`s and `{#id}` in-place when matched."""
    if not nodes or not isinstance(nodes[-1], h.RawText):
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
        nodes[-1] = h.RawText(
            s=lastNode.s,
            start=lastNode.start,
            end=lastNode.end,
            text=prefix,
        )
    else:
        nodes.pop()
    return headingId


def tokenizeLines(lines: t.Iterable[NodeLine], config: MarkdownConfig) -> list[Token]:
    """Classifies each NodeLine into a block-level Markdown Token."""
    blockElements = {*config.blockElements, "if-wrapper"}

    tokens: list[Token] = []
    blockquoteWarned = False

    for line in lines:
        strippedNodes = stripWsNodes(line.nodes)
        # Skip lines that are entirely a single comment or doctype.
        if len(strippedNodes) == 1 and isinstance(strippedNodes[0], (h.Comment, h.Doctype)):
            continue

        if not strippedNodes:
            tokens.append(Token(type="blank", prefixlen=float("inf"), line=line))
            continue

        firstNode = strippedNodes[0]
        token: Token

        if not isinstance(firstNode, h.RawText):
            if isInlineStart(firstNode, blockElements):
                token = Token(type="text", nodes=strippedNodes)
            else:
                token = Token(type="htmlblock")
        else:
            firstText = firstNode.text
            singleRaw = len(strippedNodes) == 1

            if config.headings and singleRaw and _EQUALS_LINE_RE.match(firstText):
                token = Token(type="equals-line")
            elif config.headings and singleRaw and _DASH_LINE_RE.match(firstText):
                token = Token(type="dash-line")
            elif (
                config.headings
                and (match := _HEADING_START_RE.match(firstText))
                and (not singleRaw or bool(match.group(2)))
            ):
                level = len(match.group(1)) + 1
                headingNodes, headingId = parseSingleLineHeadingNodes(strippedNodes, match)
                token = Token(type="heading", nodes=headingNodes, level=level, id=headingId)
            elif singleRaw and _RULE_RE.match(firstText):
                token = Token(type="rule")
            elif match := _NUMBERED_START_RE.match(firstText):
                token = Token(
                    type="numbered",
                    nodes=sliceFirstText(strippedNodes, match.start(2)),
                    num=int(match.group(1)),
                )
            elif singleRaw and (match := _NUMBERED_EMPTY_RE.match(firstText)):
                token = Token(type="numbered", nodes=[], num=int(match.group(1)))
            elif match := _BULLETED_START_RE.match(firstText):
                token = Token(type="bulleted", nodes=sliceFirstText(strippedNodes, match.start(1)))
            elif singleRaw and _BULLETED_EMPTY_RE.match(firstText):
                token = Token(type="bulleted", nodes=[])
            elif match := _DL_START_RE.match(firstText):
                tagtype = "dt" if len(match.group(1)) == 1 else "dd"
                token = Token(type=tagtype, nodes=sliceFirstText(strippedNodes, match.start(2)))
            elif singleRaw and (match := _DL_EMPTY_RE.match(firstText)):
                tagtype = "dt" if len(match.group(1)) == 1 else "dd"
                token = Token(type=tagtype, nodes=[])
            elif config.blockquotes and (firstText.startswith(">") or firstText.startswith(constants.bqChar)):
                if not blockquoteWarned and not config.explicitBlockquotes:
                    blockquoteWarned = True
                    m.warn(
                        f"Line {line.i} looks like the start of a markdown blockquote.\nIf this is intended, please set `Markup Shorthands: markdown-blockquotes yes`; if not, set it to `no`.\nSee https://speced.github.io/bikeshed/#md-blockquote for details.",
                    )
                match = _BQ_START_RE.match(firstText)
                assert match is not None
                token = Token(type="blockquote", nodes=sliceFirstText(strippedNodes, match.start(1)))
            else:
                token = Token(type="text", nodes=strippedNodes)

        token.prefixlen = prefixCountFromNodes(line.nodes, config.indent)
        token.line = line
        tokens.append(token)

    return tokens


def prefixCountFromNodes(nodes: list[h.ParserNode], numSpacesForIndentation: int) -> int:
    """Returns the number of leading indentation levels on a line of nodes."""
    if not nodes or not isinstance(nodes[0], h.RawText):
        return 0
    return prefixCount(nodes[0].text, numSpacesForIndentation)


def prefixCount(text: str, numSpacesForIndentation: int) -> int:
    """Counts leading tab or space-group indentation levels in `text`."""
    i = 0
    prefixLen = 0
    spaces = " " * numSpacesForIndentation
    while i < len(text):
        if text[i] == "\t":
            i += 1
            prefixLen += 1
        elif text[i : i + numSpacesForIndentation] == spaces:
            i += numSpacesForIndentation
            prefixLen += 1
        else:
            break
    return prefixLen


def stripPrefix(token: Token, numSpacesForIndentation: int, numIndents: int) -> NodeLine:
    """Removes `numIndents` indentation levels from the start of `token.line`."""
    line = token.line

    # Don't mess with "infinite" prefix lines
    if token.prefixlen == float("inf"):
        return NodeLine(line.i, list(line.nodes))

    # Allow empty lines
    if not stripWsNodes(line.nodes):
        return NodeLine(line.i, list(line.nodes))

    if not line.nodes or not isinstance(line.nodes[0], h.RawText):
        m.die(
            f'Line {line.i} isn\'t indented enough (needs {numIndents} indent{"" if numIndents == 1 else "s"}) to be valid Markdown:\n"{h.strFromNodes(line.nodes)}"',
        )
        return NodeLine(line.i, list(line.nodes))

    text = line.nodes[0].text
    offset = 0
    spaces = " " * numSpacesForIndentation
    for _ in range(numIndents):
        if offset < len(text) and text[offset] == "\t":
            offset += 1
        elif text[offset : offset + numSpacesForIndentation] == spaces:
            offset += numSpacesForIndentation
        else:
            m.die(
                f'Line {line.i} isn\'t indented enough (needs {numIndents} indent{"" if numIndents == 1 else "s"}) to be valid Markdown:\n"{h.strFromNodes(line.nodes)}"',
            )
            return NodeLine(line.i, list(line.nodes))
    return NodeLine(line.i, sliceFirstText(line.nodes, offset))


def parseTokens(tokens: list[Token], config: MarkdownConfig) -> list[h.ParserNode]:
    """
    Converts a list of Markdown line Tokens into a flat list of ParserNodes.

    Token types:
    blank, equals-line, dash-line, heading, rule, numbered,
    bulleted, dt, dd, text, htmlblock, blockquote, raw
    """
    nodes: list[h.ParserNode] = []
    i = 0
    numTokens = len(tokens)

    while i < numTokens:
        tok = tokens[i]
        currtype = tok.type
        if currtype in ("raw", "htmlblock"):
            nodes.extend(tok.line.nodes)
            nodes.append(h.RawText(text="\n"))
            i += 1
        elif currtype == "heading":
            nodes.extend(parseSingleLineHeading(tok))
            i += 1
        elif currtype == "text" and i + 1 < numTokens and tokens[i + 1].type in ("equals-line", "dash-line"):
            parsed, i = parseMultiLineHeading(tokens, i)
            nodes.extend(parsed)
        elif currtype == "text" and (i == 0 or tokens[i - 1].type == "blank"):
            parsed, i = parseParagraph(tokens, i)
            nodes.extend(parsed)
        elif currtype in ("rule", "dash-line"):
            nodes.extend(parseHorizontalRule())
            i += 1
        elif currtype == "bulleted":
            parsed, i = parseBulleted(tokens, i, config)
            nodes.extend(parsed)
        elif currtype == "numbered":
            parsed, i = parseNumbered(tokens, i, config, start=tok.num)
            nodes.extend(parsed)
        elif currtype in ("dt", "dd"):
            parsed, i = parseDl(tokens, i, config)
            nodes.extend(parsed)
        elif currtype == "blockquote":
            parsed, i = parseBlockquote(tokens, i, config)
            nodes.extend(parsed)
        else:
            nodes.extend(tok.line.nodes)
            nodes.append(h.RawText(text="\n"))
            i += 1

    return nodes


def makeStartTag(tagName: str, lineNumber: int, attrs: dict[str, str] | None = None) -> h.StartTag:
    """Creates a StartTag with `bs-line-number` and escaped attributes."""
    safeAttrs: t.SafeAttrDict = {"bs-line-number": t.SafeAttrStr(str(lineNumber))}
    if attrs:
        for k, v in attrs.items():
            safeAttrs[k] = t.SafeAttrStr(h.escapeAttr(v))
    return h.StartTag(tag=tagName, attrs=safeAttrs)


def rawTokenLine(tokens: list[Token], idx: int) -> str:
    """Serializes `tokens[idx]` back to a newline-terminated string for error messages."""
    if 0 <= idx < len(tokens):
        return h.strFromNodes(tokens[idx].line.nodes) + "\n"
    return "\n"


# Multi-line block parsers take `(tokens, i, ...)` and return `(nodes, nextIndex)`,
# where `nextIndex` is the index of the first token after the construct.


def parseSingleLineHeading(tok: Token) -> list[h.ParserNode]:
    """Parses a single-line `#` heading token into `<hN>...</hN>` nodes."""
    attrs: dict[str, str] = {}
    if tok.id:
        attrs["id"] = tok.id
    tagName = f"h{tok.level}"
    return [
        makeStartTag(tagName, tok.line.i, attrs),
        *tok.nodes,
        h.EndTag(tag=tagName),
        h.RawText(text="\n"),
    ]


def parseMultiLineHeading(tokens: list[Token], i: int) -> tuple[list[h.ParserNode], int]:
    """Parses a Setext-style underlined heading (`===` or `---`) into `<h2>` or `<h3>` nodes."""
    tok = tokens[i]
    nexttype = tokens[i + 1].type if i + 1 < len(tokens) else "eof"
    if nexttype == "equals-line":
        tagName = "h2"
    elif nexttype == "dash-line":
        tagName = "h3"
    else:
        m.die(
            "Markdown parser error: tried to parse a multiline heading from:\n"
            + rawTokenLine(tokens, i - 1)
            + rawTokenLine(tokens, i)
            + rawTokenLine(tokens, i + 1),
        )
        tagName = "h2"
    attrs: dict[str, str] = {}
    headingNodes = list(tok.nodes)
    if headingNodes and isinstance(headingNodes[-1], h.RawText):
        lastText = headingNodes[-1].text
        if match := _MULTILINE_HEADING_ID_RE.search(lastText):
            attrs["id"] = match.group(1)
            prefix = lastText[: match.start()]
            if prefix:
                headingNodes[-1] = h.RawText(
                    s=headingNodes[-1].s,
                    start=headingNodes[-1].start,
                    end=headingNodes[-1].end,
                    text=prefix,
                )
            else:
                headingNodes.pop()
                rstripNodes(headingNodes)
    nodes: list[h.ParserNode] = [
        makeStartTag(tagName, tok.line.i, attrs),
        *headingNodes,
        h.EndTag(tag=tagName),
        h.RawText(text="\n"),
    ]
    return nodes, i + 2


def parseHorizontalRule() -> list[h.ParserNode]:
    """Parses a horizontal rule line (`***`, `---`, `___`) into an `<hr>` node."""
    return [h.SelfClosedTag(tag="hr"), h.RawText(text="\n")]


def parseParagraph(tokens: list[Token], i: int) -> tuple[list[h.ParserNode], int]:
    """Parses consecutive text lines into a `<p>` block (handling NOTE/ISSUE/ASSERT/ADVISEMENT prefixes)."""
    tok = tokens[i]
    firstLineNodes = list(tok.nodes)
    lineNum = tok.line.i
    initialPrefixLen = tok.prefixlen
    prefixNodes: list[h.ParserNode]
    endTags: list[h.ParserNode] = [h.EndTag(tag="p")]

    if firstLineNodes and isinstance(firstLineNodes[0], h.RawText):
        firstText = firstLineNodes[0].text
        lowerFirst = firstText.lower()
        if matchNote := _NOTE_START_RE.match(firstText):
            firstLineNodes = sliceFirstText(firstLineNodes, matchNote.start(3))
            prefixNodes = [
                makeStartTag("p", lineNum, {"class": "replace-with-note-class"}),
                makeStartTag("span", lineNum, {"class": "marker"}),
                h.RawText(text=matchNote.group(1)),
                h.EndTag(tag="span"),
            ]
            if matchNote.group(2):
                prefixNodes.append(h.RawText(text=matchNote.group(2)))
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
            endTags = [h.EndTag(tag="strong"), h.EndTag(tag="p")]
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

    contentNodes: list[h.ParserNode] = list(firstLineNodes)
    i += 1
    while i < len(tokens) and tokens[i].type == "text" and tokens[i].prefixlen >= initialPrefixLen:
        contentNodes.append(h.RawText(text="\n"))
        contentNodes.extend(tokens[i].line.nodes)
        i += 1

    rstripNodes(contentNodes)
    return [*prefixNodes, *contentNodes, *endTags, h.RawText(text="\n")], i


def blankEndsList(tokens: list[Token], i: int, itemTypes: tuple[str, ...], prefixLen: int) -> bool:
    """Returns whether a blank token at `i` terminates a list of `itemTypes` at `prefixLen`."""
    if i + 1 >= len(tokens):
        return True
    nextTok = tokens[i + 1]
    return nextTok.type not in itemTypes and nextTok.prefixlen <= prefixLen


def parseListItems(
    tokens: list[Token],
    i: int,
    config: MarkdownConfig,
    itemTypes: tuple[str, ...],
    prefixLen: int,
) -> tuple[list[tuple[str, int, list[NodeLine]]], int]:
    """Collects consecutive list items of `itemTypes` at `prefixLen`, returning `(items, nextIndex)`."""
    items: list[tuple[str, int, list[NodeLine]]] = []
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "blank" and blankEndsList(tokens, i, itemTypes, prefixLen):
            break
        if tok.prefixlen < prefixLen:
            break
        if tok.type == "blank":
            i += 1
            tok = tokens[i]
        itemType = tok.type
        itemLineNum = tok.line.i
        itemLines: list[NodeLine] = [NodeLine(itemLineNum, list(tok.nodes))]
        i += 1
        while i < len(tokens):
            cur = tokens[i]
            if cur.type in itemTypes and cur.prefixlen == prefixLen:
                break
            if cur.prefixlen < prefixLen:
                break
            if cur.type == "blank" and blankEndsList(tokens, i, itemTypes, prefixLen):
                break
            itemLines.append(stripPrefix(cur, config.indent, prefixLen + 1))
            i += 1
        items.append((itemType, itemLineNum, itemLines))
    return items, i


def parseBulleted(
    tokens: list[Token],
    i: int,
    config: MarkdownConfig,
) -> tuple[list[h.ParserNode], int]:
    """Parses a bulleted list (`*`, `+`, `-`) and its nested items into `<ul>`/`<li>` nodes."""
    prefixLen = int(tokens[i].prefixlen)
    ulLineNum = tokens[i].line.i
    items, i = parseListItems(tokens, i, config, ("bulleted",), prefixLen)
    nodes: list[h.ParserNode] = [makeStartTag("ul", ulLineNum, {"bs-md-list": ""})]
    for _, liLineNum, liLines in items:
        nodes.append(makeStartTag("li", liLineNum, {"data-md": ""}))
        nodes.extend(parseLines(liLines, config))
    nodes.append(h.EndTag(tag="ul"))
    return nodes, i


def parseNumbered(
    tokens: list[Token],
    i: int,
    config: MarkdownConfig,
    start: int = 1,
) -> tuple[list[h.ParserNode], int]:
    """Parses a numbered list (`1.`, etc.) and its nested items into `<ol>`/`<li>` nodes."""
    prefixLen = int(tokens[i].prefixlen)
    olLineNum = tokens[i].line.i
    items, i = parseListItems(tokens, i, config, ("numbered",), prefixLen)
    nodes: list[h.ParserNode]
    if start == 1:
        nodes = [makeStartTag("ol", olLineNum, {"bs-md-list": ""})]
    else:
        nodes = [makeStartTag("ol", olLineNum, {"bs-md-list": "", "start": str(start)})]
    for _, liLineNum, liLines in items:
        nodes.append(makeStartTag("li", liLineNum, {"data-md": ""}))
        nodes.extend(parseLines(liLines, config))
        nodes.append(h.EndTag(tag="li"))
    nodes.append(h.EndTag(tag="ol"))
    return nodes, i


def parseDl(
    tokens: list[Token],
    i: int,
    config: MarkdownConfig,
) -> tuple[list[h.ParserNode], int]:
    """Parses a definition list (`:` and `::` lines) into `<dl>`/`<dt>`/`<dd>` nodes."""
    prefixLen = int(tokens[i].prefixlen)
    dlLineNum = tokens[i].line.i
    items, i = parseListItems(tokens, i, config, ("dt", "dd"), prefixLen)
    nodes: list[h.ParserNode] = [makeStartTag("dl", dlLineNum, {"bs-md-list": ""})]
    for tagtype, diLineNum, diLines in items:
        nodes.append(makeStartTag(tagtype, diLineNum, {"data-md": ""}))
        nodes.extend(parseLines(diLines, config))
        nodes.append(h.EndTag(tag=tagtype))
    nodes.append(h.EndTag(tag="dl"))
    return nodes, i


def stripBlockquoteFromOpaqueNodes(
    nodes: list[h.ParserNode],
    opaqueElements: frozenset[str],
) -> list[h.ParserNode]:
    """Strips one leading blockquote `>` prefix from inner lines of raw/opaque nodes."""
    result: list[h.ParserNode] = []
    opaqueDepth = 0
    afterNewline = False
    for node in nodes:
        if isinstance(node, (h.RawElement, h.SafeElement)):
            if "\n" in node.data:
                newData = _BQ_INNER_LINE_RE.sub("\n", node.data)
                result.append(replace(node, data=newData))
            else:
                result.append(node)
            afterNewline = False
            continue
        if opaqueDepth > 0:
            if isinstance(node, h.StartTag) and node.tag in opaqueElements:
                opaqueDepth += 1
                result.append(node)
                afterNewline = False
            elif isinstance(node, h.EndTag) and node.tag in opaqueElements:
                opaqueDepth -= 1
                result.append(node)
                afterNewline = False
            elif isinstance(node, h.RawText):
                text = node.text
                if afterNewline:
                    text = _BQ_LINE_START_RE.sub("", text, count=1)
                if "\n" in text:
                    text = _BQ_INNER_LINE_RE.sub("\n", text)
                afterNewline = text.endswith("\n")
                if text != node.text:
                    result.append(h.RawText(s=node.s, start=node.start, end=node.end, text=text))
                else:
                    result.append(node)
            else:
                result.append(node)
                afterNewline = False
        else:
            if isinstance(node, h.StartTag) and node.tag in opaqueElements:
                opaqueDepth += 1
                afterNewline = False
            result.append(node)
    return result


def parseBlockquote(
    tokens: list[Token],
    i: int,
    config: MarkdownConfig,
) -> tuple[list[h.ParserNode], int]:
    """Parses consecutive `>`-prefixed lines into a `<blockquote>` block."""
    tok = tokens[i]
    prefixLen = tok.prefixlen
    lineNum = tok.line.i
    bqLines: list[NodeLine] = [
        NodeLine(lineNum, stripBlockquoteFromOpaqueNodes(tok.nodes, config.opaqueElements)),
    ]
    i += 1
    while i < len(tokens):
        cur = tokens[i]
        if cur.prefixlen < prefixLen or cur.type not in ("blockquote", "text"):
            break
        curNodes = (
            stripBlockquoteFromOpaqueNodes(cur.nodes, config.opaqueElements)
            if cur.type == "blockquote"
            else list(cur.nodes)
        )
        bqLines.append(NodeLine(cur.line.i, curNodes))
        i += 1

    nodes: list[h.ParserNode] = [
        makeStartTag("blockquote", lineNum),
        *parseLines(bqLines, config),
        h.EndTag(tag="blockquote"),
        h.RawText(text="\n"),
    ]
    return nodes, i
