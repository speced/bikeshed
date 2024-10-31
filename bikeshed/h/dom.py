from __future__ import annotations

import collections.abc
import hashlib
import re
from collections import OrderedDict

import html5lib
from lxml import etree
from lxml.cssselect import CSSSelector
from lxml.html import tostring

from .. import t
from ..messages import die, warn

if t.TYPE_CHECKING:
    ElementPredT: t.TypeAlias = t.Callable[[t.ElementT], bool]


def flatten(arr: t.Iterable) -> t.Iterator:
    for el in arr:
        if isinstance(el, collections.abc.Iterable) and not isinstance(el, str) and not etree.iselement(el):
            yield from flatten(el)
        else:
            yield el


def unescape(string: str) -> str:
    import html

    return html.unescape(string)


def findAll(sel: str, context: t.SpecT | t.ElementT | t.DocumentT) -> list[t.ElementT]:
    context = t.cast("t.ElementT", getattr(context, "document", context))
    try:
        return t.cast("list[t.ElementT]", CSSSelector(sel, namespaces={"svg": "http://www.w3.org/2000/svg"})(context))
    except Exception as e:
        die(f"The selector '{sel}' returned an error:\n{e}")
        return []


def find(sel: str, context: t.SpecT | t.ElementT | t.DocumentT) -> t.ElementT | None:
    result = findAll(sel, context)
    if result:
        return result[0]
    else:
        return None


def escapeCSSIdent(val: str) -> str:
    if len(val) == 0:
        die("Programming error: can't escape an empty ident.")
        return ""
    ident = ""
    firstCode = val[0]
    for i, code in enumerate(ord(x) for x in val):
        if code == 0:
            die(f"Invalid character: the string '{val}' somehow has a NUL in it.")
            return ""
        if (
            0x1 <= code <= 0x1F
            or code == 0x7F
            or (i == 0 and 0x30 <= code <= 0x39)
            or (i == 1 and 0x30 <= code <= 0x39 and firstCode == 0x2D)
        ):
            ident += rf"\{code:x} "
        elif (
            code >= 0x80 or code in (0x2D, 0x5F) or 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A or 0x61 <= code <= 0x7A
        ):
            ident += chr(code)
        else:
            ident += r"\{}".format(chr(code))
    return ident


def escapeUrlFrag(val: str) -> str:
    result = ""
    for char in val:
        if validUrlUnit(char):
            result += char
        else:
            for b in char.encode("utf-8"):
                result += f"%{b:0>2x}"
    return result


def validUrlUnit(char: str) -> bool:
    c = ord(char)
    if c < 0xA0:
        # ASCII range
        return (
            c in (0x21, 0x24)
            or 0x26 <= c <= 0x29
            or 0x2A <= c <= 0x3B
            or c == 0x3D
            or 0x3F <= c <= 0x5A
            or c == 0x5F
            or 0x61 <= c <= 0x7A
            or c == 0x7E
        )
    else:
        if 0xD800 <= c <= 0xDFFF or 0xFDD0 <= c <= 0xFDEF:
            return False
        if (c % 0xFFFF) in [0xFFFE, 0xFFFF]:  # noqa: SIM103
            # Last two bytes are FFFE or FFFF
            return False
        return True


def textContent(el: t.ElementT, exact: bool = False) -> str:
    # If exact is False, then any elements with data-deco attribute
    # get ignored in the textContent.
    # This allows me to ignore things added by Bikeshed by default.
    if len(el) == 0:
        return el.text or ""
    if exact:
        return t.cast(str, tostring(el, method="text", with_tail=False, encoding="unicode"))
    else:
        return textContentIgnoringDecorative(el)


def textContentIgnoringDecorative(el: t.ElementT) -> str:
    s = ""
    for child in childNodes(el):
        if isinstance(child, str):
            s += child
        elif child.get("data-deco") is None:
            s += textContentIgnoringDecorative(child)
    return s


def innerHTML(el: t.ElementT | None) -> str:
    if el is None:
        return ""
    return (el.text or "") + "".join(tostring(x, encoding="unicode") for x in el)


