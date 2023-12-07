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
from .parser import POSSIBLE_NODE_START_CHARS, nodesFromStream
from .stream import Failure, ParseConfig, ParseFailure, Result, Stream


def nodesFromHtml(data: str, config: ParseConfig, startLine: int = 1) -> t.Generator[ParserNode, None, None]:
    s = Stream(data, startLine=startLine, config=config)
    yield from nodesFromStream(s, 0)


def initialDocumentParse(text: str, config: ParseConfig, startLine: int = 1) -> list[ParserNode]:
    # Just do a document parse.
    # This will add `bs-line-number` attributes,
    # normalize any difficult shorthands
    # (ones that look like tags, or that contain raw text),
    # and blank out comments.

    return list(nodesFromHtml(text, config, startLine=startLine))


def strFromNodes(nodes: t.Iterable[ParserNode], withIlcc: bool = False) -> str:
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
    return "".join(strs)


def linesFromNodes(nodes: t.Iterable[ParserNode]) -> list[str]:
    return strFromNodes(nodes).split("\n")


def debugNodes(nodes: t.Iterable[ParserNode]) -> list[ParserNode]:
    nodes = list(nodes)
    for node in nodes:
        print(repr(node))  # noqa: T201
        print(repr(strFromNodes([node], withIlcc=True)))  # noqa: T201
    return nodes


def parseLines(textLines: list[str], config: ParseConfig, startLine: int = 1) -> list[str]:
    # Runs a list of lines thru the parser,
    # returning another list of lines.

    if len(textLines) == 0:
        return textLines
    endingWithNewline = textLines[0].endswith("\n")
    if endingWithNewline:
        text = "".join(textLines)
    else:
        text = "\n".join(textLines)
    parsedLines = strFromNodes(nodesFromHtml(text, config, startLine=startLine)).split("\n")
    if endingWithNewline:
        parsedLines = [x + "\n" for x in parsedLines]

    return parsedLines


def parseText(text: str, config: ParseConfig, startLine: int = 1) -> str:
    # Just runs the text thru the parser.
    return strFromNodes(nodesFromHtml(text, config, startLine=startLine))


def parseTitle(text: str, config: ParseConfig, startLine: int = 1) -> str:
    # Parses the text, but removes any tags from the content,
    # as they'll just show up as literal text in <title>.
    nodes = nodesFromHtml(text, config, startLine=startLine)
    return strFromNodes(n for n in nodes if isinstance(n, Text))
