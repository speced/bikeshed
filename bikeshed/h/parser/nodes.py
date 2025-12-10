from __future__ import annotations

import dataclasses
import re
from abc import ABCMeta, abstractmethod
from collections import Counter
from dataclasses import InitVar, dataclass, field

from ... import constants, t
from ... import messages as m

if t.TYPE_CHECKING:
    from .stream import Stream  # pylint: disable=cyclic-import

ParserNodeT: t.TypeAlias = (
    "Comment | Doctype | EndTag | RawElement | RawText | SafeElement | SafeText | SelfClosedTag | StartTag"
)


def startTagStr(tagName: str, attrs: t.SafeAttrDict) -> str:
    s = f"<{tagName}"
    lineBreakAttrs = []
    for k, v in sortAttrs(attrs):
        if "\n" in v:
            lineBreakAttrs.append(k)
            v = v.replace("\n", constants.virtualLineBreak)
        s += f' {k}="{v}"'
    if lineBreakAttrs:
        s += f' bs-line-break-attrs="{" ".join(lineBreakAttrs)}"'
    s += ">"
    return s


def sortAttrs(attrs: t.SafeAttrDict) -> t.Iterator[tuple[str, str]]:
    if "bs-line-number" in attrs:
        yield "bs-line-number", attrs["bs-line-number"]
    for k, v in sorted(attrs.items()):
        if k in ("bs-line-number", "class"):
            continue
        yield k, v
    if "class" in attrs:
        yield "class", attrs["class"]


def startTagStrFromNode(node: StartTag | SelfClosedTag) -> str:
    if "bs-line-number" not in node.attrs:
        node.attrs["bs-line-number"] = escapeAttr(node.loc)
    if "bs-parse-context" not in node.attrs and node.context:
        node.attrs["bs-parse-context"] = escapeAttr(node.context)
    if node.classes:
        node.attrs["class"] = escapeAttr(" ".join(sorted(node.classes)))
    return startTagStr(node.tag, node.attrs)


@dataclass
class ParserNode(metaclass=ABCMeta):
    line: int
    endLine: int
    loc: str
    endLoc: str
    context: str | None

    @property
    def height(self) -> int:
        return self.endLine - self.line

    @abstractmethod
    def __str__(self) -> str:
        pass


@dataclass
class Text(ParserNode, metaclass=ABCMeta):
    text: str


@dataclass
class RawText(Text):
    # Raw source text, might contain HTML characters/etc

    def __str__(self) -> str:
        return self.text

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            text=text if text is not None else s.slice(start, end),
        )

    @classmethod
    def fromSafeText(cls, node: SafeText) -> t.Self:
        return cls(
            line=node.line,
            endLine=node.endLine,
            loc=node.loc,
            endLoc=node.endLoc,
            context=node.context,
            text=str(node),
        )

    def curlifyApostrophes(self, lastNode: ParserNode | None) -> RawText:
        if re.match(r"'\w", self.text):
            if isinstance(lastNode, (EndTag, RawElement, SelfClosedTag)):
                self.text = "’" + self.text[1:]
            elif isinstance(lastNode, RawText) and re.match(r"\w", lastNode.text[-1]):
                self.text = "’" + self.text[1:]
        if "'" in self.text:
            self.text = re.sub(r"(\w)'(\w)", r"\1’\2", self.text)
        if isinstance(lastNode, EndTag) and lastNode.tag == "var" and re.match(r"'\s", self.text):
            self.text = "’" + self.text[1:]
        return self

    def needsLCCs(self) -> bool:
        """
        Whether or not the node will eventally insert an ILCC or DLCC
        to fix the line count when serializing to a string.
        """
        return self.text.count("\n") != self.height


@dataclass
class SafeText(Text):
    # "Safe" text, automatically escapes special HTML chars
    # when stringified.
    def __str__(self) -> str:
        return escapeHTML(self.text)

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            text=text if text is not None else s.slice(start, end),
        )


