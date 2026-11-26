"""Bounded front-of-document metadata block and fallback `<h1>` extraction."""

from __future__ import annotations

import dataclasses
import io
import re

from ... import messages as m
from .. import elements
from . import html, markdown
from .nodes import RawElement, StartTag
from .stream import ParseConfig, Stream

_METADATA_SCAN_RE = re.compile(
    r"<!--|<(?P<tag>pre|xmp|script|style|h1)(?=[\t\n\x0c />])|^[ \t]*(?:`{3,}|~{3,})",
    re.I | re.M,
)
_H1_LINE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>")


@dataclasses.dataclass
class ExtractedMetadata:
    """Metadata blocks and optional fallback `<h1>` title extracted from near the start of a document."""

    blocks: list[RawElement] = dataclasses.field(default_factory=list)
    spans: dict[int, int] = dataclasses.field(default_factory=dict)
    h1Title: str | None = None
    h1Line: int | None = None


def extractMetadata(text: str, config: ParseConfig | None = None) -> ExtractedMetadata:
    """Scan near the start of `text` using the HTML/Markdown parser primitives to extract metadata blocks.

    Skips comments, `<script>`, `<style>`, non-metadata `<xmp>`, other `<pre>` datablocks, and fenced code
    blocks so embedded `<pre class=metadata>` examples are ignored. Only scans up to `config.metadataScanLimit`
    non-metadata characters from the start of the document; any metadata block further down is flagged during
    the main parse.
    """
    result = ExtractedMetadata()
    rawConfig = ParseConfig(rawHtml=True) if config is None else dataclasses.replace(config, rawHtml=True)
    s = Stream(text, config=rawConfig)
    chars = s.chars
    length = s.length
    limit = s.config.metadataScanLimit
    i = 0

    with m.newMessageState(io.StringIO(), dieOn="nothing", silent=True) as savedState:
        while i < length and i < limit:
            match = _METADATA_SCAN_RE.search(chars, i)
            if match is None or match.start() >= limit:
                break
            pos = match.start()
            tag = match.group("tag")

            if tag is None:
                if chars.startswith("<!--", pos):
                    comment, nextI, _ = html.parseComment(s, pos)
                    i = nextI if comment is not None else match.end()
                else:
                    fenceStart = pos
                    while fenceStart < length and chars[fenceStart] in (" ", "\t"):
                        fenceStart += 1
                    fence, nextI, _ = markdown.parseFencedCodeBlock(s, fenceStart)
                    i = nextI if fence is not None else match.end()
                continue

            tagLower = tag.lower()
            if tagLower == "h1":
                if result.h1Title is None and s.precedingTextOnLine(pos).strip() == "":
                    lineEnd = chars.find("\n", pos)
                    if lineEnd == -1:
                        lineEnd = length
                    h1Match = _H1_LINE_RE.match(chars, pos, lineEnd)
                    if h1Match is not None:
                        result.h1Title = h1Match.group(1)
                        result.h1Line = s.line(pos)
                        i = h1Match.end()
                        continue
                i = match.end()
                continue

            startTag, tagEnd, _ = html.parseStartTag(s, pos)
            if not isinstance(startTag, StartTag):
                i = tagEnd if startTag is not None else match.end()
                continue

            if tagLower in ("pre", "xmp") and html.isMetadataBlock(startTag) and pos == s.currentLineStart(pos):
                with m.usingMessageState(savedState):
                    el, nextI, _ = html.parseMetadataBlockToEnd(s, pos, startTag, tagEnd)
                if el is not None:
                    result.blocks.append(el)
                    result.spans[el.start] = el.end
                    limit += el.end - el.start
                    i = nextI
                    continue

            if tagLower in elements.RAW_ELEMENTS:
                _, i, _ = html.parseRawElementToEnd(s, tagEnd, tagLower)
            elif tagLower == "pre" and html.isDatablock(startTag, s.loc(tagEnd)):
                _, nextI, _ = html.parseDatablockPreToEnd(s, tagEnd)
                i = nextI if nextI > tagEnd else tagEnd
            else:
                i = tagEnd

    return result
