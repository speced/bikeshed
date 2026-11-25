# pylint: skip-file
from __future__ import annotations

import enum
import io
import os
import re

from ... import messages as m
from ... import t
from .blocks import IndentChecker, parseBlockStream
from .nodes import (
    Doctype,
    EndTag,
    ParserNode,
    RawElement,
    RawText,
    SafeText,
    SelfClosedTag,
    StartTag,
    Text,
)
from .parser import (
    POSSIBLE_NODE_START_CHARS,
    ExtractedMetadata,
    closeOpenElements,
    debugNode,
    extractMetadata,
    nodesFromStream,
)
from .stream import ParseConfig, Stream


def nodesFromHtml(
    data: str,
    config: ParseConfig,
    startLine: int = 1,
    closeElements: bool = False,
    context: str | StartTag | t.ElementT | None = None,
    *,
    blockMarkdown: bool = False,
) -> t.Generator[ParserNode, None, None]:
    """Parse `data` into a stream of `ParserNode`s, optionally running block Markdown and closing open elements."""
    s = Stream(data, startLine=startLine, config=config, blockParser=parseBlockStream)
    if blockMarkdown and config.markdownBlock:
        yield from parseBlockStream(s)
    else:
        yield from nodesFromStream(s, 0)
    if closeElements:
        # FIXME: This start= value isn't accurate, but nodesFromStream
        # doesn't give stream offsets...
        yield from closeOpenElements(s, start=None, context=context)
    if blockMarkdown and config.markdownBlock and data.endswith("\n"):
        # parseBlockStream joins blocks with "\n" without a trailing newline; preserve one if the input ended with one.
        yield RawText(text="\n")


def initialDocumentParse(
    text: str,
    config: ParseConfig,
    startLine: int = 1,
    indentChecker: IndentChecker | None = None,
    metadataSpans: dict[int, int] | None = None,
) -> list[ParserNode]:
    """Run the full single-pass document parse, expanding block/inline syntax, checking indentation, and closing tags."""
    # Adds `bs-line-number` / `bs-parse-context` via the emitted StartTags,
    # converts block Markdown (when enabled) and inline Bikeshed-isms into HTML,
    # records mixed-indentation lints when `indentChecker` is provided,
    # auto-skips pre-extracted metadata block spans (flagging any late metadata blocks as fatal errors),
    # and logs errors for any elements left open at EOF.

    s = Stream(
        text,
        startLine=startLine,
        config=config,
        blockParser=parseBlockStream,
        metadataSpans=metadataSpans,
    )
    if config.markdownBlock:
        nodes = parseBlockStream(s, indentChecker=indentChecker)
        nodes.extend(closeOpenElements(s, start=None, context=None))
        if text.endswith("\n"):
            nodes.append(RawText(text="\n"))
    else:
        nodes = list(nodesFromStream(s, 0))
        if indentChecker is not None:
            indentChecker.checkNodes(nodes)
        nodes.extend(closeOpenElements(s, start=None, context=None))
        if nodes:
            nodes.append(RawText(text="\n"))
    return nodes


def strFromNodes(nodes: t.Iterable[ParserNode]) -> str:
    """Serialize an iterable of `ParserNode`s back into an HTML string."""
    return "".join(str(node) for node in nodes)


def linesFromNodes(nodes: t.Iterable[ParserNode]) -> list[str]:
    """Serialize an iterable of `ParserNode`s and split the result on newlines."""
    return strFromNodes(nodes).split("\n")


def debugNodes(nodes: t.Iterable[ParserNode]) -> list[ParserNode]:
    """Print a debug representation of each node and return the materialized list."""
    nodes = list(nodes)
    print("=" * 50)  # noqa: T201
    for node in nodes:
        print(debugNode(node))  # noqa: T201
    return nodes


def parseLines(
    textLines: list[str],
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None,
    startLine: int = 1,
    closeElements: bool = False,
) -> list[str]:
    """Parse a list of source lines into HTML, preserving whether lines end with `\\n`."""
    if len(textLines) == 0:
        return textLines
    endingWithNewline = textLines[0].endswith("\n")
    if endingWithNewline:
        text = "".join(textLines)
    else:
        text = "\n".join(textLines)
    parsedNodes = list(nodesFromHtml(text, config, startLine=startLine, closeElements=closeElements, context=context))
    parsedLines = linesFromNodes(parsedNodes)
    if endingWithNewline:
        parsedLines = [x + "\n" for x in parsedLines]

    return parsedLines


def parseText(
    text: str,
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None,
    startLine: int = 1,
    closeElements: bool = False,
) -> str:
    """Parse `text` through the inline HTML/Bikeshed parser and return the serialized HTML string."""
    return strFromNodes(
        nodesFromHtml(text, config, startLine=startLine, closeElements=closeElements, context=context),
    )


def parseTitle(
    text: str,
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None = None,
    startLine: int = 1,
) -> str:
    """Parse `text` for a `<title>` element, stripping all tag nodes so only text remains."""
    nodes = nodesFromHtml(text, config, startLine=startLine, context=context)
    return strFromNodes(n for n in nodes if isinstance(n, Text))
