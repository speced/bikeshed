from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime

from .. import config, h, messages as m, t


def addCanIUsePanels(doc: t.SpecT) -> None:
    # Constructs "Can I Use panels" which show a compatibility data summary
    # for a term's feature.
    if not doc.md.includeCanIUsePanels:
        return

    canIUseData = CanIUseManager(dataFile=doc.dataFile)

    lastUpdated = datetime.utcfromtimestamp(canIUseData.updated).date().isoformat()

    # e.g. 'iOS Safari' -> 'ios_saf'
    classFromBrowser = canIUseData.agents

    atLeastOnePanel = False
    elements = h.findAll("[caniuse]", doc)
    if not elements:
        return
    validateCanIUseURLs(doc, canIUseData, elements)
    for dfn in elements:
        featId = dfn.get("caniuse")
        if not featId:
            continue
        del dfn.attrib["caniuse"]

        featId = featId.lower()
        if not canIUseData.hasFeature(featId):
            m.die(f"Unrecognized Can I Use feature ID: {featId}", el=dfn)
            continue
        feature = canIUseData.getFeature(featId)

        h.addClass(doc, dfn, "caniuse-paneled")
        panel = canIUsePanelFor(
            id=featId,
            data=feature,
            update=lastUpdated,
            classFromBrowser=classFromBrowser,
        )
        dfnId = dfn.get("id")
        if not dfnId:
            m.die(f"Elements with `caniuse` attribute need to have an ID as well. Got:\n{h.serializeTag(dfn)}", el=dfn)
            continue
        panel.set("data-dfn-id", dfnId)
        h.appendChild(doc.body, panel)
        atLeastOnePanel = True

    if atLeastOnePanel:
        doc.extraScripts["script-caniuse-panel"] = getModuleFile("caniuse.js")
        doc.extraStyles["style-caniuse-panel"] = getModuleFile("caniuse.css")
        doc.extraStyles["style-darkmode"] += getModuleFile("caniuse-dark.css")


def canIUsePanelFor(id: str, data: t.JSONT, update: str, classFromBrowser: dict[str, str]) -> t.ElementT:
    panel = h.E.aside(
        {"class": "caniuse-status wrapped", "data-deco": ""},
        h.E.input({"value": "CanIUse", "type": "button", "class": "caniuse-panel-btn"}),
    )
    mainPara = h.E.p({"class": "support"}, h.E.b({}, "Support:"))
    h.appendChild(panel, mainPara)
    for browser, support in data["support"].items():
        statusCode = support[0]
        if statusCode == "u":
            continue
        minVersion = support[2:]
        h.appendChild(
            mainPara,
            browserCompatSpan(classFromBrowser[browser], browser, statusCode, minVersion),
        )
    h.appendChild(
        panel,
        h.E.p(
            {"class": "caniuse"},
            "Source: ",
            h.E.a({"href": "https://caniuse.com/#feat=" + id}, "caniuse.com"),
            " as of " + update,
        ),
    )
    return panel


def browserCompatSpan(
    browserCodeName: str, browserFullName: str, statusCode: str, minVersion: str | None = None
) -> t.ElementT:
    if statusCode == "n" or minVersion is None:
        minVersion = "None"
    elif minVersion == "all":
        minVersion = "All"
    else:
        minVersion = minVersion + "+"
    # browserCodeName: e.g. and_chr, ios_saf, ie, etc...
    # browserFullName: e.g. "Chrome for Android"
    statusClass = {"y": "yes", "n": "no", "a": "partial"}[statusCode]
    outer = h.E.span({"class": browserCodeName + " " + statusClass})
    if statusCode == "a":
        h.appendChild(outer, h.E.span({}, h.E.span({}, browserFullName, " (limited)")))
    else:
        h.appendChild(outer, h.E.span({}, browserFullName))
    h.appendChild(outer, h.E.span({}, minVersion))
    return outer


def validateCanIUseURLs(doc: t.SpecT, canIUseData: CanIUseManager, elements: list[t.ElementT]) -> None:
    # First, ensure that each Can I Use URL shows up at least once in the data;
    # otherwise, it's an error to be corrected somewhere.
    urlFeatures = set()
    for url in doc.md.canIUseURLs:
        sawTheURL = False
        for featureID, featureUrl in canIUseData.urlFromFeature.items():
            if featureUrl.startswith(url):
                sawTheURL = True
                urlFeatures.add(featureID)
        if not sawTheURL and url not in doc.md.ignoreCanIUseUrlFailure:
            m.warn(
                f"The Can I Use URL '{url}' isn't associated with any of the Can I Use features."
                "Please check Can I Use for the correct spec url, and either correct your spec or correct Can I Use."
                "If the URL is correct and you'd like to keep it in pre-emptively, add the URL to a 'Ignore Can I Use URL Failure' metadata."
            )

    # Second, ensure that every feature in the data corresponding to one of the listed URLs
    # has a corresponding Can I Use entry in the document;
    # otherwise, you're missing some features.
    docFeatures = set()
    for el in elements:
        canIUseAttr = el.get("caniuse")
        assert canIUseAttr is not None
        featureID = canIUseAttr.lower()
        docFeatures.add(featureID)

    unusedFeatures = urlFeatures - docFeatures
    if unusedFeatures:
        featureList = "\n".join(" * {0} - https://caniuse.com/#feat={0}".format(x) for x in sorted(unusedFeatures))
        m.warn(
            f"The following Can I Use features are associated with your URLs, but don't show up in your spec:\n{featureList}"
        )


class CanIUseManager:
    def __init__(self, dataFile: t.DataFileRequester):
        self.dataFile = dataFile
        data = json.loads(
            self.dataFile.fetch("caniuse", "data.json", str=True),
            object_pairs_hook=OrderedDict,
        )
        self.updated = data["updated"]
        self.agents = data["agents"]
        self.urlFromFeature = data["features"]
        self.features: t.JSONT = {}

    def hasFeature(self, featureName: str) -> bool:
        return featureName in self.urlFromFeature

    def getFeature(self, featureName: str) -> t.JSONT:
        if featureName in self.features:
            return t.cast("t.JSONT", self.features[featureName])
        if not self.hasFeature(featureName):
            return {}
        data = json.loads(
            self.dataFile.fetch("caniuse", f"feature-{featureName}.json", str=True),
            object_pairs_hook=OrderedDict,
        )
        self.features[featureName] = data
        return t.cast("t.JSONT", data)


def getModuleFile(filename: str) -> str:
    with open(config.scriptPath("caniuse", filename), "r", encoding="utf-8") as fh:
        return fh.read()
