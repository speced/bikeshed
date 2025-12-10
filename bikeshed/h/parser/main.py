# pylint: skip-file
from __future__ import annotations

import enum
import io
import os
import re

from ... import constants, t
from ... import messages as m
from .nodes import (
    Comment,
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
) -> t.Generator[ParserNode, None, None]:
    s = Stream(data, startLine=startLine, config=config)
    yield from nodesFromStream(s, 0)
    if closeElements:
        # FIXME: This start= value isn't accurate, but nodesFromStream
        # doesn't give stream offsets...
        yield from closeOpenElements(s, start=None, context=context)


def initialDocumentParse(
    text: str,
    config: ParseConfig,
    startLine: int = 1,
) -> list[ParserNode]:
    # Just do a document parse.
    # * adds `bs-line-number` and `bs-parse-context` attributes, for error messages
    # * converts any inline Bikeshed-isms into HTML (autolinks, markdown, etc)
    # * blank out comments so they can't interfere with other passes
    # * close any left-open elements, logging an error
    # * check if there are any html/head/body elements and error

    s = Stream(text, startLine=startLine, config=config)
    nodes = list(nodesFromStream(s, 0))
    nodes.extend(closeOpenElements(s, start=None, context=None))
    return nodes


def strFromNodes(nodes: t.Iterable[ParserNode], withIlcc: bool = False) -> t.EarlyParsedHtmlStr:
    strs = []
    ilcc = constants.incrementLineCountChar
    dlcc = constants.decrementLineCountChar
    for node in nodes:
        if isinstance(node, Comment):
            # Serialize comments as a standardized, recognizable sequence
            # so Markdown processing can ignore them better.
            strs.append(constants.bsComment)
            if withIlcc:
                strs.append(ilcc * node.data.count("\n"))
            continue
        s = str(node)
        if withIlcc:
            diff = node.height - s.count("\n")
            if diff > 0:
                s += ilcc * diff
            elif diff < 0:
                s += dlcc * -diff
        strs.append(s)
    return t.EarlyParsedHtmlStr("".join(strs))


def linesFromNodes(nodes: t.Iterable[ParserNode]) -> list[t.EarlyParsedHtmlStr]:
    return t.cast("list[t.EarlyParsedHtmlStr]", strFromNodes(nodes).split("\n"))


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
) -> list[t.EarlyParsedHtmlStr]:
    # Runs a list of lines thru the parser,
    # returning another list of lines.

    if len(textLines) == 0:
        return t.cast("list[t.EarlyParsedHtmlStr]", textLines)
    endingWithNewline = textLines[0].endswith("\n")
    if endingWithNewline:
        text = "".join(textLines)
    else:
        text = "\n".join(textLines)
    parsedNodes = list(nodesFromHtml(text, config, startLine=startLine, closeElements=closeElements, context=context))
    parsedLines = linesFromNodes(parsedNodes)
    if endingWithNewline:
        parsedLines = [t.EarlyParsedHtmlStr(x + "\n") for x in parsedLines]

    return parsedLines


def parseText(
    text: str,
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None,
    startLine: int = 1,
    closeElements: bool = False,
) -> t.EarlyParsedHtmlStr:
    # Just runs the text thru the parser.
    return strFromNodes(
        nodesFromHtml(text, config, startLine=startLine, closeElements=closeElements, context=context),
    )


def parseTitle(
    text: str,
    config: ParseConfig,
    context: str | StartTag | t.ElementT | None = None,
    startLine: int = 1,
) -> t.EarlyParsedHtmlStr:
    # Parses the text, but removes any tags from the content,
    # as they'll just show up as literal text in <title>.
    nodes = nodesFromHtml(text, config, startLine=startLine, context=context)
    return strFromNodes(n for n in nodes if isinstance(n, Text))
