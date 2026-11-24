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
    """Build a full LXML document from `nodes` and return `(html, head, body)`."""
    builder = TreeBuilder()
    consumeNodes(nodes, builder)
    return builder.finish()


def buildFragment(nodes: t.Iterable[ParserNode]) -> t.ElementT:
    """Build an LXML container element (`<bs-fragment-container>`) holding parsed `nodes` in body context."""
    builder = TreeBuilder()
    # Wrapping in a non-head tag immediately transitions into <body> so fragment nodes stay together.
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
    """Decode a single numeric or basic named HTML entity match."""
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
    """Unescape numeric and basic named (`&lt;`, `&amp;`, `&apos;`, `&quot;`) HTML character references in `text`."""
    if "&" not in text:
        return text
    return _ESCAPE_RE.sub(_replaceEscape, text)


def prepareAttrs(node: StartTag | SelfClosedTag) -> dict[str, str]:
    """Finalize, sort, normalize, and unescape a tag node's attributes for LXML SAX."""
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
        # LXML's SAX handler rejects undeclared XML namespace prefixes, so strip any `prefix:`.
        if ":" in k:
            _, _, k = k.partition(":")
        if "&" in v:
            attrs[k] = unescapeHtml(v)
        else:
            attrs[k] = v
    return attrs


def consumeNodes(nodes: t.Iterable[ParserNode], builder: TreeBuilder) -> None:
    """Feed each `ParserNode` into `builder` as SAX-like tree events."""
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


class TreeBuilder:
    """Constructs an LXML document from parser events via SAX, handling HTML head/body placement and auto-closing."""

    # Note that `_tagStack` never holds html/head/body; those are opened eagerly and
    # have their attributes merged onto the real elements in `finish()`.
    _handler: t.Any  # Ugh, lxml doesn't give this a type
    _tagStack: list[str]
    _inHead: bool
    _htmlAttrs: list[dict[str, str]]
    _headAttrs: list[dict[str, str]]
    _bodyAttrs: list[dict[str, str]]

    def __init__(self) -> None:
        """Initialize the SAX tree handler with an open `<html><head>` skeleton."""
        self._handler = lxml.sax.ElementTreeContentHandler()
        self._htmlAttrs = []
        self._headAttrs = []
        self._bodyAttrs = []
        self._inHead = True
        self._tagStack = []
        self._handler.startElement("html", {})
        self._handler.startElement("head", {})

    def finish(self) -> tuple[t.ElementT, t.ElementT, t.ElementT]:
        """Close all open tags, apply deferred root attributes, and return `(html, head, body)`."""
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
        """Emit an opening tag, handling root-element deferral, head-to-body transitions, and HTML auto-closing."""
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
        """Emit a closing tag, auto-closing intermediate open elements when needed."""
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
        if tagName == "li":
            # Per HTML list-item scoping, </li> cannot cross an enclosing <ul>/<ol>.
            self.virtualClose(["li"], ["ol", "ul"])
            return
        if tagName in ("dt", "dd"):
            # Per HTML scoping, </dt>/</dd> cannot cross an enclosing <dl>.
            self.virtualClose([tagName], ["dl"])
            return
        if tagName in self._tagStack:
            self.autoCloseEnd(tagName)
            self.popEl()
            self._handler.endElement(tagName)

    def selfClosedTag(self, tagName: str, attrs: dict[str, str]) -> None:
        """Emit a start tag immediately followed by its matching end tag."""
        self.startTag(tagName, attrs)
        self.endTag(tagName)

    def characters(self, chars: str) -> None:
        """Append character data, transitioning from `<head>` to `<body>` on non-whitespace text."""
        if self._inHead and not self._tagStack and chars.strip() != "":
            self.startBody()
        self._handler.characters(chars)

    def pushEl(self, tagName: str) -> None:
        """Push `tagName` onto the open-element stack."""
        self._tagStack.append(tagName)

    def popEl(self) -> None:
        """Pop the top tag name from the open-element stack."""
        self._tagStack.pop()

    def startBody(self) -> None:
        """Transition from `<head>` to `<body>`, closing any remaining head elements."""
        if self._inHead:
            self._inHead = False
            self.autoCloseAll()
            self._handler.endElement("head")
            self._handler.startElement("body")

    def autoCloseAll(self) -> None:
        """Close all elements currently on `_tagStack`."""
        while self._tagStack:
            tag = self._tagStack.pop()
            self._handler.endElement(tag)

    def autoCloseEnd(self, tagName: str) -> None:
        """Close all open elements above `tagName` on `_tagStack`."""
        while self._tagStack[-1] != tagName:
            endTagName = self._tagStack.pop()
            self._handler.endElement(endTagName)

    def autoCloseStart(self, tagName: str) -> None:
        """Close any HTML elements implicitly terminated by opening `tagName`."""
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
        """If any tag in `tags` is open within `scopes`, close it and everything nested inside it."""
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
    """Merge a sequence of attribute dicts onto `el`, concatenating `class` values."""
    for attrs in attrList:
        for k, v in attrs.items():
            if k == "class" and el.get("class"):
                el.set(k, el.get(k, "") + " " + v)
            else:
                el.set(k, v)
    return el
