from __future__ import annotations

import json
import os
import re
from collections import defaultdict

import certifi
import tenacity
from json_home_client import Client as APIClient

from .. import config, messages as m, t

if t.TYPE_CHECKING:
    AnchorT: t.TypeAlias = dict[str, str | None]
    AnchorsT: t.TypeAlias = defaultdict[str, list[AnchorT]]
    HeadingT: t.TypeAlias = dict[str, dict[str, str]]
    HeadingsT: t.TypeAlias = defaultdict[str, HeadingT]
    RawSpecT: t.TypeAlias = dict[str, str | None]
    SpecT: t.TypeAlias = dict[str, str | None]
    SpecsT: t.TypeAlias = dict[str|None, SpecT]
    MethodsT: t.TypeAlias = defaultdict[str, dict[str, t.Any]]
    ForsT: t.TypeAlias = defaultdict[str, set[str]]


def progressMessager(index: int, total: int) -> t.Callable[[], None]:
    return lambda: m.say(f"Downloading data for spec {index}/{total}...")


def update(path: str, dryRun: bool = False) -> set[str] | None:
    m.say("Downloading anchor data...")
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
    headings: HeadingsT = defaultdict(dict)
    lastMsgTime: float = 0
    for i, rawSpec in enumerate(rawSpecData.values(), 1):
        lastMsgTime = config.doEvery(
            s=5,
            lastTime=lastMsgTime,
            action=progressMessager(i, len(rawSpecData)),
        )
        rawSpec = dataFromApi(shepherd, "specifications", draft=True, anchors=True, spec=rawSpec["name"])
        spec = genSpec(rawSpec)
        specs[spec["vshortname"]] = spec
        specHeadings = headings[spec["vshortname"]]

        def setStatus(obj: AnchorT, status: str) -> AnchorT:
            obj["status"] = status
            return obj

        rawAnchorData = [setStatus(x, "snapshot") for x in linearizeAnchorTree(rawSpec.get("anchors", []))] + [
            setStatus(x, "current") for x in linearizeAnchorTree(rawSpec.get("draft_anchors", []))
        ]
        for rawAnchor in rawAnchorData:
            rawAnchor = fixupAnchor(rawAnchor)
            linkingTexts = rawAnchor["linking_text"]
            assert linkingTexts is not None
            if linkingTexts[0] is None:
                # Happens if it had no linking text at all originally
                continue
            if len(linkingTexts) == 1 and linkingTexts[0].strip() == "":
                # Happens if it was marked with an empty lt and Shepherd still picked it up
                continue
            if "section" in rawAnchor and rawAnchor["section"] is True:
                addToHeadings(rawAnchor, specHeadings, spec=spec)
            if rawAnchor["type"] not in ["heading"]:
                addToAnchors(rawAnchor, anchors, spec=spec)

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
    return data


def linearizeAnchorTree(multiTree: list, list: list[dict[str, t.Any]] = None) -> list[AnchorT]:
    if list is None:
        list = []
    # Call with multiTree being a list of trees
    for item in multiTree:
        if item["type"] in config.dfnTypes.union(["dfn", "heading"]):
            list.append(item)
        if item.get("children"):
            linearizeAnchorTree(item["children"], list)
            del item["children"]
    return list


def genSpec(rawSpec: RawSpecT) -> SpecT:
    spec = {
        "vshortname": rawSpec["name"],
        "shortname": rawSpec.get("short_name"),
        "snapshot_url": rawSpec.get("base_uri"),
        "current_url": rawSpec.get("draft_uri"),
        "title": rawSpec.get("title"),
        "description": rawSpec.get("description"),
        "work_status": rawSpec.get("work_status"),
        "working_group": rawSpec.get("working_group"),
        "domain": rawSpec.get("domain"),
        "status": rawSpec.get("status"),
        "abstract": rawSpec.get("abstract"),
    }
    vShortname = spec["vshortname"]
    assert vShortname is not None
    if spec["shortname"] is not None and vShortname.startswith(spec["shortname"]):
        # S = "foo", V = "foo-3"
        # Strip the prefix
        level = vShortname[len(spec["shortname"]) :]
        if level.startswith("-"):
            level = level[1:]
        if level.isdigit():
            spec["level"] = str(int(level))
        else:
            spec["level"] = "1"
    elif spec["shortname"] is None and re.match(r"(.*)-(\d+)", vShortname):
        # S = None, V = "foo-3"
        match = t.cast(re.Match, re.match(r"(.*)-(\d+)", vShortname))
        spec["shortname"] = match.group(1)
        spec["level"] = str(int(match.group(2)))
    else:
        spec["shortname"] = vShortname
        spec["level"] = "1"
    return spec


