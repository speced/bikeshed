"""Line-scanning, indentation-counting, and mixed-indentation linting helpers for the unified parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ... import messages as m
from ... import t
from .nodes import EndTag, ParserNode, RawText, StartTag
from .stream import Stream

_MIXED_INDENT_TAB_AFTER_SPACE_RE = re.compile(r"(?:\t+ +\t)|( +\t)")


def skipHws(chars: str, pos: int, end: int) -> int:
    """Advance `pos` past ASCII spaces and tabs up to `end`."""
    while pos < end and chars[pos] in (" ", "\t"):
        pos += 1
    return pos


def findLineEnd(s: Stream, pos: int) -> int:
    """Return the index of the next `\\n` at or after `pos` (or `s.length` at EOF)."""
    lineEnd = s.chars.find("\n", pos)
    return s.length if lineEnd == -1 else lineEnd


def nextLinePos(lineEnd: int, length: int) -> int:
    """Return the index immediately after a line ending at `lineEnd` (clamped to `length`)."""
    return lineEnd + 1 if lineEnd < length else length


def lineLoc(s: Stream, lineNum: int) -> str | int:
    """Format `lineNum` with `s.context` when present so errors inside macros identify their source."""
    return f"{lineNum} of {s.context}" if s.context else lineNum


def prefixCountAt(s: Stream, lineStart: int, indent: int) -> int:
    """Count whole indentation levels (each a tab or `indent` spaces) starting at `lineStart`."""
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
    """Advance `lineStart` past `numIndents` indentation levels, or return `None` if fewer are present."""
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


@dataclass(slots=True)
class IndentChecker:
    """Records mixed-indentation lint issues during parsing for emission afterward."""

    indentChar: str
    opaqueTags: frozenset[str]
    issues: list[tuple[str | int, str]] = field(default_factory=list)
    _lastCheckedStream: Stream | None = None
    _lastCheckedStart: int = -1

    def _checkPart(self, part: str, lineNum: str | int) -> None:
        """Record any wrong-indent-character or tab-after-space lint issues on a line slice."""
        badIndentChar = " " if self.indentChar == "\t" else "\t"
        if part[0] == badIndentChar:
            if self.indentChar == " ":
                self.issues.append((lineNum, "Line starts with tabs, but document is space-indented"))
            else:
                self.issues.append((lineNum, "Line starts with spaces, but document is tab-indented"))
        if _MIXED_INDENT_TAB_AFTER_SPACE_RE.match(part):
            self.issues.append((lineNum, "Line's indent contains tabs after spaces."))

    def checkLine(self, s: Stream, lineStart: int) -> None:
        """Check indentation on the physical line at `lineStart`, skipping lines already checked."""
        if lineStart >= s.length:
            return
        # We're in an already-indented substream, so bail.
        if lineStart == 0 and s.colOffset(0) > 0:
            return
        # Deduplicate lines inspected by both parseParagraph() and parseBlocks() (e.g. after a break).
        if s is self._lastCheckedStream and lineStart <= self._lastCheckedStart:
            return
        self._lastCheckedStream = s
        self._lastCheckedStart = lineStart
        ch = s.chars[lineStart]
        if ch not in (" ", "\t"):
            return
        lineEnd = findLineEnd(s, lineStart)
        part = s.chars[lineStart:lineEnd]
        self._checkPart(part, lineLoc(s, s.line(lineStart)))

    def checkNodes(self, nodes: t.Sequence[ParserNode], *, atLineStart: bool = True) -> None:
        """Walk parsed `nodes` and check indentation on non-opaque lines (used for macros and non-block mode)."""
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

    def checkMacroNodes(self, nodes: t.Sequence[ParserNode], atLineStart: bool) -> None:
        """Callback to lint indentation inside macro-expanded nodes."""
        self.checkNodes(nodes, atLineStart=atLineStart)

    def emit(self) -> None:
        """Emit all recorded indentation lint messages."""
        for lineNum, msg in self.issues:
            m.lint(msg, lineNum=lineNum)
