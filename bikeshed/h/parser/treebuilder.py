from __future__ import annotations

import re

import lxml.sax

from ... import messages as m
from ... import t
from .. import elements
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    ParserNodeT,
    RawElement,
    RawText,
    SafeElement,
    SafeText,
    SelfClosedTag,
    StartTag,
    escapeAttr,
    sortAttrs,
)

# This module turns a stream of already-parsed ParserNodes into an LXML tree
# via the SAX API, handling auto-closing tags and head/body placement.


def buildDocument(nodes: t.Iterable[ParserNode]) -> tuple[t.ElementT, t.ElementT, t.ElementT]:
    builder = TreeBuilder()
    consumeNodes(nodes, builder)
    return builder.finish()


def buildFragment(nodes: t.Iterable[ParserNode]) -> t.ElementT:
    builder = TreeBuilder()
    builder.startTag("bs-fragment-container", {})
    consumeNodes(nodes, builder)
    builder.endTag("bs-fragment-container")
    _, _, body = builder.finish()
    return body[0]


_NAMED_ESCAPES: dict[str, str] = {
    "lt": "<",
    "amp": "&",
    "apos": "'",
    "quot": '"',
}
_ESCAPE_RE = re.compile(r"&(?:#x([^;]*);|#([^;]*);|(lt|amp|apos|quot);)")


def _replaceEscape(match: re.Match[str]) -> str:
    if (hexDigits := match.group(1)) is not None:
        try:
            return chr(int(hexDigits, 16))
        except ValueError:
            m.die(f"Couldn't parse the HTML escape '{match.group(0)}'.")
            return match.group(0)
    if (decDigits := match.group(2)) is not None:
        try:
            return chr(int(decDigits))
        except ValueError:
            m.die(f"Couldn't parse the HTML escape '{match.group(0)}'.")
            return match.group(0)
    return _NAMED_ESCAPES[match.group(3)]


def unescapeHtml(text: str) -> str:
    if "&" not in text:
        return text
    return _ESCAPE_RE.sub(_replaceEscape, text)


def prepareAttrs(node: StartTag | SelfClosedTag) -> dict[str, str]:
    rawAttrs = node.attrs
    addLineInfo = node.s is None or not node.s.config.rawHtml
    if addLineInfo and "bs-line-number" not in rawAttrs and node.loc:
        rawAttrs["bs-line-number"] = escapeAttr(node.loc)
    if addLineInfo and "bs-parse-context" not in rawAttrs and node.context:
        rawAttrs["bs-parse-context"] = escapeAttr(node.context)
    if node.classes:
        rawAttrs["class"] = escapeAttr(" ".join(sorted(node.classes)))
    attrs: dict[str, str] = {}
    for k, v in sortAttrs(rawAttrs):
        if ":" in k:
            _, _, k = k.partition(":")
        if "&" in v:
            attrs[k] = unescapeHtml(v)
        else:
            attrs[k] = v
    return attrs


def consumeNodes(nodes: t.Iterable[ParserNode], builder: TreeBuilder) -> None:
    for node in nodes:
        node = t.cast(ParserNodeT, node)
        if isinstance(node, RawText):
            if node.text:
                builder.characters(unescapeHtml(node.text))
        elif isinstance(node, SafeText):
            if node.text:
                builder.characters(node.text)
        elif isinstance(node, StartTag):
            attrs = prepareAttrs(node)
            if node.tag in elements.VOID_ELEMENTS:
                builder.selfClosedTag(node.tag, attrs)
            else:
                builder.startTag(node.tag, attrs)
        elif isinstance(node, EndTag):
            builder.endTag(node.tag)
        elif isinstance(node, SelfClosedTag):
            builder.selfClosedTag(node.tag, prepareAttrs(node))
        elif isinstance(node, (RawElement, SafeElement)):
            builder.startTag(node.tag, prepareAttrs(node.startTag))
            if node.data:
                builder.characters(node.data)
            builder.endTag(node.tag)
        elif isinstance(node, (Comment, Doctype)):
            pass
        else:
            t.assert_never(node)


