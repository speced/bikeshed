from __future__ import annotations

import lxml.sax

from ... import messages as m
from ... import t

# This module is an *incredibly simple* HTML parser,
# whose sole purpose is to parse HTML that's already been Bikeshed-parsed
# (and thus is serialized to a simple, predictable structure)
# and generate an LXML tree from it via the SAX api.
# It *cannot* handle real-world HTML.
# The only "incorrect" HTML it does something fancy with is auto-closing tags.


def parseDocument(text: str) -> tuple[t.ElementT, t.ElementT, t.ElementT]:
    stream = SimpleStream(text)
    return parse(stream, 0)


VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "command",
    "embed",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "meta",
    "param",
    "source",
    "track",
}

HEAD_ELEMENTS = {
    "title",
    "meta",
    "link",
    "script",
    "style",
}

HEADING_ELEMENTS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}


def parse(s: SimpleStream, start: int) -> tuple[t.ElementT, t.ElementT, t.ElementT]:
    i = start
    segmentStart = i
    while not s.eof(i):
        if s[i] == "<":
            if segmentStart < i:
                s.characters(s.slice(segmentStart, i))
            if s[i + 1] == "/":
                i = parseEndTag(s, i)
            elif s[i + 1] == "!":
                i = parseDoctype(s, i)
            else:
                i = parseStartTag(s, i)
            segmentStart = i
        elif s[i] == "&":
            if segmentStart < i:
                s.characters(s.slice(segmentStart, i))
            escape, i = parseEscape(s, i)
            s.characters(escape)
            segmentStart = i
        else:
            i += 1
    if segmentStart < i:
        s.characters(s.slice(segmentStart, i))
    return s.finish()


def parseDoctype(s: SimpleStream, start: int) -> int:
    i = start + 2  # skip the <!
    while s[i] != ">":
        i += 1
    return i + 1


def parseStartTag(s: SimpleStream, start: int) -> int:
    i = start + 1  # skip the <

    tagStart = i
    while s[i] not in (" ", ">", "/"):
        i += 1
    tagName = s.slice(tagStart, i)

    attrs, i = parseAttributeList(s, i)

    while s[i] == " ":
        i += 1

    if s[i] == "/" and s[i + 1] == ">":
        s.selfClosedTag(tagName, attrs)
        return i + 2

    # Else it's >
    if tagName in VOID_ELEMENTS:
        s.selfClosedTag(tagName, attrs)
    else:
        s.startTag(tagName, attrs)
    return i + 1


def parseEndTag(s: SimpleStream, start: int) -> int:
    i = start + 2  # skip the </
    tagStart = i
    while s[i] != ">":
        i += 1
    tagName = s.slice(tagStart, i)
    s.endTag(tagName)
    return i + 1


def parseAttributeList(s: SimpleStream, start: int) -> tuple[dict[str, str], int]:
    i = start
    attrs: dict[str, str] = {}
    while True:
        if s.eof(i):
            break
        while s[i] == " ":
            i += 1
        if s[i] == ">":
            break
        attrName, attrValue, i = parseAttribute(s, i)
        attrs[attrName] = attrValue
    return attrs, i


def parseAttribute(s: SimpleStream, start: int) -> tuple[str, str, int]:
    i = start
    while s[i] != "=":
        i += 1

    attrName = s.slice(start, i)
    if ":" in attrName:
        _, _, attrName = attrName.partition(":")
    i += 2  # skip the ="
    segmentStart = i
    attrValue = ""
    while s[i] != '"':
        if s[i] == "&":  # &#0000;
            attrValue += s.slice(segmentStart, i)
            escape, i = parseEscape(s, i)
            attrValue += escape
            segmentStart = i
            continue
        else:
            i += 1
    attrValue += s.slice(segmentStart, i)
    i += 1  # skip the "
    return (attrName, attrValue, i)


def parseEscape(s: SimpleStream, start: int) -> tuple[str, int]:
    i = start + 1  # skip the &
    if s[i] == "#":
        i += 1
        digitStart = i
        while s[i] != ";":
            i += 1
        escape = chr(int(s.slice(digitStart, i)))
        i += 1  # skip the ;
        return escape, i
    else:
        m.die(f"Whoops, I see a different escape at {i}: {s.slice(start, start+10)}")
        return "&", i


# SimpleStream holds the text to be parsed, and an lxml sax handler
# for constructing a document from that text, plus enough tag context
# to ensure the document structure is reasonably correct per HTML's rules.
# Note that tagStack never holds the html/head/body element; those are
# handled specially instead.
class SimpleStream:
    _text: str
    _len: int
    _handler: t.Any  # Ugh, lxml doesn't give this a type
    _tagStack: list[str]
    _inHead: bool
    _htmlAttrs: list[dict[str, str]]
    _headAttrs: list[dict[str, str]]
    _bodyAttrs: list[dict[str, str]]

    def __init__(self, text: str) -> None:
        self._text = text
        self._len = len(text)
        self._handler = lxml.sax.ElementTreeContentHandler()
        self._htmlAttrs = []
        self._headAttrs = []
        self._bodyAttrs = []
        self._inHead = True
        self._tagStack = []
        self._handler.startElement("html", {})
        self._handler.startElement("head", {})

    def __getitem__(self, key: int) -> str:
        if key < 0 or key >= self._len:
            return ""
        return self._text[key]

    def slice(self, start: int, end: int) -> str:
        return self._text[start:end]

    def eof(self, i: int) -> bool:
        return i >= self._len

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
        if self._inHead and tagName not in HEAD_ELEMENTS:
            self.startBody()
        if tagName == "body":
            if attrs:
                self._bodyAttrs.append(attrs)
            return
        self.autoCloseStart(tagName)
        self._handler.startElement(tagName, attrs)
        self.pushEl(tagName)

    def endTag(self, tagName: str) -> None:
        if self._tagStack and tagName == self._tagStack[-1]:
            # Simple case
            self.popEl()
            self._handler.endElement(tagName)
            return
        if self._inHead and tagName in HEAD_ELEMENTS:
            self.autoCloseEnd(tagName)
            self.popEl()
            self._handler.endElement(tagName)
            return
        self.startBody()
        if tagName in ("html", "head", "body"):
            self.autoCloseAll()
            return
        if tagName in HEADING_ELEMENTS and HEADING_ELEMENTS.intersection(self._tagStack):
            # People regularly close headings with the wrong tag. They can't nest,
            # so when I see a heading end tag, just close whatever heading is open.
            self.virtualClose(HEADING_ELEMENTS)
            return
        if tagName in self._tagStack:
            self.autoCloseEnd(tagName)
            self.popEl()
            self._handler.endElement(tagName)

    def selfClosedTag(self, tagName: str, attrs: dict[str, str]) -> None:
        self.startTag(tagName, attrs)
        self.endTag(tagName)

    def characters(self, chars: str) -> None:
        if self._inHead and chars.strip() != "":
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
        if tagName in (
            "address",
            "article",
            "aside",
            "blockquote",
            "center",
            "details",
            "dialog",
            "dir",
            "div",
            "dl",
            "fieldset",
            "figcaption",
            "figure",
            "footer",
            "header",
            "hgroup",
            "main",
            "menu",
            "nav",
            "ol",
            "p",
            "search",
            "section",
            "summary",
            "ul",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "pre",
            "listing",
            "form",
            "plaintext",
            "table",
            "hr",
            "xmp",
        ):
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

    def virtualClose(self, tags: list[str] | set[str], scopes: list[str] | None = None) -> None:
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
