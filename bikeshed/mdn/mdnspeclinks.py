from __future__ import annotations

import json
from collections import OrderedDict

from .. import h, t
from .. import messages as m
from ..translate import _t

if t.TYPE_CHECKING:

    class MdnFeatureT(t.TypedDict, total=False):
        engines: list[str]
        filename: str
        name: str
        slug: str
        summary: str
        mdn_url: str
        support: dict[str, t.Any]
        # the support values are wild

    MdnDataT: t.TypeAlias = dict[str, list[MdnFeatureT]]


def addMdnPanels(doc: t.SpecT) -> list[t.ElementT]:
    if not doc.md.includeMdnPanels:
        return []

    try:
        filename = f"{doc.md.vshortname}.json"
        datafile = doc.dataFile.fetch("mdn", filename, str=True)
    except OSError:
        try:
            filename = f"{doc.md.shortname}.json"
            datafile = doc.dataFile.fetch("mdn", filename, str=True)
        except OSError:
            if doc.md.includeMdnPanels == "maybe":
                # if "maybe", failure is fine, don't complain
                pass
            else:
                m.die(f"Couldn't find the MDN data for '{doc.md.vshortname}' nor '{doc.md.shortname}'.")
            return []
    try:
        data = t.cast("MdnDataT", json.loads(datafile, object_pairs_hook=OrderedDict))
    except Exception as e:
        m.die(f"Couldn't load MDN Spec Links data for this spec.\n{e}")
        return []

    panels = panelsFromData(doc, data)
    if panels:
        doc.extraJC.addMdn()

    return panels


def createAnno(className: str, mdnButton: t.ElementT, featureDivs: list[t.ElementT]) -> t.ElementT:
    return h.E.div({"class": className}, mdnButton, featureDivs)


def panelsFromData(doc: t.SpecT, data: MdnDataT) -> list[t.ElementT]:
    mdnBaseUrl = "https://developer.mozilla.org/en-US/docs/Web/"

    browsersProvidingCurrentEngines = ["firefox", "safari", "chrome"]
    browsersWithBorrowedEngines = ["opera", "edge_blink"]
    browsersWithRetiredEngines = ["edge", "ie"]
    browsersForMobileDevices = [
        "firefox_android",
        "safari_ios",
        "chrome_android",
        "webview_android",
        "samsunginternet_android",
        "opera_android",
    ]

    # BCD/mdn-spec-links shortnames to full names
    nameFromCodeName = {
        "chrome": "Chrome",
        "chrome_android": "Chrome for Android",
        "edge": "Edge (Legacy)",
        "edge_blink": "Edge",
        "firefox": "Firefox",
        "firefox_android": "Firefox for Android",
        "ie": "IE",
        "nodejs": "Node.js",
        "opera": "Opera",
        "opera_android": "Opera Mobile",
        "safari": "Safari",
        "samsunginternet_android": "Samsung Internet",
        "safari_ios": "iOS Safari",
        "webview_android": "Android WebView",
    }

    panels = []
    missingIds = []
    for elementId, features in data.items():
        lessThanTwoEngines = 0
        onlyTwoEngines = 0
        allEngines = 0
        featureDivs = []
        targetElement = h.find(f"[id='{elementId}']", doc)
        if targetElement is None and elementId not in doc.md.ignoreMDNFailure:
            missingIds.append(elementId)
            continue

        for feature in features:
            if "engines" in feature:
                engines = len(feature["engines"])
                if engines < 2:
                    lessThanTwoEngines = lessThanTwoEngines + 1
                elif engines == 2:
                    onlyTwoEngines = onlyTwoEngines + 1
                elif engines >= len(browsersProvidingCurrentEngines):
                    allEngines = allEngines + 1
            featureDivs.append(
                mdnPanelFor(
                    feature,
                    mdnBaseUrl,
                    nameFromCodeName,
                    browsersProvidingCurrentEngines,
                    browsersWithBorrowedEngines,
                    browsersWithRetiredEngines,
                    browsersForMobileDevices,
                ),
            )

        summary = h.E.summary()
        if lessThanTwoEngines > 0:
            h.appendChild(
                summary,
                h.E.b(
                    {
                        "class": "less-than-two-engines-flag",
                        "title": _t("This feature is in less than two current engines."),
                    },
                    "\u26A0",
                ),
            )
        elif allEngines > 0 and lessThanTwoEngines == 0 and onlyTwoEngines == 0:
            h.appendChild(
                summary,
                h.E.b(
                    {
                        "class": "all-engines-flag",
                        "title": _t("This feature is in all current engines."),
                    },
                    "\u2714",
                ),
            )
        h.appendChild(summary, h.E.span("MDN"))
        anno = h.E.details({"class": "mdn-anno unpositioned", "data-anno-for": elementId}, summary, featureDivs)
        panels.append(anno)
        h.appendChild(doc.body, anno)

    if missingIds:
        msg = "Skipped generating some MDN panels, because the following IDs weren't present in the document. Use `Ignore MDN Failures` if this is expected.\n"
        msg += "\n".join("  #" + missingId for missingId in missingIds)
        m.warn(msg)

    return panels


