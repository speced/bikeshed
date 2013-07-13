import html5lib
from html5lib import treewalkers
from html5lib.serializer import htmlserializer
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
from fuckunicode import u

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
    for prevEl in prevElements(el):
        if prevEl.tag in ("h2", "h3", "h4", "h5", "h6") and prevEl.get('data-level') is not None:
            return u(prevEl.get('data-level'))
    return None


def prevElements(startEl, tag=None, *tags):
    els = []
    for el in startEl.getroottree().getroot().iter(tag=tag, *tags):
        if el == startEl:
            return reversed(els)
        els.append(el)
