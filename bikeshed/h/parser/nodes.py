from __future__ import annotations

import dataclasses
import re
from collections import Counter
from dataclasses import InitVar, dataclass, field

from ... import messages as m
from ... import t
from .. import elements

if t.TYPE_CHECKING:
    from .stream import Stream  # pylint: disable=cyclic-import

ParserNodeT: t.TypeAlias = (
    "Comment | Doctype | EndTag | RawElement | RawText | SafeElement | SafeText | SelfClosedTag | StartTag"
)
TagNodeT: t.TypeAlias = "StartTag | EndTag | SelfClosedTag | RawElement | SafeElement"


_APOS_START_WORD_RE = re.compile(r"'\w")
_APOS_WORD_CHAR_RE = re.compile(r"\w")
_APOS_IN_WORD_RE = re.compile(r"(?<=\w)'(?=\w)")
_APOS_START_SPACE_RE = re.compile(r"'\s")


def startTagStr(tagName: str, attrs: t.SafeAttrDict) -> str:
    """Serialize an HTML start tag with canonically sorted attributes."""
    s = f"<{tagName}"
    for k, v in sortAttrs(attrs):
        s += f' {k}="{v}"'
    s += ">"
    return s


def sortAttrs(attrs: t.SafeAttrDict) -> t.Iterator[tuple[str, str]]:
    """Yield `(name, value)` pairs with `bs-line-number` first, `class` last, and others alphabetical."""
    # Fast-path common tags that only carry bs-line-number (and optionally class) to avoid sorting.
    if "bs-line-number" in attrs:
        yield "bs-line-number", attrs["bs-line-number"]
        if len(attrs) == 1:
            return
        if len(attrs) == 2 and "class" in attrs:
            yield "class", attrs["class"]
            return
    for k, v in sorted(attrs.items()):
        if k in ("bs-line-number", "class"):
            continue
        yield k, v
    if "class" in attrs:
        yield "class", attrs["class"]


def startTagStrFromNode(node: StartTag | SelfClosedTag) -> str:
    """Populate synthetic line/context/class attributes on `node` and serialize its start tag."""
    if "bs-line-number" not in node.attrs and node.loc:
        node.attrs["bs-line-number"] = escapeAttr(node.loc)
    if "bs-parse-context" not in node.attrs and node.context:
        node.attrs["bs-parse-context"] = escapeAttr(node.context)
    if node.classes:
        node.attrs["class"] = escapeAttr(" ".join(sorted(node.classes)))
    return startTagStr(node.tag, node.attrs)


@dataclass
class ParserNode:
    """Base class for all nodes emitted by the HTML/Markdown parser, carrying optional source span info."""

    s: Stream | None = field(default=None, repr=False, kw_only=True)
    start: int = field(default=0, repr=False, kw_only=True)
    end: int = field(default=0, repr=False, kw_only=True)

    @property
    def line(self) -> int:
        """Return the 1-based starting line number of this node."""
        return self.s.line(self.start) if self.s is not None else 1

    @property
    def endLine(self) -> int:
        """Return the 1-based ending line number of this node."""
        return self.s.line(self.end) if self.s is not None else 1

    @property
    def loc(self) -> str:
        """Return the formatted starting `line:col` location (or `""` for synthetic nodes)."""
        return self.s.loc(self.start) if self.s is not None else ""

    @property
    def endLoc(self) -> str:
        """Return the formatted ending `line:col` location (or `""` for synthetic nodes)."""
        return self.s.loc(self.end) if self.s is not None else ""

    @property
    def context(self) -> str | None:
        """Return the source context label from this node's stream, if any."""
        return self.s.context if self.s is not None else None

    @property
    def height(self) -> int:
        """Return the number of newlines spanned by this node."""
        if self.start == self.end or self.s is None:
            return 0
        return self.s.line(self.end) - self.s.line(self.start)

    def __str__(self) -> str:
        """Serialize this node to HTML."""
        raise NotImplementedError


@dataclass
class Text(ParserNode):
    """Base class for text nodes (`RawText` and `SafeText`)."""

    text: str

    def __str__(self) -> str:
        """Serialize this text node to HTML."""
        raise NotImplementedError