def outerHTML(el: t.NodesT | None, literal: bool = False, with_tail: bool = False) -> str:
    if el is None:
        return ""
    if isinstance(el, str):
        return el
    if isinstance(el, list):
        return "".join(outerHTML(x) for x in el)
    if el.get("bs-autolink-syntax") is not None and not literal:
        return el.get("bs-autolink-syntax") or ""
    return t.cast(str, tostring(el, with_tail=with_tail, encoding="unicode"))


def printNodeTree(node: t.NodeT | str) -> str:
    # Debugging tool
    if isinstance(node, str):
        return "#text: " + repr(node)
    if isOddNode(node):
        return outerHTML(node)
    if isinstance(node, list):
        s = "[]"
    else:
        s = f"{serializeTag(node)}"
    linesPerChild = [printNodeTree(child).split("\n") for child in childNodes(node, skipOddNodes=False)]
    if linesPerChild:
        for childLines in linesPerChild[:-1]:
            childLines[0] = " ├" + childLines[0]
            childLines[1:] = [" │" + line for line in childLines[1:]]
            s += "\n" + "\n".join(childLines)
        childLines = linesPerChild[-1]
        childLines[0] = " ╰" + childLines[0]
        childLines[1:] = ["  " + line for line in childLines[1:]]
        s += "\n" + "\n".join(childLines)
    return s


def linkTextsFromElement(el: t.ElementT) -> list[str]:
    if el.get("data-lt") == "":
        return []
    elif el.get("data-lt"):
        rawText = el.get("data-lt", "")
        if rawText in ["|", "||", "|||"]:
            texts = [rawText]
        else:
            texts = [x.strip() for x in rawText.split("|")]
    else:
        if el.tag in ("dfn", "a"):
            texts = [textContent(el).strip()]
        elif el.tag in ("h2", "h3", "h4", "h5", "h6"):
            textEl = find(".content", el)
            if textEl is None:
                textEl = el
            texts = [textContent(textEl).strip()]
    if el.get("data-local-lt"):
        localTexts = [x.strip() for x in el.get("data-local-lt", "").split("|")]
        for text in localTexts:
            if text in texts:
                # lt and local-lt both specify the same thing
                raise DuplicatedLinkText(text, texts + localTexts, el)
        texts += localTexts

    texts = [re.sub(r"\s+", " ", x) for x in texts if x != ""]
    return texts


class DuplicatedLinkText(Exception):
    def __init__(self, offendingText: str, allTexts: list[str], el: t.ElementT) -> None:
        super().__init__()
        self.offendingText = offendingText
        self.allTexts = allTexts
        self.el = el

    def __unicode__(self) -> str:
        return f"<Text '{self.offendingText}' shows up in both lt and local-lt>"


def firstLinkTextFromElement(el: t.ElementT) -> str | None:
    try:
        texts = linkTextsFromElement(el)
    except DuplicatedLinkText as e:
        texts = e.allTexts
    return texts[0] if len(texts) > 0 else None


def serializeTag(el: t.ElementT) -> str:
    # Serialize *just* the opening tag for the element.
    # Use when you want to output the HTML,
    # but it might be a container with a lot of content.
    tag = "<" + el.tag
    for n, v in el.attrib.items():
        tag += ' {n}="{v}"'.format(n=str(n), v=escapeAttr(str(v)))
    tag += ">"
    return tag


def tagName(el: t.ElementT | None) -> str | None:
    # Returns the tagname, or None if passed None
    # Iow, safer version of el.tagName
    if el is None:
        return None
    return el.tag


def foldWhitespace(text: str) -> str:
    return re.sub(r"(\s|\xa0)+", " ", text)


def sortElements(el: t.Iterable[t.ElementT]) -> list[t.ElementT]:
    return sorted(el, key=lambda x: (x.get("bs-line-number", ""), textContent(x)))


