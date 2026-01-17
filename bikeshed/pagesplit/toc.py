from __future__ import annotations

import copy

from .. import boilerplate, h, t
from ..translate import _t
from .main import SubPage

if t.TYPE_CHECKING:
    from ..boilerplate import TOCEntry


def addSmallTOCSection(doc: t.SpecT, body: t.ElementT, page: SubPage) -> None:
    # A "reduced" version of the ToC, just containing the headings needed for this subpage.
    tocContainer = boilerplate.getFillContainer("small-table-of-contents", doc=doc, tree=body)
    if tocContainer is None:
        return
    h.appendChild(
        tocContainer,
        h.E.h2(
            {"class": "no-num no-toc no-ref", "id": h.safeID(doc, "contents")},
            _t("Table of Contents"),
        ),
        buildSmallTOCLevel(doc.tocEntries, page),
    )


def addSmallTOCInner(doc: t.SpecT, body: t.ElementT, page: SubPage) -> None:
    # Just the list of links, not the header.
    tocContainer = boilerplate.getFillContainer("small-toc-links", doc=doc, tree=body)
    if tocContainer is None:
        return
    h.appendChild(
        tocContainer,
        buildSmallTOCLevel(doc.tocEntries, page),
    )


def buildSmallTOCLevel(entries: list[TOCEntry], page: SubPage) -> t.ElementT:
    ol = h.E.ol({"class": "toc"})
    for entry in entries:
        if not tocSectionInPage(entry, page):
            continue
        if entry.id in page.ids:
            currItem = h.E.a(
                {"href": "#" + entry.id},
                h.E.span({"class": "secno"}, entry.level),
                " ",
                copy.deepcopy(entry.content),
            )
        else:
            currItem = h.E.span(
                {},
                h.E.span({"class": "secno"}, entry.level),
                " ",
                copy.deepcopy(entry.content),
            )
        h.appendChild(
            ol,
            h.E.li(
                currItem,
                buildSmallTOCLevel(entry.children, page) if entry.children else [],
            ),
        )
    return ol


def tocSectionInPage(entry: TOCEntry, page: SubPage) -> bool:
    if entry.id in page.ids:
        return True
    return any(tocSectionInPage(child, page) for child in entry.children)


def addPageLinks(doc: t.SpecT, body: t.ElementT, page: SubPage, pages: list[SubPage]) -> None:
    prevPageContainer = boilerplate.getFillContainer("prev-page-link", doc=doc, tree=body)
    if prevPageContainer is not None:
        link = buildPrevPageLink(page, pages, doc.tocEntries)
        if link is not None:
            h.replaceContents(
                prevPageContainer,
                [link],
            )
    nextPageContainer = boilerplate.getFillContainer("next-page-link", doc=doc, tree=body)
    if nextPageContainer is not None:
        link = buildNextPageLink(page, pages, doc.tocEntries)
        if link is not None:
            h.replaceContents(
                nextPageContainer,
                [link],
            )
    thisPageContainer = boilerplate.getFillContainer("this-page-link", doc=doc, tree=body)
    if thisPageContainer is not None:
        link = buildThisPageLink(page, doc.tocEntries)
        if link is not None:
            h.replaceContents(
                thisPageContainer,
                [link],
            )


def buildThisPageLink(page: SubPage, toc: list[TOCEntry]) -> t.ElementT | None:
    entry = tocEntryMatchingElement(toc, page.incitingElement)
    if entry is None:
        return None
    return h.E.a(
        {"href": "#" + entry.id},
        h.E.span({"class": "secno"}, entry.level),
        " ",
        copy.deepcopy(entry.content),
    )


def buildPrevPageLink(page: SubPage, pages: list[SubPage], toc: list[TOCEntry]) -> t.ElementT | None:
    pageIndex = pages.index(page)
    if pageIndex == 0:
        return None

    prevPage = pages[pageIndex - 1]
    entry = tocEntryMatchingElement(toc, prevPage.incitingElement)
    if entry is None:
        return None
    return h.E.a(
        {"href": "#" + entry.id},
        h.E.span({"class": "secno"}, entry.level),
        " ",
        copy.deepcopy(entry.content),
    )


def buildNextPageLink(page: SubPage, pages: list[SubPage], toc: list[TOCEntry]) -> t.ElementT | None:
    pageIndex = pages.index(page)
    if pageIndex == len(pages) - 1:
        return None

    prevPage = pages[pageIndex + 1]
    entry = tocEntryMatchingElement(toc, prevPage.incitingElement)
    if entry is None:
        return None
    return h.E.a(
        {"href": "#" + entry.id},
        h.E.span({"class": "secno"}, entry.level),
        " ",
        copy.deepcopy(entry.content),
    )


def tocEntryMatchingElement(toc: list[TOCEntry], el: t.ElementT) -> TOCEntry | None:
    id = el.get("id")
    if not id:
        return None
    for entry in toc:
        if entry.id == id:
            return entry
        rec = tocEntryMatchingElement(entry.children, el)
        if rec:
            return rec
    return None