@dataclass
class RawText(Text):
    """Raw source text that may already contain HTML entities and is serialized verbatim."""

    def __str__(self) -> str:
        """Return the raw text unchanged."""
        return self.text

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:
        """Construct a `RawText` node tied to `s[start:end]` (or explicit `text`)."""
        return cls(
            s=s,
            start=start,
            end=end,
            text=s.chars[start:end] if text is None else text,
        )

    @classmethod
    def fromSafeText(cls, node: SafeText) -> t.Self:
        """Convert a `SafeText` node into an already-escaped `RawText` node."""
        return cls(
            s=node.s,
            start=node.start,
            end=node.end,
            text=str(node),
        )

    def curlifyApostrophes(self, lastNode: ParserNode | None) -> RawText:
        """Convert straight apostrophes in contractions and possessives (including after `</var>`) to `’`."""
        if "'" not in self.text:
            return self
        if self.text[0] == "'":
            if _APOS_START_WORD_RE.match(self.text):
                if isinstance(lastNode, (EndTag, RawElement, SafeElement, SelfClosedTag)):
                    self.text = "’" + self.text[1:]
                elif isinstance(lastNode, RawText) and _APOS_WORD_CHAR_RE.match(lastNode.text[-1]):
                    self.text = "’" + self.text[1:]
            elif (
                isinstance(lastNode, EndTag)
                and lastNode.tag == "var"
                and (
                    _APOS_START_SPACE_RE.match(self.text)
                    # Inline line parsing stops before "\n", so a line-ending `|var|'` leaves self.text == "'".
                    or (self.text == "'" and self.s is not None and self.s[self.end] == "\n")
                )
            ):
                self.text = "’" + self.text[1:]
        if "'" in self.text:
            self.text = _APOS_IN_WORD_RE.sub("’", self.text)
        return self


@dataclass
class SafeText(Text):
    """Plain text whose `<` and `&` characters are HTML-escaped when serialized."""

    def __str__(self) -> str:
        """Return the HTML-escaped text."""
        return escapeHTML(self.text)

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:
        """Construct a `SafeText` node tied to `s[start:end]` (or explicit `text`)."""
        return cls(
            s=s,
            start=start,
            end=end,
            text=s.chars[start:end] if text is None else text,
        )


@dataclass
class Doctype(ParserNode):
    """An HTML `<!doctype ...>` declaration node."""

    data: str

    def __str__(self) -> str:
        """Return the doctype declaration text."""
        return self.data

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:
        """Construct a `Doctype` node tied to `s[start:end]`."""
        return cls(
            s=s,
            start=start,
            end=end,
            data=data,
        )


@dataclass
class StartTag(ParserNode):
    """An HTML opening tag node with attributes, parsed class set, and optional paired `EndTag`."""

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
        attrs: t.SafeAttrDict | None = None,
    ) -> t.Self:
        """Construct a `StartTag` node tied to `s[start:end]`."""
        if attrs is None:
            attrs = {}
        return cls(
            s=s,
            start=start,
            end=end,
            tag=tag,
            attrs=attrs,
        )

    def __str__(self) -> str:
        """Serialize this start tag to HTML."""
        return startTagStrFromNode(self)

    def printEndTag(self) -> str:
        """Return the matching `</tag>` string for this start tag."""
        return f"</{self.tag}>"

    def finalize(self) -> StartTag:
        """Move any `class` attribute into `self.classes` for easier manipulation."""
        if "class" in self.attrs:
            self.classes = set(unescapeAttr(self.attrs["class"]).split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> StartTag:
        """Return a shallow copy of this `StartTag` with optional field overrides."""
        return dataclasses.replace(self, **kwargs)


@dataclass
class SelfClosedTag(ParserNode):
    """An HTML void element or self-closed SVG/MathML tag node."""

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
        attrs: t.SafeAttrDict | None = None,
    ) -> t.Self:
        """Construct a `SelfClosedTag` node tied to `s[start:end]`."""
        if attrs is None:
            attrs = {}
        return cls(
            s=s,
            start=start,
            end=end,
            tag=tag,
            attrs=attrs,
        )

    @classmethod
    def fromStartTag(cls, tag: StartTag) -> t.Self:
        """Convert an existing `StartTag` into an equivalent `SelfClosedTag`."""
        return cls(
            s=tag.s,
            start=tag.start,
            end=tag.end,
            tag=tag.tag,
            attrs=tag.attrs,
            classes=tag.classes,
        )

    def __str__(self) -> str:
        """Serialize as `<tag ...>` for void elements, or `<tag ...></tag>` for non-void elements."""
        s = startTagStrFromNode(self)
        if self.tag in elements.VOID_ELEMENTS:
            return s
        return s + f"</{self.tag}>"

    def finalize(self) -> SelfClosedTag:
        """Move any `class` attribute into `self.classes` for easier manipulation."""
        if "class" in self.attrs:
            self.classes = set(unescapeAttr(self.attrs["class"]).split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> SelfClosedTag:
        """Return a shallow copy of this `SelfClosedTag` with optional field overrides."""
        return dataclasses.replace(self, **kwargs)


@dataclass
class EndTag(ParserNode):
    """An HTML closing tag node, optionally linked back to its opening `StartTag`."""

    tag: str
    startTag: StartTag | None = None

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, tag: str | StartTag) -> t.Self:
        """Construct an `EndTag` tied to `s[start:end]`, linking `tag.endTag` when given a `StartTag`."""
        endTag = cls(
            s=s,
            start=start,
            end=end,
            tag=tag if isinstance(tag, str) else tag.tag,
            startTag=tag if isinstance(tag, StartTag) else None,
        )
        if isinstance(tag, StartTag):
            tag.endTag = endTag
        return endTag

    def __str__(self) -> str:
        """Serialize as `</tag>`."""
        return f"</{self.tag}>"