def parseHTML(text: str) -> list[t.ElementT]:
    doc = html5lib.parse(text, treebuilder="lxml", namespaceHTMLElements=False)
    head = doc.getroot()[0]
    body = doc.getroot()[1]
    if len(body) > 0 or body.text is not None:
        # Body contains something, so return that.
        contents = [body.text] if body.text is not None else []
        contents.extend(childElements(body))
        return contents
    elif len(head) > 0 or head.text is not None:
        # Okay, anything in the head?
        contents = [head.text] if head.text is not None else []
        contents.extend(childElements(head))
        return contents
    else:
        return []


def parseDocument(text: str) -> t.DocumentT:
    doc = html5lib.parse(text, treebuilder="lxml", namespaceHTMLElements=False)
    return t.cast("t.DocumentT", doc)


def escapeHTML(text: str) -> str:
    # Escape HTML
    return text.replace("&", "&amp;").replace("<", "&lt;")


def escapeAttr(text: str) -> str:
    return text.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;")


def clearContents(el: t.ElementT) -> t.ElementT:
    del el[:]
    el.text = ""
    return el


def parentElement(el: t.ElementT | None, depth: int = 1) -> t.ElementT | None:
    for _ in range(depth):
        if el is None:
            return None
        el = el.getparent()
    return el


def nextSiblingNode(el: t.ElementT) -> t.ElementT | None:
    return el.getnext()


def nextSiblingElement(el: t.ElementT) -> t.ElementT | None:
    while True:
        next = nextSiblingNode(el)
        if next is None:
            return None
        if isElement(next):
            return next


@t.overload
def appendChild(parent: t.ElementT, *els: t.NodesT, allowEmpty: t.Literal[False] = False) -> t.ElementT: ...


@t.overload
def appendChild(parent: t.ElementT, *els: t.NodesT, allowEmpty: bool) -> t.ElementT | None: ...


def appendChild(parent: t.ElementT, *els: t.NodesT, allowEmpty: bool = False) -> t.ElementT | None:
    # Appends either text or an element.
    child: t.NodeT | None = None
    for child in flatten(els):
        assert child is not None
        if isinstance(child, str):
            if len(parent) > 0:
                parent[-1].tail = (parent[-1].tail or "") + child
            else:
                parent.text = (parent.text or "") + child
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
    if child is None and not allowEmpty:
        msg = "Empty child list appended without allowEmpty=True"
        raise Exception(msg)
    if isElement(child):
        return child
    else:
        return None


def prependChild(parent: t.ElementT, *children: t.NodesT) -> None:
    # Prepends either text or an element to the parent.
    for child in reversed(list(flatten(children))):
        if isinstance(child, str):
            if parent.text is None:
                parent.text = child
            else:
                parent.text = child + parent.text
        else:
            removeNode(child)
            parent.insert(0, child)
            if parent.text is not None:
                child.tail = (child.tail or "") + parent.text
                parent.text = None


def insertBefore(target: t.ElementT, *els: t.NodesT) -> t.ElementT:
    parent = target.getparent()
    assert parent is not None
    index = parent.index(target)
    prevSibling = parent[index - 1] if index > 0 else None
    for el in flatten(els):
        if isinstance(el, str):
            if prevSibling is not None:
                prevSibling.tail = (prevSibling.tail or "") + el
            else:
                parent.text = (parent.text or "") + el
        else:
            parent.insert(index, el)
            index += 1
            prevSibling = el
    return target


def insertAfter(target: t.ElementT, *els: t.NodesT) -> t.ElementT:
    parent = target.getparent()
    assert parent is not None
    for el in flatten(els):
        if isinstance(el, str):
            target.tail = (target.tail or "") + el
        else:
            parent.insert(parent.index(target) + 1, el)
            target = el
    return target


def removeNode(node: t.ElementT) -> t.ElementT:
    parent = node.getparent()
    if parent is None:
        return node
    index = parent.index(node)
    text = node.tail or ""
    node.tail = None
    if index == 0:
        parent.text = (parent.text or "") + text
    else:
        prevsibling = parent[index - 1]
        prevsibling.tail = (prevsibling.tail or "") + text
    parent.remove(node)
    return node


