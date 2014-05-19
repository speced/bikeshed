# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import html5lib
from html5lib import treewalkers
from html5lib.serializer import htmlserializer
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
import re

from . import config
from .messages import *


def findAll(sel, context=None):
    if context is None:
        context = config.doc.document
    try:
        return CSSSelector(sel, namespaces={"svg":"http://www.w3.org/2000/svg"})(context)
    except Exception, e:
        die("The selector '{0}' returned an error:\n{1}", sel, e)
        return []


def find(sel, context=None):
    result = findAll(sel, context)
    if result:
        return result[0]
    else:
        return None

def textContent(el):
    str =  html.tostring(el, method='text', with_tail=False, encoding="unicode")
    return re.sub(r"\s+", r" ", str)


def innerHTML(el):
    if el is None:
        return ''
    return (el.text or '') + ''.join(html.tostring(x, encoding="unicode") for x in el)


def outerHTML(el):
    if el is None:
        return ''
    return html.tostring(el, with_tail=False, encoding="unicode")


def parseHTML(text):
    doc = html5lib.parse(text, treebuilder='lxml', namespaceHTMLElements=False)
    body = doc.getroot()[1]
    if body.text is None:
        if len(body):
            return list(body.iterchildren())
        head = doc.getroot()[0]
        if head.text is None:
            return list(head.iterchildren())
        return [head.text] + list(head.iterchildren())
    else:
        return [body.text] + list(body.iterchildren())


def parseDocument(text):
    doc = html5lib.parse(text, treebuilder='lxml', namespaceHTMLElements=False)
    return doc


def escapeHTML(text):
    # Escape HTML
    return text.replace('&', '&amp;').replace('<', '&lt;')


def escapeAttr(text):
    return text.replace('&', '&amp;').replace("'", '&apos;').replace('"', '&quot;')


def clearContents(el):
    for child in el.iterchildren():
        el.remove(child)
    el.text = ''
    return el


def appendChild(parent, child):
    # Appends either text or an element.
    try:
        parent.append(child)
    except TypeError:
        # child is a string
        if len(parent) > 0:
            parent[-1].tail = (parent[-1].tail or '') + child
        else:
            parent.text = (parent.text or '') + child

def prependChild(parent, child):
    # Prepends either text or an element to the parent.
    if isinstance(child, basestring):
        if parent.text is None:
            parent.text = child
        else:
            parent.text = child + parent.text
    else:
        parent.insert(0, child)
        if parent.text is not None:
            child.tail = (child.tail or '') + parent.text
            parent.text = None

def insertBefore(target, el):
    parent = target.getparent()
    parent.insert(parent.index(target), el)

def insertAfter(target, el):
    parent = target.getparent()
    parent.insert(parent.index(target)+1, el)


def removeNode(node):
    text = node.tail or ''
    parent = node.getparent()
    index = parent.index(node)
    if index == 0:
        parent.text = (parent.text or '') + text
    else:
        prevsibling = parent[index-1]
        prevsibling.tail = (prevsibling.tail or '') + text
    parent.remove(node)


def appendContents(el, newElements):
    if(etree.iselement(newElements) and newElements.text is not None):
        appendChild(el, newElements.text)
    for new in newElements:
        appendChild(el, new)
    return el


def replaceContents(el, newElements):
    clearContents(el)
    return appendContents(el, newElements)


def moveContents(targetEl, sourceEl):
    replaceContents(targetEl, sourceEl)
    sourceEl.text = ''


def headingLevelOfElement(el):
    for el in relevantHeadings(el, levels=[2,3,4,5,6]):
        if el.get('data-level') is not None:
            return el.get('data-level')
    return None


def relevantHeadings(startEl, levels=None):
    if levels is None:
        levels = [1,2,3,4,5,6]
    levels = ["h"+str(level) for level in levels]
    currentHeadingLevel = float('inf')
    for el in scopingElements(startEl, *levels):
        tagLevel = int(el.tag[1])
        if tagLevel < currentHeadingLevel:
            yield el
            currentHeadingLevel = tagLevel
        if tagLevel == 2:
            return


def scopingElements(startEl, *tags):
    # Elements that could form a "scope" for the startEl
    # Ancestors, and preceding siblings of ancestors.
    # Maps to the things that can establish a counter scope.
    els = []
    tagFilter = set(tags)

    for el in startEl.itersiblings(preceding=True, *tags):
        els.append(el)
    for el in startEl.iterancestors():
        if el.tag in tagFilter:
            els.append(el)
        for el in el.itersiblings(preceding=True, *tags):
            els.append(el)
    return els

def previousElements(startEl, tag=None, *tags):
    # Elements preceding the startEl in document order.
    # Like .iter(), but in the opposite direction.
    els = []
    for el in startEl.getroottree().getroot().iter(tag=tag, *tags):
        if el == startEl:
            return reversed(els)
        els.append(el)
    return els

def treeAttr(el, attrName):
    if el.get(attrName) is not None:
        return el.get(attrName)
    for ancestor in el.iterancestors():
        if ancestor.get(attrName) is not None:
            return ancestor.get(attrName)


def addClass(el, cls):
    if el.get('class') is None:
        el.set('class', cls)
    else:
        el.set('class', "{0} {1}".format(el.get('class'), cls))

def hasClass(el, cls):
    if el.get('class') is None:
        return False
    paddedAttr = " {0} ".format(el.get('class'))
    paddedCls = " {0} ".format(cls)
    return paddedCls in paddedAttr

def isElement(node):
    return isinstance(node.tag, basestring)

def isOpaqueElement(el):
    return el.tag in ('pre', 'code', 'style', 'script')

def fixTypography(text):
    # Replace straight aposes with curly quotes for possessives and contractions.
    text = re.sub(r"([\w])'([\w])", r"\1’\2", text)
    text = re.sub(r"(</[\w]+>)'([\w])", r"\1’\2", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"([^<][^!])(—|--)\r?\n\s+(\S)", r"\1—<wbr>\3", text)
    return text

def unfixTypography(text):
    # Replace curly quotes with straight quotes, and emdashes with double dashes.
    text = re.sub(r"’", r"'", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"—<wbr>", r"--", text)
    return text
