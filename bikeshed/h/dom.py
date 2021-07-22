import collections
import hashlib
import re

import html5lib
from lxml import etree
from lxml.cssselect import CSSSelector
from lxml.html import tostring

from ..DefaultOrderedDict import DefaultOrderedDict
from ..messages import *


def flatten(arr):
    for el in arr:
        if (
            isinstance(el, collections.Iterable)
            and not isinstance(el, str)
            and not lxml.etree.iselement(el)
        ):
            yield from flatten(el)
        else:
            yield el


def unescape(string):
    import html

    return html.unescape(string)


def findAll(sel, context):
    if isinstance(context, constants.specClass):
        context = context.document
    try:
        return CSSSelector(sel, namespaces={"svg": "http://www.w3.org/2000/svg"})(
            context
        )
    except Exception as e:
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
    ident = ""
    firstCode = val[0]
    for i, code in enumerate(ord(x) for x in val):
        if code == 0:
            die("Invalid character: the string '{0}' somehow has a NUL in it.", val)
            return ""
        if (
            0x1 <= code <= 0x1F
            or code == 0x7F
            or (i == 0 and 0x30 <= code <= 0x39)
            or (i == 1 and 0x30 <= code <= 0x39 and firstCode == 0x2D)
        ):
            ident += fr"\{code:x} "
        elif (
            code >= 0x80
            or code == 0x2D
            or code == 0x5F
            or 0x30 <= code <= 0x39
            or 0x41 <= code <= 0x5A
            or 0x61 <= code <= 0x7A
        ):
            ident += chr(code)
        else:
            ident += r"\{}".format(chr(code))
    return ident


def escapeUrlFrag(val):
    result = ""
    for char in val:
        if validUrlUnit(char):
            result += char
        else:
            for b in char.encode("utf-8"):
                result += f"%{b:0>2x}"
    return result


def validUrlUnit(char):
    c = ord(char)
    if c < 0xA0:
        # ASCII range
        if (
            c == 0x21
            or c == 0x24
            or 0x26 <= c <= 0x29
            or 0x2A <= c <= 0x3B
            or c == 0x3D
            or 0x3F <= c <= 0x5A
            or c == 0x5F
            or 0x61 <= c <= 0x7A
            or c == 0x7E
        ):
            return True
        return False
    else:
        if 0xD800 <= c <= 0xDFFF or 0xFDD0 <= c <= 0xFDEF:
            return False
        if (c % 0xFFFF) in [0xFFFE, 0xFFFF]:
            # Last two bytes are FFFE or FFFF
            return False
        return True


def textContent(el, exact=False):
    # If exact is False, then any elements with data-deco attribute
    # get ignored in the textContent.
    # This allows me to ignore things added by Bikeshed by default.
    if len(el) == 0:
        return el.text or ""
    if exact:
        return tostring(el, method="text", with_tail=False, encoding="unicode")
    else:
        return textContentIgnoringDecorative(el)


def textContentIgnoringDecorative(el):
    str = el.text or ""
    for child in childElements(el):
        if child.get("data-deco") is None:
            str += textContentIgnoringDecorative(child)
        str += child.tail or ""
    return str


def innerHTML(el):
    if el is None:
        return ""
    return (el.text or "") + "".join(tostring(x, encoding="unicode") for x in el)


def outerHTML(el, literal=False):
    if el is None:
        return ""
    if isinstance(el, str):
        return el
    if isinstance(el, list):
        return "".join(map(outerHTML, el))
    if el.get("bs-autolink-syntax") is not None and not literal:
        return el.get("bs-autolink-syntax")
    return tostring(el, with_tail=False, encoding="unicode")


def serializeTag(el):
    # Serialize *just* the opening tag for the element.
    # Use when you want to output the HTML,
    # but it might be a container with a lot of content.
    tag = "<" + el.tag
    for n, v in el.attrib.items():
        tag += ' {n}="{v}"'.format(n=n, v=escapeAttr(v))
    tag += ">"
    return tag


