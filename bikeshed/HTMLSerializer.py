# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import StringIO
from .htmlhelpers import childNodes, isElement, outerHTML, escapeHTML, escapeAttr
from .messages import *


class HTMLSerializer(object):
    inlineEls = frozenset(["a", "em", "strong", "small", "s", "cite", "q", "dfn", "abbr", "data", "time", "code", "var", "samp", "kbd", "sub", "sup", "i", "b", "u", "mark", "ruby", "bdi", "bdo", "span", "br", "wbr", "img", "meter", "progress", "[]"])
    rawEls = frozenset(["xmp", "script", "style"])
    voidEls = frozenset(["area", "base", "br", "col", "command", "embed", "hr", "img", "input", "keygen", "link", "meta", "param", "source", "track", "wbr"])
    omitEndTagEls = frozenset(["td", "th", "tr", "thead", "tbody", "tfoot", "colgroup", "col", "li", "dt", "dd", "html", "head", "body"])

    def __init__(self, tree, opaqueElements, blockElements):
        self.tree = tree
        self.opaqueEls = frozenset(opaqueElements)
        self.blockEls = frozenset(blockElements)

    def serialize(self):
        output = StringIO.StringIO()
        writer = output.write
        writer("<!doctype html>")
        root = self.tree.getroot()
        self._serializeEl(root, writer)
        str = output.getvalue()
        output.close()
        return str

    def unfuckName(self, n):
        # LXML does namespaces stupidly
        if n.startswith("{"):
            return n.partition("}")[2]
        return n

    def groupIntoBlocks(self, nodes):
        collect = []
        for node in nodes:
            if self.isElement(node) and not self.isInlineElement(node.tag):
                yield collect
                collect = []
                yield node
                continue
            else:
                collect.append(node)
        yield collect

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
        if tag != "[]":
            write("<" + tag)
            for attrName, attrVal in sorted(el.items()):
                write(" " + self.unfuckName(attrName) + '="' + escapeAttr(attrVal) + '"')
            write(">")

    def endTag(self, tag, write):
        if tag != "[]":
            write("</" + tag + ">")

    def isElement(self, node):
        return isElement(node)

    def isAnonBlock(self, block):
        return not isElement(block)

    def isVoidElement(self, tag):
        return tag in self.voidEls

    def isRawElement(self, tag):
        return tag in self.rawEls

    def isOpaqueElement(self, tag):
        return tag in self.opaqueEls

    def isInlineElement(self, tag):
        return (tag in self.inlineEls) or ("-" in tag and tag not in self.blockEls)

    def justWS(self, block):
        if self.isElement(block):
            return False
        return len(block) == 1 and not self.isElement(block[0]) and block[0].strip() == ""

    def _serializeEl(self, el, write, indent=0, pre=False, inline=False):
        if self.isElement(el):
            tag = self.unfuckName(el.tag)
        else:
            # el is an array
            tag = "[]"

        if self.isVoidElement(tag):
            write(" " * indent)
            self.startTag(tag, el, write)
            return
        elif self.isRawElement(tag):
            self.startTag(tag, el, write)
            for node in childNodes(el):
                if self.isElement(node):
                    die("Somehow a CDATA element got an element child:\n{0}", outerHTML(el))
                    return
                else:
                    write(node)
            self.endTag(tag, write)
            return
        elif pre or self.isOpaqueElement(tag):
            self.startTag(tag, el, write)
            for node in childNodes(el):
                if self.isElement(node):
                    self._serializeEl(node, write, indent=indent, pre=True)
                else:
                    write(escapeHTML(node))
            self.endTag(tag, write)
            return
        elif inline or self.isInlineElement(el):
            self.startTag(tag, el, write)
            for node in childNodes(el):
                if self.isElement(node):
                    self._serializeEl(node, write, inline=inline)
                else:
                    write(escapeHTML(self.fixWS(node)))
            self.endTag(tag, write)
            return

        # Otherwise I'm a block element.

        # Dropping pure-WS anonymous blocks.
        # This maintains whitespace between *inline* elements, which is required.
        # It just avoids serializing a line of "inline content" that's just WS.
        blocks = [block for block in self.groupIntoBlocks(childNodes(el)) if not self.justWS(block)]

        # Handle all the possibilities
        if len(blocks) == 0:
            write(" " * indent)
            self.startTag(tag, el, write)
            if el.tag not in self.omitEndTagEls:
                self.endTag(tag, write)
            return
        elif len(blocks) == 1 and self.isAnonBlock(blocks[0]):
            # Contains only inlines, print accordingly
            write(" " * indent)
            self.startTag(tag, el, write)
            self._serializeEl(blocks[0], write, inline=True)
            if el.tag not in self.omitEndTagEls:
                self.endTag(tag, write)
            return
        else:
            # Otherwise I'm a block that contains at least one block
            write(" " * indent)
            self.startTag(tag, el, write)
            for block in blocks:
                if self.isElement(block):
                    write("\n")
                    self._serializeEl(block, write, indent=indent + 1)
                else:
                    # is an array of inlines
                    if len(block) > 0:
                        write("\n" + (" " * (indent + 1)))
                        self._serializeEl(block, write, inline=True)
            if tag not in self.omitEndTagEls:
                write("\n" + (" " * indent))
                self.endTag(tag, write)
        return
