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
from .parser import POSSIBLE_NODE_START_CHARS, closeOpenElements, debugNode, nodesFromStream
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
    s = Stream(data, startLine=startLine, config=config)
    if blockMarkdown and config.markdownBlock:
        yield from parseBlockStream(s)
    else:
        yield from nodesFromStream(s, 0)
    if closeElements:
        # FIXME: This start= value isn't accurate, but nodesFromStream
        # doesn't give stream offsets...
        yield from closeOpenElements(s, start=None, context=context)
    if blockMarkdown and config.markdownBlock and data.endswith("\n"):
        yield RawText(text="\n")


def initialDocumentParse(
    text: str,
    config: ParseConfig,
    startLine: int = 1,
    indentChecker: IndentChecker | None = None,
) -> list[ParserNode]:
    # Does a full document parse in a single pass:
    # * adds `bs-line-number` and `bs-parse-context` attributes, for error messages
    # * converts block-level Markdown (when enabled) and inline Bikeshed-isms into HTML
    # * records mixed-indentation lints when `indentChecker` is provided
    # * closes any left-open elements, logging an error

    s = Stream(text, startLine=startLine, config=config)
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
    return "".join(str(node) for node in nodes)


def linesFromNodes(nodes: t.Iterable[ParserNode]) -> list[str]:
    return strFromNodes(nodes).split("\n")


def debugNodes(nodes: t.Iterable[ParserNode]) -> list[ParserNode]:
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
    # Runs a list of lines thru the parser,
    # returning another list of lines.

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
    # Just runs the text thru the parser.
    return strFromNodes(
        nodesFromHtml(text, config, startLine=startLine, closeElements=closeElements, context=context),
    )


def parseTitle(
    text: str,
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None = None,
    startLine: int = 1,
) -> str:
    # Parses the text, but removes any tags from the content,
    # as they'll just show up as literal text in <title>.
    nodes = nodesFromHtml(text, config, startLine=startLine, context=context)
    return strFromNodes(n for n in nodes if isinstance(n, Text))
