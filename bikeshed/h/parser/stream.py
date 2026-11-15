from __future__ import annotations

import bisect
import dataclasses
from dataclasses import dataclass, field

from ... import t
from .nodes import TagStack
from .result import Err, Ok, isOk

if t.TYPE_CHECKING:
    from .nodes import ParserNode, StartTag
    from .result import OkT, ResultT


@dataclass
class ParseConfig:
    algorithm: bool = False
    biblio: bool = False
    cddl: bool = False
    css: bool = False
    dfn: bool = False
    header: bool = False
    idl: bool = False
    macrosInAutolinks: bool = False
    markdownBlock: bool = False
    markdownBlockquotes: bool = False
    markdownInline: bool = False
    markdownEscapes: bool = False
    markup: bool = False
    repositoryLinks: bool = False
    macros: dict[str, str] = field(default_factory=dict)
    context: str | None = None
    opaqueElements: set[str] = field(default_factory=set)

    @staticmethod
    def fromSpec(doc: t.SpecT, context: str | None = None) -> ParseConfig:
        return ParseConfig(
            algorithm="algorithm" in doc.md.markupShorthands,
            biblio="biblio" in doc.md.markupShorthands,
            cddl="cddl" in doc.md.markupShorthands,
            css="css" in doc.md.markupShorthands,
            dfn="dfn" in doc.md.markupShorthands,
            header="http" in doc.md.markupShorthands,
            idl="idl" in doc.md.markupShorthands,
            macrosInAutolinks="macros-in-autolinks" in doc.md.markupShorthands,
            markdownBlock="markdown-block" in doc.md.markupShorthands,
            markdownInline="markdown-inline" in doc.md.markupShorthands,
            markdownEscapes="markdown-escapes" in doc.md.markupShorthands,
            markup="markup" in doc.md.markupShorthands,
            repositoryLinks="repository-links" in doc.md.markupShorthands,
            macros=doc.macros,
            context=context,
            opaqueElements=set(doc.md.opaqueElements),
        )


DEFAULT_PARSE_CONFIG = ParseConfig()


