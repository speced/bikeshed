from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime

from .. import h, t
from .. import messages as m
from ..translate import _t


def addCanIUsePanels(doc: t.SpecT) -> list[t.ElementT]:
    # Constructs "Can I Use panels" which show a compatibility data summary
    # for a term's feature.
    if not doc.md.includeCanIUsePanels:
        return []

    canIUseData = CanIUseManager(dataFile=doc.dataFile)

    lastUpdated = datetime.utcfromtimestamp(canIUseData.updated).date().isoformat()

    # e.g. 'iOS Safari' -> 'ios_saf'
    classFromBrowser = canIUseData.agents

    panels = []
    elements = h.findAll("[caniuse]", doc)
    if not elements:
        return []
    validateCanIUseURLs(doc, canIUseData, elements)
    for dfn in elements:
        dfnId = dfn.get("id")
        if not dfnId:
            m.die(f"Elements with `caniuse` attribute need to have an ID as well. Got:\n{h.serializeTag(dfn)}", el=dfn)
            continue

        featId = dfn.get("caniuse")
        if not featId:
            continue
        if not canIUseData.hasFeature(featId):
            m.die(f"Unrecognized Can I Use feature ID: {featId}", el=dfn)
            continue
        del dfn.attrib["caniuse"]
        featId = featId.lower()
        feature = canIUseData.getFeature(featId)

        h.addClass(doc, dfn, "caniuse-paneled")
        panel = canIUsePanelFor(
            id=featId,
            data=feature,
            update=lastUpdated,
            classFromBrowser=classFromBrowser,
        )
        panel.set("data-anno-for", dfnId)
        h.appendChild(doc.body, panel)
        panels.append(panel)

    if panels:
        doc.extraJC.addCiu()

    return panels


def canIUsePanelFor(id: str, data: t.JSONT, update: str, classFromBrowser: dict[str, str]) -> t.ElementT:
    panel = h.E.details(
        {"class": "caniuse-status unpositioned", "data-deco": ""},
        h.E.summary({}, "CanIUse"),
    )
    mainPara = h.E.p({"class": "support"}, h.E.b({}, _t("Support:")))
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
            _t("Source: "),
            h.E.a({"href": "https://caniuse.com/#feat=" + id}, "caniuse.com"),
            _t(" as of {date}").format(date=update),
        ),
    )
    return panel


def browserCompatSpan(
    browserCodeName: str,
    browserFullName: str,
    statusCode: str,
    minVersion: str | None = None,
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
        h.appendChild(outer, h.E.span({}, h.E.span({}, browserFullName, _t(" (limited)"))))
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
                + "Please check Can I Use for the correct spec url, and either correct your spec or correct Can I Use."
                + "If the URL is correct and you'd like to keep it in pre-emptively, add the URL to a 'Ignore Can I Use URL Failure' metadata.",
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
            f"The following Can I Use features are associated with your URLs, but don't show up in your spec:\n{featureList}",
        )


class CanIUseManager:
    def __init__(self, dataFile: t.DataFileRequester) -> None:
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
