from __future__ import annotations

import json
import os
import re
from collections import defaultdict

import certifi
import tenacity
import requests
from json_home_client import Client as APIClient

from .. import config, messages as m, t

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

    class HeadingT(t.TypedDict):
        url: str
        number: str
        text: str
        spec: str

    RawAnchorT = t.TypedDict(
        "RawAnchorT",
        {
            "name": t.Required[str],
            "type": t.Required[str],
            "for": list[str],
            "section": bool,
            "title": str,
            "status": t.Required[str],
            "normative": bool,
            "export": bool,
            "linking_text": list[str],
            "uri": t.Required[str],
        },
        total=False,
    )

    RawWebrefAnchorT = t.TypedDict(
        "RawWebrefAnchorT",
        {
            "id": t.Required[str],
            "type": t.Required[str],
            "for": list[str],
            "informative": bool,
            "access": t.Required[str],
            "linkingText": list[str],
            "href": t.Required[str],
        },
        total=False,
    )

    RawWebrefHeadingT = t.TypedDict(
        "RawWebrefHeadingT",
        {
            "id": t.Required[str],
            "href": t.Required[str],
            "title": t.Required[str],
            "level": t.Required[int],
            "number": t.Required[str]
        },
        total=False)

    # Need to use function form due to "for" key
    # being invalid as a property name
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

    class RawSpecT(t.TypedDict, total=False):
        name: t.Required[str]
        short_name: t.Required[str]
        title: t.Required[str]
        level: t.Required[int]
        description: str | None
        base_uri: str | None
        draft_uri: str | None
        abstract: str | None

    class RawWebrefSpecT(t.TypedDict, total=False):
        url: t.Required[str]
        shortname: t.Required[str]
        title: t.Required[str]
        shortTitle: t.Required[str]
        series: t.Required(dict[str, str])
        nightly: t.Required(dict[str, str | list(str)])
        release: dict[str, str | list(str)] | None
        seriesVersion: str | None

    class SpecT(t.TypedDict):
        vshortname: str
        shortname: str
        snapshot_url: str | None
        current_url: str | None
        title: str
        description: str | None
        abstract: str | None
        level: int | None


def progressMessager(index: int, total: int) -> t.Callable[[], None]:
    return lambda: m.say(f"Downloading data for spec {index}/{total}...")

