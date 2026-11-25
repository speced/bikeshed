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

    class ResultGeneratorFn(t.Protocol):
        """Callable matching `generateResults(s, start, experimental=...)`."""

        def __call__(
            self,
            s: Stream,
            start: int,
            experimental: bool = False,
        ) -> t.Generator[OkT[ParserNode | list[ParserNode]], None, None]:
            """Yield `Ok` parse results from `s` starting at `start`."""

    class ExperimentalNodesFn(t.Protocol):
        """Callable matching `generateExperimentalNodes(s, start, coll)`."""

        def __call__(
            self,
            s: Stream,
            start: int,
            coll: list[ParserNode],
        ) -> t.Generator[int, None, None]:
            """Collect experimental nodes from `s` into `coll`, yielding each stream index."""

    class BlockParserFn(t.Protocol):
        """Callable matching `parseBlockStream(s)`."""

        def __call__(self, s: Stream) -> list[ParserNode]:
            """Parse block-level Markdown and inline markup from `s`."""


@dataclass
class ParseConfig:
    """Configuration flags and metadata controlling HTML, shorthand, macro, and Markdown parsing."""

    # Enable |var| algorithm variable shorthands.
    algorithm: bool = False
    # Enable [[SPEC]] and [[SPEC#section]] bibliography/section autolinks.
    biblio: bool = False
    # Enable {^foo^} CDDL autolinks.
    cddl: bool = False
    # Enable 'prop', ''value'', and <<type>> CSS autolinks.
    css: bool = False
    # Enable [=dfn=] and [$abstract op$] autolinks.
    dfn: bool = False
    # Enable [:Header:] HTTP header autolinks.
    header: bool = False
    # Enable {{Interface}} WebIDL autolinks.
    idl: bool = False
    # Expand [MACRO] text macros inside autolink shorthands.
    macrosInAutolinks: bool = False
    # Enable block-level Markdown (headings, lists, paragraphs, rules).
    markdownBlock: bool = False
    # Enable `>` Markdown blockquotes.
    markdownBlockquotes: bool = False
    # Whether `markdown-blockquotes` was explicitly enabled (suppresses unset warning).
    markdownBlockquotesExplicit: bool = False
    # Enable inline Markdown (`code` spans and [text](url) links).
    markdownInline: bool = False
    # Enable backslash escapes for Markdown punctuation (\*, \[, etc.).
    markdownEscapes: bool = False
    # Enable <{element}> and <{element/attr}> markup autolinks.
    markup: bool = False
    # Enable <org/repo#123> and <#123> repository issue links.
    repositoryLinks: bool = False
    # Number of spaces per indentation level for Markdown lists.
    indent: int = 4
    # Map of lowercased [MACRO] names to their replacement text.
    macros: dict[str, str] = field(default_factory=dict)
    # Optional source description appended to Stream.loc() (e.g. for macros or includes).
    context: str | None = None
    # Extra element tag names treated as block-level HTML (not inline) by Markdown.
    blockElements: set[str] = field(default_factory=set)
    # Extra opaque tag names whose contents skip shorthands, block Markdown, and curly apostrophes.
    opaqueElements: set[str] = field(default_factory=set)
    # Parse strictly as plain HTML: disables shorthands, macros, attr shortcuts,
    # curly apostrophes, em-dashes, TagStack errors, and synthetic bs-line-number attrs.
    rawHtml: bool = False

    @staticmethod
    def fromSpec(doc: t.SpecT, context: str | None = None) -> ParseConfig:
        """Build a `ParseConfig` from a specification's metadata and macro table."""
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
            markdownBlockquotes=not doc.md.markupShorthands.explicitFalse("markdown-blockquotes"),
            markdownBlockquotesExplicit=doc.md.markupShorthands.explicitTrue("markdown-blockquotes"),
            markdownInline="markdown-inline" in doc.md.markupShorthands,
            markdownEscapes="markdown-escapes" in doc.md.markupShorthands,
            markup="markup" in doc.md.markupShorthands,
            repositoryLinks="repository-links" in doc.md.markupShorthands,
            indent=doc.md.indent,
            macros=doc.macros,
            context=context,
            blockElements=set(doc.md.blockElements) | set(doc.md.opaqueElements),
            opaqueElements=set(doc.md.opaqueElements),
        )


DEFAULT_PARSE_CONFIG = ParseConfig()


