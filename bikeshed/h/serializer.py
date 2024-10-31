from __future__ import annotations

import io
import itertools

from .. import t
from . import dom

if t.TYPE_CHECKING:
    WriterFn: t.TypeAlias = t.Callable[[str], t.Any]

    # more specific than t.NodesT, as nested lists can't happen
    Nodes: t.TypeAlias = t.ElementT | list[str | t.ElementT]
    Blocks: t.TypeAlias = list[Nodes]


class Serializer:
    inlineEls = frozenset(
        [
            "a",
            "em",
            "strong",
            "small",
            "s",
            "cite",
            "q",
            "dfn",
            "abbr",
            "data",
            "time",
            "code",
            "var",
            "samp",
            "kbd",
            "sub",
            "sup",
            "i",
            "b",
            "u",
            "mark",
            "ruby",
            "bdi",
            "bdo",
            "span",
            "br",
            "wbr",
            "img",
            "meter",
            "progress",
            "math",
            "[]",
        ],
    )
    rawEls = frozenset(["xmp", "script", "style"])
    voidEls = frozenset(
        [
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
        ],
    )
    omitEndTagEls = frozenset(
        [
            "td",
            "th",
            "tr",
            "thead",
            "tbody",
            "tfoot",
            "colgroup",
            "col",
            "li",
            "dt",
            "dd",
            "html",
            "head",
            "body",
        ],
    )

    def __init__(self, opaqueElements: t.Iterable[str], blockElements: t.Iterable[str]) -> None:
        self.opaqueEls = frozenset(opaqueElements)
        self.blockEls = frozenset(blockElements)

    def serialize(self, tree: t.DocumentT) -> str:
        output = io.StringIO()
        writer = output.write
        writer("<!doctype html>")
        self._serializeEl(tree.getroot(), writer)
        s = output.getvalue()
        output.close()
        return s

    def unfuckName(self, n: str) -> str:
        # LXML does namespaces stupidly
        if n.startswith("{"):
            return n.partition("}")[2]
        return n

    def groupIntoBlocks(self, nodes: t.Iterable[t.NodeT]) -> t.Generator[Nodes, None, None]:
        nonBlockNodes: list[str | t.ElementT] = []
        for node in nodes:
            if self.isElement(node) and self.isBlockElement(node.tag):
                if nonBlockNodes:
                    yield nonBlockNodes
                    nonBlockNodes = []
                yield node
                continue
            else:
                nonBlockNodes.append(node)
        if nonBlockNodes:
            yield nonBlockNodes

    def fixWS(self, text: str) -> str:
        import string

        t1 = text.lstrip(string.whitespace)
        if text != t1:
            t1 = " " + t1
        t2 = t1.rstrip(string.whitespace)
        if t1 != t2:
            t2 = t2 + " "
        return t2

    def startTag(self, tag: str, el: Nodes, write: WriterFn) -> None:
        if isinstance(el, list):
            return
        if not dom.hasAttrs(el):
            write("<" + tag + ">")
            return

        strs = []
        strs.append("<" + tag)
        for attrName, attrVal in sorted(el.items()):
            if str(attrName).startswith("bs-"):
                # Skip bs- prefixed attributes, as they're used
                # for Bikeshed-internal purposes.
                continue
            if attrVal == "":
                strs.append(" " + self.unfuckName(str(attrName)))
            else:
                strs.append(" " + self.unfuckName(str(attrName)) + '="' + dom.escapeAttr(str(attrVal)) + '"')
        strs.append(">")
        write("".join(strs))

    def endTag(self, tag: str, write: WriterFn) -> None:
        if tag != "[]":
            write("</" + tag + ">")

    def isElement(self, node: t.Any) -> t.TypeGuard[t.ElementT]:
        return dom.isElement(node)

    def isAnonBlock(self, block: t.Any) -> bool:
        return not dom.isElement(block)

    def isVoidElement(self, tag: str) -> bool:
        return tag in self.voidEls

    def isRawElement(self, tag: str) -> bool:
        return tag in self.rawEls

    def isOpaqueElement(self, tag: str) -> bool:
        return tag in self.opaqueEls

    def isInlineElement(self, tag: str) -> bool:
        return (tag in self.inlineEls) or ("-" in tag and tag not in self.blockEls)

    def isBlockElement(self, tag: str) -> bool:
        return not self.isInlineElement(tag)

    def needsEndTag(self, el: t.ElementT, nextEl: Nodes | None = None) -> bool:
        if el.tag not in self.omitEndTagEls:
            return True
        if el.tag in ["dt", "dd"]:
            if nextEl is None:
                return False
            if self.isElement(nextEl) and nextEl.tag in ["dt", "dd"]:  # noqa: SIM103
                return False
            return True
        return False

    def justWS(self, block: t.NodesT) -> bool:
        if self.isElement(block):
            return False
        return len(block) == 1 and isinstance(block[0], str) and block[0].strip() == ""

    def _writeVoidElement(self, tag: str, el: t.ElementT, write: WriterFn, indent: int) -> None:
        write(" " * indent)
        self.startTag(tag, el, write)

    def _writeRawElement(self, tag: str, el: t.ElementT, write: WriterFn, indent: int) -> None:
        if tag == "script" and el.get("src") is not None:
            # A *linking* script, doesn't need to be treated specially.
            write(" " * indent)
            self.startTag(tag, el, write)
            self.endTag(tag, write)
            return

        # Otherwise, dedent completely, since I don't know if indenting
        # is significant for the element.
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                msg = f"Somehow a CDATA element got an element child:\n{dom.outerHTML(el)}"
                raise Exception(msg)
            else:
                assert isinstance(node, str)
                write(node)
        self.endTag(tag, write)

    def _writeOpaqueElement(self, tag: str, el: t.ElementT, write: WriterFn, indent: int) -> None:
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                self._serializeEl(node, write, indent=indent, pre=True)
            else:
                assert isinstance(node, str)
                write(dom.escapeHTML(node))
        self.endTag(tag, write)

    def _writeInlineElement(self, tag: str, el: Nodes, write: WriterFn, inline: bool) -> None:
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                self._serializeEl(node, write, inline=inline)
            else:
                assert isinstance(node, str)
                write(dom.escapeHTML(self.fixWS(node)))
        self.endTag(tag, write)

    def _blocksFromChildren(self, children: t.Iterable[t.NodeT]) -> Nodes:
        return t.cast("Nodes", [block for block in self.groupIntoBlocks(children) if not self.justWS(block)])

    def _categorizeBlockChildren(self, el: Nodes) -> tuple[str, Nodes | None]:
        """
        Figure out what sort of contents the block has,
        so we know what serialization strategy to use.
        """
        if self.isElement(el) and len(el) == 0 and dom.emptyText(el.text):
            return "empty", None
        children = dom.childNodes(el, clear=True)
        for child in children:
            if self.isElement(child) and self.isBlockElement(child.tag):
                return "blocks", self._blocksFromChildren(children)
        return "inlines", children

    def _writeBlockElement(self, tag: str, el: t.ElementT, write: WriterFn, indent: int, nextEl: Nodes | None) -> None:
        # Dropping pure-WS anonymous blocks.
        # This maintains whitespace between *inline* elements, which is required.
        # It just avoids serializing a line of "inline content" that's just WS.
        contentsType, contents = self._categorizeBlockChildren(el)

        if contentsType == "empty":
            # Empty of text and children
            assert self.isElement(el)
            write(" " * indent)
            self.startTag(tag, el, write)
            if self.needsEndTag(el, nextEl):
                self.endTag(tag, write)
        elif contentsType == "inlines":
            # Contains only inlines, print accordingly
            assert contents is not None
            # el might be a list of inline content
            write(" " * indent)
            self.startTag(tag, el, write)
            self._serializeEl(contents, write, inline=True)
            if self.needsEndTag(el, nextEl):
                self.endTag(tag, write)
            return
        else:
            # Otherwise I'm a block that contains at least one block
            assert contents is not None
            assert self.isElement(el)
            write(" " * indent)
            self.startTag(tag, el, write)
            for block, nextBlock in t.cast("itertools.zip_longest[tuple[Nodes, Nodes|None]]", pairwise(contents)):
                if isinstance(block, list):
                    # is an array of inlines
                    if len(block) > 0:
                        write("\n" + (" " * (indent + 1)))
                        self._serializeEl(block, write, inline=True)
                else:
                    write("\n")
                    self._serializeEl(block, write, indent=indent + 1, nextEl=nextBlock)
            if self.needsEndTag(el, nextEl):
                write("\n" + (" " * indent))
                self.endTag(tag, write)

    def _serializeEl(
        self,
        el: Nodes,
        write: WriterFn,
        indent: int = 0,
        pre: bool = False,
        inline: bool = False,
        nextEl: Nodes | None = None,
    ) -> None:
        if isinstance(el, list):
            tag = "[]"
        else:
            tag = self.unfuckName(el.tag)

        if self.isVoidElement(tag):
            assert self.isElement(el)
            self._writeVoidElement(tag, el, write, indent)
        elif self.isRawElement(tag):
            assert self.isElement(el)
            self._writeRawElement(tag, el, write, indent)
        elif pre or self.isOpaqueElement(tag):
            assert self.isElement(el)
            self._writeOpaqueElement(tag, el, write, indent)
        elif inline:
            self._writeInlineElement(tag, el, write, inline)
        else:
            assert self.isElement(el)
            self._writeBlockElement(tag, el, write, indent, nextEl)


if t.TYPE_CHECKING:
    PairwiseU = t.TypeVar("PairwiseU")


def pairwise(iterable: t.Iterable[PairwiseU]) -> itertools.zip_longest[tuple[PairwiseU, PairwiseU | None]]:
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG GNone
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.zip_longest(a, b)