def update(path: str, dryRun: bool = False) -> set[str] | None:
    def setStatus(obj: RawAnchorT, status: str) -> RawAnchorT:
        obj["status"] = status
        return obj

    def isSpecInList(spec: SpecT, specs: SpecsT) -> bool:
        if spec["vshortname"].lower() in specs:
            return True
        for s in specs.values():
            # Shortnames don't always match. Let's compare URLs
            if (s["snapshot_url"] is not None and s["snapshot_url"] == spec["snapshot_url"]) or (s["current_url"] is not None and s["current_url"] == spec["current_url"]):
                return True
        return False

    def processRawAnchors(rawAnchorData: list(RawAnchorT), anchors: AnchorsT, specHeadings: AllHeadingsT) -> None:
        for rawAnchor in rawAnchorData:
            rawAnchor = fixupAnchor(rawAnchor)
            linkingTexts = rawAnchor["linking_text"]
            assert linkingTexts is not None
            if len(linkingTexts) == 0:
                # Happens if it had no linking text at all originally
                continue
            if len(linkingTexts) == 1 and linkingTexts[0].strip() == "":
                # Happens if it was marked with an empty lt and Shepherd still picked it up
                continue
            if "section" in rawAnchor and rawAnchor["section"] is True:
                addToHeadings(rawAnchor, specHeadings, spec=spec)
            if rawAnchor["type"] in config.dfnTypes.union(["dfn"]):
                addToAnchors(rawAnchor, anchors, spec=spec)

    m.say("Downloading anchor data from Shepherd...")
    shepherd = APIClient(
        "https://api.csswg.org/shepherd/",
        version="vnd.csswg.shepherd.v1",
        ca_cert_path=certifi.where(),
    )
    rawSpecData = dataFromApi(shepherd, "specifications", draft=True)
    if not rawSpecData:
        return None

    specs: SpecsT = dict()
    anchors: AnchorsT = defaultdict(list)
    headings: AllHeadingsT = {}
    lastMsgTime: float = 0
    for i, rawSpec in enumerate(rawSpecData.values(), 1):
        lastMsgTime = config.doEvery(
            s=5,
            lastTime=lastMsgTime,
            action=progressMessager(i, len(rawSpecData)),
        )
        rawSpec = dataFromApi(shepherd, "specifications", draft=True, anchors=True, spec=rawSpec["name"])
        spec = genSpec(rawSpec)
        assert spec["vshortname"] is not None
        specs[spec["vshortname"]] = spec
        specHeadings: HeadingsT = {}
        headings[spec["vshortname"]] = specHeadings

        rawAnchorData = [setStatus(x, "snapshot") for x in linearizeAnchorTree(rawSpec.get("anchors", []))] + [
            setStatus(x, "current") for x in linearizeAnchorTree(rawSpec.get("draft_anchors", []))
        ]
        processRawAnchors(rawAnchorData, anchors, specHeadings)

    m.say("Downloading anchor data from Webref...")
    webrefAPIUrl = "https://raw.githubusercontent.com/w3c/webref/main/"
    currentWebrefData = dataFromWebref(webrefAPIUrl + "ed/index.json")
    if not currentWebrefData or not "results" in currentWebrefData or currentWebrefData["results"] is None:
        return None
    currentWebrefData = currentWebrefData["results"]
    snapshotWebrefData = dataFromWebref(webrefAPIUrl + "tr/index.json")
    snapshotWebrefData = snapshotWebrefData["results"] if snapshotWebrefData and "results" in snapshotWebrefData and snapshotWebrefData["results"] is not None else None

    for i, currentSpec in enumerate(currentWebrefData, 1):
        lastMsgTime = config.doEvery(
            s=5,
            lastTime=lastMsgTime,
            action=progressMessager(i, len(currentWebrefData)),
        )
        if "dfns" not in currentSpec and "headings" not in currentSpec:
            continue
        spec = genWebrefSpec(currentSpec)
        if isSpecInList(spec, specs):
            # Skip specs that are already in Shepherd's database
            continue

        assert spec["vshortname"] is not None
        specs[spec["vshortname"]] = spec
        specHeadings: HeadingsT = {}
        headings[spec["vshortname"]] = specHeadings
        rawAnchorData: list[RawAnchorT] = []
        if "dfns" in currentSpec:
            currentAnchors = dataFromWebref(webrefAPIUrl + "ed/" + currentSpec["dfns"])
            if currentAnchors:
                rawAnchorData = [setStatus(convertWebrefAnchor(x, spec["current_url"]), "current") for x in currentAnchors["dfns"]]
        if "headings" in currentSpec:
            currentHeadings = dataFromWebref(webrefAPIUrl + "ed/" + currentSpec["headings"])
            if currentHeadings:
                rawAnchorData += [setStatus(convertWebrefHeading(x, spec["current_url"]), "current") for x in currentHeadings["headings"]]

        # Complete list of anchors/headings with those from the snapshot version of the spec
        if spec["snapshot_url"] is not None and snapshotWebrefData is not None:
            snapshotSpec = [s for s in snapshotWebrefData if s["shortname"] == currentSpec["shortname"]]
            if len(snapshotSpec) > 0:
                snapshotSpec = snapshotSpec.pop()
                if "dfns" in snapshotSpec:
                    snapshotAnchors = dataFromWebref(webrefAPIUrl + "tr/" + snapshotSpec["dfns"])
                    if snapshotAnchors:
                        rawAnchorData += [setStatus(convertWebrefAnchor(x, spec["snapshot_url"]), "snapshot") for x in snapshotAnchors["dfns"]]
                if "headings" in snapshotSpec:
                    snapshotHeadings = dataFromWebref(webrefAPIUrl + "tr/" + snapshotSpec["headings"])
                    if snapshotHeadings:
                        rawAnchorData += [setStatus(convertWebrefHeading(x, spec["snapshot_url"]), "snapshot") for x in snapshotHeadings["headings"]]

        if len(rawAnchorData) > 0:
            processRawAnchors(rawAnchorData, anchors, specHeadings)

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


@tenacity.retry(reraise=True, stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_random(1, 2))
def dataFromApi(api: APIClient, *args: t.Any, **kwargs: t.Any) -> t.JSONT:
    anchorDataContentTypes = [
        "application/json",
        "application/vnd.csswg.shepherd.v1+json",
    ]
    res = api.get(*args, **kwargs)
    if not res:
        raise Exception(
            "Unknown error fetching anchor data. This might be transient; try again in a few minutes, and if it's still broken, please report it on GitHub."
        )
    data = res.data
    if res.status_code == 406:
        raise Exception(
            "This version of the anchor-data API is no longer supported. Try updating Bikeshed. If the error persists, please report it on GitHub."
        )
    if res.content_type not in anchorDataContentTypes:
        raise Exception(f"Unrecognized anchor-data content-type '{res.content_type}'.")
    if res.status_code >= 300:
        raise Exception(
            f"Unknown error fetching anchor data; got status {res.status_code} and bytes:\n{data.decode('utf-8')}"
        )
    if isinstance(data, bytes):
        raise Exception(f"Didn't get expected JSON data. Got:\n{data.decode('utf-8')}")
    return t.cast("t.JSONT", data)

