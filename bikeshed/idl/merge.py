from __future__ import annotations

import collections
import copy
import dataclasses

from .. import h, t
from .. import messages as m


@dataclasses.dataclass(eq=False)
class _OrigElement:
    element: t.ElementT
    start: int
    end: int
    parent: _OrigElement | None = None
    children: list[_OrigElement] = dataclasses.field(default_factory=list)
    valid: bool = False

    def empty(self) -> bool:
        return self.start == self.end


@dataclasses.dataclass(eq=False)
class _PostElement:
    element: t.ElementT
    start: int
    end: int
    parent: _PostElement | None = None
    children: list[_PostElement] = dataclasses.field(default_factory=list)
    remove: bool = False


def _extractPostElements(tree: t.ElementT | list[t.NodeT]) -> tuple[str, list[_PostElement]]:
    """
    Extracts all elements from the post-parsing tree along with their character offsets,
    and returns the concatenated text and the list of extracted elements.
    """
    elements: list[_PostElement] = []
    textPieces: list[str] = []
    currentOffset = 0

    def walk(nodeList: list[t.NodeT], parent: _PostElement | None) -> None:
        nonlocal currentOffset
        for child in nodeList:
            if isinstance(child, str):
                textPieces.append(child)
                currentOffset += len(child)
            else:
                postEl = _PostElement(
                    element=child,
                    start=currentOffset,
                    end=currentOffset,
                    parent=parent,
                )
                if parent is not None:
                    parent.children.append(postEl)
                elements.append(postEl)
                walk(h.childNodes(child), postEl)
                postEl.end = currentOffset

    if h.isElement(tree):
        walk(h.childNodes(tree), None)
    else:
        walk(tree, None)
    return "".join(textPieces), elements


def _extractOrigElements(tree: t.ElementT | list[t.NodeT]) -> tuple[str, list[_OrigElement]]:
    """
    Extracts all elements from the original markup tree along with their character offsets,
    and returns the concatenated text and the list of extracted elements.
    """
    elements: list[_OrigElement] = []
    textPieces: list[str] = []
    currentOffset = 0

    def walk(nodeList: list[t.NodeT], parent: _OrigElement | None) -> None:
        nonlocal currentOffset
        for child in nodeList:
            if isinstance(child, str):
                textPieces.append(child)
                currentOffset += len(child)
            else:
                origEl = _OrigElement(
                    element=child,
                    start=currentOffset,
                    end=currentOffset,
                    parent=parent,
                )
                if parent is not None:
                    parent.children.append(origEl)
                elements.append(origEl)
                walk(h.childNodes(child), origEl)
                origEl.end = currentOffset

    if h.isElement(tree):
        walk(h.childNodes(tree), None)
    else:
        walk(tree, None)
    return "".join(textPieces), elements


def _markDescendantsValid(orig: _OrigElement) -> None:
    """
    Recursively marks all descendant elements of an original element as valid.
    """
    for child in orig.children:
        child.valid = True
        _markDescendantsValid(child)


def _evaluateOrigElement(
    orig: _OrigElement,
    postContext: _PostElement | None,
    allPostElements: list[_PostElement],
    origByPost: dict[_PostElement | None, list[_OrigElement]],
) -> None:
    """
    Checks whether an original element can be safely merged into postContext.
    If fully contained within a child post element, recurse into that child.
    If it overlaps with any child post element boundary, it is dropped with a fatal error.
    Otherwise, it is disjoint from all child post elements and valid in postContext.
    """
    if postContext is None:
        childPosts = [p for p in allPostElements if p.parent is None]
    else:
        childPosts = postContext.children

    for cp in childPosts:
        # Empty elements can't misnest, just ID which post element they're inside of.
        if orig.empty():
            if cp.start < orig.start < cp.end:
                _evaluateOrigElement(orig, cp, allPostElements, origByPost)
                return
            continue
        # Exactly matching markup, with the original being the sort of element
        # that the parser markup will turn into.
        if cp.start == orig.start and cp.end == orig.end and orig.element.tag in ("a", "dfn"):
            if orig.element.tag == "dfn" and cp.element.tag == "a":
                orig.valid = False
                m.die("<dfn> element used on a term that is *not* a defining instance in WebIDL.", el=orig.element)
                return
            _evaluateOrigElement(orig, cp, allPostElements, origByPost)
            if orig.valid:
                _replacePostWithOrig(orig, cp)
            return
        # Check if orig is fully contained in the post element
        if cp.start <= orig.start and orig.end <= cp.end:
            _evaluateOrigElement(orig, cp, allPostElements, origByPost)
            return
        # Any other combo indicates either post is inside of orig, or they're misnested.
        elif max(orig.start, cp.start) < min(orig.end, cp.end):
            orig.valid = False
            m.die(
                f"The original markup <{h.tagName(orig.element)}> contains or crosses markup generated by the IDL parser, which isn't allowed. Original element will be dropped.",
                el=orig.element,
            )
            for child in orig.children:
                _evaluateOrigElement(child, postContext, allPostElements, origByPost)
            return
    # Disjoint from all child post elements; valid in postContext
    orig.valid = True
    origByPost[postContext].append(orig)
    _markDescendantsValid(orig)


CANON_ATTRIBUTES = [
    "data-idl-type",
    "data-link-type",
    "data-idl-for",
    "data-link-for",
]


