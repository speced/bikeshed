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
from .stream import ParseConfig, Stream


def nodesFromHtml(data: str, config: ParseConfig, startLine: int = 1) -> t.Generator[ParserNode, None, None]:
    s = Stream(data, startLine=startLine, config=config)
    yield from nodesFromStream(s, 0)


def initialDocumentParse(
    text: str,
    config: ParseConfig,
    startLine: int = 1,
) -> tuple[list[ParserNode], list[StartTag]]:
    # Just do a document parse.
    # * adds `bs-line-number` and `bs-parse-context` attributes, for error messages
    # * converts any inline Bikeshed-isms into HTML (autolinks, markdown, etc)
    # * blank out comments so they can't interfere with other passes
    # * close any left-open elements, logging an error
    # * check if there are any html/head/body elements and error

    s = Stream(text, startLine=startLine, config=config)
    nodes = list(nodesFromStream(s, 0))
    nodes.extend(closeOpenElements(s))
    for node in nodes:
        if isinstance(node, StartTag) and node.tag in ("html", "head", "body"):
            return extractStructuralNodes(nodes)
    return nodes, []


def extractStructuralNodes(nodes: list[ParserNode]) -> tuple[list[ParserNode], list[StartTag]]:
    # The html5lib parser properly merged html/head/body elements together,
    # but lxml parser doesn't. So I need to instead yank those tags out of
    # the document, so they can be manually merged in later and won't screw
    # with parsing otherwise.
    normalNodes: list[ParserNode] = []
    structuralNodes: list[StartTag] = []
    for node in nodes:
        if isinstance(node, StartTag) and node.tag in ("html", "head", "body"):
            structuralNodes.append(node)
        elif isinstance(node, EndTag) and node.tag in ("html", "head", "body"):
            pass
        else:
            normalNodes.append(node)
    return normalNodes, structuralNodes


def closeOpenElements(s: Stream) -> list[EndTag]:
    nodes = []
    i = s._len
    if s.openEls.tags and s.openEls.tags[-1].startTag.tag == "p":
        # A final open <p> is fine, it's meant to auto-close itself
        entry = s.openEls.popEntry()
        nodes.append(EndTag.fromStream(s, i, i, entry.startTag))
    # If there's still stuff open, tho, that's a problem
    if s.openEls.tags:
        if len(s.openEls.tags) == 1:
            entry = s.openEls.tags[0]
            msg = f"<{entry.startTag.tag}> element was still open at the end of your document."
            m.die(msg, lineNum=entry.startTag.loc)
        else:
            msg = f"{len(s.openEls.tags)} elements were still open at the end of your document.\nOpen tags: {', '.join(s.openEls.printOpenTags())}"
            m.die(msg)
        while s.openEls.tags:
            entry = s.openEls.popEntry()
            nodes.append(EndTag.fromStream(s, i, i, entry.startTag))
    return nodes


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
        print("------")  # noqa: T201
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
