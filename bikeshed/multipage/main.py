from __future__ import annotations

import dataclasses

from .. import h, t
from .. import messages as m


@dataclasses.dataclass
class Page:
    name: str
    nodes: list[t.NodeT] = dataclasses.field(default_factory=list)
    ids: set[str] = dataclasses.field(default_factory=set)


def serializePages(doc: t.SpecT, mainFilename: str) -> dict[str, str]:
    main = h.find("main", doc)
    assert main is not None
    pages = collectIntoPages(list(h.childNodes(main, clear=True)), mainFilename)
    ret = {}
    serializer = h.Serializer(doc.md.opaqueElements, doc.md.blockElements)
    for page in pages:
        h.replaceContents(main, page.nodes)
        fixupLocalRefs(h.rootElement(doc), page, pages)
        ret[page.name] = serializer.serialize(doc.document)
    return ret


def collectIntoPages(nodes: list[t.NodeT], mainFilename: str) -> list[Page]:
    pages = [Page(mainFilename)]
    for node in nodes:
        if h.isElement(node) and meaningfulHeading(node) and headingLevel(node) == 2:
            id = node.get("id")
            if not id:
                m.die("Heading doesn't have a useful ID, can't split on it.", el=node)
                return []
            filename = id + ".html"
            pages.append(Page(filename))
        pages[-1].nodes.append(node)
    for page in pages:
        collectIDs(page.nodes, page)
    return pages


def fixupLocalRefs(el: t.ElementT, currentPage: Page, pages: list[Page]) -> None:
    # On first pass, stash the href into a side attribute
    if el.get("href") and not el.get("bs-href"):
        el.set("bs-href", t.cast(str, el.get("href")))

    # If it's a local ref, find what page it's actually in and rewrite the href
    href = el.get("bs-href", "")
    if href.startswith("#"):
        id = href[1:]
        if id in currentPage.ids:
            # Local link, just make sure it stays local
            el.set("href", href)
        else:
            page = findID(id, pages)
            if page is None:
                # Either a broken link, or something in the boilerplate.
                el.set("href", href)
            else:
                el.set("href", page.name + href)
    # Otherwise, recurse.
    # (Can't nest links, so no need to recurse in positive case.)
    else:
        for child in h.childElements(el):
            fixupLocalRefs(child, currentPage, pages)


def printRedir(currentPageName: str, pageName: str, id: str, el: t.ElementT) -> str:
    print(f"{simpleLineNum(el):5}: {currentPageName:20} {pageName:20} #{id}")


def findID(id: str, pages: list[Page]) -> Page | None:
    for page in pages:
        if id in page.ids:
            return page
    return None


def collectIDs(nodes: t.NodesT, page: Page) -> Page:
    for node in nodes:
        if h.isElement(node):
            if node.get("id"):
                page.ids.add(t.cast(str, node.get("id")))
            collectIDs(h.childElements(node), page)
    return page


def meaningfulHeading(el: t.ElementT) -> bool:
    # Is a heading...
    if h.tagName(el) not in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return False
    # And both has a line number and *doesn't* have any extra context,
    # like from being part of boilerplate.
    # This isn't 100% but it works pretty well.
    lineNum = el.get("bs-line-number", "")
    if parsesAsInt(lineNum):
        return True
    else:
        num, _, rest = lineNum.partition(":")
        return parsesAsInt(num) and parsesAsInt(rest)


def parsesAsInt(s: str) -> bool:
    try:
        int(s)
        return True
    except:
        return False


def headingLevel(el: t.ElementT) -> int:
    tag = h.tagName(el)
    if tag not in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return 0
    return int(tag[1])

def simpleLineNum(el: t.ElementT) -> str:
    lineNum = el.get("bs-line-number")
    if lineNum:
        if parsesAsInt(lineNum):
            return lineNum
        num, _, rest = lineNum.partition(":")
        if parsesAsInt(num):
            return num
        return "nil"
    return "?"