def foldWhitespace(text):
    return re.sub(r"(\s|\xa0)+", " ", text)


def parseHTML(text):
    doc = html5lib.parse(text, treebuilder="lxml", namespaceHTMLElements=False)
    head = doc.getroot()[0]
    body = doc.getroot()[1]
    if len(body) > 0 or body.text is not None:
        # Body contains something, so return that.
        contents = [body.text] if body.text is not None else []
        contents.extend(body.iterchildren())
        return contents
    elif len(head) > 0 or head.text is not None:
        # Okay, anything in the head?
        contents = [head.text] if head.text is not None else []
        contents.extend(head.iterchildren())
        return contents
    else:
        return []


def parseDocument(text):
    doc = html5lib.parse(text, treebuilder="lxml", namespaceHTMLElements=False)
    return doc


def escapeHTML(text):
    # Escape HTML
    return text.replace("&", "&amp;").replace("<", "&lt;")


def escapeAttr(text):
    return text.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;")


def clearContents(el):
    del el[:]
    el.text = ""
    return el


def parentElement(el):
    return el.getparent()


def appendChild(parent, *children):
    # Appends either text or an element.
    children = list(flatten(children))
    for child in children:
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
    return children[-1] if len(children) > 0 else None


def prependChild(parent, child):
    # Prepends either text or an element to the parent.
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


def insertBefore(target, *els):
    parent = target.getparent()
    index = parent.index(target)
    prevSibling = parent[index - 1] if index > 0 else None
    for el in els:
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


def insertAfter(target, *els):
    parent = target.getparent()
    for el in els:
        if isinstance(el, str):
            target.tail = (target.tail or "") + el
        else:
            parent.insert(parent.index(target) + 1, el)
            target = el
    return target


def removeNode(node):
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


def replaceNode(node, *replacements):
    insertBefore(node, *replacements)
    removeNode(node)
    if replacements:
        return replacements[0]


def appendContents(el, container):
    # Accepts either an iterable *or* a container element
    if isElement(container):
        container = childNodes(container, clear=True)
    appendChild(el, *container)
    return el


def replaceContents(el, newElements):
    clearContents(el)
    return appendContents(el, newElements)


def moveContents(toEl, fromEl):
    replaceContents(toEl, fromEl)
    fromEl.text = ""


def wrapContents(parentEl, wrapperEl):
    appendContents(wrapperEl, parentEl)
    appendChild(parentEl, wrapperEl)
    return parentEl


def headingLevelOfElement(el):
    for heading in relevantHeadings(el, levels=[2, 3, 4, 5, 6]):
        if heading.get("data-level") is not None:
            return heading.get("data-level")
    return None


def relevantHeadings(startEl, levels=None):
    if levels is None:
        levels = [1, 2, 3, 4, 5, 6]
    levels = ["h" + str(level) for level in levels]
    currentHeadingLevel = float("inf")
    for el in scopingElements(startEl, *levels):
        tagLevel = int(el.tag[1])
        if tagLevel < currentHeadingLevel:
            yield el
            currentHeadingLevel = tagLevel
        if tagLevel == 2:
            return


def sectionName(el):
    """
    Return the name of the nearest section to el,
    or None if that section isn't meant to be referenced.
    """
    h = nextIter(relevantHeadings(el))
    if h is None:
        return "Unnamed section"
    if hasClass(h, "no-ref"):
        return None
    return textContent(h)


def scopingElements(startEl, *tags):
    # Elements that could form a "scope" for the startEl
    # Ancestors, and preceding siblings of ancestors.
    # Maps to the things that can establish a counter scope.
    tagFilter = set(tags)

    for el in startEl.itersiblings(preceding=True, *tags):
        yield el
    for el in startEl.iterancestors():
        if el.tag in tagFilter:
            yield el
        for el in el.itersiblings(preceding=True, *tags):
            yield el


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
    if len(parentEl) == 0:
        return iter(())
    return parentEl.iterchildren(tag=tag, *tags, **stuff)


