"""Bikeshed `[MACRO]` and `[MACRO?]` text macro parsing and expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ... import constants, t
from ... import messages as m
from .nodes import ParserNode, RawText
from .result import Err, Ok
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import ResultT

MACRO_RE = re.compile(r"([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]")

# Treat [ as an escape character, too, so [[RFC2119]]/etc won't
# get accidentally recognized as a macro.
MACRO_ATTRIBUTE_RE = re.compile(r"([\[\\]?)\[([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]")


@dataclass(slots=True)
class _ResolvedMacro:
    """Resolved macro expansion metadata returned by `_resolveMacro()`."""

    status: t.Literal["ok", "missing-optional", "error"]
    end: int
    display: str = ""
    text: str = ""
    streamContext: str = ""
    stream: Stream | None = None


def isMacroStart(s: Stream, start: int) -> bool:
    """Fast pre-check returning True if `s[start]` could begin a `[MACRO]` name."""
    ch = s[start]
    return ch.isalpha() or ch.isdigit() or ch == "-"


def _resolveMacro(s: Stream, start: int) -> _ResolvedMacro | None:
    """Match `[MACRO]` / `[MACRO?]` at `start`, look up its value, and build a child `Stream`."""
    if s[start] != "[":
        return None
    match, i, _ = s.matchRe(start + 1, MACRO_RE)
    if match is None:
        return None
    macroName = match[1].lower()
    optional = match[2] == "?"
    if macroName not in s.config.macros:
        if optional:
            return _ResolvedMacro(status="missing-optional", end=i)
        m.die(
            f"Found unmatched text macro {s.slice(start, i)}. Correct the macro, or escape it by replacing the opening [ with &bs[;",
            lineNum=s.loc(i),
        )
        return _ResolvedMacro(status="error", end=i)
    macroDisplay = s.slice(start, i)
    macroText = s.config.macros[macroName]
    streamContext = f"macro {macroDisplay} (line {s.loc(start)})"
    try:
        newStream = s.subStream(context=streamContext, chars=macroText)
    except RecursionError:
        m.die(
            f"Macro replacement for {macroDisplay} recursed more than {s.depth} levels deep; probably your text macros are accidentally recursive.",
            lineNum=s.loc(start),
        )
        return _ResolvedMacro(status="error", end=i)
    return _ResolvedMacro(
        status="ok",
        end=i,
        display=macroDisplay,
        text=macroText,
        streamContext=streamContext,
        stream=newStream,
    )


def parseMacroToNodes(
    s: Stream,
    start: int,
    parseStream: t.Callable[[Stream, int], t.Iterable[ParserNode]],
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a `[MACRO]` at `start` and expand its replacement text into `ParserNode`s."""
    res = _resolveMacro(s, start)
    if res is None:
        return Err(start)
    if res.status == "missing-optional":
        return Ok([], res.end)
    if res.status == "error":
        return Ok(RawText.fromStream(s, start, res.end), res.end)
    assert res.stream is not None
    return Ok(list(parseStream(res.stream, 0)), res.end)


def parseMacroToAttrs(
    s: Stream,
    start: int,
    parseAttrList: t.Callable[[Stream, int], ResultT[dict[str, str]]],
    parseWs: t.Callable[[Stream, int], ResultT[bool]],
) -> ResultT[dict[str, str]]:
    """Parse a `[MACRO]` at `start` and expand its replacement text into a dict of HTML attributes."""
    res = _resolveMacro(s, start)
    if res is None:
        return Err(start)
    if res.status != "ok":
        return Ok({}, res.end)
    assert res.stream is not None
    attrs, attrsEnd, _ = parseAttrList(res.stream, 0)
    _, wsEnd, _ = parseWs(res.stream, attrsEnd)
    if not res.stream.eof(wsEnd):
        m.die(
            f"While parsing {res.display} (on {s.loc(start)}) as an attribute list, found non-attribute content: {res.stream.slice(attrsEnd, attrsEnd+10)}...",
            lineNum=res.stream.loc(attrsEnd),
        )
    if attrs:
        return Ok(attrs, res.end)
    return Err(start)


def parseMacroToText(s: Stream, start: int) -> ResultT[str]:
    """Parse a `[MACRO]` at `start` and expand its replacement text recursively as a string."""
    res = _resolveMacro(s, start)
    if res is None:
        return Err(start)
    if res.status == "missing-optional":
        return Ok("", res.end)
    if res.status == "error":
        return Ok(s.slice(start, res.end), res.end)
    assert res.stream is not None
    macroText = replaceMacrosInText(res.text, res.stream.config.macros, res.stream, 0, res.streamContext)
    return Ok(macroText, res.end)


def replaceMacrosInText(text: str, macros: dict[str, str], s: Stream, start: int, context: str) -> str:
    """Iteratively expand `[MACRO]` references inside plain-text contexts (attributes, raw blocks, autolink data)."""
    # Wrap each substitution in sentinel chars (stripped at the end) so adjacent
    # expansions cannot accidentally fuse into a new `[MACRO]`, and escape failed/escaped
    # brackets as numeric entities so subsequent passes skip them.
    msc = constants.macroStartChar
    mec = constants.macroEndChar

    def doRep(match: t.Match) -> str:
        """Expand a single `MACRO_ATTRIBUTE_RE` match, preserving escaped or `[[...]]` brackets."""
        escaped = match[1] == "\\"
        biblio = match[1] == "["
        macroName = match[2].lower()
        optional = match[3] == "?"
        if escaped:
            return msc + "&#91;" + match[0][2:-1] + "&#93;" + mec
        if biblio:
            return msc + "&#91;&#91;" + match[0][2:-1] + "&#93;" + mec
        if macroName in macros:
            return msc + macros[macroName] + mec
        if optional:
            return msc + mec
        m.die(
            f"Found unmatched text macro {match[0]} in {context}. Correct the macro, or escape it by replacing the opening [ with &bs[;.",
            lineNum=s.loc(start),
        )
        return msc + "&#91;" + match[0][1:-1] + "&#93;" + mec

    text, count = MACRO_ATTRIBUTE_RE.subn(doRep, text)
    if count > 0:
        loops = 1
        while True:
            if loops > 10:
                m.die(
                    f"Macro replacement in {context} recursed more than 10 levels deep; probably your text macros are accidentally recursive.",
                    lineNum=s.loc(start),
                )
                break
            if "[" not in text:
                break
            newText = MACRO_ATTRIBUTE_RE.sub(doRep, text)
            if text == newText:
                break
            text = newText
            loops += 1
    return text.replace(msc, "").replace(mec, "")