def replaceNode(node: t.ElementT, *replacements: t.NodesT) -> t.NodesT | None:
    insertBefore(node, *replacements)
    removeNode(node)
    if replacements:
        return replacements[0]
    return None


def transferAttributes(source: t.ElementT, target: t.ElementT) -> t.ElementT:
    for k, v in source.attrib.items():
        target.set(k, v)
    return target


def appendContents(el: t.ElementT, container: t.ElementT | t.Iterable[t.NodesT]) -> t.ElementT:
    # Accepts either an iterable *or* a container element
    if isElement(container):
        container = childNodes(container, clear=True)
    appendChild(el, *container, allowEmpty=True)
    return el


def replaceContents(el: t.ElementT, newElements: t.NodesT | t.Iterable[t.NodesT]) -> t.ElementT:
    clearContents(el)
    return appendContents(el, newElements)


def replaceWithContents(el: t.ElementT) -> t.NodesT | None:
    return replaceNode(el, childNodes(el, clear=True))


def moveContents(toEl: t.ElementT, fromEl: t.ElementT) -> None:
    replaceContents(toEl, fromEl)
    fromEl.text = ""


def wrapContents(parentEl: t.ElementT, wrapperEl: t.ElementT) -> t.ElementT:
    appendContents(wrapperEl, parentEl)
    appendChild(parentEl, wrapperEl, allowEmpty=True)
    return parentEl


def headingLevelOfElement(el: t.ElementT) -> str | None:
    for heading in relevantHeadings(el, levels=[2, 3, 4, 5, 6]):
        if heading.get("data-level") is not None:
            return heading.get("data-level")
    return None


def relevantHeadings(startEl: t.ElementT, levels: list[int] | None = None) -> t.Generator[t.ElementT, None, None]:
    if levels is None:
        levels = [1, 2, 3, 4, 5, 6]
    tagNames = ["h" + str(level) for level in levels]
    currentHeadingLevel = float("inf")
    for el in scopingElements(startEl, tagNames):
        tagLevel = int(el.tag[1])
        if tagLevel < currentHeadingLevel:
            yield el
            currentHeadingLevel = tagLevel
        if tagLevel == 2:
            return


def sectionName(doc: t.SpecT, el: t.ElementT) -> str | None:
    """
    Return the name of the nearest section to el,
    or None if that section isn't meant to be referenced.
    """
    try:
        h = next(relevantHeadings(el))
    except StopIteration:
        return "Unnamed section"
    if hasClass(doc, h, "no-ref"):
        return None
    return textContent(h)


def scopingElements(startEl: t.ElementT, tags: list[str]) -> t.Generator[t.ElementT, None, None]:
    # Elements that could form a "scope" for the startEl
    # Ancestors, and preceding siblings of ancestors.
    # Maps to the things that can establish a counter scope.
    tagFilter = set(tags)

    for sib in siblingElements(startEl, preceding=True):
        if sib.tag in tagFilter:
            yield sib
    for ancestor in ancestorElements(startEl):
        if ancestor.tag in tagFilter:
            yield ancestor
        for sib in siblingElements(ancestor, preceding=True):
            if sib.tag in tagFilter:
                yield sib


def previousElements(startEl: t.ElementT, tag: str | None = None, *tags: str) -> list[t.ElementT]:
    # Elements preceding the startEl in document order.
    # Like .iter(), but in the opposite direction.
    els: list[t.ElementT] = []
    for el in startEl.getroottree().getroot().iter(tag, *tags):
        if el == startEl:
            return list(reversed(els))
        els.append(el)
    return els


def childElements(parentEl: t.ElementT, oddNodes: bool = False) -> t.Generator[t.ElementT, None, None]:
    if len(parentEl) == 0:
        return
    tag = None if oddNodes else "*"
    yield from parentEl.iterchildren(tag)


def siblingElements(el: t.ElementT, preceding: bool = False) -> t.Iterable[t.ElementT]:
    return el.itersiblings("*", preceding=preceding)