def addSupportRow(
    browserCodeName: str,
    nameFromCodeName: dict[str, str],
    support: dict[str, t.Any],
    supportData: t.ElementT,
) -> None:
    if browserCodeName not in support:
        return
    isEdgeLegacy = browserCodeName == "edge"
    isIE = browserCodeName == "ie"
    needsFlag = False
    versionAdded = None
    versionRemoved = None
    thisBrowserSupport = support[browserCodeName]
    if isinstance(thisBrowserSupport, dict):
        if "version_added" in thisBrowserSupport:
            versionAdded = thisBrowserSupport["version_added"]
            if "flags" in thisBrowserSupport:
                needsFlag = True
            if (
                "prefix" in thisBrowserSupport
                or "alternative_name" in thisBrowserSupport
                or "partial_implementation" in thisBrowserSupport
            ):
                versionAdded = False
        if "version_removed" in thisBrowserSupport:
            versionRemoved = thisBrowserSupport["version_removed"]
    if isinstance(thisBrowserSupport, list):
        for versionDetails in thisBrowserSupport:
            if "version_removed" in versionDetails:
                versionRemoved = versionDetails["version_removed"]
                continue
            if "version_added" in versionDetails:
                if versionDetails["version_added"] is False:
                    versionAdded = False
                    continue
                if versionDetails["version_added"] is None:
                    versionAdded = None
                    continue
                if (
                    "prefix" in versionDetails
                    or "alternative_name" in versionDetails
                    or "partial_implementation" in versionDetails
                ):
                    continue
                if "flags" in thisBrowserSupport:
                    needsFlag = True
                versionAdded = versionDetails["version_added"]
                versionRemoved = None
                break
    statusCode = "n"
    if versionAdded is None:
        minVersion = "?"
    elif versionAdded is False:
        minVersion = "None"
    elif versionAdded is True:
        minVersion = "Yes"
        statusCode = "y"
    else:
        if versionRemoved is None:
            statusCode = "y"
            minVersion = versionAdded + "+"
            if isEdgeLegacy and versionAdded == "18":
                minVersion = "18"
            if isIE and versionAdded == "11":
                minVersion = "11"
        else:
            statusCode = "n"
            if versionAdded is not None:
                minVersion = versionAdded + "\u2013" + versionRemoved
            else:
                minVersion = "None"
    browserFullName = nameFromCodeName[browserCodeName]
    h.appendChild(
        supportData,
        browserCompatSpan(browserCodeName, browserFullName, statusCode, minVersion, needsFlag),
    )


def mdnPanelFor(
    feature: MdnFeatureT,
    mdnBaseUrl: str,
    nameFromCodeName: dict[str, str],
    browsersProvidingCurrentEngines: list[str],
    browsersWithBorrowedEngines: list[str],
    browsersWithRetiredEngines: list[str],
    browsersForMobileDevices: list[str],
) -> t.ElementT:
    featureDiv = h.E.div({"class": "feature"})
    if "slug" in feature:
        slug = feature["slug"]
        displaySlug = slug.split("/", 1)[1]
        title = feature.get("summary", "")
        mdnURL = mdnBaseUrl + slug
        h.appendChild(featureDiv, h.E.p({}, h.E.a({"href": mdnURL, "title": title}, displaySlug)))
    if "engines" in feature:
        engines = len(feature["engines"])
        enginesPara = None
        if engines == 0:
            enginesPara = h.E.p({"class": "less-than-two-engines-text"}, _t("In no current engines."))
        elif engines == 1:
            enginesPara = h.E.p({"class": "less-than-two-engines-text"}, _t("In only one current engine."))
        elif engines >= len(browsersProvidingCurrentEngines):
            enginesPara = h.E.p({"class": "all-engines-text"}, _t("In all current engines."))
        if enginesPara is not None:
            h.appendChild(featureDiv, enginesPara)
    supportData = h.E.div({"class": "support"})
    h.appendChild(featureDiv, supportData)
    support = feature["support"]
    for browserCodeName in browsersProvidingCurrentEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    h.appendChild(supportData, h.E.hr())
    for browserCodeName in browsersWithBorrowedEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    h.appendChild(supportData, h.E.hr())
    for browserCodeName in browsersWithRetiredEngines:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    h.appendChild(supportData, h.E.hr())
    for browserCodeName in browsersForMobileDevices:
        addSupportRow(browserCodeName, nameFromCodeName, support, supportData)
    if "nodejs" in support:
        h.appendChild(supportData, h.E.hr())
        addSupportRow("nodejs", nameFromCodeName, support, supportData)
    return featureDiv


def browserCompatSpan(
    browserCodeName: str,
    browserFullName: str,
    statusCode: str,
    minVersion: str,
    needsFlag: bool,
) -> t.ElementT:
    # browserCodeName: e.g. "chrome"
    # browserFullName: e.g. "Chrome for Android"
    minVersionAttributes = {}
    flagSymbol = ""
    if needsFlag:
        flagSymbol = "\U0001f530 "
        minVersionAttributes["title"] = _t("Requires setting a user preference or runtime flag.")
    statusClass = {"y": "yes", "n": "no"}[statusCode]
    outer = h.E.span({"class": browserCodeName + " " + statusClass})
    h.appendChild(outer, h.E.span({}, browserFullName))
    h.appendChild(outer, h.E.span(minVersionAttributes, flagSymbol + minVersion))
    return outer
