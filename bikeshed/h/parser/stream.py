from __future__ import annotations

import bisect
import dataclasses
import re
from dataclasses import dataclass, field

from ... import t


@dataclass
class Failure:
    pass


@dataclass
class ParseFailure(Failure):
    details: str
    s: Stream
    index: int

    def __str__(self) -> str:
        return f"{self.s.loc(self.index)} {self.details}"


ResultT_co = t.TypeVar("ResultT_co", covariant=True)


@dataclass
class Result(t.Generic[ResultT_co]):
    value: ResultT_co | None
    i: int
    err: Failure | None = None

    @property
    def valid(self) -> bool:
        return self.err is None

    @staticmethod
    def fail(index: int) -> Result[ResultT_co]:
        return Result(None, index, Failure())

    @staticmethod
    def parseerror(s: Stream, index: int, details: str) -> Result[ResultT_co]:
        return Result(None, index, ParseFailure(details, s, index))

    @property
    def vi(self) -> tuple[ResultT_co | None, int]:
        # Returns a tuple of the value and index for easy
        # destructuring.
        # If error, value is None for simple detection;
        # use .vie if None is a valid value.
        if self.err:
            value = None
        else:
            value = self.value
        return (value, self.i)

    @property
    def vie(self) -> tuple[ResultT_co | None, int, Failure | None]:
        # Like .vi, but returns the error as the third tuple item.
        if self.err:
            value = None
        else:
            value = self.value
        return (value, self.i, self.err)


@dataclass
class ParseConfig:
    markdown: bool = False
    css: bool = False
    macros: dict[str, str] = field(default_factory=dict)
    context: str | None = None

    @staticmethod
    def fromSpec(doc: t.SpecT, context: str | None = None) -> ParseConfig:
        return ParseConfig(
            markdown="markdown" in doc.md.markupShorthands,
            css="css" in doc.md.markupShorthands,
            macros=doc.macros,
            context=context,
        )


class Stream:
    _chars: str
    _len: int
    _lineBreaks: list[int]
    startLine: int
    config: ParseConfig
    depth: int = 1

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
        for i, char in enumerate(chars):
            if char == "\n":
                self._lineBreaks.append(i)

    def subStream(self, context: str, chars: str, startLine: int = 1) -> Stream:
        newConfig = dataclasses.replace(self.config, context=context)
        return Stream(chars, config=newConfig, startLine=startLine, depth=self.depth + 1)

    def __getitem__(self, key: int | slice) -> str:
        try:
            return self._chars[key]
        except IndexError:
            return ""

    def eof(self, index: int) -> bool:
        return index >= self._len

    def __len__(self) -> int:
        return self._len

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

    def skipTo(self, start: int, text: str) -> Result[str]:
        # Skip forward until encountering `text`.
        # Produces the text encountered before this point.
        i = start
        textLen = len(text)
        while not self.eof(i):
            if self[i : i + textLen] == text:
                break
            i += 1
        if self[i : i + textLen] == text:
            return Result(self[start:i], i)
        else:
            return Result.fail(start)

    def matchRe(self, start: int, pattern: re.Pattern) -> Result[re.Match]:
        match = pattern.match(self._chars, start)
        if match:
            return Result(match, match.end())
        else:
            return Result.fail(start)

    def searchRe(self, start: int, pattern: re.Pattern) -> Result[re.Match]:
        match = pattern.search(self._chars, start)
        if match:
            return Result(match, match.end())
        else:
            return Result.fail(start)

    def skipToNextLine(self, start: int) -> Result[str]:
        # Skips to the next line.
        # Produces the leftover text on the current line.
        textAfter = self.remainingTextOnLine(start)
        return Result(textAfter, start + len(textAfter))

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
        return self[self.currentLineStart(start) : start]

    def remainingTextOnLine(self, start: int) -> str:
        # The text on the current line from the start point on.
        # Includes the newline, if present.
        return self[start : self.nextLineStart(start)]
