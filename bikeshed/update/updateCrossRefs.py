from __future__ import annotations

import json
import os
import re
from collections import defaultdict

import requests
import tenacity
from alive_progress import alive_it

from .. import config, t
from .. import messages as m

if t.TYPE_CHECKING:
    AnchorsT: t.TypeAlias = defaultdict[str, list[AnchorT]]
    HeadingGroupT: t.TypeAlias = dict[SpecStatusT, HeadingT]
    HeadingKeyT: t.TypeAlias = str
    SpecStatusT: t.TypeAlias = str
    HeadingsT: t.TypeAlias = dict[HeadingKeyT, list[HeadingKeyT] | HeadingGroupT]
    AllHeadingsT: t.TypeAlias = dict[str, HeadingsT]
    SpecsT: t.TypeAlias = dict[str | None, SpecT]
    MethodsT: t.TypeAlias = defaultdict[str, dict[str, t.Any]]
    ForsT: t.TypeAlias = defaultdict[str, list[str]]

    # https://github.com/w3c/reffy/blob/main/schemas/browserlib/extract-headings.json
    class WebrefHeadingT(t.TypedDict, total=False):
        id: t.Required[str]
        href: t.Required[str]
        title: t.Required[str]
        level: t.Required[int]
        number: str

    class HeadingT(t.TypedDict):
        url: str
        number: str
        text: str
        spec: str

    # https://github.com/w3c/reffy/blob/main/schemas/browserlib/extract-dfns.json
    WebrefAnchorT = t.TypedDict(
        "WebrefAnchorT",
        {
            "href": t.Required[str],
            "linkingText": list[str],
            "type": t.Required[str],
            "for": t.Required[list[str]],
            "access": t.Required[str],
            "informative": t.Required[bool],
        },
        total=False,
    )

    AnchorT = t.TypedDict(
        "AnchorT",
        {
            "status": str,
            "type": str,
            "spec": str,
            "shortname": str,
            "level": int,
            "export": bool,
            "normative": bool,
            "url": str,
            "for": list[str],
        },
    )

    class WebrefSpecT(t.TypedDict, total=False):
        url: t.Required[str]
        shortname: t.Required[str]
        title: t.Required[str]
        shortTitle: t.Required[str]
        series: t.Required[dict[str, str]]
        nightly: t.Required[dict[str, str | list[str]]]
        release: dict[str, str | list[str]]
        seriesVersion: str
        seriesComposition: str
        links: str
        refs: str
        idl: str
        dfns: str
        headings: str
        ids: str

    class SpecT(t.TypedDict):
        vshortname: str
        shortname: str
        snapshot_url: str | None
        current_url: str | None
        title: str
        description: str | None
        abstract: str | None
        level: int | None


