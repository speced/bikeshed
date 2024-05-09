from __future__ import annotations

import dataclasses
import re
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field

from ... import config, t
from ... import messages as m

if t.TYPE_CHECKING:
    from .stream import Stream  # pylint: disable=cyclic-import


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


@dataclass
class Text(ParserNode, metaclass=ABCMeta):
    text: str

    @abstractmethod
    def __str__(self) -> str:
        pass


@dataclass
class RawText(Text):
    # Raw source text, might contain HTML characters/etc

    def __str__(self) -> str:
        return self.text

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:  # noqa: ANN102
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            text=text if text is not None else s[start:end],
        )

    def curlifyApostrophes(self, lastNode: ParserNode | None) -> RawText:
        if re.match(r"'\w", self.text):
            if isinstance(lastNode, (EndTag, RawElement, SelfClosedTag)):
                self.text = "’" + self.text[1:]
            elif isinstance(lastNode, RawText) and re.match(r"\w", lastNode.text[-1]):
                self.text = "’" + self.text[1:]
        if "'" in self.text:
            self.text = re.sub(r"(\w)'(\w)", r"\1’\2", self.text)
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
    def fromStream(cls, s: Stream, start: int, end: int, text: str | None = None) -> t.Self:  # noqa: ANN102
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            text=text if text is not None else s[start:end],
        )


