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

    def _serializeEl(self, el, write, indent=0, pre=False, inline=False):
        def unfuckName(n):
            # LXML does namespaces stupidly
            if n.startswith("{"):
                return n.partition("}")[2]
            return n
        def groupIntoBlocks(nodes):
            collect = []
            for node in nodes:
                if isElement(node) and not isInlineElement(node.tag):
                    yield collect
                    collect = []
                    yield node
                    continue
                else:
                    collect.append(node)
            yield collect
        def fixWS(text):
            import string
            t1 = text.lstrip(string.whitespace)
            if text != t1:
                t1 = " " + t1
            t2 = t1.rstrip(string.whitespace)
            if t1 != t2:
                t2 = t2 + " "
            return t2
        def startTag():
            if isElement(el):
                write("<")
                write(unfuckName(el.tag))
                for attrName, attrVal in sorted(el.items()):
                    write(" ")
                    write(unfuckName(attrName))
                    write('="')
                    write(escapeAttr(attrVal))
                    write('"')
                write(">")
        def endTag():
            if isElement(el):
                write("</")
                write(unfuckName(el.tag))
                write(">")
        def isAnonBlock(block):
            return not isElement(block)
        def isVoidElement(tag):
            return tag in self.voidEls
        def isRawElement(tag):
            return tag in self.rawEls
        def isOpaqueElement(tag):
            return tag in self.opaqueEls
        def isInlineElement(tag):
            return (tag in self.inlineEls) or ("-" in tag and tag not in self.blockEls)

        if isElement(el):
            tag = unfuckName(el.tag)
        else:
            # el is an array
            tag = "[]"

        if isVoidElement(tag):
            write(" "*indent)
            startTag()
            return
        if isRawElement(tag):
            startTag()
            for node in childNodes(el):
                if isElement(node):
                    die("Somehow a CDATA element got an element child:\n{0}", outerHTML(el))
                    return
                else:
                    write(node)
            endTag()
            return
        if pre or isOpaqueElement(tag):
            startTag()
            for node in childNodes(el):
                if isElement(node):
                    self._serializeEl(node, write, indent=indent, pre=True)
                else:
                    write(escapeHTML(node))
            endTag()
            return
        if inline or isInlineElement(el):
            startTag()
            for node in childNodes(el):
                if isElement(node):
                    self._serializeEl(node, write, inline=inline)
                else:
                    write(escapeHTML(fixWS(node)))
            endTag()
            return

        # Otherwise I'm a block element
        def justWS(block):
            if isElement(block):
                return False
            return len(block) == 1 and not isElement(block[0]) and block[0].strip() == ""
        # Dropping pure-WS anonymous blocks.
        # This maintains whitespace between *inline* elements, which is required.
        # It just avoids serializing a line of "inline content" that's just WS.
        blocks = [block for block in groupIntoBlocks(childNodes(el)) if not justWS(block)]

        # Handle all the possibilities
        if len(blocks) == 0:
            write(" "*indent)
            startTag()
            if el.tag not in self.omitEndTagEls:
                endTag()
            return
        elif len(blocks) == 1 and isAnonBlock(blocks[0]):
            # Contains only inlines, print accordingly
            write(" "*indent)
            startTag()
            self._serializeEl(blocks[0], write, inline=True)
            if el.tag not in self.omitEndTagEls:
                endTag()
            return
        else:
            # Otherwise I'm a block that contains at least one block
            write(" "*indent)
            startTag()
            for block in blocks:
                if isElement(block):
                    write("\n")
                    self._serializeEl(block, write, indent=indent+1)
                else:
                    # is an array of inlines
                    if len(block) > 0:
                        write("\n")
                        write(" "*(indent+1))
                        self._serializeEl(block, write, inline=True)
            if el.tag not in self.omitEndTagEls:
                write("\n")
                write(" "*indent)
                endTag()
        return