@dataclass
class Stream:
    chars: str
    length: int
    _lineBreaks: list[int]
    startLine: int
    config: ParseConfig
    depth: int = 1
    openEls: TagStack = field(default_factory=TagStack)

    def __init__(self, chars: str, config: ParseConfig, startLine: int = 1, depth: int = 1) -> None:
        if depth > 10:
            msg = "HTML parsing recursed more than 10 levels deep; probably an infinite loop."
            raise RecursionError(msg)
        self.chars = chars
        self.length = len(chars)
        lineBreaks = []
        idx = chars.find("\n")
        while idx != -1:
            lineBreaks.append(idx)
            idx = chars.find("\n", idx + 1)
        self._lineBreaks = lineBreaks
        self.startLine = startLine
        self.config = config
        self.depth = depth
        self.openEls = TagStack(opaqueTags=config.opaqueElements)

    def subStream(self, context: str, chars: str, startLine: int = 1) -> Stream:
        newConfig = dataclasses.replace(self.config, context=context)
        return Stream(chars, config=newConfig, startLine=startLine, depth=self.depth + 1)

    def __getitem__(self, key: int) -> str:
        if key < 0 or key >= self.length:
            return ""
        return self.chars[key]

    def slice(self, start: int | None, stop: int | None) -> str:
        if start is not None and start < 0:
            start = 0
        if stop is not None and stop < 0:
            stop = 0
        return self.chars[start:stop]

    def eof(self, index: int) -> bool:
        return index >= self.length

    def __len__(self) -> int:
        return self.length

    @property
    def context(self) -> str | None:
        return self.config.context

    def lineIndex(self, index: int) -> int:
        # Zero-based line index
        return bisect.bisect_left(self._lineBreaks, index)

    def line(self, index: int, lineIndex: int | None = None) -> int:
        if lineIndex is None:
            lineIndex = self.lineIndex(index)
        return lineIndex + self.startLine

    def col(self, index: int, lineIndex: int | None = None) -> int:
        if lineIndex is None:
            lineIndex = self.lineIndex(index)
        if lineIndex == 0:
            return index + 1
        startOfCol = self._lineBreaks[lineIndex - 1]
        return index - startOfCol

    def loc(self, index: int) -> str:
        lineIndex = self.lineIndex(index)
        rc = f"{self.line(index, lineIndex)}:{self.col(index, lineIndex)}"
        if self.config.context is None:
            return rc
        return f"{rc} of {self.config.context}"

    def skipTo(self, start: int, text: str) -> ResultT[str]:
        # Skip forward until encountering `text`.
        # Produces the text encountered before this point.
        i = self.chars.find(text, start)
        if i != -1:
            return Ok(self.chars[start:i], i)
        return Err(start)

    def skipToSameLine(self, start: int, text: str) -> ResultT[str]:
        # Skips forward, but no further than the end of the current line.
        # Produces the text encountered before this point.
        lineEnd = self.chars.find("\n", start)
        i = self.chars.find(text, start) if lineEnd == -1 else self.chars.find(text, start, lineEnd)
        if i != -1:
            return Ok(self.chars[start:i], i)
        return Err(start)

    def matchRe(self, start: int, pattern: t.Pattern) -> ResultT[t.Match]:
        match = pattern.match(self.chars, start)
        if match:
            return Ok(match, match.end())
        else:
            return Err(start)

    def searchRe(self, start: int, pattern: t.Pattern) -> ResultT[t.Match]:
        match = pattern.search(self.chars, start)
        if match:
            return Ok(match, match.end())
        else:
            return Err(start)

    def skipToNextLine(self, start: int) -> OkT[str]:
        # Skips to the next line.
        # Produces the leftover text on the current line.
        textAfter = self.remainingTextOnLine(start)
        return Ok(textAfter, start + len(textAfter))

    def precedingLinebreakIndex(self, start: int) -> int:
        # Index in self._lineBreaks of the linebreak preceding `start`.
        lineIndex = bisect.bisect_left(self._lineBreaks, start)
        return lineIndex - 1

    def followingLinebreakIndex(self, start: int) -> int:
        # Same but the linebreak after.
        # Note that a newline char is at the end of its line;
        # the actual break in the line is *after* it.
        return bisect.bisect_left(self._lineBreaks, start)

    def currentLineStart(self, start: int) -> int:
        # The index of the first character on the current line.
        lineIndex = self.precedingLinebreakIndex(start)
        if lineIndex == -1:
            return 0
        else:
            return self._lineBreaks[lineIndex] + 1

    def nextLineStart(self, start: int) -> int:
        # The index of the first character on the next line.
        # Returns an OOB index if on the last line.
        lineIndex = self.followingLinebreakIndex(start)
        if lineIndex >= len(self._lineBreaks):
            return self.length
        else:
            return self._lineBreaks[lineIndex] + 1

    def precedingTextOnLine(self, start: int) -> str:
        # The text on the current line before the start point.
        return self.slice(self.currentLineStart(start), start)

    def remainingTextOnLine(self, start: int) -> str:
        # The text on the current line from the start point on.
        # Includes the newline, if present.
        return self.slice(start, self.nextLineStart(start))

    def observeResult(self, res: ResultT[ParserNode | list[ParserNode]]) -> None:
        if isOk(res):
            val, _, _ = res
            if isinstance(val, list):
                self.observeNodes(val)
            else:
                self.observeNode(val)

    def observeNode(self, node: ParserNode) -> None:
        self.openEls.update(node)

    def observeNodes(self, nodes: list[ParserNode]) -> None:
        for node in nodes:
            self.openEls.update(node)

    def observeShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.openEls.updateShorthandOpen(startTag, sigils)

    def observeShorthandClose(self, s: Stream, i: int, startTag: StartTag, sigils: tuple[str, str]) -> list[ParserNode]:
        return list(self.openEls.updateShorthandClose(s, i, startTag, sigils))

    def cancelShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.openEls.cancelShorthandOpen(startTag, sigils)

    def inOpaqueElement(self) -> bool:
        return self.openEls.inOpaqueElement()

    def inTagContext(self, tagName: str) -> bool:
        return self.openEls.inTagContext(tagName)
