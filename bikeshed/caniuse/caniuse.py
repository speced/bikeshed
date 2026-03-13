from __future__ import annotations

import dataclasses
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

    canIUseData = CIUData(dataFile=doc.dataFile)

    lastUpdated = datetime.utcfromtimestamp(canIUseData.updated).date().isoformat()

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

        featId = dfn.get("caniuse", "").lower()
        if not featId:
            continue
        feature = canIUseData.getFeature(featId)
        if not feature:
            m.die(f"Unrecognized Can I Use feature ID: {featId}", el=dfn)
            continue
        del dfn.attrib["caniuse"]

        h.addClass(doc, dfn, "caniuse-paneled")
        panel = canIUsePanelFor(
            id=featId,
            feature=feature,
            update=lastUpdated,
        )
        panel.set("data-anno-for", dfnId)
        h.appendChild(doc.body, panel)
        panels.append(panel)

    if panels:
        doc.extraJC.addCiu()

    return panels


def canIUsePanelFor(id: str, feature: CIUFeature, update: str) -> t.ElementT:
    panel = h.E.details(
        {"class": "caniuse-status unpositioned", "data-deco": ""},
        h.E.summary({}, "CanIUse"),
    )
    mainPara = h.E.p({"class": "support"}, h.E.b({}, _t("Support:")))
    h.appendChild(panel, mainPara)
    for support in feature.support:
        if support.status == "unsupported":
            continue
        h.appendChild(
            mainPara,
            browserCompatSpan(support),
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


def browserCompatSpan(support: CIUSupport) -> t.ElementT:
    # browserCodeName: e.g. and_chr, ios_saf, ie, etc...
    # browserFullName: e.g. "Chrome for Android"
    outer = h.E.span({"class": support.browserClass + " " + support.status})
    if support.status == "partial":
        h.appendChild(outer, h.E.span({}, h.E.span({}, support.browserName, _t(" (limited)"))))
    else:
        h.appendChild(outer, h.E.span({}, support.browserName))
    h.appendChild(outer, h.E.span({}, support.minVersion))
    return outer


def validateCanIUseURLs(doc: t.SpecT, canIUseData: CIUData, elements: list[t.ElementT]) -> None:
    # First, ensure that each Can I Use URL shows up at least once in the data;
    # otherwise, it's an error to be corrected somewhere.
    urlFeatures = set()
    for url in doc.md.canIUseURLs:
        sawTheURL = False
        for featureID, featureUrl in canIUseData.urlFromFeatureName.items():
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


class CIUData:
    def __init__(self, dataFile: t.DataFileRequester) -> None:
        self.dataFile = dataFile
        data = json.loads(
            self.dataFile.fetch("caniuse", "data.json", str=True),
            object_pairs_hook=OrderedDict,
        )
        self.updated = t.cast(int, data["updated"])
        self.classFromBrowser = t.cast("dict[str, str]", data["agents"])
        self.urlFromFeatureName = t.cast("dict[str, str]", data["features"])
        self.features: dict[str, CIUFeature] = {}

    def hasFeature(self, featureName: str) -> bool:
        return featureName in self.urlFromFeatureName

    def getFeature(self, featureName: str) -> CIUFeature | None:
        if featureName in self.features:
            return self.features[featureName]
        if not self.hasFeature(featureName):
            return None
        data = CIUFeature.fromJSON(
            self,
            json.loads(
                self.dataFile.fetch("caniuse", f"feature-{featureName}.json", str=True),
                object_pairs_hook=OrderedDict,
            ),
        )
        self.features[featureName] = data
        return data


@dataclasses.dataclass
class CIUFeature:
    notes: str
    url: str
    support: list[CIUSupport]

    @classmethod
    def fromJSON(cls, data: CIUData, j: t.JSONObject) -> t.Self:
        return cls(
            notes=t.cast(str, j["notes"]),
            url=t.cast(str, j["url"]),
            support=[
                CIUSupport.fromJSON(data, name, unparsed)
                for name, unparsed in t.cast("dict[str, str]", j["support"]).items()
            ],
        )


@dataclasses.dataclass
class CIUSupport:
    browserName: str
    browserClass: str
    status: str
    minVersion: str

    @classmethod
    def fromJSON(cls, data: CIUData, browserName: str, unparsed: str) -> t.Self:
        code = unparsed[0]
        if code == "y":
            status = "yes"
        elif code == "n":
            status = "no"
        elif code == "a":
            status = "partial"
        else:
            status = "unsupported"
        minVersion = unparsed[2:]
        if code == "n" or not minVersion:
            # has to come first, "n all" should output as "none"
            minVersion = "None"
        elif minVersion == "all":
            minVersion = "All"
        else:
            # numeric
            minVersion += "+"
        browserClass = data.classFromBrowser[browserName]
        return cls(browserName, browserClass, status, minVersion)
