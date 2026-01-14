from __future__ import annotations

from collections import OrderedDict

from .. import h, t
from .. import messages as m
from ..translate import _t
from . import main

if t.TYPE_CHECKING:
    MetadataValueT: t.TypeAlias = str | t.NodesT | None
    MetadataT: t.TypeAlias = t.Mapping[str, t.Sequence[MetadataValueT]]


def addSpecMetadataSection(doc: t.SpecT, body: t.ElementT) -> None:
    md: OrderedDict[str, list[MetadataValueT]] = OrderedDict()
    mac = doc.macros
    if "version" in mac:
        md.setdefault("This version", []).append(h.E.a({"href": mac["version"], "class": "u-url"}, mac["version"]))
    if doc.md.TR:
        md.setdefault("Latest published version", []).append(h.E.a({"href": doc.md.TR}, doc.md.TR))
    if doc.md.ED and "TR" in doc.doctype.status.requires:
        md.setdefault("Editor's Draft", []).append(h.E.a({"href": doc.md.ED}, doc.md.ED))
    if doc.md.previousVersions:
        md["Previous Versions"] = [printPreviousVersion(doc, ver) for ver in doc.md.previousVersions]
    if "history" in mac:
        md["History"] = [h.E.a({"href": mac["history"], "class": "u-url"}, mac["history"])]
    else:
        if doc.md.versionHistory:
            md["Version History"] = [h.E.a({"href": vh}, vh) for vh in doc.md.versionHistory]
    if doc.md.mailingList:
        span = h.E.span(
            h.E.a(
                {
                    "href": "mailto:"
                    + doc.md.mailingList
                    + "?subject=%5B"
                    + mac["shortname"]
                    + "%5D%20YOUR%20TOPIC%20HERE",
                },
                doc.md.mailingList,
            ),
            " with subject line “",
            h.E.kbd("[", mac["shortname"], "] ", h.E.i({"lt": ""}, "… message topic …")),
            "”",
        )
        if doc.md.mailingListArchives:
            h.appendChild(
                span,
                " (",
                h.E.a(
                    {"rel": "discussion", "href": doc.md.mailingListArchives},
                    "archives",
                ),
                ")",
            )
        md.setdefault("Feedback", []).append(span)
    if doc.md.implementationReport is not None:
        md.setdefault("Implementation Report", []).append(
            h.E.a({"href": doc.md.implementationReport}, doc.md.implementationReport),
        )
    if doc.md.testSuite is not None:
        md.setdefault("Test Suite", []).append(h.E.a({"href": doc.md.testSuite}, doc.md.testSuite))
    if doc.md.issues:
        if doc.md.TR:
            md.setdefault("Feedback", []).extend([h.E.a({"href": href}, text) for text, href in doc.md.issues])
        else:
            md["Issue Tracking"] = [h.E.a({"href": href}, text) for text, href in doc.md.issues]
    if doc.md.editors:
        md["Editor"] = [printEditor(x) for x in doc.md.editors]
    if doc.md.previousEditors:
        md["Former Editor"] = [printEditor(x) for x in doc.md.previousEditors]
    if doc.md.translations:
        md["Translations"] = [printTranslation(doc, x) for x in doc.md.translations]
    if doc.md.audience:
        md["Audience"] = [", ".join(doc.md.audience)]
    if doc.md.toggleDiffs:
        md["Toggle Diffs"] = [
            h.E.label(
                {"for": h.safeID(doc, "hidedel"), "id": h.safeID(doc, "hidedel-label")},
                "Hide deleted text",
            ),
        ]
        h.prependChild(
            body,
            h.E.input(
                {
                    "type": "checkbox",
                    "id": h.safeID(doc, "hidedel"),
                    "style": "display:none",
                },
            ),
        )
        doc.extraJC.addHidedel()

    # Merge "custom" metadata into non-custom, when they match up
    # and upgrade html-text values into real elements
    otherMd: OrderedDict[str, list[MetadataValueT]] = OrderedDict()
    for k, vs in doc.md.otherMetadata.items():
        parsed: list[t.NodesT] = []
        for v in vs:
            if isinstance(v, str):
                if v == "":
                    continue
                htmlText = h.parseText(
                    v,
                    h.ParseConfig.fromSpec(doc, context=f"!{k} metadata"),
                    context=f"!{k} metadata",
                )
                parsed.append(h.parseHTML(htmlText))
            else:
                parsed.append(v)
        if k in md:
            md[k].extend(parsed)
        else:
            otherMd[k] = t.cast("list[t.NodesT|None]", parsed)

    el = [htmlFromMd(md, otherMd, doc)]

    main.fillWith("spec-metadata", el, doc=doc, tree=body)


def printEditor(editor: dict[str, str | None]) -> t.ElementT | None:
    dd = h.E.dd({"class": "editor p-author h-card vcard"})
    if editor["w3cid"]:
        dd.attrib["data-editor-id"] = editor["w3cid"]
    if editor["link"]:
        h.appendChild(
            dd,
            h.E.a(
                {"class": "p-name fn u-url url", "href": editor["link"]},
                editor["name"],
            ),
        )
    elif editor["email"]:
        h.appendChild(
            dd,
            h.E.a(
                {
                    "class": "p-name fn u-email email",
                    "href": "mailto:" + editor["email"],
                },
                editor["name"],
            ),
        )
    else:
        h.appendChild(dd, h.E.span({"class": "p-name fn"}, editor["name"]))
    if editor["org"]:
        if editor["orglink"]:
            el = h.E.a({"class": "p-org org", "href": editor["orglink"]}, editor["org"])
        else:
            el = h.E.span({"class": "p-org org"}, editor["org"])
        h.appendChild(dd, " (", el, ")")
    if editor["email"] and editor["link"]:
        h.appendChild(
            dd,
            " ",
            h.E.a(
                {"class": "u-email email", "href": "mailto:" + editor["email"]},
                editor["email"],
            ),
        )
    return dd