@dataclass
class Doctype(ParserNode):
    data: str

    def __str__(self) -> str:
        return self.data

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            data=data,
        )


@dataclass
class StartTag(ParserNode):
    tag: str
    attrs: t.SafeAttrDict = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)
    endTag: EndTag | None = None

    @classmethod
    def fromStream(
        cls,
        s: Stream,
        start: int,
        end: int,
        tag: str,
        attrs: None | t.SafeAttrDict = None,
    ) -> t.Self:
        if attrs is None:
            attrs = {}
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=tag,
            attrs=attrs,
        )

    def __str__(self) -> str:
        return startTagStrFromNode(self)

    def printEndTag(self) -> str:
        return f"</{self.tag}>"

    def finalize(self) -> StartTag:
        if "class" in self.attrs:
            self.classes = set(unescapeAttr(self.attrs["class"]).split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> StartTag:
        return dataclasses.replace(self, **kwargs)


@dataclass
class SelfClosedTag(ParserNode):
    tag: str
    attrs: t.SafeAttrDict = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)

    @classmethod
    def fromStream(
        cls,
        s: Stream,
        start: int,
        end: int,
        tag: str,
        attrs: None | t.SafeAttrDict = None,
    ) -> t.Self:
        if attrs is None:
            attrs = {}
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=tag,
            attrs=attrs,
        )

    @classmethod
    def fromStartTag(cls, tag: StartTag) -> t.Self:
        return cls(
            line=tag.line,
            endLine=tag.endLine,
            loc=tag.loc,
            endLoc=tag.endLoc,
            context=tag.context,
            tag=tag.tag,
            attrs=tag.attrs,
            classes=tag.classes,
        )

    def __str__(self) -> str:
        s = startTagStrFromNode(self)
        if self.tag in (
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
            "wbr",
        ):
            return s
        else:
            return s + f"</{self.tag}>"
        return s

    def finalize(self) -> SelfClosedTag:
        if "class" in self.attrs:
            self.classes = set(unescapeAttr(self.attrs["class"]).split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> SelfClosedTag:
        return dataclasses.replace(self, **kwargs)


@dataclass
class EndTag(ParserNode):
    tag: str
    startTag: StartTag | None = None

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, tag: str | StartTag) -> t.Self:
        endTag = cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=tag if isinstance(tag, str) else tag.tag,
            startTag=tag if isinstance(tag, StartTag) else None,
        )
        if isinstance(tag, StartTag):
            tag.endTag = endTag
        return endTag

    def __str__(self) -> str:
        return f"</{self.tag}>"


@dataclass
class Comment(ParserNode):
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            data=data,
        )

    def __str__(self) -> str:
        return f"<!--{escapeHTML(self.data)}-->"


# RawElement is for things like <script> or <style>
# which have special parsing rules that just look
# for the ending tag and treat the entire rest of
# the contents as raw text, without escaping.
@dataclass
class RawElement(ParserNode):
    tag: str
    startTag: StartTag
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, startTag: StartTag, data: str) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=startTag.tag,
            startTag=startTag,
            data=data,
        )

    def __str__(self) -> str:
        return f"{self.startTag}{self.data}</{self.tag}>"


# SafeElement is for elements like <xmp>, which are
# basically RawElements, but might not be understood
# by random HTML parsers, and so need their contents
# escaped instead.
@dataclass
class SafeElement(ParserNode):
    tag: str
    startTag: StartTag
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, startTag: StartTag, data: str) -> t.Self:
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=startTag.tag,
            startTag=startTag,
            data=data,
        )

    def __str__(self) -> str:
        return f"{self.startTag}{escapeHTML(self.data)}</{self.tag}>"


def escapeHTML(text: str) -> str:
    # Escape HTML
    return text.replace("&", "&#38;").replace("<", "&#60;")


def escapeAttr(text: str) -> t.SafeAttrStr:
    return t.SafeAttrStr(text.replace("&", "&#38;").replace('"', "&#34;"))