def _replacePostWithOrig(orig: _OrigElement, post: _PostElement) -> None:
    """
    When Post is an <idl> and Orig is an <a> or <dfn>, just use Orig instead.
    Transfer some attributes from Post, if necessary.
    """

    # Dfning something the IDL parser *knows* is in a linking position is weird.
    if orig.element.tag == "dfn" and post.element.tag == "a":
        m.die("<dfn> element used on a term that is *not* a defining instance in WebIDL.", el=orig.element)
        return

    post.remove = True
    # If it's a fully manual link, don't transfer any attributes
    if orig.element.tag == "a" and h.hasAttr(orig.element, "href"):
        return
    # Otherwise, transfer the dfn or linking attributes from parser-created element,
    # overriding whatever was put in manually.
    for attrname in CANON_ATTRIBUTES:
        if h.hasAttr(post.element, attrname):
            origAttr = _translateAttribute(orig.element, attrname)
            postValue = post.element.get(attrname)
            assert isinstance(postValue, str)
            if h.hasAttr(orig.element, origAttr):
                origValue = orig.element.get(origAttr)
                if origValue != postValue:
                    m.die(
                        f"The IDL parser says this element should have {origAttr}='{postValue}', but you've marked it as '{origValue}'.",
                        el=orig.element,
                    )
            orig.element.set(origAttr, postValue)


def _translateAttribute(el: t.ElementT, attrname: str) -> str:
    """
    Attributes on <idl> don't know whether they'll be on a link or dfn,
    so they're spelled data-idl-foo.
    Translate them to data-link-foo or data-dfn-foo.
    """
    if not attrname.startswith("data-idl-"):
        return attrname
    suffix = attrname[len("data-idl-") :]
    if el.tag == "a":
        prefix = "data-link-"
    else:
        prefix = "data-dfn-"
    return prefix + suffix


def _reconstructOrigElement(orig: _OrigElement, fullText: str) -> t.ElementT:
    """
    Reconstructs an original markup element and its valid child elements using text slices from fullText.
    """
    newEl = copy.deepcopy(orig.element)
    h.clearContents(newEl)
    newEl.tail = None

    validChildren = [c for c in orig.children if c.valid]
    validChildren.sort(key=lambda c: (c.start, c.end))

    current = orig.start
    nodes: list[t.NodeT] = []
    for c in validChildren:
        if c.start > current:
            nodes.append(fullText[current : c.start])
        nodes.append(_reconstructOrigElement(c, fullText))
        current = max(current, c.end)
    if orig.end > current:
        nodes.append(fullText[current : orig.end])

    h.appendChild(newEl, *nodes, allowEmpty=True)
    return newEl


def _reconstructPostElement(
    postEl: _PostElement | None,
    fullText: str,
    allPostElements: list[_PostElement],
    origByPost: dict[_PostElement | None, list[_OrigElement]],
) -> list[t.NodeT]:
    """
    Reconstructs the post-parsing element tree, interleaving post elements and valid original markup elements.
    """
    if postEl is None:
        start = 0
        end = len(fullText)
        childPosts = [p for p in allPostElements if p.parent is None]
    else:
        start = postEl.start
        end = postEl.end
        childPosts = postEl.children

    origItems = origByPost.get(postEl, [])

    items: list[tuple[str, _OrigElement | _PostElement, int, int]] = []
    for cp in childPosts:
        items.append(("post", cp, cp.start, cp.end))
    for orig in origItems:
        items.append(("orig", orig, orig.start, orig.end))

    items.sort(key=lambda x: (x[2], x[3]))

    current = start
    nodes: list[t.NodeT] = []
    for itemType, item, itemStart, itemEnd in items:
        if itemStart > current:
            nodes.append(fullText[current:itemStart])
        if itemType == "post":
            assert isinstance(item, _PostElement)
            newEl = copy.deepcopy(item.element)
            h.clearContents(newEl)
            newEl.tail = None
            childContent = _reconstructPostElement(item, fullText, allPostElements, origByPost)
            # Removed post elements leave themselves out and just drop in their contents.
            if item.remove:
                nodes.extend(childContent)
            else:
                h.appendChild(newEl, *childContent, allowEmpty=True)
                nodes.append(newEl)
        else:
            assert isinstance(item, _OrigElement)
            nodes.append(_reconstructOrigElement(item, fullText))
        current = max(current, itemEnd)
    if end > current:
        nodes.append(fullText[current:end])
    return nodes


def mergeMarkup(
    el: t.ElementT,
    postParseContents: list[t.NodeT],
) -> list[t.NodeT]:
    """
    Conservatively merges the original markup tree and the new post-parsing one.
    Original markup elements are preserved only if wrapping text unaffected by the IDL parser,
    or fully-contained within an element emitted by the IDL parser.
    Otherwise, they are dropped with a fatal error.
    """
    origText, allOrigElements = _extractOrigElements(el)
    if not allOrigElements:
        return postParseContents

    postText, allPostElements = _extractPostElements(postParseContents)
    if origText != postText:
        m.warn(
            "PROGRAMMING ERROR: IDL parsing changed the text of the element, so I can't merge the IDL-parser markup with the original markup. Dropping the original markup...",
            el=el,
        )
        return postParseContents

    origByPost: dict[_PostElement | None, list[_OrigElement]] = collections.defaultdict(list)
    topLevelOrigElements = [orig for orig in allOrigElements if orig.parent is None]
    for orig in topLevelOrigElements:
        _evaluateOrigElement(orig, None, allPostElements, origByPost)

    return _reconstructPostElement(None, postText, allPostElements, origByPost)