# TreeBuilder holds an lxml sax handler for constructing a document from
# ParserNodes, plus enough tag context to ensure the document structure is
# reasonably correct per HTML's rules.
# Note that tagStack never holds the html/head/body element; those are
# handled specially instead.
class TreeBuilder:
    _handler: t.Any  # Ugh, lxml doesn't give this a type
    _tagStack: list[str]
    _inHead: bool
    _htmlAttrs: list[dict[str, str]]
    _headAttrs: list[dict[str, str]]
    _bodyAttrs: list[dict[str, str]]

    def __init__(self) -> None:
        self._handler = lxml.sax.ElementTreeContentHandler()
        self._htmlAttrs = []
        self._headAttrs = []
        self._bodyAttrs = []
        self._inHead = True
        self._tagStack = []
        self._handler.startElement("html", {})
        self._handler.startElement("head", {})

    def finish(self) -> tuple[t.ElementT, t.ElementT, t.ElementT]:
        if self._inHead:
            self.startBody()
        self.autoCloseAll()
        self._handler.endElement("body")
        self._handler.endElement("html")
        html = self._handler.etree.getroot()
        head = html[0]
        body = html[1]
        assert head is not None
        assert body is not None
        applyAttrs(html, self._htmlAttrs)
        applyAttrs(head, self._headAttrs)
        applyAttrs(body, self._bodyAttrs)
        return html, head, body

    def startTag(self, tagName: str, attrs: dict[str, str]) -> None:
        if tagName == "html":
            if attrs:
                self._htmlAttrs.append(attrs)
            return
        if tagName == "head":
            if attrs:
                self._headAttrs.append(attrs)
            return
        if self._inHead and tagName not in elements.HEAD_ELEMENTS:
            self.startBody()
        if tagName == "body":
            if attrs:
                self._bodyAttrs.append(attrs)
            return
        self.autoCloseStart(tagName)
        if tagName == "tr" and self._tagStack and self._tagStack[-1] == "table":
            self.startTag("tbody", {})
        try:
            self._handler.startElement(tagName, attrs)
        except ValueError:
            self._handler.startElement(tagName)
            m.die(
                f"PROGRAMMING ERROR: A <{tagName}> start tag ended up with invalid attributes. Please report this!\n  (Element was still added to the tree, but without attributes.)\n  {attrs!r}",
                lineNum=attrs.get("bs-line-number"),
            )
        self.pushEl(tagName)

    def endTag(self, tagName: str) -> None:
        if self._tagStack and tagName == self._tagStack[-1]:
            # Simple case
            self.popEl()
            self._handler.endElement(tagName)
            return
        if self._inHead and tagName in elements.HEAD_ELEMENTS:
            self.autoCloseEnd(tagName)
            self.popEl()
            self._handler.endElement(tagName)
            return
        self.startBody()
        if tagName in ("html", "head", "body"):
            self.autoCloseAll()
            return
        if tagName in elements.HEADING_ELEMENTS and elements.HEADING_ELEMENTS.intersection(self._tagStack):
            # People regularly close headings with the wrong tag. They can't nest,
            # so when I see a heading end tag, just close whatever heading is open.
            self.virtualClose(elements.HEADING_ELEMENTS)
            return
        if tagName in self._tagStack:
            self.autoCloseEnd(tagName)
            self.popEl()
            self._handler.endElement(tagName)

    def selfClosedTag(self, tagName: str, attrs: dict[str, str]) -> None:
        self.startTag(tagName, attrs)
        self.endTag(tagName)

    def characters(self, chars: str) -> None:
        if self._inHead and not self._tagStack and chars.strip() != "":
            self.startBody()
        self._handler.characters(chars)

    def pushEl(self, tagName: str) -> None:
        self._tagStack.append(tagName)

    def popEl(self) -> None:
        self._tagStack.pop()

    def startBody(self) -> None:
        # I saw something that needs to live in the <body>
        if self._inHead:
            self._inHead = False
            self.autoCloseAll()
            self._handler.endElement("head")
            self._handler.startElement("body")

    def autoCloseAll(self) -> None:
        # Close all currently-open elements
        while self._tagStack:
            tag = self._tagStack.pop()
            self._handler.endElement(tag)

    def autoCloseEnd(self, tagName: str) -> None:
        # auto-close all tags still open until you hit the one that's actually being closed
        while self._tagStack[-1] != tagName:
            endTagName = self._tagStack.pop()
            self._handler.endElement(endTagName)

    def autoCloseStart(self, tagName: str) -> None:
        # auto-close special tags who get closed by another tag opening
        if tagName in elements.AUTO_CLOSE_P_START_ELEMENTS:
            self.virtualClose(["p"])
        if tagName == "li":
            self.virtualClose(["li"], ["ol", "ul"])
        elif tagName in ("dt", "dd"):
            self.virtualClose(["dt", "dd"], ["dl"])
        elif tagName == "option":
            self.virtualClose(["option"])
        elif tagName == "optgroup":
            self.virtualClose(["option"])
            self.virtualClose(["optgroup"])
        elif tagName in ("td", "th"):
            self.virtualClose(["td", "th"], ["table"])
        elif tagName == "tr":
            self.virtualClose(["td", "th"], ["table"])
            self.virtualClose(["tr"], ["table"])
            self.virtualClose(["caption", "colgroup"], ["table"])
        elif tagName in ("thead", "tbody", "tfoot"):
            self.virtualClose(["td", "th"], ["table"])
            self.virtualClose(["tr"], ["table"])
            self.virtualClose(["thead", "tbody", "tfoot", "caption", "colgroup"], ["table"])
        elif tagName in ("caption", "colgroup"):
            self.virtualClose(["td", "th"], ["table"])
            self.virtualClose(["tr"], ["table"])
            self.virtualClose(["thead", "tbody", "tfoot", "caption", "colgroup"], ["table"])
        elif tagName == "col":
            self.virtualClose(["td", "th"], ["table"])
            self.virtualClose(["tr"], ["table"])
            self.virtualClose(["thead", "tbody", "tfoot", "caption"], ["table"])
        elif tagName in ("rb", "rtc"):
            self.virtualClose(["rb", "rp", "rt"], ["ruby"])
            self.virtualClose(["rtc"], ["ruby"])
        elif tagName in ("rp", "rt"):
            self.virtualClose(["rb", "rp", "rt"], ["ruby"])

    def virtualClose(self, tags: list[str] | frozenset[str], scopes: list[str] | None = None) -> None:
        # If tags exist, below a scopes, pop everything up and and including the tags.
        i = len(self._tagStack) - 1
        while i >= 0:
            if self._tagStack[i] in tags:
                # Found the tag to auto-close, pop everything up to and including it
                closers = self._tagStack[i:]
                self._tagStack = self._tagStack[0:i]
                for closeTagName in closers[::-1]:
                    self._handler.endElement(closeTagName)
                return
            elif scopes and self._tagStack[i] in scopes:
                # Found a scoping element without finding the tag, just stop
                return
            else:
                # Neither the tag nor the scope, keep looking
                i -= 1


def applyAttrs(el: t.ElementT, attrList: list[dict[str, str]]) -> t.ElementT:
    for attrs in attrList:
        for k, v in attrs.items():
            if k == "class" and el.get("class"):
                el.set(k, el.get(k, "") + " " + v)
            else:
                el.set(k, v)
    return el