@dataclass
class Doctype(ParserNode):
    data: str

    def __str__(self) -> str:
        return self.data

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:  # noqa: ANN102
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
    attrs: dict[str, str] = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)

    @classmethod
    def fromStream(
        cls,  # noqa: ANN102
        s: Stream,
        start: int,
        end: int,
        tag: str,
        attrs: None | dict[str, str] = None,
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
        s = f"<{self.tag} bs-line-number={self.line}"
        if self.context:
            s += f' bs-parse-context="{escapeAttr(self.context)}"'
        for k, v in sorted(self.attrs.items()):
            if k == "bs-line-number":
                continue
            v = v.replace('"', "&#34;")
            s += f' {k}="{v}"'
        if self.classes:
            s += f' class="{" ".join(sorted(self.classes))}"'
        s += ">"
        return s

    def printEndTag(self) -> str:
        return f"</{self.tag}>"

    def finalize(self) -> StartTag:
        if "class" in self.attrs:
            self.classes = set(self.attrs["class"].split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> StartTag:
        return dataclasses.replace(self, **kwargs)


@dataclass
class SelfClosedTag(ParserNode):
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)

    @classmethod
    def fromStream(
        cls,  # noqa: ANN102
        s: Stream,
        start: int,
        end: int,
        tag: str,
        attrs: None | dict[str, str] = None,
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
    def fromStartTag(cls, tag: StartTag) -> t.Self:  # noqa: ANN102
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
        s = f"<{self.tag} bs-line-number={self.line}"
        if self.context:
            s += f' bs-parse-context="{escapeAttr(self.context)}"'
        for k, v in sorted(self.attrs.items()):
            if k == "bs-line-number":
                continue
            v = v.replace('"', "&#34;")
            s += f' {k}="{v}"'
        if self.classes:
            s += f' class="{" ".join(sorted(self.classes))}"'
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
            s += ">"
        else:
            s += f"></{self.tag}>"
        return s

    def finalize(self) -> SelfClosedTag:
        if "class" in self.attrs:
            self.classes = set(self.attrs["class"].split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> SelfClosedTag:
        return dataclasses.replace(self, **kwargs)


@dataclass
class EndTag(ParserNode):
    tag: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, tag: str | StartTag) -> t.Self:  # noqa: ANN102
        return cls(
            line=s.line(start),
            endLine=s.line(end),
            loc=s.loc(start),
            endLoc=s.loc(end),
            context=s.context,
            tag=tag if isinstance(tag, str) else tag.tag,
        )

    def __str__(self) -> str:
        return f"</{self.tag}>"


@dataclass
class Comment(ParserNode):
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, data: str) -> t.Self:  # noqa: ANN102
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


# RawElement is for things like <script> or <xmp>
# which have special parsing rules that just look
# for the ending tag and treat the entire rest of
# the contents as raw text, without escaping.
@dataclass
class RawElement(ParserNode):
    tag: str
    startTag: StartTag
    data: str

    @classmethod
    def fromStream(cls, s: Stream, start: int, end: int, startTag: StartTag, data: str) -> t.Self:  # noqa: ANN102
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


def escapeHTML(text: str) -> str:
    # Escape HTML
    return text.replace("&", "&amp;").replace("<", "&lt;")


def escapeAttr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;")


@dataclass
class TagStack:
    tags: list[TagStackEntry] = field(default_factory=list)

    def inOpaqueElement(self, opaqueTags: t.Collection[str] | None = None) -> bool:
        if opaqueTags is None:
            opaqueTags = {"pre", "xmp", "script", "style"}
        return any(x.tag in opaqueTags or "bs-opaque" in x.startTag.attrs for x in self.tags)

    def inIDLContext(self) -> bool:
        # IDL contexts are imposed by IDL dfns or links,
        # so we can fail fast if there's nothing.
        if not any(x.tag in ("a", "dfn") for x in self.tags):
            return False

        # Determining whether the dfn/link is an *IDL* dfn/link is more difficult,
        # since the type can be set on an ancestor.
        # So I have to crawl all the tags, and look for alternate spellings,
        # since there are several possible shortenings.
        spottedDfn = False
        spottedLink = False
        for tag in reversed(self.tags):
            tagName = tag.tag
            attrs = tag.startTag.attrs
            if tagName == "dfn":
                spottedDfn = True
            elif tagName == "a":
                spottedLink = True
            if spottedDfn and "data-dfn-type" in attrs:
                return attrs["data-dfn-type"] in config.idlTypes
            if spottedDfn and "dfn-type" in attrs:
                return attrs["dfn-type"] in config.idlTypes
            if tagName == "dfn" and any(x in attrs for x in config.idlTypes):
                return True
            if spottedLink and "data-link-type" in attrs:
                return attrs["data-link-type"] in config.idlTypes or attrs["data-link-type"] == "idl"
            if spottedLink and "link-type" in attrs:
                return attrs["link-type"] in config.idlTypes or attrs["link-type"] == "idl"
            if tagName == "a" and any(x in attrs for x in config.idlTypes) or "idl" in attrs:
                return True
        return False

    def update(self, i: int, node: ParserNode) -> None:
        # Updates the stack based on the passed node.
        # Start tags add to the stack, close tags pop from it.
        # Auto-closing tags mean start tags can also pop from the stack.
        if isinstance(node, StartTag):
            self.autoCloseStart(node.tag)
            self.tags.append(TagStackEntry(i, node))
            return
        elif isinstance(node, EndTag):
            self.autoCloseEnd(node.tag)
            if self.tags and self.tags[-1].tag == node.tag:
                self.tags.pop()
            else:
                if node.tag in ("html", "head", "body", "main"):
                    # If your boilerplate closes these for safety,
                    # but they're not actually open,
                    # that's fine
                    return
                for entry in reversed(self.tags):
                    if entry.tag == node.tag:
                        openTags = [f"<{x.tag}> at {x.startTag.loc}" for x in self.tags]
                        m.die(
                            f"Saw an end tag {node}, but there were unclosed elements remaining before the nearest matching start tag (on line {entry.startTag.line}).\nOpen tags: {', '.join(openTags)}",
                            lineNum=node.line,
                        )
                        break
                else:
                    m.die(f"Saw an end tag {node}, but there's no open element corresponding to it.", lineNum=node.line)
        elif isinstance(node, (SelfClosedTag, RawElement)):
            self.autoCloseStart(node.tag)

    def autoCloseStart(self, tag: str) -> None:
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
            self.virtualClose("p")
        if tag == "li":
            self.virtualClose("p")
            self.virtualClose("li")
        elif tag in ("dt", "dd"):
            self.virtualClose("p")
            self.virtualClose("dt", "dd")
        elif tag == "option":
            self.virtualClose("option")
        elif tag == "optgroup":
            self.virtualClose("option")
            self.virtualClose("optgroup")
        elif tag in ("td", "th"):
            self.virtualClose("p")
            self.virtualClose("td", "th")
        elif tag == "tr":
            self.virtualClose("p")
            self.virtualClose("td", "th")
            self.virtualClose("tr")
            self.virtualClose("caption", "colgroup")
        elif tag in ("thead", "tbody", "tfoot"):
            self.virtualClose("p")
            self.virtualClose("td", "th")
            self.virtualClose("tr")
            self.virtualClose("thead", "tbody", "tfoot", "caption", "colgroup")
        elif tag in ("caption", "colgroup"):
            self.virtualClose("p")
            self.virtualClose("td", "th")
            self.virtualClose("tr")
            self.virtualClose("thead", "tbody", "tfoot", "caption", "colgroup")
        elif tag == "col":
            self.virtualClose("p")
            self.virtualClose("td", "th")
            self.virtualClose("tr")
            self.virtualClose("thead", "tbody", "tfoot", "caption")
        elif tag in ("rb", "rtc"):
            self.virtualClose("rb", "rp", "rt")
            self.virtualClose("rtc")
        elif tag in ("rp", "rt"):
            self.virtualClose("rb", "rp", "rt")

    def autoCloseEnd(self, tag: str) -> None:
        # Handle any auto-closing that occurs as a result
        # of seeing a particular end tag.
        # (Only valid HTML; real parsers do a lot more work.)
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
            self.virtualClose("p")
        if tag in ("ol", "ul"):
            self.virtualClose("li")
        elif tag == "dl":
            self.virtualClose("dt", "dd")
        elif tag == "tr":
            self.virtualClose("td", "th")
        elif tag in ("thead", "tbody", "tfoot"):
            self.virtualClose("td", "th")
            self.virtualClose("tr")
        elif tag == "table":
            self.virtualClose("td", "th")
            self.virtualClose("tr")
            self.virtualClose("thead", "tbody", "tfoot", "caption", "colgroup")
        elif tag == "rtc":
            self.virtualClose("rt")
        elif tag == "ruby":
            self.virtualClose("rt", "rb", "rp")
            self.virtualClose("rtc")
        elif tag == "optgroup":
            self.virtualClose("option")
        elif tag == "select":
            self.virtualClose("option")
            self.virtualClose("optgroup")

    def virtualClose(self, *tags: str) -> None:
        if not self.tags:
            return
        if self.tags[-1].tag in tags:
            self.tags.pop()


@dataclass
class TagStackEntry:
    i: int
    startTag: StartTag

    @property
    def tag(self) -> str:
        return self.startTag.tag
