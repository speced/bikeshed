from __future__ import annotations

from .. import h, t
from .. import messages as m
from .main import PageSplitConfig, SubPage


def extractPages(tree: t.ElementT, config: PageSplitConfig) -> list[SubPage] | None:
    """
    Splits a full HTML tree into subtrees.
    """
    root = findPagesRoot(tree)
    if root is None:
        m.die("Can't split document into multiple pages.")
        return None

    pages = [SubPage(name=config.rootPageName, incitingElement=root, level=1)]
    children = list(h.childNodes(root, clear=True))
    for node in children:
        if not h.isElement(node):
            pages[-1].nodes.append(node)
            continue
        if newPage := startsNewPage(node, config):
            pages.append(newPage)
            pages[-1].nodes.append(node)
            continue
        if (level := isHeading(node)) is not None:
            if level < pages[-1].level:
                # A page must stop at a stronger heading;
                # if that heading didn't declare a new page, it's an error.
                m.die(
                    f"Current page started by an <h{pages[-1].level}> (on {h.approximateLineNumber(pages[-1].incitingElement)}), but the next <h{level}> didn't start a fresh page.",
                    el=node,
                )
                h.appendChild(root, children)
                return None
        pages[-1].nodes.append(node)

    for page in pages:
        gatherIds(page)

    # Put the initial elements back in...
    h.appendChild(root, pages[0].nodes)
    return pages


def findPagesRoot(tree: t.ElementT) -> t.ElementT | None:
    explicit = h.findAll("bs-pages-root", tree)
    if len(explicit) == 1:
        return explicit[0]
    elif len(explicit) > 1:
        pageRootLocs = [f" * <{h.tagName(x)}> at {h.approximateLineNumber(x)}" for x in explicit]
        m.die(f"Multiple elements declaring bs-pages-root.\n{"\n".join(pageRootLocs)}")
        return None
    implicit = h.findAll("main", tree)
    if len(implicit) == 1:
        return implicit[0]
    elif len(implicit) > 1:
        pageRootLocs = [f" * <{h.tagName(x)}> at {h.approximateLineNumber(x)}" for x in implicit]
        m.die(f"Multiple <main> elements implicitly acting as page roots.\n{"\n".join(pageRootLocs)}")
        return None
    body = h.find("body", tree)
    if body:
        return body
    else:
        m.die("Your document somehow lacks a <body> element entirely???")
        return None


def startsNewPage(el: t.ElementT, config: PageSplitConfig) -> SubPage | None:
    if (level := isHeading(el)) is None:
        return None
    if el.get("bs-page") is not None:
        pass
    elif config.autoLevel is not None and level <= config.autoLevel:
        pass
    else:
        return None
    if (name := getPageName(el)) is None:
        return None
    return SubPage(name=name + ".html", level=level, incitingElement=el)


def isHeading(el: t.ElementT) -> int | None:
    tag = h.tagName(el)
    if tag not in ("h2", "h3", "h4", "h5", "h6"):
        return None
    return int(tag[1])


def getPageName(el: t.ElementT) -> str | None:
    if name := el.get("bs-page"):
        return name.strip()
    elif name := el.get("id"):
        return name.strip()
    else:
        m.die("Can't determine the name of the new page (missing bs-page or id).", el=el)
        return None


def getIdElements(page: SubPage) -> t.Iterator[tuple[t.ElementT, str]]:
    for el in h.descendantElements(page.nodes, self=True):
        id = el.get("id")
        if id is not None:
            yield el, id


def gatherIds(page: SubPage) -> None:
    # Gather the IDs, so later things can rewrite.
    for _, id in getIdElements(page):
        page.ids.add(id)
