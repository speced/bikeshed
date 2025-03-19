from __future__ import annotations

import bisect
import dataclasses
import re
from dataclasses import dataclass, field

from ... import t
from .nodes import TagStack
from .result import Err, Ok, OkT, ResultT, isOk

if t.TYPE_CHECKING:
    from .nodes import ParserNode, StartTag


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
    markdown: bool = False
    markdownEscapes: bool = False
    markup: bool = False
    repositoryLinks: bool = False
    macros: dict[str, str] = field(default_factory=dict)
    context: str | None = None
    opaqueElements: set[str] = field(default_factory=lambda: {"pre", "xmp", "script", "style"})

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
            markdown="markdown" in doc.md.markupShorthands,
            markdownEscapes="markdown-escapes" in doc.md.markupShorthands,
            markup="markup" in doc.md.markupShorthands,
            repositoryLinks="repository-links" in doc.md.markupShorthands,
            macros=doc.macros,
            context=context,
            opaqueElements=set(doc.md.opaqueElements),
        )


@dataclass
class Stream:
    _chars: str
    _len: int
    _lineBreaks: list[int]
    startLine: int
    config: ParseConfig
    depth: int = 1
    openEls: TagStack = field(default_factory=TagStack)

    def __init__(self, chars: str, config: ParseConfig, startLine: int = 1, depth: int = 1) -> None:
        if depth > 10:
            msg = "HTML parsing recursed more than 10 levels deep; probably an infinite loop."
            raise RecursionError(msg)
        self._chars = chars
        self._len = len(chars)
        self._lineBreaks = []
        self.startLine = startLine
        self.config = config
        self.depth = depth
        self.openEls = TagStack(opaqueTags=config.opaqueElements)
        for i, char in enumerate(chars):
            if char == "\n":
                self._lineBreaks.append(i)

    def subStream(self, context: str, chars: str, startLine: int = 1) -> Stream:
        newConfig = dataclasses.replace(self.config, context=context)
        return Stream(chars, config=newConfig, startLine=startLine, depth=self.depth + 1)

    def __getitem__(self, key: int) -> str:
        if key < 0 or key >= self._len:
            return ""
        return self._chars[key]

    def slice(self, start: int | None, stop: int | None) -> str:
        if start is not None and start < 0:
            start = 0
        if stop is not None and stop < 0:
            stop = 0
        return self._chars[start:stop]

    def eof(self, index: int) -> bool:
        return index >= self._len

    def __len__(self) -> int:
        return self._len

    @property
    def context(self) -> str | None:
        return self.config.context

    def line(self, index: int) -> int:
        # Zero-based line index
        lineIndex = bisect.bisect_left(self._lineBreaks, index)
        return lineIndex + self.startLine

    def col(self, index: int) -> int:
        lineIndex = bisect.bisect_left(self._lineBreaks, index)
        if lineIndex == 0:
            return index + 1
        startOfCol = self._lineBreaks[lineIndex - 1]
        return index - startOfCol

    def loc(self, index: int) -> str:
        rc = f"{self.line(index)}:{self.col(index)}"
        if self.config.context is None:
            return rc
        return f"{rc} of {self.config.context}"

    def skipTo(self, start: int, text: str) -> ResultT[str]:
        # Skip forward until encountering `text`.
        # Produces the text encountered before this point.
        i = start
        textLen = len(text)
        while not self.eof(i):
            if self.slice(i, i + textLen) == text:
                break
            i += 1
        if self.slice(i, i + textLen) == text:
            return Ok(self.slice(start, i), i)
        else:
            return Err(start)

    def skipToSameLine(self, start: int, text: str) -> ResultT[str]:
        # Skips forward, but no further than the end of the current line.
        # Produces the text encounted before this point.
        i = start
        textLen = len(text)
        while not self.eof(i) and self[i] != "\n":
            if self.slice(i, i + textLen) == text:
                return Ok(self.slice(start, i), i)
            i += 1
        return Err(start)

    def matchRe(self, start: int, pattern: re.Pattern) -> ResultT[re.Match]:
        match = pattern.match(self._chars, start)
        if match:
            return Ok(match, match.end())
        else:
            return Err(start)

    def searchRe(self, start: int, pattern: re.Pattern) -> ResultT[re.Match]:
        match = pattern.search(self._chars, start)
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
            return len(self._chars)
        else:
            return self._lineBreaks[lineIndex] + 1

    def precedingTextOnLine(self, start: int) -> str:
        # The text on the current line before the start point.
        return self.slice(self.currentLineStart(start), start)

    def remainingTextOnLine(self, start: int) -> str:
        # The text on the current line from the start point on.
        # Includes the newline, if present.
        return self.slice(start, self.nextLineStart(start))

    def observeResult(self, res: ResultT[ParserNode | list[ParserNode]]) -> ResultT[ParserNode | list[ParserNode]]:
        if isOk(res):
            val, _, _ = res
            if isinstance(val, list):
                for node in val:
                    self.observeNode(node)
            else:
                self.observeNode(val)
        return res

    def observeNode(self, node: ParserNode) -> ParserNode:
        self.openEls.update(node)
        return node

    def observeNodes(self, nodes: list[ParserNode]) -> list[ParserNode]:
        for node in nodes:
            self.openEls.update(node)
        return nodes

    def observeShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.openEls.updateShorthandOpen(startTag, sigils)

    def observeShorthandClose(self, loc: str, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.openEls.updateShorthandClose(loc, startTag, sigils)

    def cancelShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.openEls.cancelShorthandOpen(startTag, sigils)

    def inOpaqueElement(self) -> bool:
        return self.openEls.inOpaqueElement()

    def inTagContext(self, tagName: str) -> bool:
        return self.openEls.inTagContext(tagName)