@tenacity.retry(reraise=True, stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_random(1, 2))
def dataFromWebref(url: str) -> t.JSONT:
    try:
        response = requests.get(url)
    except Exception as e:
        raise Exception(
            f"Couldn't download data from Webref.\n{e}"
        )
    try:
        data = response.json()
    except Exception as e:
        raise Exception(
            f"Data retrieved from Webref wasn't valid JSON for some reason. Try downloading again?\n{e}")
    return data

def linearizeAnchorTree(multiTree: list, rawAnchors: list[dict[str, t.Any]] | None = None) -> list[RawAnchorT]:
    if rawAnchors is None:
        rawAnchors = []
    # Call with multiTree being a list of trees
    for item in multiTree:
        if (item["type"] in config.dfnTypes.union(["dfn"])) or ("section" in item and item["section"] is True):
            rawAnchors.append(item)
        if item.get("children"):
            linearizeAnchorTree(item["children"], rawAnchors)
            del item["children"]
    return t.cast("list[RawAnchorT]", rawAnchors)


def genSpec(rawSpec: RawSpecT) -> SpecT:
    assert rawSpec["name"] is not None
    assert rawSpec["short_name"] is not None
    assert rawSpec["title"] is not None
    assert rawSpec["description"] is not None
    spec: SpecT = {
        "vshortname": rawSpec["name"],
        "shortname": rawSpec["short_name"],
        "snapshot_url": rawSpec.get("base_uri"),
        "current_url": rawSpec.get("draft_uri"),
        "title": rawSpec["title"],
        "description": rawSpec["description"],
        "abstract": rawSpec.get("abstract"),
        "level": None,
    }
    vShortname = spec["vshortname"]
    if spec["shortname"] is not None and vShortname.startswith(spec["shortname"]):
        # S = "foo", V = "foo-3"
        # Strip the prefix
        level = vShortname[len(spec["shortname"]) :]
        if level.startswith("-"):
            level = level[1:]
        if level.isdigit():
            spec["level"] = int(level)
        else:
            spec["level"] = 1
    elif spec["shortname"] is None and re.match(r"(.*)-(\d+)", vShortname):
        # S = None, V = "foo-3"
        match = t.cast(re.Match, re.match(r"(.*)-(\d+)", vShortname))
        spec["shortname"] = match.group(1)
        spec["level"] = int(match.group(2))
    else:
        spec["shortname"] = vShortname
        spec["level"] = 1
    return spec

def genWebrefSpec(rawSpec: RawWebrefSpecT) -> SpecT:
    """Generate a spec object from data gleaned from Webref"""
    assert rawSpec["shortname"] is not None
    assert rawSpec["series"] is not None
    assert rawSpec["nightly"] is not None
    assert rawSpec["title"] is not None
    assert rawSpec["shortTitle"] is not None
    spec: SpecT = {
        "vshortname": rawSpec["shortname"],
        "shortname": rawSpec["series"]["shortname"],
        "snapshot_url": rawSpec["release"]["url"] if "release" in rawSpec else None,
        "current_url": rawSpec["nightly"]["url"],
        "title": rawSpec["shortTitle"],
        "description": rawSpec["title"],
        "abstract": None,
        "level": int(rawSpec["seriesVersion"]) if "seriesVersion" in rawSpec and re.match(r"^\d+$", rawSpec["seriesVersion"]) else None,
    }
    return spec

def convertWebrefHeading(heading: RawWebrefHeadingT, specUrl: str) -> RawAnchorT:
    """Convert a heading returned by Webref to the anchor format used in Shepherd"""
    assert heading["id"] is not None
    assert heading["title"] is not None
    assert heading["href"] is not None
    anchor: RawAnchorT = {
        "name": heading["number"] if "number" in heading else heading["id"],
        "type": "heading",
        "for": [],
        "section": True,
        "title": heading["title"],
        "status": "unknown",
        "normative": True,
        "export": "public",
        "linking_text": [heading["title"]],
        "uri": heading["href"].replace(specUrl, ""),
    }
    return anchor