def ancestorElements(el: t.ElementT, self: bool = False) -> t.Generator[t.ElementT, None, None]:
    if self:
        yield el
    yield from el.iterancestors()


def childNodes(parentEl: t.ElementishT, clear: bool = False, skipOddNodes: bool = True) -> list[t.NodeT]:
    """
    This function returns all the nodes in a parent element in the DOM sense,
    mixing text nodes (strings) and other nodes together
    (rather than LXML's default stupid handling of text).

    If you set "clear" to True, it'll
    1. remove all of parentEl's children,
       so you can append nodes back to it safely, and
    2. Set parentEl.text and child elements' .tail to null,
       again so you can safely append text to parentEl.
    In other words, the following is a no-op:

    ```
    appendChild(parentEl, *childNodes(parentEl, clear=True), allowEmpty=True)
    ```

    Using clear=True is required if you're going to be modifying the element or its children,
    otherwise you'll get weird results (repeated/misplaced text).
    But if you're just reading nodes,
    it's not necessary.

    skipOddNodes ensures that the return value will only be text and Element nodes;
    if it's false, there might be comments, PIs, etc.
    """
    ret: list[t.NodeT] = []

    if isinstance(parentEl, list):
        for c in parentEl:
            if isinstance(c, str):
                ret.append(c)
                continue
            if skipOddNodes and isOddNode(c):
                pass
            else:
                ret.append(c)
            if not emptyText(c.tail, wsAllowed=False):
                ret.append(t.cast(str, c.tail))
                if clear:
                    c.tail = None
        if clear:
            parentEl[:] = []
        return ret

    if not emptyText(parentEl.text, wsAllowed=False):
        ret.append(t.cast(str, parentEl.text))
        if clear:
            parentEl.text = None
    for c in childElements(parentEl, oddNodes=True):
        if skipOddNodes and isOddNode(c):
            pass
        else:
            ret.append(c)
        if not emptyText(c.tail, wsAllowed=False):
            ret.append(t.cast(str, c.tail))
            if clear:
                c.tail = None
    if clear:
        clearContents(parentEl)
    return ret


def nodeIter(el: t.ElementT, clear: bool = False, skipOddNodes: bool = True) -> t.Generator[t.NodeT, None, None]:
    # Iterates thru an element and all its descendants,
    # yielding up each child node it sees in depth-first order.
    # (In other words, same as el.iter(),
    #  but returning nodes+strings rather than the stupid LXML model.)
    # Takes the same kwargs as childNodes
    if isinstance(el, str):
        yield el
        return
    if isinstance(el, etree.t.ElementTree):
        el = el.getroot()
    text = el.text
    tail = el.tail
    if clear:
        el.text = None
        el.tail = None
    yield el
    if text is not None:
        yield text
    for c in childElements(el, oddNodes=True):
        if skipOddNodes and isOddNode(c):
            continue
        # yield from nodeIter(c, clear=clear, skipOddNodes=skipOddNodes)
        yield from nodeIter(c, clear=clear, skipOddNodes=skipOddNodes)
    if tail is not None:
        yield tail


def treeAttr(el: t.ElementT, attrName: str) -> str | None:
    # Find the nearest instance of the given attr in the tree
    # Useful for when you can put an attr on an ancestor and apply it to all contents.
    # Returns attrValue or None if nothing is found.

    for target in ancestorElements(el, self=True):
        if target.get(attrName) is not None:
            return target.get(attrName)
    return None


def closestAttr(el: t.ElementT, *attrs: str) -> tuple[str, str] | tuple[None, None]:
    # Like treeAttr, but can provide multiple attr names, and returns the first one found.
    # Useful with combos like highlight/nohighlight
    # If multiple target attrs show up on same element, priority is calling order.
    # Returns a tuple of (attrName, attrValue) or (None, None) if nothing is found.

    for target in ancestorElements(el, self=True):
        for attrName in attrs:
            if target.get(attrName) is not None:
                return attrName, t.cast(str, target.get(attrName))
    return None, None


