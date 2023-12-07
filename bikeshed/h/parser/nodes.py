from __future__ import annotations

import dataclasses
import re
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field

from ... import t


@dataclass
class ParserNode(metaclass=ABCMeta):
    line: int
    endLine: int

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


@dataclass
class Doctype(ParserNode):
    data: str

    def __str__(self) -> str:
        return self.data


@dataclass
class StartTag(ParserNode):
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)

    def __str__(self) -> str:
        s = f"<{self.tag} bs-line-number={self.line}"
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

    def __str__(self) -> str:
        s = f"<{self.tag} bs-line-number={self.line}"
        for k, v in sorted(self.attrs.items()):
            if k == "bs-line-number":
                continue
            s += f' {k}="{escapeAttr(v)}"'
        if self.classes:
            s += f' class="{" ".join(sorted(self.classes))}"'
        s += f"></{self.tag}>"
        return s

    def finalize(self) -> SelfClosedTag:
        if "class" in self.attrs:
            self.classes = set(self.attrs["class"].split())
            del self.attrs["class"]
        return self

    def clone(self, **kwargs: t.Any) -> SelfClosedTag:
        return dataclasses.replace(self, **kwargs)

    @classmethod
    def fromStartTag(cls: t.Type[SelfClosedTag], tag: StartTag) -> SelfClosedTag:
        return cls(
            line=tag.line,
            endLine=tag.endLine,
            tag=tag.tag,
            attrs=tag.attrs,
            classes=tag.classes,
        )


@dataclass
class EndTag(ParserNode):
    tag: str

    def __str__(self) -> str:
        return f"</{self.tag}>"


@dataclass
class Comment(ParserNode):
    data: str

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

    def __str__(self) -> str:
        return f"{self.startTag}{self.data}</{self.tag}>"


def escapeHTML(text: str) -> str:
    # Escape HTML
    return text.replace("&", "&amp;").replace("<", "&lt;")


def escapeAttr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;")
