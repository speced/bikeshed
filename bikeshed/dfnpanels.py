from __future__ import annotations

import hashlib
from collections import OrderedDict

from . import h, t
from .translate import _
from . import config


if t.TYPE_CHECKING:
    from . import refs as r  # pylint: disable=unused-import


def addDfnPanels(doc: t.SpecT, dfns: list[t.ElementT]) -> None:
    # Constructs "dfn panels" which show all the local references to a term
    atLeastOnePanel = False
    # Gather all the <a href>s together
    allRefs: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for a in h.findAll("a", doc):
        href = a.get("href")
        if href is None:
            continue
        if not href.startswith("#"):
            continue
        allRefs.setdefault(href[1:], []).append(a)
    for dfn in dfns:
        id = dfn.get("id")
        dfnText = h.textContent(dfn)
        if not id:
            # Something went wrong, bail.
            continue
        refs: OrderedDict[str, list[t.ElementT]] = OrderedDict()
        for link in allRefs.get(id, []):
            section = h.sectionName(doc, link)
            if section is not None:
                refs.setdefault(section, []).append(link)
        if not refs:
            # Just insert a self-link instead
            # unless it already has a self-link, of course
            if h.find(".self-link", dfn) is None:
                h.appendChild(dfn, h.E.a({"href": "#" + h.escapeUrlFrag(id), "class": "self-link"}))
            continue
        h.addClass(doc, dfn, "dfn-paneled")
        atLeastOnePanel = True
        panel = h.E.aside(
            {
                "class": "dfn-panel",
                "data-for": id,
                "id": f"infopanel-for-{id}",
                "aria-labelledby": f"infopaneltitle-for-{id}",
            },
            h.E.span(
                {"style": "display:none", "id": f"infopaneltitle-for-{id}"},
                _(f"Info about the '{dfnText}' definition."),
            ),
            h.E.b(h.E.a({"href": "#" + h.escapeUrlFrag(id)}, "#" + id)),
            h.E.b(_("Referenced in:")),
        )
        ul = h.appendChild(panel, h.E.ul())
        for text, els in refs.items():
            li = h.appendChild(ul, h.E.li())
            for i, el in enumerate(els):
                refID = el.get("id")
                if refID is None:
                    refID = f"ref-for-{id}"
                    el.set("id", h.safeID(doc, refID))
                if i == 0:
                    h.appendChild(
                        li,
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(refID),
                                "data-silently-dedup": "",
                            },
                            text,
                        ),
                    )
                else:
                    h.appendChild(
                        li,
                        " ",
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(refID),
                                "data-silently-dedup": "",
                            },
                            "(" + str(i + 1) + ")",
                        ),
                    )
        h.appendChild(doc.body, panel)
    if atLeastOnePanel:
        doc.extraScripts["script-dfn-panel"] = getModuleFile("dfnpanels.js")
        doc.extraStyles["style-dfn-panel"] = getModuleFile("dfnpanels.css")


def addExternalDfnPanel(termEl: t.ElementT, ref: r.RefWrapper, doc: t.SpecT) -> None:
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

    # Group the relevant links according to the section they're in.
    linksBySection: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for link in doc.cachedLinksFromHref[ref.url]:
        section = h.sectionName(doc, link) or _("Unnumbered Section")
        linksBySection.setdefault(section, []).append(link)
    if linksBySection:
        h.addClass(doc, termEl, "dfn-paneled")
        termID = uniqueId(ref.url + ref.text)
        termEl.set("id", termID)
        termText = h.textContent(termEl)
        panel = h.E.aside(
            {
                "class": "dfn-panel",
                "data-for": termID,
                "id": f"infopanel-for-{termID}",
                "aria-labelledby": f"infopaneltitle-for-{termID}",
            },
            h.E.span(
                {"style": "display:none", "id": f"infopaneltitle-for-{termID}"},
                _(f"Info about the '{termText}' external reference."),
            ),
            h.E.a({"href": ref.url}, ref.url),
            h.E.b(_("Referenced in:")),
        )
        ul = h.appendChild(panel, h.E.ul())
        for text, els in linksBySection.items():
            li = h.appendChild(ul, h.E.li())
            for i, el in enumerate(els):
                linkID = el.get("id")
                if linkID is None:
                    linkID = f"ref-for-{termID}"
                    el.set("id", h.safeID(doc, linkID))
                if i == 0:
                    h.appendChild(
                        li,
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(linkID),
                            },
                            text,
                        ),
                    )
                else:
                    h.appendChild(
                        li,
                        " ",
                        h.E.a(
                            {
                                "href": "#" + h.escapeUrlFrag(linkID),
                            },
                            "(" + str(i + 1) + ")",
                        ),
                    )
        h.appendChild(doc.body, panel)


def uniqueId(s: str) -> str:
    # Turns a unique string into a more compact (and ID-safe)
    # hashed string
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def addExternalDfnPanelStyles(doc: t.SpecT) -> None:
    doc.extraScripts["script-dfn-panel"] = getModuleFile("dfnpanels.js")
    doc.extraStyles["style-dfn-panel"] = getModuleFile("dfnpanels.css")
    doc.extraStyles["style-darkmode"] += getModuleFile("dfnpanels-dark.css")


def getModuleFile(filename: str) -> str:
    with open(config.scriptPath(".", filename), "r", encoding="utf-8") as fh:
        return fh.read()
