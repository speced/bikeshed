from __future__ import annotations

import json
from collections import OrderedDict

from .. import config, h, t, messages as m
from ..translate import _


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
    scriptLines = []
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
        if not refsFromSection:
            # Just insert a self-link instead
            # unless it already has a self-link, of course
            if h.find(".self-link", dfn) is None:
                h.appendChild(dfn, h.E.a({"href": "#" + h.escapeUrlFrag(id), "class": "self-link"}))
            continue
        h.addClass(doc, dfn, "dfn-paneled")
        atLeastOnePanel = True
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
                }
            )
        panelJson = {
            "dfnID": id,
            "url": "#" + h.escapeUrlFrag(id),
            "dfnText": dfnText,
            "refSections": sectionsJson,
            "external": False,
        }
        scriptLines.append(f"window.dfnpanelData['{id}'] = {json.dumps(panelJson)};")
    if len(scriptLines) > 0:
        if "script-dfn-panel-json" not in doc.extraScripts:
            doc.extraScripts["script-dfn-panel-json"] = "window.dfnpanelData = {};\n"
        doc.extraScripts["script-dfn-panel-json"] += "\n".join(scriptLines)
    if atLeastOnePanel:
        doc.extraScripts["script-dfn-panel"] = getModuleFile("dfnpanels.js")
        doc.extraStyles["style-dfn-panel"] = getModuleFile("dfnpanels.css")
        h.addDOMHelperScript(doc)


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

    # Group the relevant links according to the section they're in.
    refsFromSection: OrderedDict[str, list[t.ElementT]] = OrderedDict()
    for link in doc.cachedLinksFromHref[ref.url]:
        section = h.sectionName(doc, link) or _("Unnumbered Section")
        refsFromSection.setdefault(section, []).append(link)

    h.addClass(doc, termEl, "dfn-paneled")
    termID = termEl.get("id")
    if termID is None:
        m.warn("An external reference index entry ended up without an ID:\n{ref}")
        return
    termText = h.textContent(termEl)
    sectionsJson = []
    for text, els in refsFromSection.items():
        refsJson = []
        for i, el in enumerate(els):
            linkID = el.get("id")
            if linkID is None:
                linkID = h.uniqueID("external-link", ref.url, termID) + str(i)
                el.set("id", h.safeID(doc, linkID))
            refsJson.append(
                {
                    "id": linkID,
                }
            )
        sectionsJson.append(
            {
                "refs": refsJson,
                "title": text,
            }
        )
    panelJson = {
        "dfnID": termID,
        "url": ref.url,
        "dfnText": termText,
        "refSections": sectionsJson,
        "external": True,
    }

    if "script-dfn-panel-json" not in doc.extraScripts:
        doc.extraScripts["script-dfn-panel-json"] = "window.dfnpanelData = {};\n"
    doc.extraScripts["script-dfn-panel-json"] += f"window.dfnpanelData['{termID}'] = {json.dumps(panelJson)};\n"


def addExternalDfnPanelStyles(doc: t.SpecT) -> None:
    doc.extraScripts["script-dfn-panel"] = getModuleFile("dfnpanels.js")
    doc.extraStyles["style-dfn-panel"] = getModuleFile("dfnpanels.css")
    doc.extraStyles["style-darkmode"] += getModuleFile("dfnpanels-dark.css")
    h.addDOMHelperScript(doc)


def getModuleFile(filename: str) -> str:
    with open(config.scriptPath("dfnpanels", filename), "r", encoding="utf-8") as fh:
        return fh.read()