def update(path: str, dryRun: bool = False) -> set[str] | None:
    specs: SpecsT = {}
    anchors: AnchorsT = defaultdict(list)
    headings: AllHeadingsT = {}

    gatherWebrefData(specs, anchors, headings)
    cleanSpecHeadings(headings)
    methods = extractMethodData(anchors)
    fors = extractForsData(anchors)

    if not dryRun:
        writtenPaths = set()
        try:
            p = os.path.join(path, "specs.json")
            writtenPaths.add(p)
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(specs, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as e:
            m.die(f"Couldn't save spec database to disk.\n{e}")
            return None
        try:
            for specName, specHeadings in headings.items():
                p = os.path.join(path, "headings", f"headings-{specName}.json")
                writtenPaths.add(p)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(json.dumps(specHeadings, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as e:
            m.die(f"Couldn't save headings database to disk.\n{e}")
            return None
        try:
            writtenPaths.update(writeAnchorsFile(anchors, path))
        except Exception as e:
            m.die(f"Couldn't save anchor database to disk.\n{e}")
            return None
        try:
            p = os.path.join(path, "methods.json")
            writtenPaths.add(p)
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(methods, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as e:
            m.die(f"Couldn't save methods database to disk.\n{e}")
            return None
        try:
            p = os.path.join(path, "fors.json")
            writtenPaths.add(p)
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(fors, ensure_ascii=False, indent=2, sort_keys=True))
        except Exception as e:
            m.die(f"Couldn't save fors database to disk.\n{e}")
            return None

    m.say("Success!")
    return writtenPaths


def gatherWebrefData(specs: SpecsT, anchors: AnchorsT, headings: AllHeadingsT) -> None:
    m.say("Downloading anchor data from Webref...")
    currentWebrefData = [x for x in specsFromWebref("current") if "dfns" in x or "headings" in x]
    snapshotWebrefData = specsFromWebref("snapshot")

    progress = alive_it(currentWebrefData, dual_line=True)
    for rawWSpec in t.cast("t.Generator[WebrefSpecT, None, None]", progress):
        spec = canonSpecFromWebref(rawWSpec)
        currentUrl = spec["current_url"]
        assert currentUrl is not None
        progress.text(spec["vshortname"].lower())

        specs[spec["vshortname"].lower()] = spec
        specHeadings: HeadingsT = {}
        headings[spec["vshortname"]] = specHeadings

        if "dfns" in rawWSpec:
            currentAnchors = anchorsFromWebref("current", rawWSpec["dfns"])
            if currentAnchors:
                for anchor in currentAnchors:
                    addToAnchors(anchor, anchors, spec, "current")
        if "headings" in rawWSpec:
            currentHeadings = headingsFromWebref("current", rawWSpec["headings"])
            if currentHeadings:
                for heading in currentHeadings:
                    addToHeadings(heading, specHeadings, spec, "current")

        # Complete list of anchors/headings with those from the snapshot version of the spec
        if spec["snapshot_url"] is not None and snapshotWebrefData is not None:
            rawSnapshotSpec: WebrefSpecT | None = None
            for s in snapshotWebrefData:
                if s["shortname"].lower() == spec["vshortname"].lower():
                    rawSnapshotSpec = s
                    break
            else:
                m.warn(f"Despite claiming to have a snapshot url, no snapshot data found for '{spec['vshortname']}'.")
            if rawSnapshotSpec:
                if "dfns" in rawSnapshotSpec:
                    snapshotAnchors = anchorsFromWebref("snapshot", rawSnapshotSpec["dfns"])
                    if snapshotAnchors:
                        for anchor in snapshotAnchors:
                            addToAnchors(anchor, anchors, spec, "snapshot")
                if "headings" in rawSnapshotSpec:
                    snapshotHeadings = headingsFromWebref("snapshot", rawSnapshotSpec["headings"])
                    if snapshotHeadings:
                        for heading in snapshotHeadings:
                            addToHeadings(heading, specHeadings, spec, "snapshot")


def specsFromWebref(status: t.Literal["current" | "snapshot"]) -> list[WebrefSpecT]:
    url = ("ed" if status == "current" else "tr") + "/index.json"
    j = dataFromWebref(url)
    if j is None or j.get("results") is None:
        msg = f"No {status} specs data from WebRef. Got:\n{json.dumps(j, indent=1)}"
        raise Exception(msg)
    rawSpecs = t.cast("list[WebrefSpecT]", j["results"])
    filteredSpecs: list[WebrefSpecT] = []
    for spec in rawSpecs:
        if spec["seriesComposition"] == "fork":
            continue
        filteredSpecs.append(spec)
    return filteredSpecs


def anchorsFromWebref(status: t.Literal["current" | "snapshot"], urlSuffix: str) -> list[WebrefAnchorT]:
    url = ("ed" if status == "current" else "tr") + "/" + urlSuffix
    j = dataFromWebref(url)
    if j is None or j.get("dfns") is None:
        msg = f"No WebRef dfns data at {url}. Got:\n{json.dumps(j, indent=1)}"
        raise Exception(msg)
    return t.cast("list[WebrefAnchorT]", j["dfns"])


def headingsFromWebref(status: t.Literal["current" | "snapshot"], urlSuffix: str) -> list[WebrefHeadingT]:
    url = ("ed" if status == "current" else "tr") + "/" + urlSuffix
    j = dataFromWebref(url)
    if j is None or j.get("headings") is None:
        msg = f"No WebRef headings data at {url}. Got:\n{json.dumps(j, indent=1)}"
        raise Exception(msg)
    return t.cast("list[WebrefHeadingT]", j["headings"])


@tenacity.retry(reraise=True, stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_random(1, 2))
def dataFromWebref(url: str) -> t.JSONT:
    webrefAPIUrl = "https://raw.githubusercontent.com/w3c/webref/main/"
    try:
        response = requests.get(webrefAPIUrl + url, timeout=5)
    except Exception as e:
        msg = f"Couldn't download data from Webref.\n{e}"
        raise Exception(msg) from e
    try:
        data = response.json()
    except Exception as e:
        msg = f"Data retrieved from Webref wasn't valid JSON for some reason. Try downloading again?\n{e}"
        raise Exception(msg) from e
    return t.cast("t.JSONT", data)


def canonSpecFromWebref(rawSpec: WebrefSpecT) -> SpecT:
    """Generate a spec object from data gleaned from Webref"""
    assert rawSpec["shortname"] is not None
    assert rawSpec["series"] is not None
    assert rawSpec["nightly"] is not None
    assert rawSpec["title"] is not None
    assert rawSpec["shortTitle"] is not None
    spec: SpecT = {
        "vshortname": rawSpec["shortname"].lower(),
        "shortname": rawSpec["series"]["shortname"].lower(),
        "snapshot_url": t.cast("str", rawSpec.get("release", {}).get("url")),
        "current_url": t.cast("str", rawSpec["nightly"]["url"]),
        "title": rawSpec["shortTitle"],
        "description": rawSpec["title"],
        "abstract": None,
        "level": (
            int(rawSpec["seriesVersion"])
            if "seriesVersion" in rawSpec and re.match(r"^\d+$", rawSpec.get("seriesVersion", ""))
            else None
        ),
    }
    return spec


def addToAnchors(
    rawAnchor: WebrefAnchorT,
    anchors: AnchorsT,
    spec: SpecT,
    status: t.Literal["current"] | t.Literal["snapshot"],
) -> None:
    baseUrl = spec["snapshot_url"] if status == "snapshot" else spec["current_url"]
    assert baseUrl is not None
    assert rawAnchor["type"] is not None
    assert rawAnchor["linkingText"] is not None
    assert rawAnchor["access"] is not None
    assert rawAnchor["href"] is not None
    assert rawAnchor["informative"] is not None
    assert rawAnchor["for"] is not None

    anchor: AnchorT = {
        "status": status,
        "type": rawAnchor["type"],
        "export": rawAnchor["access"] == "public",
        "normative": not rawAnchor["informative"],
        "url": rawAnchor["href"],
        "for": rawAnchor["for"],
        "spec": spec["vshortname"],
        "shortname": spec["shortname"],
        "level": int(spec["level"] or "1"),
    }
    for text in rawAnchor["linkingText"]:
        text = re.sub(r"‘|’", "'", text)
        text = re.sub(r"“|”", '"', text)
        text = re.sub(r"\s+", " ", text)
        anchors[text].append(anchor)


def addToHeadings(
    rawAnchor: WebrefHeadingT,
    specHeadings: HeadingsT,
    spec: SpecT,
    status: t.Literal["current"] | t.Literal["snapshot"],
) -> None:
    heading: HeadingT = {
        "url": rawAnchor["href"],
        "number": rawAnchor.get("number", ""),
        "text": rawAnchor["title"],
        "spec": spec["title"],
    }
    specUrl = spec["snapshot_url"] if status == "snapshot" else spec["current_url"]
    assert specUrl is not None
    if heading["url"].startswith(specUrl):
        truncatedUrl = heading["url"][len(specUrl) :]
    else:
        m.warn(f"Invalid heading - URL doesn't start with the spec's url <{specUrl}>.\n{heading}")
        return
    if truncatedUrl[0] == "#":
        # Either single-page spec, or link on the top page of a multi-page spec
        fragment = truncatedUrl
        shorthand = "/" + fragment
    else:
        # Multi-page spec, need to guard against colliding IDs
        if "#" in truncatedUrl:
            # url to a heading in the page, like "foo.html#bar"
            match = re.match(r"([\w-]+).*?(#.*)", truncatedUrl)
            if not match:
                m.die(
                    f"Unexpected URI pattern '{truncatedUrl}' for spec '{spec['vshortname']}'. Please report this to the Bikeshed maintainer.",
                )
                return
            page, fragment = match.groups()
            page = "/" + page
        else:
            # url to a page itself, like "foo.html"
            page, _, _ = truncatedUrl.partition(".")
            page = "/" + page
            fragment = "#"
        shorthand = page + fragment
    if shorthand not in specHeadings:
        specHeadings[shorthand] = {}
    headingGroup = t.cast("HeadingGroupT", specHeadings[shorthand])
    headingGroup[status] = heading
    if fragment not in specHeadings:
        specHeadings[fragment] = []
    keyList = t.cast("list[HeadingKeyT]", specHeadings[fragment])
    if shorthand not in specHeadings[fragment]:
        keyList.append(shorthand)


def cleanSpecHeadings(headings: AllHeadingsT) -> None:
    """Headings data was purposely verbose, assuming collisions even when there wasn't one.
    Want to keep the collision data for multi-page, so I can tell when you request a non-existent page,
    but need to collapse away the collision stuff for single-page."""
    for specHeadings in headings.values():
        for k, v in list(specHeadings.items()):
            if k[0] != "#":
                # a HeadingGroupT, not a list of HeadingKeyTs
                continue
            assert isinstance(v, list)
            if len(v) == 1 and v[0][0:2] == "/#":
                # No collision, and this is either a single-page spec or a non-colliding front-page link
                # Go ahead and collapse them.
                specHeadings[k] = specHeadings[v[0]]
                del specHeadings[v[0]]


def extractMethodData(anchors: AnchorsT) -> MethodsT:
    """Compile a db of {argless methods => {argfull method => {args, fors, url, shortname}}"""

    methods: defaultdict[str, dict] = defaultdict(dict)
    for key, anchors_ in anchors.items():
        # Extract the name and arguments
        match = re.match(r"([^(]+)\((.*)\)", key)
        if not match:
            continue
        methodName, argstring = match.groups()
        arglessMethod = methodName + "()"
        args = [x.strip() for x in argstring.split(",")] if argstring else []
        for anchor in anchors_:
            if anchor["type"] not in config.idlMethodTypes:
                continue
            if key not in methods[arglessMethod]:
                methods[arglessMethod][key] = {
                    "args": args,
                    "for": set(),
                    "shortname": anchor["shortname"],
                }
            methods[arglessMethod][key]["for"].update(anchor["for"])
    # Translate the "for" set back to a list for JSONing
    for signatures in methods.values():
        for signature in signatures.values():
            signature["for"] = sorted(signature["for"])
    return methods


def extractForsData(anchors: AnchorsT) -> ForsT:
    """Compile a db of {for value => dict terms that use that for value}"""

    fors: ForsT = defaultdict(list)
    for key, anchors_ in anchors.items():
        for anchor in anchors_:
            for for_ in anchor["for"]:
                if for_ == "":
                    continue
                fors[for_].append(key)
            if not anchor["for"]:
                fors["/"].append(key)
    for key, val in list(fors.items()):
        fors[key] = sorted(set(val))
    return fors


def writeAnchorsFile(anchors: AnchorsT, path: str) -> set[str]:
    """
    Keys may be duplicated.

    key
    type
    spec
    shortname
    level
    status
    url
    export (boolish string)
    normative (boolish string)
    for* (one per line, unknown #)
    - (by itself, ends the segment)
    """
    writtenPaths = set()
    groupedEntries: defaultdict[str, dict[str, list[AnchorT]]] = defaultdict(dict)
    for key, entries in anchors.items():
        group = config.groupFromKey(key)
        groupedEntries[group][key] = entries
    for group, group_anchors in groupedEntries.items():
        p = os.path.join(path, "anchors", f"anchors-{group}.data")
        writtenPaths.add(p)
        with open(p, "w", encoding="utf-8") as fh:
            for key, entries in sorted(group_anchors.items(), key=lambda x: x[0]):
                for e in sorted(entries, key=lambda x: x["url"]):
                    refKey, displayKey = config.adjustKey(key, e.get("type", ""))
                    fh.write(refKey + "\n")
                    fh.write(displayKey + "\n")
                    for field in [
                        "type",
                        "spec",
                        "shortname",
                        "level",
                        "status",
                        "url",
                    ]:
                        fh.write(str(e.get(field, "")) + "\n")
                    for field in ["export", "normative"]:
                        if e.get(field, False):
                            fh.write("1\n")
                        else:
                            fh.write("\n")
                    for forValue in e.get("for", []):
                        if forValue:  # skip empty strings
                            fh.write(forValue + "\n")
                    fh.write("-" + "\n")
    return writtenPaths
