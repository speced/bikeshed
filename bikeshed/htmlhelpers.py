# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import hashlib
import html5lib
from html5lib import treewalkers
from html5lib.serializer import htmlserializer
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
import re
import HTMLParser

from . import config
from .messages import *

unescapeParser = HTMLParser.HTMLParser()
def unescape(string):
    return unescapeParser.unescape(string)

def findAll(sel, context):
    if isinstance(context, config.specClass):
        context = context.document
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

def escapeCSSIdent(val):
    if len(val) == 0:
        die("Programming error: can't escape an empty ident.")
        return ""
    ident = "";
    firstCode = val[0]
    for i,code in enumerate(ord(x) for x in val):
        if code == 0:
            die("Invalid character: the string '{0}' somehow has a NUL in it.", val)
            return ""
        if (0x1 <= code <= 0x1f or
            code == 0x7f or
            (i == 0 and 0x30 <= code <= 0x39) or
            (i == 1 and 0x30 <= code <= 0x39 and firstCode == 0x2d)):
            ident += r"\{0:x} ".format(code)
        elif (code >= 0x80 or
            code == 0x2d or
            code == 0x5f or
            0x30 <= code <= 0x39 or
            0x41 <= code <= 0x5a or
            0x61 <= code <= 0x7a):
            ident += chr(code)
        else:
            ident += r"\{0}".format(chr(code))
    return ident

def textContent(el):
    return html.tostring(el, method='text', with_tail=False, encoding="unicode")


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
    head = doc.getroot()[0]
    body = doc.getroot()[1]
    if len(body) or body.text is not None:
        # Body contains something, so return that.
        contents = [body.text] if body.text is not None else []
        contents.extend(body.iterchildren())
        return contents
    elif len(head) or head.text is not None:
        # Okay, anything in the head?
        contents = [head.text] if head.text is not None else []
        contents.extend(head.iterchildren())
        return contents
    else:
        return []


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

def parentElement(el):
    return el.getparent()


def appendChild(parent, *children):
    # Appends either text or an element.
    for child in children:
        if isinstance(child, basestring):
            if len(parent) > 0:
                parent[-1].tail = (parent[-1].tail or '') + child
            else:
                parent.text = (parent.text or '') + child
        else:
            if len(parent) == 0 and parent.text is not None:
                # LXML "helpfully" assumes you meant to insert it before the text,
                # and so moves the text into the element's tail when you append.
                text, parent.text = parent.text, None
                parent.append(child)
                parent.text = text
            else:
                # For some reason it doesn't make any weird assumptions about text
                # when the parent already has children; the last child's tail
                # doesn't get moved into the appended child or anything.
                parent.append(child)
    return children[-1] if len(children) else None

def prependChild(parent, child):
    # Prepends either text or an element to the parent.
    if isinstance(child, basestring):
        if parent.text is None:
            parent.text = child
        else:
            parent.text = child + parent.text
    else:
        removeNode(child)
        parent.insert(0, child)
        if parent.text is not None:
            child.tail = (child.tail or '') + parent.text
            parent.text = None

def insertBefore(target, el):
    parent = target.getparent()
    parent.insert(parent.index(target), el)

def insertAfter(target, *els):
    parent = target.getparent()
    for el in els:
        if isinstance(el, basestring):
            target.tail = (target.tail or '') + el
        else:
            parent.insert(parent.index(target)+1, el)
            target = el
    return target


def removeNode(node):
    parent = node.getparent()
    if parent is None:
        return node
    index = parent.index(node)
    text = node.tail or ''
    if index == 0:
        parent.text = (parent.text or '') + text
    else:
        prevsibling = parent[index-1]
        prevsibling.tail = (prevsibling.tail or '') + text
    parent.remove(node)
    node.tail = None
    return node


def appendContents(el, container):
    # Accepts either an iterable *or* a container element
    if isElement(container):
        container = childNodes(container, clear=True)
    appendChild(el, *container)
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

def childElements(parentEl, tag="*", *tags, **stuff):
    return parentEl.iterchildren(tag=tag, *tags, **stuff)

