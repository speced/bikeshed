from __future__ import annotations

from .. import boilerplate, datablocks, h, retrieve, t
from .. import messages as m
from . import toc
from .main import SubPage


def prepTree(page: SubPage, pages: list[SubPage], doc: t.SpecT) -> t.ElementT | None:
    # Given a SubPage's content, wrap it in a full page's worth of markup
    # (using the correct template).
    fullPageText = h.safeBikeshedHtml(
        retrieve.retrieveBoilerplateFile(doc, "multipage"),
        h.ParseConfig.fromSpec(doc, context="multipage.include"),
    )
    newRoot, newHead, newBody = h.parseDocument(fullPageText)
    datablocks.transformDataBlocks(doc, newRoot)
    if (fillContainer := findFillRoot(newRoot)) is None:
        m.die(f"Can't fill out the full page for {page.name}.html")
        return None
    h.appendChild(fillContainer, page.nodes)

    boilerplate.addBikeshedVersion(doc=doc, head=newHead)
    # boilerplate.addCanonicalURL(doc)
    boilerplate.addFavicon(doc=doc, head=newHead)
    boilerplate.addSpecVersion(doc=doc, head=newHead)
    boilerplate.addStatusSection(doc=doc, body=newBody)
    boilerplate.addLogo(doc=doc, body=newBody)
    boilerplate.addCopyright(doc=doc, body=newBody)
    boilerplate.addSpecMetadataSection(doc=doc, body=newBody)
    boilerplate.addAbstract(doc=doc, body=newBody)
    boilerplate.addExpiryNotice(doc=doc, body=newBody)
    boilerplate.addObsoletionNotice(doc=doc, body=newBody)
    boilerplate.addAtRisk(doc=doc, body=newBody)
    # boilerplate.addIndexSection(doc)
    boilerplate.addExplicitIndexes(doc=doc, body=newBody)
    boilerplate.addStyles(doc=doc, head=newHead)
    # boilerplate.addReferencesSection(doc)
    # boilerplate.addPropertyIndex(doc)
    # boilerplate.addIDLSection(doc)
    # boilerplate.addCDDLSection(doc)
    # boilerplate.addIssuesSection(doc)
    boilerplate.addCustomBoilerplate(doc=doc, root=newRoot)
    boilerplate.removeUnwantedBoilerplate(doc=doc, root=newRoot)
    boilerplate.addTOCSection(doc=doc, body=newBody)
    boilerplate.addTOCInner(doc=doc, body=newBody)
    toc.addSmallTOCSection(doc=doc, body=newBody, page=page)
    toc.addSmallTOCInner(doc=doc, body=newBody, page=page)
    toc.addPageLinks(doc=doc, body=newBody, page=page, pages=pages)
    boilerplate.addBikeshedStyleScripts(doc=doc, head=newHead)
    boilerplate.addDarkmodeIndicators(doc=doc, head=newHead)

    rewriteLocalLinks(newRoot, page, pages)

    return newRoot


def findFillRoot(tree: t.ElementT) -> t.ElementT | None:
    explicit = h.findAll("bs-pages-fill", tree)
    if len(explicit) == 1:
        return explicit[0]
    elif len(explicit) > 1:
        pageRootLocs = [f" * <{h.tagName(x)}> at {h.approximateLineNumber(x)}" for x in explicit]
        m.die(f"Multiple elements declaring bs-pages-fill.\n{"\n".join(pageRootLocs)}")
        return None
    implicit = h.findAll("main", tree)
    if len(implicit) == 1:
        return implicit[0]
    elif len(implicit) > 1:
        pageRootLocs = [f" * <{h.tagName(x)}> at {h.approximateLineNumber(x)}" for x in implicit]
        m.die(f"Multiple <main> elements implicitly acting as page fill containers.\n{"\n".join(pageRootLocs)}")
        return None
    body = h.find("body", tree)
    if body:
        return body
    else:
        m.die("Your multipage.include somehow lacks a <body> element entirely???")
        return None


def rewriteLocalLinks(root: t.ElementT, page: SubPage, pages: list[SubPage]) -> None:
    for el, href in getLocalLinkElements(root):
        id = href[1:]
        pageName = pageFromId(id, pages)
        if pageName is None:
            # A link in the boilerplate, presumably.
            # TODO: verify that the ID still links to something in the page.
            continue
        if pageName == page.name:
            # A still-local link, leave alone
            continue
        # Rewrite into a non-local link to the correct page.
        el.set("href", pageName + href)


def getLocalLinkElements(root: t.ElementT) -> t.Iterator[tuple[t.ElementT, str]]:
    for el in h.descendantElements(root, self=True):
        if h.tagName(el) == "a":
            href = el.get("href")
            if href is not None and href.startswith("#"):
                yield el, href


def pageFromId(id: str, pages: list[SubPage]) -> str | None:
    for page in pages:
        if id in page.ids:
            return page.name
    return None