def minimalEscapeAttr(text: str) -> t.SafeAttrStr:
    return t.SafeAttrStr(text.replace('"', "&#34;"))


def unescapeAttr(text: t.SafeAttrStr | t.EmptyLiteralStr) -> str:
    return str(text.replace("&#34;", '"').replace("&#38;", "&"))


@dataclass
class TagStack:
    tags: list[TagStackEntry] = field(default_factory=list)
    opaqueTags: set[str] = field(default_factory=lambda: {"pre", "xmp", "script", "style"})
    _opaqueCount: int = 0
    _tagCounts: Counter[str] = field(default_factory=Counter)

    def printOpenTags(self) -> list[str]:
        return [f"{x.name} at {x.startTag.loc}" for x in self.tags]

    def inOpaqueElement(self) -> bool:
        return self._opaqueCount > 0

    def inTagContext(self, tagName: str, stopTags: list[str] | None = None) -> bool:
        if self._tagCounts[tagName] == 0:
            return False
        if not stopTags:
            return True
        # If there are stopTags, make sure the tag you're asking about
        # occurs *before* you hit a stopTag.
        for entry in reversed(self.tags):
            if entry.startTag.tag == tagName:
                return True
            if entry.startTag.tag in stopTags:
                return False
        assert False, "unreachable"

    def getDeepestFromTag(self, tagName: str) -> TagStackEntry | None:
        for entry in reversed(self.tags):
            if entry.startTag.tag == tagName:
                return entry
        return None

    def pushEntry(self, entry: TagStackEntry) -> None:
        self.tags.append(entry)
        if entry.isOpaque:
            self._opaqueCount += 1
        self._tagCounts[entry.startTag.tag] += 1

    def popEntry(self) -> TagStackEntry:
        entry = self.tags.pop()
        if entry.isOpaque:
            self._opaqueCount -= 1
        self._tagCounts[entry.startTag.tag] -= 1
        return entry

    def undo(self, startTag: StartTag) -> None:
        # If a tag was added experimentally, reverse back to undo any stack changes
        while entry := self.popEntry():
            if entry.startTag == startTag:
                return
        m.die(
            f"PROGRAMMING ERROR: Tried to pop an experimental <{startTag.tag}> from the tag stack, but instead popped the entire stack away.",
            lineNum=startTag.loc,
        )

    def update(self, node: ParserNode) -> None:
        # Updates the stack based on the passed node.
        # Start tags add to the stack, close tags pop from it.
        # Auto-closing tags mean start tags can also pop from the stack.
        # If any auto-closing occurs, this method yields the appropriate EndTags for it.
        node = t.cast(ParserNodeT, node)
        if isinstance(node, StartTag):
            self.autoCloseStart(node.tag, node)
            self.pushEntry(TagStackEntry(node, self.opaqueTags))
            self.verifyTagContext(node)
            return
        elif isinstance(node, EndTag):
            self.autoCloseEnd(node.tag, node)
            if (
                self.tags
                and self.tags[-1].startTag.tag == node.tag
                and not isinstance(self.tags[-1], TagStackShorthandEntry)
            ):
                self.popEntry()
            else:
                if node.tag in ("html", "head", "body", "main"):
                    # If your boilerplate closes these for safety,
                    # but they're not actually open,
                    # that's fine
                    return
                if node.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    # People put the wrong closing tag on headings all the time.
                    # Auto-close the nearest heading, whatever it is,
                    # and report it as an error.
                    headingStart = self.nearestHeading()
                    if headingStart and headingStart.startTag.tag != node.tag:
                        self.virtualCloseUntil(["h1", "h2", "h3", "h4", "h5", "h6"], node)
                        m.die(
                            f"Saw a heading end tag {node}, but the current open heading is <{headingStart.startTag.tag}> (at {headingStart.startTag.loc}).",
                            lineNum=node.loc,
                        )
                        return
                for entry in reversed(self.tags):
                    # If the corresponding start tag exists on the stack, just further
                    # away, close everything between you and the start tag.
                    if entry.startTag.tag == node.tag:
                        m.die(
                            f"Saw an end tag {node}, but there were unclosed elements remaining before the nearest matching start tag (at {entry.startTag.loc}).\nOpen tags: {', '.join(self.printOpenTags())}",
                            lineNum=node.loc,
                        )
                        self.virtualCloseUntil([node.tag], node, realEndTag=True)
                        break
                else:
                    # Didn't encounter the corresponding start tag, so this is just
                    # a markup error to report.
                    openTagsMsg = f"\nOpen tags: {', '.join(self.printOpenTags())}" if self.tags else ""
                    m.die(
                        f"Saw an end tag {node}, but there's no open element corresponding to it.{openTagsMsg}",
                        lineNum=node.loc,
                    )
        elif isinstance(node, (SelfClosedTag, RawElement, SafeElement)):
            self.autoCloseStart(node.tag, node)
        elif isinstance(node, (Text, Comment, Doctype)):
            pass
        else:
            t.assert_never(node)

    def updateShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        self.pushEntry(TagStackShorthandEntry(startTag, self.opaqueTags, sigils))

    def updateShorthandClose(
        self,
        s: Stream,
        i: int,
        startTag: StartTag,
        sigils: tuple[str, str],
    ) -> t.Generator[EndTag, None, None]:
        if self.tags and self.tags[-1].startTag == startTag:
            self.popEntry()
            return
        shorthand = sigils[0] + "..." + sigils[1]
        if any(x.startTag == startTag for x in self.tags):
            m.die(
                f"{shorthand} shorthand (opened on {startTag.loc}) was closed, but there were still open elements inside of it.\nOpen tags: {', '.join(self.printOpenTags())}",
                lineNum=s.loc(i),
            )
            yield from self.virtualCloseShorthand(s, i, startTag)
        else:
            m.die(
                f"PROGRAMMING ERROR: Tried to close a {shorthand} shorthand, but there's no matching open tag on the stack of open elements. Please report this!",
                lineNum=s.loc(i),
            )

    def cancelShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        if not any(x.startTag == startTag for x in self.tags):
            shorthand = sigils[0] + "..." + sigils[1]
            m.die(
                f"Programming error - tried to close a {shorthand} shorthand, but there's no matching open tag on the stack of open elements. Please report this!",
                lineNum=startTag.loc,
            )
            return
        while self.tags and self.tags[-1].startTag != startTag:
            self.popEntry()
        self.popEntry()

    def autoCloseStart(self, tag: str, node: ParserNode) -> None:
        # Handle any auto-closing that occurs as a result
        # of seeing a particular start tag.
        # (Only valid HTML; real parsers do a lot more work.)
        if not self.tags:
            return
        if tag in (
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
            self.virtualClose(node, ["p"])
        if tag == "li":
            self.virtualClose(node, ["p"], ["ol", "ul"])
            self.virtualClose(node, ["li"], ["ol", "ul"])
        elif tag in ("dt", "dd"):
            self.virtualClose(node, ["p"], ["dl"])
            self.virtualClose(node, ["dt", "dd"], ["dl"])
        elif tag == "option":
            self.virtualClose(node, ["option"])
        elif tag == "optgroup":
            self.virtualClose(node, ["option"])
            self.virtualClose(node, ["optgroup"])
        elif tag in ("td", "th"):
            self.virtualClose(node, ["p"], ["table"])
            self.virtualClose(node, ["td", "th"], ["table"])
        elif tag == "tr":
            self.virtualClose(node, ["p"], ["table"])
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
            self.virtualClose(node, ["caption", "colgroup"], ["table"])
        elif tag in ("thead", "tbody", "tfoot"):
            self.virtualClose(node, ["p"], ["table"])
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
            self.virtualClose(node, ["thead", "tbody", "tfoot", "caption", "colgroup"], ["table"])
        elif tag in ("caption", "colgroup"):
            self.virtualClose(node, ["p"], ["table"])
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
            self.virtualClose(node, ["thead", "tbody", "tfoot", "caption", "colgroup"], ["table"])
        elif tag == "col":
            self.virtualClose(node, ["p"], ["table"])
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
            self.virtualClose(node, ["thead", "tbody", "tfoot", "caption"], ["table"])
        elif tag in ("rb", "rtc"):
            self.virtualClose(node, ["rb", "rp", "rt"], ["ruby"])
            self.virtualClose(node, ["rtc"], ["ruby"])
        elif tag in ("rp", "rt"):
            self.virtualClose(node, ["rb", "rp", "rt"], ["ruby"])

    def autoCloseEnd(self, tag: str, node: ParserNode) -> None:
        # Handle any auto-closing that occurs as a result
        # of seeing a particular end tag.
        # (Only valid HTML; real parsers do a lot more work.)
        if tag in (
            "address",
            "article",
            "aside",
            "blockquote",
            "body",
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
            "html",
            "main",
            "menu",
            "nav",
            "ol",
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
            "caption",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "td",
            "th",
            "li",
            "dt",
            "dd",
        ):
            self.virtualClose(node, ["p"])
        if tag in ("ol", "ul"):
            self.virtualClose(node, ["li"], ["ol", "ul"])
        elif tag == "dl":
            self.virtualClose(node, ["dt", "dd"], ["dl"])
        elif tag == "tr":
            self.virtualClose(node, ["td", "th"], ["table"])
        elif tag in ("thead", "tbody", "tfoot"):
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
        elif tag == "table":
            self.virtualClose(node, ["td", "th"], ["table"])
            self.virtualClose(node, ["tr"], ["table"])
            self.virtualClose(node, ["thead", "tbody", "tfoot", "caption", "colgroup"], ["table"])
        elif tag == "rtc":
            self.virtualClose(node, ["rt"], ["ruby"])
        elif tag == "ruby":
            self.virtualClose(node, ["rt", "rb", "rp"], ["ruby"])
            self.virtualClose(node, ["rtc"], ["ruby"])
        elif tag == "optgroup":
            self.virtualClose(node, ["option"])
        elif tag == "select":
            self.virtualClose(node, ["option"])
            self.virtualClose(node, ["optgroup"])

    def virtualClose(
        self,
        node: ParserNode,
        tags: list[str],
        stopTags: list[str] | None = None,
    ) -> None:
        if not self.tags:
            return
        entry: TagStackEntry | None
        if self.tags[-1].startTag.tag in tags:
            # If the tag is top of the stack, silently pop it
            entry = self.popEntry()
            # yield makeVirtualEndTag(entry.startTag, node, virtual=self.distinguishVirtualTags)
        else:
            # Otherwise, see if it needs popping further up, which is an error.
            for tag in tags:
                if self.inTagContext(tag, stopTags):
                    entry = self.getDeepestFromTag(tag)
                    assert entry is not None
                    m.die(
                        f"Tried to auto-close a <{tag}>, but there were unclosed elements remaining before the nearest matching start tag (at {entry.startTag.loc}).\nOpen tags: {', '.join(self.printOpenTags())}",
                        lineNum=node.loc,
                    )
                    # yield from self.virtualCloseUntil([tag], node)

    def virtualCloseUntil(self, tags: list[str], node: ParserNode, realEndTag: bool = False) -> None:
        # Now that the lxml parser doesn't run HTML's auto-closing rules,
        # I need to auto-close things myself when they're misordered.
        # Don't go past a shorthand, tho, as those are definitively scoped.
        # node
        while self.tags:
            lastEntry = self.tags[-1]
            lastStartTag = lastEntry.startTag
            if lastStartTag.tag in tags:
                # The tag I'm stopping at.
                self.popEntry()
                if not realEndTag:
                    pass
                    # yield makeVirtualEndTag(entry.startTag, node, virtual=self.distinguishVirtualTags)
                return
            if isinstance(lastEntry, TagStackShorthandEntry):
                # Can't virtual-close past a shorthand opener
                return
            if lastStartTag.endTag and isinstance(node, EndTag) and node.startTag != lastStartTag.endTag:
                # Can't virtual-close past a manually-paired start tag
                return
            # Otherwise, good to pop the tag
            self.popEntry()
            # yield makeVirtualEndTag(entry.startTag, node, virtual=self.distinguishVirtualTags)
        m.die(
            f"PROGRAMMING ERROR: Tried to auto-close a still-open element, but the specified opening tags {tags} aren't on the stack. Please report this!",
            lineNum=node.loc,
        )

    def virtualCloseShorthand(self, s: Stream, i: int, startTag: StartTag) -> t.Generator[EndTag, None, None]:
        # Auto-close anything that was opened inside the shorthand and left open.
        while self.tags and self.tags[-1].startTag != startTag:
            entry = self.popEntry()
            yield EndTag.fromStream(s, i, i, entry.startTag)
        # And pop the shorthand opener
        if self.tags and self.tags[-1].startTag == startTag:
            self.popEntry()
        else:
            m.die(
                "PROGRAMMING ERROR: Tried to auto-close still-open elements in a shorthand, but the shorthand opener is no longer on the stack. Please report this!",
                lineNum=startTag.loc,
            )

    def nearestHeading(self) -> TagStackEntry | None:
        for entry in reversed(self.tags):
            if entry.startTag.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                return entry
        return None

    def verifyTagContext(self, node: StartTag) -> None:
        # Checks that elements that can only live in certain contexts
        # actually have their correct wrappers.
        tag = node.tag
        reqs: list[tuple[tuple[str, ...], str]] = [
            (("td", "th"), "tr"),
            (("col",), "colgroup"),
            (("td", "th", "tr", "tbody", "thead", "tfoot", "caption", "col", "colgroup"), "table"),
            (("figcaption",), "figure"),
            (("legend",), "fieldset"),
            (("fieldset",), "form"),
            (("dt", "dd"), "dl"),
        ]
        for tagNames, parentTag in reqs:
            if tag in tagNames and not self.inTagContext(parentTag):
                m.die(f"Saw a <{tag}> that wasn't in a <{parentTag}>", lineNum=node.loc)
        # FIXME: Until I integrate the markdown parser, I can't rely on this,
        # since there might be a *markdown* li/dt/dd between the element
        # and the "parent" ul.
        """
        if len(self.tags) >= 2:
            parentTag = self.tags[-2].startTag.tag
            if parentTag in ("ol", "ul") and tag != "li":
                m.die(f"Saw a <{tag}> that's a direct child of a <{parentTag}>", lineNum=node.loc)
            if parentTag == "dl" and tag not in ("dt", "dd", "div"):
                m.die(f"Saw a <{tag}> that's a direct child of a <dl>", lineNum=node.loc)
        """


@dataclass
class TagStackEntry:
    startTag: StartTag
    opaqueTags: InitVar[set[str]]
    isOpaque: bool = field(init=False)

    def __post_init__(self, opaqueTags: set[str]) -> None:
        if (
            self.startTag.tag in opaqueTags
            or self.startTag.tag in ("pre", "xmp", "script", "style")
            or "bs-opaque" in self.startTag.attrs
            or "data-opaque" in self.startTag.attrs
        ):
            self.isOpaque = True
        else:
            self.isOpaque = False

    @property
    def name(self) -> str:
        return "<" + self.startTag.tag + ">"


@dataclass
class TagStackShorthandEntry(TagStackEntry):
    sigils: tuple[str, str]

    @property
    def name(self) -> str:
        return self.sigils[0] + "..." + self.sigils[1]
