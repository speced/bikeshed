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
        support: dict[str, MdnSupportEntry | list[MdnSupportEntry] | t.Literal["mirror"]]
        # the support values are wild

    class MdnSupportEntry(t.TypedDict, total=False):
        version_added: bool | str
        version_removed: str
        prefix: str
        alternative_name: str
        partial_implementation: t.Literal[True]
        flags: t.Any

    MdnDataT: t.TypeAlias = dict[str, list[MdnFeatureT]]

BROWSER_DATA = {
    "current": ["firefox", "safari", "chrome"],
    "retired": {"edge":"18", "ie":"11"},
    "cell_order": [
        "firefox",
        "safari",
        "chrome",  # current
        "opera",
        "edge_blink",  # borrowed
        "edge",
        "ie",  # retired
        "firefox_android",
        "safari_ios",
        "chrome_android",
        "webview_android",
        "samsunginternet_android",
        "opera_android",  # mobile
        "nodejs",  # JS
    ],
    "mirrors": {
        "chrome_android": "chrome",
        "webview_android": "chrome",
        "samsunginternet_android": "chrome_android",
        "opera": "chrome",
        "opera_android": "chrome_android",
        "firefox_android": "firefox",
        "safari_ios": "safari",
    },
}


def addMdnPanels(doc: t.SpecT) -> list[t.ElementT]:
    if not doc.md.includeMdnPanels:
        return []

    data = loadMdnData(doc)
    panels = panelsFromData(doc, data)
    if panels:
        doc.extraJC.addMdn()
    return panels


def loadMdnData(doc: t.SpecT) -> MdnDataT:
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
                return {}
            else:
                m.die(f"Couldn't find the MDN data for '{doc.md.vshortname}' nor '{doc.md.shortname}'.")
                return {}
    try:
        data = t.cast("MdnDataT", json.loads(datafile, object_pairs_hook=OrderedDict))
        return data
    except Exception as e:
        m.die(f"Couldn't parse MDN data for this spec.\n{e}")
        return {}


# MDN annotation panels do not ship their body as markup. Each panel carries a compact
# "data-mdn" attribute instead, and <https://resources.whatwg.org/standard-mdn-annos.js>
# builds the support table from it the first time the reader opens the panel. That script
# owns the browser labels, the engine-support strings and the render grouping; what is
# shared between it and the code below is only this wire format:
#
#   data-mdn = "v1|" feature ("~" feature)*
#   feature  = slug "|" level "|" cells ["|" caniuse-feature "," caniuse-title]
#   level    = "" no remark | "0" no engines | "1" one engine | "9" all engines
#            | "s"/"S" one/some engines under another name
#            | "v"/"V" one/some engines prefixed
#            | "p"/"P" one/some engines partially
#   cells    = cell ("," cell)*  one per entry of MDNBrowserSlots, in that order. An
#                               empty cell means "no row for this browser", and trailing
#                               empty cells may be left out entirely.
#   cell     = [caveat] body
#   caveat   = "*" partial | "^" needs a flag | "$" needs a prefix or alternative name
#   body     = "?" unknown | "-" unsupported | "!" supported, version unknown
#            | "=" version           supported since exactly this version, no trailing "+"
#            | version "-" version   supported over a range, rendered with an en dash
#            | version               supported since this version, rendered with a "+"
#
# None of "|" and "~" occurs in any field of the current data, so no escaping is needed;
# the two free-text fields are squashed defensively rather than escaped.
#
# New browsers must be APPENDED to MDNBrowserSlots and never inserted. Archived commit
# snapshots keep loading the script above forever, and older copies of it simply ignore
# the cells they do not know about, which only works while the order is append-only.
# Anything that this scheme cannot express needs a new version prefix, not a redefinition
# of "v1".


def panelsFromData(doc: t.SpecT, data: MdnDataT) -> list[t.ElementT]:
    panels = []
    missingIds = []
    docIds = h.collectIds(doc.body)
    for elementId, features in data.items():
        targetElement = docIds.get(elementId)
        if targetElement is None and elementId not in doc.md.ignoreMDNFailure:
            missingIds.append(elementId)
            continue

        featureCode = encodeFeatureData(features)

        summary = buildSummary(features, numEngines=len(BROWSER_DATA["current"]))
        anno = h.E.details(
            {"class": "mdn-anno unpositioned", "data-anno-for": elementId, "data-mdn": featureCode},
            summary,
        )
        panels.append(anno)
        h.appendChild(doc.body, anno)

    if missingIds:
        msg = "Skipped generating some MDN panels, because the following IDs weren't present in the document. Use `Ignore MDN Failure` if this is expected.\n"
        msg += "\n".join("  #" + missingId for missingId in missingIds)
        m.warn(msg)

    return panels


def encodeFeatureData(features: list[MdnFeatureT]) -> str:
    fullCode = "v1|" + ("~".join(codeFromFeature(x) for x in features))
    return fullCode


def codeFromFeature(feature: MdnFeatureT) -> str:
    #   feature  = slug "|" level "|" cells ["|" caniuse-feature "," caniuse-title]
    code = cleanCodeText(feature["slug"]) + "|"
    code += levelFromFeature(feature) + "|"
    code += cellsFromFeature(feature)
    return code