def closestAncestor(el: t.ElementT, pred: ElementPredT) -> t.ElementT | None:
    # Finds the nearest ancestor matching a predicate
    for target in ancestorElements(el):
        if pred(target):
            return target
    return None


def filterAncestors(el: t.ElementT, pred: ElementPredT) -> t.Generator[t.ElementT, None, None]:
    # Returns all ancestors that match the predicate
    for target in el.iterancestors():
        if pred(target):
            yield target


def hasAncestor(el: t.ElementT, pred: ElementPredT) -> bool:
    return closestAncestor(el, pred) is not None


def removeAttr(el: t.ElementT, *attrNames: str) -> t.ElementT:
    # Remove an attribute, silently ignoring if attr doesn't exist.
    for attrName in attrNames:
        if attrName in el.attrib:
            del el.attrib[attrName]
    return el


def hasAttr(el: t.ElementT, *attrNames: str) -> bool:
    # Returns True if the element has at least one of the named attributes
    return any(attrName in el.attrib for attrName in attrNames)


def hasAttrs(el: t.ElementT) -> bool:
    return bool(el.attrib)


def addClass(doc: t.SpecT, el: t.ElementT, cls: str) -> t.ElementT:
    if el.get("class") is None:
        el.set("class", cls)
    elif hasClass(doc, el, cls):
        pass
    else:
        el.set("class", "{} {}".format(el.get("class"), cls))
    return el


def hasClass(doc: t.SpecT, el: t.ElementT, cls: str) -> bool:
    elClass = el.get("class")
    if elClass is None:
        return False
    if cls == elClass:
        return True
    if cls not in elClass:
        return False
    key = cls, elClass
    if key in doc.cachedClassTests:
        return doc.cachedClassTests[key]
    ret = bool(re.search(r"(^|\s)" + cls + r"($|\s)", elClass))
    doc.cachedClassTests[key] = ret
    return ret


def removeClass(el: t.ElementT, cls: str) -> t.ElementT:
    oldClass = el.get("class")
    if oldClass is None:
        return el
    newClass = " ".join(c for c in oldClass.split() if c != cls)
    if newClass == "":
        del el.attrib["class"]
    else:
        el.set("class", newClass)
    return el


def isElement(node: t.Any) -> t.TypeGuard[t.ElementT]:
    # LXML HAS THE DUMBEST XML TREE DATA MODEL IN THE WORLD
    return etree.iselement(node) and isinstance(node.tag, str)


def isNode(node: t.Any) -> t.TypeGuard[t.NodeT]:
    return isElement(node) or isinstance(node, str)


def isNodes(nodes: t.Any) -> t.TypeGuard[t.NodesT]:
    if isNode(nodes):
        return True
    if not isinstance(nodes, list):
        return False
    return all(isNodes(child) for child in nodes)


def isOddNode(node: t.Any) -> bool:
    # Something other than an element node or string.
    if isinstance(node, str):
        return False
    if isElement(node):  # noqa: SIM103
        return False
    return True


def isNormative(doc: t.SpecT, el: t.ElementT) -> bool:
    # Returns whether the element is "informative" or "normative" with a crude algo.
    # Currently just tests whether the element is in a class=example or class=note block, or not.
    if el in doc.cachedNormativeEls:
        return doc.cachedNormativeEls[el]
    informativeClasses = [
        "note",
        "example",
        "non-normative",
        "informative",
    ] + doc.md.informativeClasses
    for cls in informativeClasses:
        if hasClass(doc, el, cls):
            doc.cachedNormativeEls[el] = False
            return False
    if hasClass(doc, el, "normative"):
        doc.cachedNormativeEls[el] = True
        return True
    parent = parentElement(el)
    if not isElement(parent):
        # Went past the root without finding any indicator,
        # so normative by default.
        doc.cachedNormativeEls[el] = True
        return True
    # Otherwise, walk the tree
    norm = isNormative(doc, parent)
    doc.cachedNormativeEls[el] = norm
    return norm