def printTranslation(doc: t.SpecT, tr: dict[str, str]) -> t.ElementT | None:
    lang = tr["lang-code"]
    # canonicalize the lang-code structure
    lang = lang.lower().replace("_", "-")
    name = tr["name"]
    nativeName = tr["native-name"]
    url = tr["url"]
    missingInfo = False
    if name is None:
        if lang in doc.languages:
            name = doc.languages[lang].name
        else:
            missingInfo = True
    if nativeName is None:
        if lang in doc.languages:
            nativeName = doc.languages[lang].nativeName
        else:
            missingInfo = True
    if missingInfo:
        m.warn(
            f"Bikeshed doesn't have all the translation info for '{lang}'. Please add to bikeshed/spec-data/readonly/languages.json and submit a PR!",
        )
    if nativeName:
        return h.E.span(
            {"title": name or lang},
            h.E.a(
                {"href": url, "hreflang": lang, "rel": "alternate", "lang": lang},
                nativeName,
            ),
        )
    if name:
        return h.E.a({"href": url, "hreflang": lang, "rel": "alternate", "title": lang}, name)
    return h.E.a({"href": url, "hreflang": lang, "rel": "alternate"}, lang)


def printPreviousVersion(doc: t.SpecT, v: dict[str, str]) -> t.ElementT | None:
    if v["type"] == "url":
        return h.E.a({"href": v["value"], "rel": "prev"}, v["value"])
    # Otherwise, generate an implicit line from the latest known
    key: str
    if v["type"] == "from-biblio":
        key = v["value"]
    elif v["type"] == "from-biblio-implicit":  # "from-biblio-implicit"
        if doc.md.vshortname is None:
            return None
        key = doc.md.vshortname
    dated = doc.refs.getLatestBiblioRef(key)
    if not dated:
        m.die(
            f"While trying to generate a Previous Version line, couldn't find a dated biblio reference for {key}.",
        )
        return None
    return h.E.a({"href": dated.url, "rel": "prev"}, dated.url)


def createMdEntry(key: str, dirtyVals: t.Sequence[MetadataValueT], doc: t.SpecT) -> t.NodesT:
    # Turns a metadata key/vals pair
    # into a list of dt/dd elements.

    vals: list[t.NodesT] = [x for x in dirtyVals if x is not None]
    if not vals:
        return []
    # Convert the canonical key to a display version
    if key == "Editor":
        displayKey = doc.md.editorTerm["singular"]
    elif key == "Former Editor":
        displayKey = "Former " + doc.md.editorTerm["singular"]
    else:
        displayKey = key
    # Pluralize appropriate words
    pluralization = {
        "Previous Version": "Previous Versions",
        "Test Suite": "Test Suites",
        doc.md.editorTerm["singular"]: doc.md.editorTerm["plural"],
        "Former " + doc.md.editorTerm["singular"]: "Former " + doc.md.editorTerm["plural"],
    }
    if len(vals) > 1 and displayKey in pluralization:
        displayKey = pluralization[displayKey]
    displayKey = _t(displayKey)
    # Handle some custom <dt> structures
    if key in ("Editor", "Former Editor"):
        ret = [h.E.dt({"class": "editor"}, displayKey, ":")]
    elif key == "Translations":
        ret = [h.E.dt(displayKey, " ", h.E.small(_t("(non-normative)")), ":")]
    else:
        ret = [h.E.dt(displayKey, ":")]
    # Add all the values, wrapping in a <dd> if necessary.
    for val in vals:
        if h.isElement(val) and h.tagName(val) == "dd":
            ret.append(val)
        else:
            ret.append(h.E.dd({}, val))
    return ret


def htmlFromMd(md: MetadataT, otherMd: MetadataT, doc: t.SpecT) -> t.ElementT:
    # Turns canonical and "other" metadata
    # into a <dl>, per Metadata Order.

    dl = h.E.dl({"bs-line-number": "[auto-generated spec-metadata block]"})
    for key in doc.md.metadataOrder:
        if key == "*":
            # Do all the non-explicit non-custom keys
            for k, vs in md.items():
                if k in doc.md.metadataOrder:
                    # Handled explicitly, don't put in the * spot
                    continue
                if k not in doc.md.metadataInclude:
                    # Explicitly excluded
                    continue
                h.appendChild(dl, *createMdEntry(k, vs, doc), allowEmpty=True)
        elif key == "!*":
            # Do all the non-explicit custom keys
            for k, vs in otherMd.items():
                if k in doc.md.metadataOrder:
                    continue
                if k not in doc.md.metadataInclude:
                    continue
                h.appendChild(dl, *createMdEntry(k, vs, doc), allowEmpty=True)
        elif key not in doc.md.metadataInclude:
            # Key explicitly excluded
            continue
        elif key in md:
            h.appendChild(dl, *createMdEntry(key, md[key], doc), allowEmpty=True)
        elif key in otherMd:
            h.appendChild(dl, *createMdEntry(key, otherMd[key], doc), allowEmpty=True)
    return dl