def levelFromFeature(feature: MdnFeatureT) -> str:
    #   level    = "" no remark | "0" no engines | "1" one engine | "9" all engines
    #            | "s"/"S" one/some engines under another name
    #            | "v"/"V" one/some engines prefixed
    #            | "p"/"P" one/some engines partially
    if "engines" in feature:
        numEngines = len(feature["engines"])
        if numEngines == 0:
            return "0"
        elif numEngines == 1:
            return "1"
        elif numEngines >= len(BROWSER_DATA["current"]):
            return "9"
    return ""


def cellsFromFeature(feature: MdnFeatureT) -> str:
    #   cells    = cell ("," cell)*  one per entry of BROWSER_DATA["cell_order"], in that order. An
    #                                empty cell means "no row for this browser", and trailing
    #                                empty cells may be left out entirely.
    cells = []
    for browserCodeName in BROWSER_DATA["cell_order"]:
        cells.append(cellFromFeature(feature, browserCodeName))
    return ",".join(cells)


def cleanCodeText(text: str) -> str:
    # | and ~ are used in the data-mdn code as separators, so can't appear in the code's contents.
    # They're not used in the text of *any* current features, so just defensively blank them out
    # in case they ever do appear.
    return text.replace("|", " ").replace("~", " ")


def buildSummary(features: list[MdnFeatureT], numEngines: int) -> t.ElementT:
    lessThanTwoEngines = 0
    onlyTwoEngines = 0
    allEngines = 0
    for feature in features:
        if "engines" in feature:
            engines = len(feature["engines"])
            if engines < 2:
                lessThanTwoEngines = lessThanTwoEngines + 1
            elif engines == 2:
                onlyTwoEngines = onlyTwoEngines + 1
            elif engines >= numEngines:
                allEngines = allEngines + 1

    summary = h.E.summary()
    if lessThanTwoEngines > 0:
        h.appendChild(
            summary,
            h.E.b(
                {
                    "class": "less-than-two-engines-flag",
                    "title": _t("This feature is in less than two current engines."),
                },
                "\u26a0",
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
    return summary


def cellFromFeature(
    feature: MdnFeatureT,
    browserCodeName: str,
) -> str:
    #   cell     = [caveat] body
    #   caveat   = "*" partial | "^" needs a flag | "$" needs a prefix or alternative name | "@" mirrored
    #   body     = "?" unknown | "-" unsupported | "!" supported, version unknown
    #            | "=" version           supported since exactly this version, no trailing "+"
    #            | version "-" version   supported over a range, rendered with an en dash
    #            | version               supported since this version, rendered with a "+"

    # Documentation for the "support" data:
    # https://github.com/mdn/browser-compat-data/blob/main/schemas/compat-data-schema.md
    # Documentation misses:
    # * apparently feature.support can be `null`
    # * apparently feature.support.version_removed can be `true`

    if feature["support"] is None or browserCodeName not in feature["support"]:
        return ""
    support = feature["support"][browserCodeName]

    if support == "mirror":
        sourceCodeName, support = followMirrors(feature, browserCodeName)
        if sourceCodeName is None:
            return "@?"
        _, version = distillSupport(support, sourceCodeName)
        if version in "?-!":
            return "@" + version
        else:
            return "@!"

    caveat, version = distillSupport(support, browserCodeName)
    return caveat+version

def distillSupport(support: MdnSupportEntry | list[MdnSupportEntry], browserCodeName: str): -> tuple[str, str]
    versionAdded = None
    versionRemoved = None
    caveat = ""
    if isinstance(support, dict):
        if "version_added" in support:
            versionAdded = support["version_added"]
            caveat = getCaveat(support)
        if "version_removed" in support:
            versionRemoved = support["version_removed"]
    else isinstance(support, list):
        # List of support objects, documenting different levels of support over time.
        # Ordered recent-first, so stop when I hit the first version_added
        for versionDetails in support:
            if "version_removed" in versionDetails:
                versionRemoved = versionDetails["version_removed"]
            if "version_added" in versionDetails:
                versionAdded = versionDetails["version_added"]
                caveat = getCaveat(versionDetails)
                break

    version = getVersionString(versionAdded, versionRemoved, browserCodeName)

    return caveat, version


def followMirrors(feature: MdnFeatureT, browserCodeName: str, ) -> tuple[str, MdnSupportEntry | list[MdnSupportEntry]] | tuple[None, None]:
    if browserCodeName not in BROWSER_DATA["mirrors"]:
        return None, None
    mirroredBrowser = BROWSER_DATA["mirrors"]
    if mirroredBrowser not in feature["support"]:
        return None, None
    support = feature["support"][mirroredBrowser]
    if support == "mirror":
        return followMirrors(feature, mirroredBrowser)
    return mirroredBrowser, support


def getCaveat(supportEntry: MdnSupportEntry) -> str:
    if "flags" in support:
        return "^"
    if "prefix" in support or "alternative_name" in support:
        return "$"
    if "partial_implementation" in support:
        return "*"
    return ""


def getVersionString(versionAdded: str | bool | None, versionRemoved: str | bool | None, browserCodeName: str) -> str:
    if versionAdded is False:
        return "-"
    elif versionAdded is True:
        return "!"
    elif versionRemoved is True:
        return "-"
    elif browserCodeName in BROWSER_DATA["retired"] and versionAdded == BROWSER_DATA["retired"][browserCodeName]:
        return "=" + versionAdded
    elif versionAdded:
        if versionRemoved:
            return versionAdded + "-" + versionRemoved
        return versionAdded
    return "?"