def convertWebrefAnchor(rawAnchor: RawWebrefAnchorT, specUrl: str) -> RawAnchorT:
    """Convert an anchor returned by Webref to the anchor format used in Shepherd"""
    assert rawAnchor["id"] is not None
    assert rawAnchor["type"] is not None
    assert rawAnchor["linkingText"] is not None
    assert rawAnchor["access"] is not None
    assert rawAnchor["href"] is not None
    anchor: RawAnchorT = {
        "name": rawAnchor["id"],
        "type": rawAnchor["type"],
        "for": rawAnchor["for"],
        "section": False,
        "title": rawAnchor["linkingText"][0],
        "status": "unknown",
        "normative": not rawAnchor["informative"],
        "export": rawAnchor["access"] == "public",
        "linking_text": rawAnchor["linkingText"],
        "uri": rawAnchor["href"].replace(specUrl, ""),
    }
    return anchor

def fixupAnchor(anchor: RawAnchorT) -> RawAnchorT:
    """Miscellaneous fixes to the anchors before I start processing"""

    # This one issue was annoying
    if anchor.get("title", None) == "'@import'":
        anchor["title"] = "@import"

    # css3-tables has this a bunch, for some strange reason
    if (anchor.get("uri") or "").startswith("??"):
        anchor["uri"] = t.cast(str, anchor.get("uri"))[2:]

    # If any smart quotes crept in, replace them with ASCII.
    linkingTexts: list[str] = anchor.get("linking_text") or [t.cast(str, anchor.get("title"))]
    for i, text in enumerate(linkingTexts):
        if text is None:
            continue
        if "’" in text or "‘" in text:
            text = re.sub(r"‘|’", "'", text)
            linkingTexts[i] = text
        if "“" in text or "”" in text:
            text = re.sub(r"“|”", '"', text)
            linkingTexts[i] = text
    anchor["linking_text"] = linkingTexts

    # Normalize whitespace to a single space
    def strip(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip())

    anchor["name"] = strip(anchor["name"])
    anchor["type"] = strip(anchor["type"])
    anchor["for"] = [strip(x) for x in anchor.get("for", [])]
    anchor["status"] = strip(anchor["status"])
    anchor["linking_text"] = [strip(x) for x in anchor.get("linking_text", []) if x is not None]
    anchor["uri"] = strip(anchor["uri"])

    return anchor


def addToHeadings(rawAnchor: RawAnchorT, specHeadings: HeadingsT, spec: SpecT) -> None:
    uri = rawAnchor["uri"]
    assert uri is not None
    if rawAnchor["status"] == "snapshot":
        baseUrl = spec["snapshot_url"]
    else:
        baseUrl = spec["current_url"]
    assert baseUrl is not None
    heading: HeadingT = {
        "url": baseUrl + uri,
        "number": rawAnchor["name"] if re.match(r"[\d.]+$", rawAnchor["name"]) else "",
        "text": rawAnchor["title"],
        "spec": spec["title"],
    }
    if uri[0] == "#":
        # Either single-page spec, or link on the top page of a multi-page spec
        fragment = uri
        shorthand = "/" + fragment
    else:
        # Multi-page spec, need to guard against colliding IDs
        if "#" in uri:
            # url to a heading in the page, like "foo.html#bar"
            match = re.match(r"([\w-]+).*?(#.*)", uri)
            if not match:
                m.die(
                    f"Unexpected URI pattern '{uri}' for spec '{spec['vshortname']}'. Please report this to the Bikeshed maintainer.",
                )
                return
            page, fragment = match.groups()
            page = "/" + page
        else:
            # url to a page itself, like "foo.html"
            page, _, _ = uri.partition(".")
            page = "/" + page
            fragment = "#"
        shorthand = page + fragment
    if shorthand not in specHeadings:
        specHeadings[shorthand] = {}
    headingGroup = t.cast("HeadingGroupT", specHeadings[shorthand])
    headingGroup[rawAnchor["status"]] = heading
    assert rawAnchor["status"] is not None
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


def addToAnchors(rawAnchor: RawAnchorT, anchors: AnchorsT, spec: SpecT) -> None:
    if rawAnchor["status"] == "snapshot":
        baseUrl = spec["snapshot_url"]
    else:
        baseUrl = spec["current_url"]
    assert baseUrl is not None
    anchor: AnchorT = {
        "status": rawAnchor["status"],
        "type": rawAnchor["type"],
        "spec": spec["vshortname"],
        "shortname": spec["shortname"],
        "level": int(spec["level"] or "1"),
        "export": rawAnchor.get("export", False),
        "normative": rawAnchor.get("normative", False),
        "url": baseUrl + rawAnchor["uri"],
        "for": rawAnchor.get("for", []),
    }
    for text in rawAnchor["linking_text"]:
        if anchor["type"] in config.lowercaseTypes:
            text = text.lower()
        text = re.sub(r"\s+", " ", text)
        anchors[text].append(anchor)


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
                for e in entries:
                    fh.write(key + "\n")
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
