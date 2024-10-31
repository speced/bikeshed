from __future__ import annotations

from collections import OrderedDict

from .. import h, t
from .. import messages as m
from ..translate import _t


def addDfnPanels(doc: t.SpecT, dfns: list[t.ElementT]) -> None:
    # Constructs "dfn panels" which show all the local references to a term
    # Gather all the <a href>s together
    allRefs: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for a in h.findAll("a", doc):
        href = a.get("href")
        if href is None:
            continue
        if not href.startswith("#"):
            continue
        allRefs.setdefault(href[1:], []).append(a)
    panelsJSON = doc.extraJC.addDfnPanels()
    for dfn in dfns:
        id = dfn.get("id")
        dfnText = h.textContent(dfn)
        if not id:
            # Something went wrong, bail.
            continue
        refsFromSection: OrderedDict[str, list[t.ElementT]] = OrderedDict()
        for link in allRefs.get(id, []):
            section = h.sectionName(doc, link)
            if section is not None:
                refsFromSection.setdefault(section, []).append(link)
        h.addClass(doc, dfn, "dfn-paneled")
        sectionsJson = []
        for text, els in refsFromSection.items():
            refsJson = []
            for el in els:
                refID = el.get("id")
                if refID is None:
                    refID = f"ref-for-{id}"
                    el.set("id", h.safeID(doc, refID))
                refsJson.append({"id": refID})
            sectionsJson.append(
                {
                    "refs": refsJson,
                    "title": text,
                },
            )
        panelsJSON[id] = {
            "dfnID": id,
            "url": "#" + h.escapeUrlFrag(id),
            "dfnText": dfnText,
            "refSections": sectionsJson,
            "external": False,
        }


def addExternalDfnPanel(termEl: t.ElementT, ref: t.RefWrapper, doc: t.SpecT) -> None:
    # Constructs "dfn panels" which show all the local references to an external term

    # Calculate and cache the doc's links,
    # so I'm not iterating the doc for links constantly.
    if not doc.cachedLinksFromHref:
        for a in h.findAll("a", doc):
            href = a.get("href")
            if href is None:
                continue
            if href.startswith("#"):
                continue
            doc.cachedLinksFromHref.setdefault(href, []).append(a)

    if ref.url not in doc.cachedLinksFromHref:
        return

    panelsJSON = doc.extraJC.addDfnPanels()

    # Group the relevant links according to the section they're in.
    refsFromSection: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for link in doc.cachedLinksFromHref[ref.url]:
        section = h.sectionName(doc, link) or _t("Unnumbered Section")
        refsFromSection.setdefault(section, []).append(link)

    h.addClass(doc, termEl, "dfn-paneled")
    termID = termEl.get("id")
    if termID is None:
        m.warn("An external reference index entry ended up without an ID:\n{ref}")
        return
    termText = h.textContent(termEl)
    sectionsJson = []
    counter = 0
    for text, els in refsFromSection.items():
        refsJson = []
        for el in els:
            linkID = el.get("id")
            if linkID is None:
                linkID = h.uniqueID("external-link", ref.url, termID) + str(counter)
                counter += 1
                el.set("id", h.safeID(doc, linkID))
            refsJson.append(
                {
                    "id": linkID,
                },
            )
        sectionsJson.append(
            {
                "refs": refsJson,
                "title": text,
            },
        )
    panelsJSON[termID] = {
        "dfnID": termID,
        "url": ref.url,
        "dfnText": termText,
        "refSections": sectionsJson,
        "external": True,
    }
