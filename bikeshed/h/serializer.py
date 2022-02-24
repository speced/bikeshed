import io
import itertools

from . import dom


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
        ]
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
        ]
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
        ]
    )

    def __init__(self, opaqueElements, blockElements):
        self.opaqueEls = frozenset(opaqueElements)
        self.blockEls = frozenset(blockElements)

    def serialize(self, tree):
        output = io.StringIO()
        writer = output.write
        writer("<!doctype html>")
        self._serializeEl(tree.getroot(), writer)
        s = output.getvalue()
        output.close()
        return s

    def unfuckName(self, n):
        # LXML does namespaces stupidly
        if n.startswith("{"):
            return n.partition("}")[2]
        return n

    def groupIntoBlocks(self, nodes):
        nonBlockNodes = []
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

    def fixWS(self, text):
        import string

        t1 = text.lstrip(string.whitespace)
        if text != t1:
            t1 = " " + t1
        t2 = t1.rstrip(string.whitespace)
        if t1 != t2:
            t2 = t2 + " "
        return t2

    def startTag(self, tag, el, write):
        if tag == "[]":
            return
        if not dom.hasAttrs(el):
            write("<" + tag + ">")
            return

        strs = []
        strs.append("<" + tag)
        for attrName, attrVal in sorted(el.items()):
            if attrVal == "":
                strs.append(" " + self.unfuckName(attrName))
            else:
                strs.append(" " + self.unfuckName(attrName) + '="' + dom.escapeAttr(attrVal) + '"')
        strs.append(">")
        write("".join(strs))

    def endTag(self, tag, write):
        if tag != "[]":
            write("</" + tag + ">")

    def isElement(self, node):
        return dom.isElement(node)

    def isAnonBlock(self, block):
        return not dom.isElement(block)

    def isVoidElement(self, tag):
        return tag in self.voidEls

    def isRawElement(self, tag):
        return tag in self.rawEls

    def isOpaqueElement(self, tag):
        return tag in self.opaqueEls

    def isInlineElement(self, tag):
        return (tag in self.inlineEls) or ("-" in tag and tag not in self.blockEls)

    def isBlockElement(self, tag):
        return not self.isInlineElement(tag)

    def needsEndTag(self, el, nextEl=None):
        if el.tag not in self.omitEndTagEls:
            return True
        if el.tag in ["dt", "dd"]:
            if nextEl is None:
                return False
            if self.isElement(nextEl) and nextEl.tag in ["dt", "dd"]:
                return False
            return True

    def justWS(self, block):
        if self.isElement(block):
            return False
        return len(block) == 1 and not self.isElement(block[0]) and block[0].strip() == ""

    def _writeVoidElement(self, tag, el, write, indent):
        write(" " * indent)
        self.startTag(tag, el, write)

    def _writeRawElement(self, tag, el, write):
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                raise Exception(f"Somehow a CDATA element got an element child:\n{dom.outerHTML(el)}")
            else:
                write(node)
        self.endTag(tag, write)

    def _writeOpaqueElement(self, tag, el, write, indent):
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                self._serializeEl(node, write, indent=indent, pre=True)
            else:
                write(dom.escapeHTML(node))
        self.endTag(tag, write)

    def _writeInlineElement(self, tag, el, write, inline):
        self.startTag(tag, el, write)
        for node in dom.childNodes(el):
            if self.isElement(node):
                self._serializeEl(node, write, inline=inline)
            else:
                write(dom.escapeHTML(self.fixWS(node)))
        self.endTag(tag, write)

    def _blocksFromChildren(self, children):
        return [block for block in self.groupIntoBlocks(children) if not self.justWS(block)]

    def _categorizeBlockChildren(self, el):
        """
        Figure out what sort of contents the block has,
        so we know what serialization strategy to use.
        """
        if len(el) == 0 and dom.emptyText(el.text):
            return "empty", None
        children = dom.childNodes(el, clear=True)
        for child in children:
            if self.isElement(child) and self.isBlockElement(child.tag):
                return "blocks", self._blocksFromChildren(children)
        return "inlines", children

    def _writeBlockElement(self, tag, el, write, indent, nextEl):
        # Dropping pure-WS anonymous blocks.
        # This maintains whitespace between *inline* elements, which is required.
        # It just avoids serializing a line of "inline content" that's just WS.
        contentsType, contents = self._categorizeBlockChildren(el)

        if contentsType == "empty":
            # Empty of text and children
            write(" " * indent)
            self.startTag(tag, el, write)
            if self.needsEndTag(el, nextEl):
                self.endTag(tag, write)
        elif contentsType == "inlines":
            # Contains only inlines, print accordingly
            write(" " * indent)
            self.startTag(tag, el, write)
            self._serializeEl(contents, write, inline=True)
            if self.needsEndTag(el, nextEl):
                self.endTag(tag, write)
            return
        else:
            # Otherwise I'm a block that contains at least one block
            write(" " * indent)
            self.startTag(tag, el, write)
            for block, nextBlock in pairwise(contents):
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

    def _serializeEl(self, el, write, indent=0, pre=False, inline=False, nextEl=None):
        if isinstance(el, list):
            tag = "[]"
        else:
            tag = self.unfuckName(el.tag)

        if self.isVoidElement(tag):
            self._writeVoidElement(tag, el, write, indent)
        elif self.isRawElement(tag):
            self._writeRawElement(tag, el, write)
        elif pre or self.isOpaqueElement(tag):
            self._writeOpaqueElement(tag, el, write, indent)
        elif inline or self.isInlineElement(el):
            self._writeInlineElement(tag, el, write, inline)
        else:
            self._writeBlockElement(tag, el, write, indent, nextEl)


def pairwise(iterable):
    # pairwise('ABCDEFG') --> AB BC CD DE EF FG GNone
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.zip_longest(a, b)