@dataclass
class Comment(ParserNode):
    """An HTML `<!-- ... -->` comment node."""

    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:
        """Construct a `Comment` node tied to `s[start:end]`."""
        return cls(
            s=s,
            start=start,
            end=end,
            data=data,
        )

    def __str__(self) -> str:
        """Serialize as an HTML comment with escaped body text."""
        return f"<!--{escapeHTML(self.data)}-->"


@dataclass
class RawElement(ParserNode):
    """An HTML raw-text element (e.g. `<script>`, `<style>`) whose body is serialized without HTML-escaping."""

    tag: str
    startTag: StartTag
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, startTag: StartTag, data: str) -> t.Self:
        """Construct a `RawElement` node spanning `s[start:end]`."""
        return cls(
            s=s,
            start=start,
            end=end,
            tag=startTag.tag,
            startTag=startTag,
            data=data,
        )

    def __str__(self) -> str:
        """Serialize the start tag, raw body, and matching end tag."""
        return f"{self.startTag}{self.data}</{self.tag}>"


@dataclass
class SafeElement(ParserNode):
    """An element (e.g. `<pre>` from `<xmp>`, fenced code, or datablocks) whose literal body is HTML-escaped on output."""

    tag: str
    startTag: StartTag
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, startTag: StartTag, data: str) -> t.Self:
        """Construct a `SafeElement` node spanning `s[start:end]`."""
        return cls(
            s=s,
            start=start,
            end=end,
            tag=startTag.tag,
            startTag=startTag,
            data=data,
        )

    def __str__(self) -> str:
        """Serialize the start tag, HTML-escaped body, and matching end tag."""
        return f"{self.startTag}{escapeHTML(self.data)}</{self.tag}>"


def isTag(node: ParserNode) -> t.TypeIs[TagNodeT]:
    """Return True if `node` represents an HTML tag or whole-element node."""
    return isinstance(node, (StartTag, EndTag, SelfClosedTag, RawElement, SafeElement))


def escapeHTML(text: str) -> str:
    """Escape `&` and `<` as numeric character references for HTML text serialization."""
    return text.replace("&", "&#38;").replace("<", "&#60;")


def escapeAttr(text: str) -> t.SafeAttrStr:
    """Escape `&` and `"` as numeric character references for double-quoted HTML attributes."""
    return t.SafeAttrStr(text.replace("&", "&#38;").replace('"', "&#34;"))


def minimalEscapeAttr(text: str) -> t.SafeAttrStr:
    """Escape only `"` (preserving existing `&` entities) for double-quoted HTML attributes."""
    return t.SafeAttrStr(text.replace('"', "&#34;"))


def unescapeAttr(text: t.SafeAttrStr | t.EmptyLiteralStr) -> str:
    """Reverse `escapeAttr` by decoding `&#34;` and `&#38;`."""
    return str(text.replace("&#34;", '"').replace("&#38;", "&"))