@dataclass
class Stream:
    """Character buffer with line/column mapping, parse configuration, and open-element tracking."""

    chars: str
    length: int
    # Indices of every "\n" in `chars`, used with bisect_left for O(log N) line/col lookup.
    _lineBreaks: list[int]
    # Optional per-line column shift (e.g. stripped blockquote prefixes) added to reported columns.
    _colOffsets: list[int] | None
    startLine: int
    config: ParseConfig
    depth: int = 1
    openEls: TagStack = field(default_factory=TagStack)
    blockParser: BlockParserFn | None = None

    def __init__(
        self,
        chars: str,
        config: ParseConfig,
        startLine: int = 1,
        depth: int = 1,
        *,
        colOffsets: list[int] | None = None,
        openEls: TagStack | None = None,
        blockParser: BlockParserFn | None = None,
    ) -> None:
        """Initialize a stream over `chars`, pre-indexing newline positions for line/column lookups."""
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
        if colOffsets is not None:
            assert len(colOffsets) == len(lineBreaks) + 1
        self._colOffsets = colOffsets
        self.startLine = startLine
        self.config = config
        self.depth = depth
        self.openEls = openEls if openEls is not None else TagStack(opaqueTags=config.opaqueElements)
        self.blockParser = blockParser

    def subStream(
        self,
        context: str | None,
        chars: str,
        startLine: int = 1,
        *,
        colOffsets: list[int] | None = None,
        openEls: TagStack | None = None,
        depth: int | None = None,
    ) -> Stream:
        """Create a child stream inheriting this stream's config (with an updated `context` and incremented depth)."""
        newConfig = dataclasses.replace(self.config, context=context)
        return Stream(
            chars,
            config=newConfig,
            startLine=startLine,
            depth=self.depth + 1 if depth is None else depth,
            colOffsets=colOffsets,
            openEls=openEls,
            blockParser=self.blockParser,
        )

    def __getitem__(self, key: int) -> str:
        """Return the character at `key`, or `""` if `key` is out of bounds."""
        if key < 0 or key >= self.length:
            return ""
        return self.chars[key]

    def slice(self, start: int | None, stop: int | None) -> str:
        """Return `chars[start:stop]`, clamping negative endpoints to 0 instead of indexing from the end."""
        if start is not None and start < 0:
            start = 0
        if stop is not None and stop < 0:
            stop = 0
        return self.chars[start:stop]

    def eof(self, index: int) -> bool:
        """Return True if `index` is at or past the end of the stream."""
        return index >= self.length

    def __len__(self) -> int:
        """Return the number of characters in the stream."""
        return self.length

    @property
    def context(self) -> str | None:
        """Return the optional source context label from this stream's config."""
        return self.config.context

    def lineIndex(self, index: int) -> int:
        """Return the zero-based line number containing `index` (newlines belong to the line they end)."""
        # bisect_left places a "\n" index on the line it terminates, while the char after "\n" starts the next line.
        return bisect.bisect_left(self._lineBreaks, index)

    def line(self, index: int, lineIndex: int | None = None) -> int:
        """Return the 1-based source line number for `index`."""
        if lineIndex is None:
            lineIndex = self.lineIndex(index)
        return lineIndex + self.startLine

    def colOffset(self, lineIndex: int) -> int:
        """Return any stripped-prefix column offset for zero-based `lineIndex`."""
        if self._colOffsets is None:
            return 0
        return self._colOffsets[lineIndex]

    def col(self, index: int, lineIndex: int | None = None) -> int:
        """Return the 1-based source column number for `index`, including any per-line column offset."""
        if lineIndex is None:
            lineIndex = self.lineIndex(index)
        if lineIndex == 0:
            col = index + 1
        else:
            startOfCol = self._lineBreaks[lineIndex - 1]
            col = index - startOfCol
        if self._colOffsets is not None:
            col += self._colOffsets[lineIndex]
        return col

    def loc(self, index: int) -> str:
        """Format `index` as a human-readable `line:col` location (with context if set)."""
        lineIndex = self.lineIndex(index)
        rc = f"{self.line(index, lineIndex)}:{self.col(index, lineIndex)}"
        if self.config.context is None:
            return rc
        return f"{rc} of {self.config.context}"

    def skipTo(self, start: int, text: str) -> ResultT[str]:
        """Advance to the next occurrence of `text`, returning the intervening substring or `Err`."""
        i = self.chars.find(text, start)
        if i != -1:
            return Ok(self.chars[start:i], i)
        return Err(start)

    def skipToSameLine(self, start: int, text: str) -> ResultT[str]:
        """Advance to `text` on the current line (before `\\n`), returning the intervening substring or `Err`."""
        lineEnd = self.chars.find("\n", start)
        i = self.chars.find(text, start) if lineEnd == -1 else self.chars.find(text, start, lineEnd)
        if i != -1:
            return Ok(self.chars[start:i], i)
        return Err(start)

    def matchRe(self, start: int, pattern: t.Pattern) -> ResultT[t.Match]:
        """Match compiled `pattern` anchored at `start`, returning the match object or `Err`."""
        match = pattern.match(self.chars, start)
        if match:
            return Ok(match, match.end())
        else:
            return Err(start)

    def searchRe(self, start: int, pattern: t.Pattern) -> ResultT[t.Match]:
        """Search for compiled `pattern` at or after `start`, returning the match object or `Err`."""
        match = pattern.search(self.chars, start)
        if match:
            return Ok(match, match.end())
        else:
            return Err(start)

    def skipToNextLine(self, start: int) -> OkT[str]:
        """Advance to the start of the next line, returning the remaining text on the current line."""
        textAfter = self.remainingTextOnLine(start)
        return Ok(textAfter, start + len(textAfter))

    def precedingLinebreakIndex(self, start: int) -> int:
        """Return the index in `_lineBreaks` of the newline before `start` (or `-1` on line 0)."""
        lineIndex = bisect.bisect_left(self._lineBreaks, start)
        return lineIndex - 1

    def followingLinebreakIndex(self, start: int) -> int:
        """Return the index in `_lineBreaks` of the newline ending `start`'s line."""
        # A newline char terminates its line; the break to the next line occurs after it.
        return bisect.bisect_left(self._lineBreaks, start)

    def currentLineStart(self, start: int) -> int:
        """Return the stream index of the first character on `start`'s line."""
        lineIndex = self.precedingLinebreakIndex(start)
        if lineIndex == -1:
            return 0
        else:
            return self._lineBreaks[lineIndex] + 1

    def nextLineStart(self, start: int) -> int:
        """Return the stream index of the first character on the line after `start` (or `length` on the last line)."""
        lineIndex = self.followingLinebreakIndex(start)
        if lineIndex >= len(self._lineBreaks):
            return self.length
        else:
            return self._lineBreaks[lineIndex] + 1

    def precedingTextOnLine(self, start: int) -> str:
        """Return the substring on the current line preceding `start`."""
        return self.slice(self.currentLineStart(start), start)

    def remainingTextOnLine(self, start: int) -> str:
        """Return the substring from `start` through the end of the current line (including `\\n` if present)."""
        return self.slice(start, self.nextLineStart(start))

    def observeResult(self, res: ResultT[ParserNode | list[ParserNode]]) -> None:
        """Update `openEls` if `res` is an `Ok` result containing a node or list of nodes."""
        if isOk(res):
            val, _, _ = res
            if isinstance(val, list):
                self.observeNodes(val)
            else:
                self.observeNode(val)

    def observeNode(self, node: ParserNode) -> None:
        """Record a parsed `node` on the open-elements stack."""
        self.openEls.update(node)

    def observeNodes(self, nodes: list[ParserNode]) -> None:
        """Record each parsed node in `nodes` on the open-elements stack."""
        for node in nodes:
            self.openEls.update(node)

    def observeShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        """Push an open shorthand wrapper onto `openEls`."""
        self.openEls.updateShorthandOpen(startTag, sigils)

    def observeShorthandClose(self, s: Stream, i: int, startTag: StartTag, sigils: tuple[str, str]) -> list[ParserNode]:
        """Close a shorthand wrapper on `openEls`, returning any auto-closed inner `EndTag`s."""
        return list(self.openEls.updateShorthandClose(s, i, startTag, sigils))

    def cancelShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        """Roll back an unclosed shorthand opener from `openEls` after a failed parse."""
        self.openEls.cancelShorthandOpen(startTag, sigils)

    def inOpaqueElement(self) -> bool:
        """Return True if the parser is currently inside an opaque element (e.g. `pre`, `script`, `bs-opaque`)."""
        return self.openEls.inOpaqueElement()

    def inTagContext(self, tagName: str) -> bool:
        """Return True if an open `<tagName>` element is currently on the stack."""
        return self.openEls.inTagContext(tagName)