def childNodes(parentEl, clear=False, skipOddNodes=True):
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
    appendChild(parentEl, *childNodes(parentEl, clear=True))
    ```

    Using clear=True is required if you're going to be modifying the element or its children,
    otherwise you'll get weird results (repeated/misplaced text).
    But if you're just reading nodes,
    it's not necessary.

    skipOddNodes ensures that the return value will only be text and Element nodes;
    if it's false, there might be comments, PIs, etc.
    """
    if isinstance(parentEl, list):
        return parentEl
    ret = []
    if not emptyText(parentEl.text, wsAllowed=False):
        ret.append(parentEl.text)
        if clear:
            parentEl.text = None
    for c in childElements(parentEl, tag=None):
        if skipOddNodes and isOddNode(c):
            pass
        else:
            ret.append(c)
        if not emptyText(c.tail, wsAllowed=False):
            ret.append(c.tail)
            if clear:
                c.tail = None
    if clear:
        clearContents(parentEl)
    return ret


def nodeIter(el, clear=False, skipOddNodes=True):
    # Iterates thru an element and all its descendants,
    # yielding up each child node it sees in depth-first order.
    # (In other words, same as el.iter(),
    #  but returning nodes+strings rather than the stupid LXML model.)
    # Takes the same kwargs as childNodes
    if isinstance(el, str):
        yield el
        return
    if isinstance(el, etree.ElementTree):
        el = el.getroot()
    text = el.text
    tail = el.tail
    if clear:
        el.text = None
        el.tail = None
    yield el
    if text is not None:
        yield text
    for c in childElements(el, tag=None):
        if skipOddNodes and isOddNode(c):
            continue
        # yield from nodeIter(c, clear=clear, skipOddNodes=skipOddNodes)
        yield from nodeIter(c, clear=clear, skipOddNodes=skipOddNodes)
    if tail is not None:
        yield tail


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


def closestAncestor(el, pred):
    # Finds the nearest ancestor matching a predicate
    for target in el.iterancestors():
        if pred(target):
            return target


def filterAncestors(el, pred):
    # Returns all ancestors that match the predicate
    for target in el.iterancestors():
        if pred(target):
            yield target


def hasAncestor(el, pred):
    return closestAncestor(el, pred) is not None


def removeAttr(el, *attrNames):
    # Remove an attribute, silently ignoring if attr doesn't exist.
    for attrName in attrNames:
        if attrName in el.attrib:
            del el.attrib[attrName]
    return el


def hasAttr(el, *attrNames):
    # Returns True if the element has at least one of the named attributes
    for attrName in attrNames:
        if attrName in el.attrib:
            return True
    return False


def hasAttrs(el):
    return bool(el.attrib)


def addClass(el, cls):
    if el.get("class") is None:
        el.set("class", cls)
    elif hasClass(el, cls):
        pass
    else:
        el.set("class", "{} {}".format(el.get("class"), cls))


_classMap = {}


def hasClass(el, cls, classMap=_classMap):
    elClass = el.get("class")
    if elClass is None:
        return False
    if cls not in elClass:
        return False
    key = cls, elClass
    if key in classMap:
        return classMap[key]
    ret = re.search(r"(^|\s)" + cls + r"($|\s)", elClass)
    classMap[key] = ret
    return ret


def removeClass(el, cls):
    oldClass = el.get("class")
    if oldClass is None:
        return
    newClass = " ".join(c for c in oldClass.split() if c != cls)
    if newClass == "":
        del el.attrib["class"]
    else:
        el.set("class", newClass)


def isElement(node):
    # LXML HAS THE DUMBEST XML TREE DATA MODEL IN THE WORLD
    return etree.iselement(node) and isinstance(node.tag, str)


def isOddNode(node):
    # Something other than an element node or string.
    if isinstance(node, str):
        return False
    if isElement(node):
        return False
    return True


def isNormative(el, doc):
    # Returns whether the element is "informative" or "normative" with a crude algo.
    # Currently just tests whether the element is in a class=example or class=note block, or not.
    if el in _normativeElCache:
        return _normativeElCache[el]
    informativeClasses = [
        "note",
        "example",
        "non-normative",
        "informative",
    ] + doc.md.informativeClasses
    for cls in informativeClasses:
        if hasClass(el, cls):
            _normativeElCache[el] = False
            return False
    if hasClass(el, "normative"):
        _normativeElCache[el] = True
        return True
    parent = parentElement(el)
    if not isElement(parent):
        # Went past the root without finding any indicator,
        # so normative by default.
        _normativeElCache[el] = True
        return True
    # Otherwise, walk the tree
    norm = isNormative(parent, doc)
    _normativeElCache[el] = norm
    return norm


_normativeElCache = {}


def isEmpty(el):
    # Returns whether the element is empty - no text or children.
    return (el.text is None or el.text.strip() == "") and len(el) == 0


def hasChildElements(el):
    try:
        next(childElements(el))
        return True
    except StopIteration:
        return False


# If the element has one child element, returns it.
# Otherwise, returns None
def hasOnlyChild(el, wsAllowed=True):
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


def fixTypography(text):
    # Replace straight aposes with curly quotes for possessives and contractions.
    text = re.sub(r"([\w])'([\w])", r"\1’\2", text)
    text = re.sub(r"(</[\w]+>)'([\w])", r"\1’\2", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"([^<][^!])(—|--)\r?\n\s*(\S)", r"\1—<wbr>\3", text)
    return text


def fixSurroundingTypography(el):
    # Applies some of the fixTypography changes to the content surrounding an element.
    # Used when a shorthand prevented fixTypography from firing previously.
    if el.tail is not None and el.tail.startswith("'"):
        el.tail = "’" + el.tail[1:]
    return el


def unfixTypography(text):
    # Replace curly quotes with straight quotes, and emdashes with double dashes.
    text = re.sub(r"’", r"'", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(r"—<wbr>", r"--", text)
    return text


def emptyText(text, wsAllowed=True):
    # Because LXML represents a complete lack of text as None,
    # you can't do something like `el.text.strip() == ""` to test for emptiness.
    # wsAllowed controls whether whitespace-only strings count as empty or not
    if text is None:
        return True
    if not wsAllowed:
        return text == ""
    return text.strip() == ""


def hashContents(el):
    # Hash the contents of an element into an 8-character alphanum string.
    # Generally used for generating probably-unique IDs.
    # Normalize whitespace away to avoid git-related newline normalization issues.
    text = re.sub(r"\s+", " ", textContent(el).strip()).encode(
        "ascii", "xmlcharrefreplace"
    )
    return hashlib.md5(text).hexdigest()[0:8]


def replaceMacros(text, macros):
    # `macros` is a dict of {lowercaseMacroName => replacementText}
    # Macro syntax is [FOO], where FOO is /[A-Z0-9-]+/
    # If written as [FOO?], failure to find a matching macro just replaced it with nothing;
    # otherwise, it throws a fatal error.
    def macroReplacer(match):
        fullText = match.group(0)
        innerText = match.group(2).lower() or ""
        optional = match.group(3) == "?"
        if fullText.startswith("\\"):
            # Escaped
            return fullText[1:]
        if fullText.startswith("[["):
            # Actually a biblio link
            return fullText
        if re.match(r"[\d-]+$", innerText):
            # No refs are all-digits (this is probably JS code, or a regex/grammar).
            return fullText
        if innerText in macros:
            # For some reason I store all the macros in lowercase,
            # despite requiring them to be spelled with uppercase.
            return str(macros[innerText])
        # Nothing has matched, so start failing the macros.
        if optional:
            return ""
        die(
            "Found unmatched text macro {0}. Correct the macro, or escape it with a leading backslash.",
            fullText,
        )
        return fullText

    return re.sub(r"(\\|\[)?\[([A-Z0-9-]+)(\??)\]", macroReplacer, text)


def replaceAwkwardCSSShorthands(text):
    # Replace the <<production>> shortcuts, because they won't survive the HTML parser.
    def replaceProduction(match):
        syntaxAttr = escapeAttr(match.group(0))
        escape, text = match.groups()
        if escape:
            return escapeHTML(match.group(0)[1:])
        return f"<fake-production-placeholder class=production bs-autolink-syntax='{syntaxAttr}' data-opaque>{text}</fake-production-placeholder>"

    text = re.sub(r"(\\)?<<([^>\n]+)>>", replaceProduction, text)

    # Replace the ''maybe link'' shortcuts.
    # They'll survive the HTML parser,
    # but the current shorthand-recognizer code won't find them if they contain an element.
    # (The other shortcuts are "atomic" and can't contain elements.)
    def replaceMaybe(match):
        syntaxAttr = escapeAttr(match.group(0))
        escape, text = match.groups()
        if escape:
            return escapeHTML(match.group(0)[1:])
        return f"<fake-maybe-placeholder bs-autolink-syntax='{syntaxAttr}'>{text}</fake-maybe-placeholder>"

    text = re.sub(r"(\\)?''([^=\n]+?)''", replaceMaybe, text)
    return text


def fixupIDs(doc, els):
    addOldIDs(els)
    dedupIDs(doc)


def safeID(transOrDoc, id):
    if isinstance(transOrDoc, dict):
        trans = transOrDoc
    else:
        trans = transOrDoc.md.translateIDs
    if id in trans:
        return trans[id]
    return id


def addOldIDs(els):
    for el in els:
        if not el.get("oldids"):
            continue
        oldIDs = [id.strip() for id in el.get("oldids").strip().split(",")]
        for oldID in oldIDs:
            appendChild(el, E.span({"id": oldID}))
        removeAttr(el, "oldids")


def dedupIDs(doc):
    import itertools as iter

    ids = DefaultOrderedDict(list)
    for el in findAll("[id]", doc):
        ids[el.get("id")].append(el)
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
                if altId not in ids:
                    el.set("id", safeID(doc, el.get("data-alternate-id")))
                    ids[altId].append(el)
                    continue
            if el.get("data-silently-dedup") is not None:
                warnAboutDupes = False
            if dupeId.startswith("ref-for-"):
                warnAboutDupes = False
            # Try to de-dup the id by appending an integer after it.
            if warnAboutDupes:
                warn(
                    "Multiple elements have the same ID '{0}'.\nDeduping, but this ID may not be stable across revisions.",
                    dupeId,
                    el=el,
                )
            for x in ints:
                altId = "{}{}".format(dupeId, circledDigits(x))
                if altId not in ids:
                    el.set("id", safeID(doc, altId))
                    ids[altId].append(el)
                    break


def approximateLineNumber(el, setIntermediate=True):
    if el.get("line-number"):
        return el.get("line-number")
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
        el.set("line-number", approx)
    return approx


def circledDigits(num):
    """
    Converts a base-10 number into a string using unicode circled digits.
    That is, 123 becomes "①②③"
    """
    num = int(num)
    assert num >= 0
    digits = ["⓪", "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
    result = "".join(digits[int(d)] for d in str(num))
    return result


def nextIter(it, default=None):
    """
    Returns the next element of the iterator,
    returning the default value if it's empty,
    rather than throwing an error.
    """
    try:
        return next(iter(it))
    except StopIteration:
        return default


def createElement(tag, attrs={}, *children):
    el = etree.Element(tag, {n: v for n, v in attrs.items() if v is not None})
    for child in children:
        appendChild(el, child)
    return el


class ElementCreationHelper:
    def __getattr__(self, name):
        def _creater(*children):
            if children and not (
                isinstance(children[0], str) or isElement(children[0])
            ):
                attrs = children[0]
                children = children[1:]
            else:
                attrs = {}
            return createElement(name, attrs, *children)

        return _creater


E = ElementCreationHelper()