_TAG_CONTEXT_REQS: dict[str, tuple[str, ...]] = {
    "td": ("tr", "table"),
    "th": ("tr", "table"),
    "col": ("colgroup", "table"),
    "tr": ("table",),
    "tbody": ("table",),
    "thead": ("table",),
    "tfoot": ("table",),
    "caption": ("table",),
    "colgroup": ("table",),
    "figcaption": ("figure",),
    "legend": ("fieldset",),
    "fieldset": ("form",),
    "dt": ("dl",),
    "dd": ("dl",),
}


@dataclass
class TagStack:
    """Tracks currently open HTML elements and shorthands for opacity checks, auto-closing, and nesting errors."""

    tags: list[TagStackEntry] = field(default_factory=list)
    opaqueTags: set[str] = field(default_factory=lambda: set(elements.DEFAULT_OPAQUE_ELEMENTS))
    # O(1) counters kept in sync by pushEntry/popEntry to avoid linear scans on hot parser paths.
    _opaqueCount: int = 0
    _tagCounts: Counter[str] = field(default_factory=Counter)
    # Tracks enclosing Markdown-synthesized block elements as `(len(tags), tagName)` without
    # polluting `self.tags` for HTML end-tag matching or error messages.
    _blockParents: list[tuple[int, str]] = field(default_factory=list)

    def printOpenTags(self) -> list[str]:
        """Format all currently open tags with their source locations for error messages."""
        return [f"{x.name} at {x.startTag.loc}" for x in self.tags if not isinstance(x, TagStackSyntheticEntry)]

    def inOpaqueElement(self) -> bool:
        """Return True if any currently open element is opaque."""
        return self._opaqueCount > 0

    def inTagContext(self, tagName: str, stopTags: list[str] | None = None) -> bool:
        """Return True if `<tagName>` is open (and appears above any `stopTags` scoping barrier)."""
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
        """Return the innermost open `TagStackEntry` matching `tagName`, or `None`."""
        for entry in reversed(self.tags):
            if entry.startTag.tag == tagName:
                return entry
        return None

    def pushEntry(self, entry: TagStackEntry) -> None:
        """Push `entry` onto the stack and update opacity and per-tag counters."""
        self.tags.append(entry)
        if entry.isOpaque:
            self._opaqueCount += 1
        self._tagCounts[entry.startTag.tag] += 1

    def popEntry(self) -> TagStackEntry:
        """Pop the top entry from the stack and update opacity and per-tag counters."""
        entry = self.tags.pop()
        if entry.isOpaque:
            self._opaqueCount -= 1
        self._tagCounts[entry.startTag.tag] -= 1
        return entry

    def pushSynthetic(self, startTag: StartTag) -> TagStackSyntheticEntry:
        """Push a synthetic container entry (e.g. a Markdown-generated `<ul>`/`<ol>`/`<dl>`) onto the stack."""
        entry = TagStackSyntheticEntry(startTag, self.opaqueTags)
        self.pushEntry(entry)
        return entry

    def popSynthetic(self, entry: TagStackSyntheticEntry) -> None:
        """Remove a previously pushed synthetic container `entry` from the stack, preserving any unclosed inner tags."""
        if self.tags and self.tags[-1] is entry:
            self.popEntry()
            return
        for idx in range(len(self.tags) - 1, -1, -1):
            if self.tags[idx] is entry:
                removed = self.tags.pop(idx)
                if removed.isOpaque:
                    self._opaqueCount -= 1
                self._tagCounts[removed.startTag.tag] -= 1
                return

    def pushBlockParent(self, tagName: str, tagDepth: int | None = None) -> None:
        """Record an active Markdown-synthesized block element (`<li>`, `<dt>`, `<dd>`, `<blockquote>`, `<p>`, heading) at `tagDepth`."""
        self._blockParents.append((len(self.tags) if tagDepth is None else tagDepth, tagName))

    def popBlockParent(self) -> None:
        """Pop the innermost Markdown-synthesized block element recorded by `pushBlockParent()`."""
        self._blockParents.pop()

    def directParentContext(self) -> tuple[str | None, str | None]:
        """Return `(parentTag, grandparentTag)` for the innermost open element (HTML or Markdown block)."""
        n = len(self.tags)
        if self._blockParents and self._blockParents[-1][0] >= n:
            return self._blockParents[-1][1], None
        if n == 0:
            return None, None
        parentTag = self.tags[-1].startTag.tag
        if n >= 2 and not (self._blockParents and self._blockParents[-1][0] >= n - 1):
            grandparentTag = self.tags[-2].startTag.tag
        else:
            grandparentTag = None
        return parentTag, grandparentTag

    def undo(self, startTag: StartTag) -> None:
        """Roll back the stack through an experimentally pushed `startTag`."""
        while entry := self.popEntry():
            if entry.startTag == startTag:
                return
        m.die(
            f"PROGRAMMING ERROR: Tried to pop an experimental <{startTag.tag}> from the tag stack, but instead popped the entire stack away.",
            lineNum=startTag.loc,
        )

    def update(self, node: ParserNode) -> None:
        """Update the open-element stack for `node`, applying HTML auto-closing and logging nesting errors."""
        node = t.cast(ParserNodeT, node)
        if isinstance(node, StartTag):
            self.autoCloseStart(node.tag, node)
            self.verifyDirectParent(node.tag, node.loc)
            self.pushEntry(TagStackEntry(node, self.opaqueTags))
            self.verifyTagContext(node)
            return
        elif isinstance(node, EndTag):
            self.autoCloseEnd(node.tag, node)
            if (
                self.tags
                and self.tags[-1].startTag.tag == node.tag
                and not isinstance(self.tags[-1], (TagStackShorthandEntry, TagStackSyntheticEntry))
            ):
                self.popEntry()
            else:
                if node.tag in ("html", "head", "body", "main"):
                    # If your boilerplate closes these for safety,
                    # but they're not actually open,
                    # that's fine
                    return
                if node.tag in elements.HEADING_ELEMENTS:
                    # People put the wrong closing tag on headings all the time.
                    # Auto-close the nearest heading, whatever it is,
                    # and report it as an error.
                    headingStart = self.nearestHeading()
                    if headingStart and headingStart.startTag.tag != node.tag:
                        self.virtualCloseUntil(elements.HEADING_ELEMENTS, node)
                        m.die(
                            f"Saw a heading end tag {node}, but the current open heading is <{headingStart.startTag.tag}> (at {headingStart.startTag.loc}).",
                            lineNum=node.loc,
                        )
                        return
                for entry in reversed(self.tags):
                    # If the corresponding start tag exists on the stack, just further
                    # away, close everything between you and the start tag.
                    if entry.startTag.tag == node.tag and not isinstance(entry, TagStackSyntheticEntry):
                        m.die(
                            f"Saw an end tag {node}, but there were unclosed elements remaining before the nearest matching start tag (at {entry.startTag.loc}).\nOpen tags: {', '.join(self.printOpenTags())}",
                            lineNum=node.loc,
                        )
                        self.virtualCloseUntil([node.tag], node, realEndTag=True)
                        break
                else:
                    # Didn't encounter the corresponding start tag, so this is just
                    # a markup error to report.
                    openTags = self.printOpenTags()
                    openTagsMsg = f"\nOpen tags: {', '.join(openTags)}" if openTags else ""
                    m.die(
                        f"Saw an end tag {node}, but there's no open element corresponding to it.{openTagsMsg}",
                        lineNum=node.loc,
                    )
        elif isinstance(node, (SelfClosedTag, RawElement, SafeElement)):
            self.autoCloseStart(node.tag, node)
            if isinstance(node, SelfClosedTag) or node.startTag.attrs.get("bs-datablock-type") != "include":
                self.verifyDirectParent(node.tag, node.loc)
        elif isinstance(node, (Text, Comment, Doctype)):
            pass
        else:
            t.assert_never(node)

    def updateShorthandOpen(self, startTag: StartTag, sigils: tuple[str, str]) -> None:
        """Push a shorthand-backed `StartTag` onto the stack as a scoping barrier."""
        self.pushEntry(TagStackShorthandEntry(startTag, self.opaqueTags, sigils))

    def updateShorthandClose(
        self,
        s: Stream,
        i: int,
        startTag: StartTag,
        sigils: tuple[str, str],
    ) -> t.Generator[EndTag, None, None]:
        """Close a shorthand entry on the stack, reporting and auto-closing any unclosed inner elements."""
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
        """Discard a failed shorthand opener and any elements pushed inside it."""
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
        """Handle valid HTML auto-closing triggered by opening `tag`."""
        # (Only valid HTML; real parsers do a lot more work.)
        if not self.tags:
            return
        if tag in elements.AUTO_CLOSE_P_START_ELEMENTS:
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
        """Handle valid HTML auto-closing triggered by closing `tag`."""
        # (Only valid HTML; real parsers do a lot more work.)
        if not self.tags:
            return
        if tag in elements.AUTO_CLOSE_P_END_ELEMENTS:
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
        """Pop the top tag if it matches `tags`; otherwise log an error if a matching tag is buried under unclosed elements."""
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

    def virtualCloseUntil(self, tags: t.Collection[str], node: ParserNode, realEndTag: bool = False) -> None:
        """Pop misordered open tags up to and including one in `tags`, stopping at shorthand or paired-tag barriers."""
        # Shorthand entries and manually-paired start tags act as hard scoping barriers
        # so a stray end tag inside a shorthand cannot close elements outside it.
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
        """Pop and yield synthetic `EndTag`s for elements left open inside a shorthand, then pop `startTag`."""
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
        """Return the innermost open `<h1>`-`<h6>` entry on the stack, or `None`."""
        for entry in reversed(self.tags):
            if entry.startTag.tag in elements.HEADING_ELEMENTS:
                return entry
        return None

    def verifyDirectParent(
        self,
        tag: str,
        loc: str | int,
        parentContext: tuple[str | None, str | None] | None = None,
    ) -> None:
        """Log a fatal error if `tag` is an invalid direct child of an open `<ul>`, `<ol>`, `<dl>`, or `<dl> > <div>`."""
        parentTag, grandparentTag = self.directParentContext() if parentContext is None else parentContext
        if parentTag in ("ol", "ul") and tag not in ("li", "script", "template"):
            m.die(f"Saw a <{tag}> that's a direct child of a <{parentTag}>", lineNum=loc)
        elif parentTag == "dl" and tag not in ("dt", "dd", "div", "script", "template"):
            m.die(f"Saw a <{tag}> that's a direct child of a <dl>", lineNum=loc)
        elif parentTag == "div" and grandparentTag == "dl" and tag not in ("dt", "dd", "script", "template"):
            m.die(f"Saw a <{tag}> that's a direct child of a <dl>'s <div>", lineNum=loc)

    def verifyTagContext(self, node: StartTag) -> None:
        """Log an error if `node` requires an enclosing ancestor element (e.g. `<td>` in `<tr>`/`<table>`) that is missing."""
        if reqParents := _TAG_CONTEXT_REQS.get(node.tag):
            for parentTag in reqParents:
                if not self.inTagContext(parentTag):
                    m.die(f"Saw a <{node.tag}> that wasn't in a <{parentTag}>", lineNum=node.loc)