def childNodes(parentEl, clear=False, skipWS=False):
    '''
    This function returns all the nodes in a parent element in the DOM sense,
    mixing text nodes (strings) and other nodes together
    (rather than LXML's default handling of text).

    If you set "clear" to True, it'll
    1. remove all of parentEl's children,
       so you can append nodes back to it safely, and
    2. Set parentEl.text and child elements' .tail to null,
       again so you can safely append text to parentEl.
    In other words, the following is a no-op:

    ```
    appendChild(parentEl, *childNodes(parentEl, clear=True))
    ```

    But omitting the clear=True argument will, generally,
    have stupid and nonsensical results,
    as text is duplicated and placed in weird spots.

    Nonetheless, clear is False by default,
    to avoid doing extra computation when not needed,
    and to match the DOM method's behavior.
    '''
    if isinstance(parentEl, list):
        return parentEl
    ret = []
    if parentEl.text is not None:
        if parentEl.text.strip() != "" or not skipWS:
            ret.append(parentEl.text)
        if clear:
            parentEl.text = None
    for c in childElements(parentEl, tag=None):
        ret.append(c)
        if c.tail is not None:
            if c.tail.strip() != "" or not skipWS:
                ret.append(c.tail)
            if clear:
                c.tail = None
    if clear:
        clearContents(parentEl)
    return ret

def treeAttr(el, attrName):
    # Find the nearest instance of the given attr in the tree
    # Useful for when you can put an attr on an ancestor and apply it to all contents.
    # Returns attrValue or None if nothing is found.
    import itertools as it
    for target in it.chain([el], el.iterancestors()):
        if target.get(attrName) is not None:
            return target.get(attrName)

def closestAttr(el, *attrs):
    # Like treeAttr, but can provide multiple attr names, and returns the first one found.
    # Useful with combos like highlight/nohighlight
    # If multiple target attrs show up on same element, priority is calling order.
    # Returns a tuple of (attrName, attrValue) or (None, None) if nothing is found.
    import itertools as it
    for target in it.chain([el], el.iterancestors()):
        for attrName in attrs:
            if target.get(attrName) is not None:
                return attrName, target.get(attrName)
    return None, None

def removeAttr(el, attrName):
    # Remove an attribute, silently ignoring if attr doesn't exist.
    try:
        del el.attrib[attrName]
    except:
        pass
    return el


def addClass(el, cls):
    if el.get('class') is None:
        el.set('class', cls)
    elif hasClass(el, cls):
        pass
    else:
        el.set('class', "{0} {1}".format(el.get('class'), cls))

def hasClass(el, cls):
    if el.get('class') is None:
        return False
    paddedAttr = " {0} ".format(el.get('class'))
    paddedCls = " {0} ".format(cls)
    return paddedCls in paddedAttr

def removeClass(el, cls):
    oldClass = el.get('class')
    if oldClass is None:
        return
    newClass = ' '.join(c for c in oldClass.split() if c != cls)
    if newClass == "":
        del el.attrib['class']
    else:
        el.set('class', newClass)


def isElement(node):
    # LXML HAS THE DUMBEST XML TREE DATA MODEL IN THE WORLD
    return etree.iselement(node) and isinstance(node.tag, basestring)

def fixTypography(text):
    # Replace straight aposes with curly quotes for possessives and contractions.
    text = re.sub(r"([\w])'([\w])", r"\1’\2", text)
    text = re.sub(r"(</[\w]+>)'([\w])", r"\1’\2", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"([^<][^!])(—|--)\r?\n\s*(\S)", r"\1—<wbr>\3", text)
    return text

def unfixTypography(text):
    # Replace curly quotes with straight quotes, and emdashes with double dashes.
    text = re.sub(r"’", r"'", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"—<wbr>", r"--", text)
    return text

def hashContents(el):
    # Hash the contents of an element into an 8-character alphanum string.
    # Generally used for generating probably-unique IDs.
    return hashlib.md5(innerHTML(el).strip().encode("ascii", "xmlcharrefreplace")).hexdigest()[0:8]

def createElement(tag, attrs={}, *children):
    el = etree.Element(tag, {n:v for n,v in attrs.items() if v is not None})
    for child in children:
        appendChild(el, child)
    return el

class ElementCreationHelper:
    def __getattr__(self, name):
        def _creater(*children):
            if children and not (isinstance(children[0], basestring) or isElement(children[0])):
                attrs = children[0]
                children = children[1:]
            else:
                attrs = {}
            return createElement(name, attrs, *children)
        return _creater
E = ElementCreationHelper()