def fixupAnchor(anchor: AnchorT) -> AnchorT:
    """Miscellaneous fixes to the anchors before I start processing"""

    # This one issue was annoying
    if anchor.get("title", None) == "'@import'":
        anchor["title"] = "@import"

    # css3-tables has this a bunch, for some strange reason
    if (anchor.get("uri") or "").startswith("??"):
        anchor["uri"] = t.cast(str, anchor.get("uri"))[2:]

    # If any smart quotes crept in, replace them with ASCII.
    linkingTexts: list[str | None] = t.cast("list[str|None]", anchor.get("linking_text")) or [anchor.get("title")]
    for i, text in enumerate(linkingTexts):
        if text is None:
            continue
        if "’" in text or "‘" in text:
            text = re.sub(r"‘|’", "'", text)
            linkingTexts[i] = text
        if "“" in text or "”" in text:
            text = re.sub(r"“|”", '"', text)
            linkingTexts[i] = text
    # FIXME: AnchorT is wrong, it can have some list values
    anchor["linking_text"] = t.cast(str, linkingTexts)

    # Normalize whitespace to a single space
    for k, v in list(anchor.items()):
        if isinstance(v, str):
            anchor[k] = re.sub(r"\s+", " ", v.strip())
        elif isinstance(v, list):
            for k1, v1 in enumerate(v):
                if isinstance(v1, str):
                    anchor[k][k1] = re.sub(r"\s+", " ", v1.strip())
    return anchor


def addToHeadings(rawAnchor: AnchorT, specHeadings: HeadingT, spec: SpecT) -> None:
    uri = rawAnchor["uri"]
    assert uri is not None
    baseUrl = spec["{}_url".format(rawAnchor["status"])]
    assert baseUrl is not None
    heading = {
        "url": baseUrl + uri,
        "number": rawAnchor["name"] if re.match(r"[\d.]+$", rawAnchor["name"] or "") else "",
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
    specHeadings[shorthand][rawAnchor["status"]] = heading
    if fragment not in specHeadings:
        specHeadings[fragment] = []
    if shorthand not in specHeadings[fragment]:
        specHeadings[fragment].append(shorthand)


def cleanSpecHeadings(headings: HeadingsT) -> None:
    """Headings data was purposely verbose, assuming collisions even when there wasn't one.
    Want to keep the collision data for multi-page, so I can tell when you request a non-existent page,
    but need to collapse away the collision stuff for single-page."""
    for specHeadings in headings.values():
        for k, v in list(specHeadings.items()):
            if k[0] == "#" and len(v) == 1 and v[0][0:2] == "/#":
                # No collision, and this is either a single-page spec or a non-colliding front-page link
                # Go ahead and collapse them.
                specHeadings[k] = specHeadings[v[0]]
                del specHeadings[v[0]]


def addToAnchors(rawAnchor: AnchorT, anchors: AnchorsT, spec: SpecT) -> None:
    anchor = {
        "status": rawAnchor["status"],
        "type": rawAnchor["type"],
        "spec": spec["vshortname"],
        "shortname": spec["shortname"],
        "level": int(spec["level"]),
        "export": rawAnchor.get("export", False),
        "normative": rawAnchor.get("normative", False),
        "url": spec["{}_url".format(rawAnchor["status"])] + rawAnchor["uri"],
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

    fors = defaultdict(set)
    for key, anchors_ in anchors.items():
        for anchor in anchors_:
            for for_ in anchor["for"]:
                if for_ == "":
                    continue
                fors[for_].add(key)
            if not anchor["for"]:
                fors["/"].add(key)
    for key, val in list(fors.items()):
        fors[key] = sorted(val)
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
    groupedEntries = defaultdict(dict)
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