def isEmpty(el: t.ElementT) -> bool:
    # Returns whether the element is empty - no text or children.
    return (el.text is None or el.text.strip() == "") and len(el) == 0


def hasChildElements(el: t.ElementT) -> bool:
    try:
        next(childElements(el))
        return True
    except StopIteration:
        return False


# If the element has one child element, returns it.
# Otherwise, returns None
def hasOnlyChild(el: t.ElementT, wsAllowed: bool = True) -> t.ElementT | None:
    if not emptyText(el.text, wsAllowed):
        # Has significant child text
        return None
    children = childElements(el)
    single = next(children, None)
    if single is None:
        # No children
        return None
    if not emptyText(single.tail, wsAllowed):
        # Has significant child text following the child element
        return None
    if next(children, None) is not None:
        # At least two children
        return None
    return single


def isOnlyChild(el: t.ElementT, wsAllowed: bool = True) -> bool:
    parent = parentElement(el)
    if parent is None:
        return True
    return hasOnlyChild(parent, wsAllowed) is not None


def fixSurroundingTypography(el: t.ElementT) -> t.ElementT:
    # Applies some of the fixTypography changes to the content surrounding an element.
    # Used when a shorthand prevented fixTypography from firing previously.
    if el.tail is not None and el.tail.startswith("'"):
        el.tail = "’" + el.tail[1:]
    return el


def unfixTypography(text: str) -> str:
    # Replace curly quotes with straight quotes, and emdashes with double dashes.
    text = re.sub(r"’", r"'", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"—<wbr>", r"--", text)
    return text


def emptyText(text: str | None, wsAllowed: bool = True) -> bool:
    # Because LXML represents a complete lack of text as None,
    # you can't do something like `el.text.strip() == ""` to test for emptiness.
    # wsAllowed controls whether whitespace-only strings count as empty or not
    if text is None:
        return True
    if not wsAllowed:
        return text == ""
    return text.strip() == ""


def hashContents(el: t.ElementT) -> str:
    # Hash the contents of an element into an 8-character alphanum string.
    # Generally used for generating probably-unique IDs.
    # Normalize whitespace away to avoid git-related newline normalization issues.
    text = re.sub(r"\s+", " ", textContent(el).strip()).encode("ascii", "xmlcharrefreplace")
    return hashlib.md5(text).hexdigest()[0:8]


def replaceMacrosTextly(text: str, macros: t.Mapping[str, str], context: str) -> str:
    # Same as replaceMacros(), but does the substitution
    # directly on the text, rather than relying on the
    # html parser to have preparsed the macro syntax
    def macroReplacer(match: re.Match) -> str:
        fullText = t.cast(str, match.group(0))
        innerText = match.group(2).lower() or ""
        optional = match.group(3) == "?"
        if fullText.startswith("\\"):
            # Escaped
            return fullText[1:]
        if fullText.startswith("[["):
            # Actually a biblio link
            return fullText
        if innerText in macros:
            # For some reason I store all the macros in lowercase,
            # despite requiring them to be spelled with uppercase.
            return macros[innerText]
        # Nothing has matched, so start failing the macros.
        if optional:
            return ""
        die(
            f"Found unmatched text macro {fullText}. Correct the macro, or escape it with a leading backslash.",
            lineNum=context,
        )
        return fullText

    return re.sub(r"(\\|\[)?\[([A-Z\d-]*[A-Z][A-Z\d-]*)(\??)\]", macroReplacer, text)


def fixupIDs(doc: t.SpecT, els: t.Iterable[t.ElementT]) -> None:
    addOldIDs(els)
    dedupIDs(doc)


def safeID(doc: t.SpecT, id: str) -> str:
    # Converts generated IDs into author-specified versions,
    # for when an ID isn't otherwise settable by the author.
    trans = doc.md.translateIDs
    if id in trans:
        return trans[id]
    return id


def uniqueID(*s: str) -> str:
    # Turns a unique string into a more compact (and ID-safe)
    # hashed string
    return hashlib.md5("".join(s).encode("utf-8")).hexdigest()[:8]


