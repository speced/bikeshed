import html5lib
from html5lib import treewalkers
from html5lib.serializer import htmlserializer
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
from lib.fuckunicode import u
import lib.config as config

def findAll(sel, context=None):
    if context is None:
        context = config.doc.document
    return CSSSelector(sel)(context)


def find(sel, context=None):
    result = findAll(sel, context)
    if result:
        return result[0]
    else:
        return None

def textContent(el):
    return u(html.tostring(el, method='text', with_tail=False, encoding="unicode"))


def innerHTML(el):
    return u((el.text or u'') + u''.join(u(html.tostring(x, encoding="unicode")) for x in el))


def outerHTML(el):
    return u(html.tostring(el, with_tail=False, encoding="unicode"))


def parseHTML(str):
    doc = html5lib.parse(u(str), treebuilder='lxml', namespaceHTMLElements=False)
    body = doc.getroot()[1]
    if body.text is None:
        return list(body.iterchildren())
    else:
        return [body.text] + list(body.iterchildren())


def parseDocument(str):
    doc = html5lib.parse(u(str), treebuilder='lxml', namespaceHTMLElements=False)
    return doc


def escapeHTML(str):
    # Escape HTML
    return u(str).replace(u'&', u'&amp;').replace(u'<', u'&lt;')


def escapeAttr(str):
    return u(str).replace(u'&', u'&amp;').replace(u"'", u'&apos;').replace(u'"', u'&quot;')


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


def replaceContents(el, newElements):
    clearContents(el)
    if(etree.iselement(newElements) and newElements.text is not None):
        appendChild(el, newElements.text)
    for new in newElements:
        appendChild(el, new)
    return el


def moveContents(targetEl, sourceEl):
    replaceContents(targetEl, sourceEl)
    sourceEl.text = ''


def headingLevelOfElement(el):
    for el in relevantHeadings(el, levels=[2,3,4,5,6]):
        if el.get('data-level') is not None:
            return u(el.get('data-level'))
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