@dataclass
class TagStackEntry:
    """An open element frame on `TagStack` with its cached opacity flag."""

    startTag: StartTag
    opaqueTags: InitVar[set[str]]
    isOpaque: bool = field(init=False)

    def __post_init__(self, opaqueTags: set[str]) -> None:
        """Compute `isOpaque` from the element's tag name and `bs-opaque` attribute."""
        if (
            self.startTag.tag in opaqueTags
            or self.startTag.tag in elements.DEFAULT_OPAQUE_ELEMENTS
            or "bs-opaque" in self.startTag.attrs
        ):
            self.isOpaque = True
        else:
            self.isOpaque = False

    @property
    def name(self) -> str:
        """Return a human-readable `<tag>` label for error messages."""
        return "<" + self.startTag.tag + ">"


@dataclass
class TagStackShorthandEntry(TagStackEntry):
    """A `TagStackEntry` representing an inline shorthand (e.g. `[=...=]`) that scopes inner HTML tags."""

    sigils: tuple[str, str]

    @property
    def name(self) -> str:
        """Return a human-readable `open...close` shorthand label for error messages."""
        return self.sigils[0] + "..." + self.sigils[1]


@dataclass
class TagStackSyntheticEntry(TagStackEntry):
    """A `TagStackEntry` representing a synthetic block container (e.g. Markdown `<ul>`/`<ol>`/`<dl>`).

    Provides ancestor context (such as `<dl>` for mixed HTML `<dt>`/`<dd>` items) and HTML
    auto-close scoping without being closable by stray HTML end tags.
    """