def addOldIDs(els: t.Iterable[t.ElementT]) -> None:
    for el in els:
        oldIdAttr = el.get("oldids")
        if not oldIdAttr:
            continue
        oldIDs = [id.strip() for id in oldIdAttr.strip().split(",")]
        for oldID in oldIDs:
            appendChild(el, E.span({"id": oldID}))
        removeAttr(el, "oldids")


def dedupIDs(doc: t.SpecT) -> None:
    import itertools as iter

    ids: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for el in findAll("[id]", doc):
        ids.setdefault(t.cast(str, el.get("id")), []).append(el)
    for dupeId, els in list(ids.items()):
        if len(els) < 2:
            # Only one instance, so nothing to do.
            continue
        warnAboutDupes = True
        if re.match(r"issue-[0-9a-fA-F]{8}$", dupeId):
            # Don't warn about issues, it's okay if they have the same ID because they're identical text.
            warnAboutDupes = False
        ints = iter.count(1)
        for el in els[1:]:
            # If I registered an alternate ID, try to use that.
            if el.get("data-alternate-id"):
                altId = el.get("data-alternate-id")
                assert altId is not None
                if altId not in ids:
                    el.set("id", safeID(doc, altId))
                    ids.setdefault(altId, []).append(el)
                    continue
            if el.get("data-silently-dedup") is not None:
                warnAboutDupes = False
            if dupeId.startswith("ref-for-"):
                warnAboutDupes = False
            # Try to de-dup the id by appending an integer after it.
            if warnAboutDupes:
                warn(
                    f"Multiple elements have the same ID '{dupeId}'.\nDeduping, but this ID may not be stable across revisions.",
                    el=el,
                )
            for x in ints:
                altId = "{}{}".format(dupeId, circledDigits(x))
                if altId not in ids:
                    el.set("id", safeID(doc, altId))
                    ids.setdefault(altId, []).append(el)
                    break


def approximateLineNumber(el: t.ElementT, setIntermediate: bool = True) -> str | None:
    if el.get("bs-line-number"):
        return el.get("bs-line-number")
    parent = parentElement(el)
    if not isElement(parent):
        if el.tag == "html":
            return None
        return None
    approx = approximateLineNumber(parent, setIntermediate=setIntermediate)
    if approx is None:
        return None
    if approx[0].isdigit():
        approx = "~" + approx
    if setIntermediate:
        el.set("bs-line-number", approx)
    return approx


def circledDigits(num: int) -> str:
    """
    Converts a base-10 number into a string using unicode circled digits.
    That is, 123 becomes "①②③"
    """
    assert num >= 0
    digits = ["⓪", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
    result = "".join(digits[int(d)] for d in str(num))
    return result


def createElement(tag: str, attrs: t.Mapping[str, str | None] | None = None, *children: t.NodesT | None) -> t.ElementT:
    if attrs is None:
        attrs = {}
    el: t.ElementT = etree.Element(tag, {n: v for n, v in attrs.items() if v is not None})
    if children:
        appendChild(el, *(x for x in children if x is not None), allowEmpty=True)
    return el


if t.TYPE_CHECKING:

    class ElementCreatorFnT(t.Protocol):
        def __call__(
            self,
            attrsOrChild: t.Mapping[str, str | None] | t.NodesT | None = None,
            *children: t.NodesT | None,
        ) -> t.ElementT: ...


class ElementCreationHelper:
    def __getattr__(self, name: str) -> ElementCreatorFnT:
        def _creater(
            attrsOrChild: t.Mapping[str, str | None] | t.NodesT | None = None,
            *children: t.NodesT | None,
        ) -> t.ElementT:
            if isNodes(attrsOrChild):
                return createElement(name, None, attrsOrChild, *children)
            else:
                assert isinstance(attrsOrChild, dict) or attrsOrChild is None
                return createElement(name, attrsOrChild, *children)

        return _creater


E = ElementCreationHelper()
