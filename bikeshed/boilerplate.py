from __future__ import annotations

import copy
import dataclasses
import os
import re
import subprocess
from collections import OrderedDict, defaultdict
from datetime import datetime

from . import conditional, config, dfnpanels, h, retrieve, t
from . import messages as m
from . import refs as r
from .translate import _t

if t.TYPE_CHECKING:
    MetadataT: t.TypeAlias = t.Mapping[str, t.Sequence[MetadataValueT]]
    MetadataValueT: t.TypeAlias = str | t.NodesT | None


def boilerplateFromHtml(doc: t.SpecT, htmlString: str, filename: str) -> t.NodesT:
    htmlString = h.parseText(htmlString, h.ParseConfig.fromSpec(doc, context=filename))
    bp = h.E.div({}, h.parseHTML(htmlString))
    conditional.processConditionals(doc, bp)
    return h.childNodes(bp, clear=True)


def loadBoilerplate(doc: t.SpecT, filename: str, bpname: str | None = None) -> None:
    if bpname is None:
        bpname = filename
    html = retrieve.retrieveBoilerplateFile(doc, filename)
    el = boilerplateFromHtml(doc, html, filename)
    fillWith(bpname, el, doc=doc)


def addBikeshedVersion(doc: t.SpecT) -> None:
    # Adds a <meta> containing the current Bikeshed semver.
    if "generator" not in doc.md.boilerplate:
        return
    try:
        # Check that we're in the bikeshed repo
        origin = subprocess.check_output(
            "git remote -v",
            cwd=config.scriptPath(),
            stderr=subprocess.DEVNULL,
            shell=True,
        ).decode(encoding="utf-8")
        if "bikeshed" not in origin:
            # In a repo, but not bikeshed's;
            # probably pip-installed into an environment's repo or something.
            raise Exception
        # Otherwise, success, this is a -e install,
        # so we're in Bikeshed's repo.
        bikeshedVersion = (
            subprocess.check_output(
                r"git log -1 --format='Bikeshed version %h, updated %cd'",
                cwd=config.scriptPath(),
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            .decode(encoding="utf-8")
            .strip()
        )
    except Exception:
        # Not in Bikeshed's repo, so instead grab from the datafile.
        bikeshedVersion = doc.dataFile.fetch("bikeshed-version.txt", fileType="readonly", str=True).strip()
    h.appendChild(doc.head, h.E.meta({"name": "generator", "content": bikeshedVersion}))


def addCanonicalURL(doc: t.SpecT) -> None:
    # Adds a <link rel=canonical> to the configured canonical url
    if doc.md.canonicalURL:
        h.appendChild(doc.head, h.E.link({"rel": "canonical", "href": doc.md.canonicalURL}))


def addFavicon(doc: t.SpecT) -> None:
    # Adds a <link rel=icon> to the configured favicon url
    if doc.md.favicon:
        h.appendChild(doc.head, h.E.link({"rel": "icon", "href": doc.md.favicon}))


def addSpecVersion(doc: t.SpecT) -> None:
    # Adds a <meta> with the current spec revision, if one was detected
    if "document-revision" not in doc.md.boilerplate:
        return

    if not doc.inputSource.hasDirectory():
        return

    revision = None
    source_dir = doc.inputSource.directory()
    try:
        # Check for a Git repo
        with open(os.devnull, "wb") as fnull:
            revision = (
                subprocess.check_output("git rev-parse HEAD", stderr=fnull, shell=True, cwd=source_dir)
                .decode(encoding="utf-8")
                .strip()
            )
    except subprocess.CalledProcessError:
        try:
            # Check for an Hg repo
            with open(os.devnull, "wb") as fnull:
                revision = (
                    subprocess.check_output(
                        "hg parent --temp='{node}'",
                        stderr=fnull,
                        shell=True,
                        cwd=source_dir,
                    )
                    .decode(encoding="utf-8")
                    .strip()
                )
        except subprocess.CalledProcessError:
            pass
    if revision:
        h.appendChild(doc.head, h.E.meta({"name": "revision", "content": revision}))


def addHeaderFooter(doc: t.SpecT) -> None:
    header = retrieve.retrieveBoilerplateFile(doc, "header") if "header" in doc.md.boilerplate else ""
    footer = retrieve.retrieveBoilerplateFile(doc, "footer") if "footer" in doc.md.boilerplate else ""

    doc.html = "\n".join(
        [
            h.parseText(header, h.ParseConfig.fromSpec(doc, context="header.include")),
            doc.html,
            h.parseText(footer, h.ParseConfig.fromSpec(doc, context="footer.include")),
        ],
    )


def fillWith(tag: str, newElements: t.NodesT, doc: t.SpecT) -> None:
    for el in doc.fillContainers[tag]:
        h.replaceContents(el, newElements)


def getFillContainer(tag: str, doc: t.SpecT, default: bool = False) -> t.ElementT | None:
    """
    Gets the element that should be filled with the stuff corresponding to tag.
    If it returns None, don't generate the section.

    If default=True,
    indicates that this is a "default on" section,
    and will be appended to <body> unless explicitly suppressed.
    Otherwise,
    it'll only be appended if explicitly requested with a data-fill-with attribute.
    """

    # If you've explicitly suppressed that section, don't do anything
    if tag not in doc.md.boilerplate:
        return None

    # If a fill-with is found, fill that
    if doc.fillContainers[tag]:
        return doc.fillContainers[tag][0]

    # Otherwise, append to the end of the document,
    # unless you're in the byos group
    if doc.doctype.group.name == "BYOS":
        return None
    if default:
        return doc.body
    return None


def addLogo(doc: t.SpecT) -> None:
    loadBoilerplate(doc, "logo")


def addCopyright(doc: t.SpecT) -> None:
    loadBoilerplate(doc, "copyright")


def addAbstract(doc: t.SpecT) -> None:
    if not doc.md.noAbstract:
        loadBoilerplate(doc, "abstract")
    else:
        container = getFillContainer("abstract", doc, default=False)
        if container is not None:
            h.removeNode(container)


def addStatusSection(doc: t.SpecT) -> None:
    loadBoilerplate(doc, "status")


def addExpiryNotice(doc: t.SpecT) -> None:
    if doc.md.expires is None:
        return
    if doc.md.date >= doc.md.expires or datetime.utcnow().date() >= doc.md.expires:
        boilerplate = "warning-expired"
    else:
        boilerplate = "warning-expires"
        doc.extraJC.addExpires()
    loadBoilerplate(doc, boilerplate, "warning")
    h.addClass(doc, doc.body, boilerplate)


def addObsoletionNotice(doc: t.SpecT) -> None:
    if doc.md.warning:
        loadBoilerplate(doc, doc.md.warning[0], "warning")


def addAtRisk(doc: t.SpecT) -> None:
    if len(doc.md.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.md.atRisk:
        html += "<li>" + h.parseText(feature, h.ParseConfig.fromSpec(doc, context="At Risk metadata"))
    html += (
        "</ul><p>“At-risk” is a W3C Process term-of-art, and does not necessarily imply that the feature is in danger of being dropped or delayed. "
        + "It means that the WG believes the feature may have difficulty being interoperably implemented in a timely manner, "
        + "and marking it as such allows the WG to drop the feature if necessary when transitioning to the Proposed Rec stage, "
        + "without having to publish a new Candidate Rec without the feature first."
    )
    frag = h.parseHTML(html)
    fillWith("at-risk", frag, doc=doc)


def addStyles(doc: t.SpecT) -> None:
    el = getFillContainer("stylesheet", doc)
    if el is not None:
        el.text = retrieve.retrieveBoilerplateFile(doc, "stylesheet")


def addCustomBoilerplate(doc: t.SpecT) -> None:
    for el in h.findAll("[boilerplate]", doc):
        tag = el.get("boilerplate", "")
        if doc.fillContainers[tag]:
            h.replaceContents(doc.fillContainers[tag][0], el)
            h.removeNode(el)


def removeUnwantedBoilerplate(doc: t.SpecT) -> None:
    for tag, els in doc.fillContainers.items():
        if tag not in doc.md.boilerplate:
            for el in els:
                h.removeNode(el)


def w3cStylesheetInUse(doc: t.SpecT) -> bool:
    return doc.md.prepTR or doc.doctype.group.name == "W3C"


def addBikeshedBoilerplate(doc: t.SpecT) -> None:
    for style in doc.extraJC.getStyles(doc.md.boilerplate):
        container = getFillContainer("style-" + style.name, doc)
        if container is None:
            container = getFillContainer("bs-styles", doc, default=True)
        if container is not None:
            h.appendChild(container, style.toElement(darkMode=doc.md.darkMode))
    for script in doc.extraJC.getScripts(doc.md.boilerplate):
        container = getFillContainer("script-" + script.name, doc)
        if container is None:
            container = getFillContainer("bs-scripts", doc, default=True)
        if container is not None:
            h.appendChild(container, script.toElement())


def addIndexSection(doc: t.SpecT) -> None:
    hasLocalDfns = len(h.findAll(config.dfnElementsSelector, doc)) > 0
    hasExternalDfns = doc.externalRefsUsed.hasRefs()
    if not hasLocalDfns and not hasExternalDfns:
        return

    container = getFillContainer("index", doc=doc, default=True)
    if container is None:
        return
    h.appendChild(container, h.E.h2({"class": "no-num no-ref", "id": h.safeID(doc, "index")}, _t("Index")))

    if hasLocalDfns:
        addIndexOfLocallyDefinedTerms(doc, container)

    if hasExternalDfns:
        addIndexOfExternallyDefinedTerms(doc, container)


def addIndexOfLocallyDefinedTerms(doc: t.SpecT, container: t.ElementT) -> None:
    h.appendChild(
        container,
        h.E.h3(
            {"class": "no-num no-ref", "id": h.safeID(doc, "index-defined-here")},
            _t("Terms defined by this specification"),
        ),
    )

    indexEntries = defaultdict(list)
    for el in h.findAll(config.dfnElementsSelector, doc):
        dfnID = el.get("id")
        dfnType = el.get("data-dfn-type")
        if dfnID is None or dfnType is None:
            continue
        linkTexts = h.linkTextsFromElement(el)
        headingLevel = h.headingLevelOfElement(el) or _t("Unnumbered section")
        if dfnType == "argument":
            # Don't generate index entries for arguments.
            continue
        if el.get("data-dfn-for") is not None:
            disamb = _t("{type} for {forVals}").format(
                type=dfnType,
                forVals=", ".join(config.splitForValues(el.get("data-dfn-for", ""))),
            )
        elif dfnType == "dfn":
            disamb = _t("definition of")
        else:
            disamb = "({})".format(dfnType)

        for linkText in linkTexts:
            entry = IndexTerm(
                url="#" + dfnID,
                label="§\u202f" + headingLevel,
                disambiguator=disamb,
            )
            indexEntries[linkText].append(entry)

    # Now print the indexes
    indexHTML = htmlFromIndexTerms(indexEntries)
    h.appendChild(container, indexHTML, allowEmpty=True)


def disambiguator(ref: r.RefWrapper, types: set[str] | None, specs: list[str] | None) -> str:
    disambInfo = []
    if types is None or len(types) > 1:
        disambInfo.append(ref.type)
    if specs is None or len(specs) > 1:
        disambInfo.append(_t("in {spec}").format(spec=ref.spec))
    if ref.for_:
        disambInfo.append(_t("for {forVals}").format(forVals=", ".join(x.strip() for x in ref.for_)))
    return ", ".join(disambInfo)


def addExplicitIndexes(doc: t.SpecT) -> None:
    # Explicit indexes can be requested for specs with <index spec="example-spec-1"></index>

    for el in h.findAll("index", doc):
        status = el.get("status")
        if status and status not in config.specStatuses:
            m.die(
                f"<index> has unknown value '{status}' for status. Must be {config.englishFromList(config.specStatuses)}.",
                el=el,
            )
            continue

        if el.get("type"):
            elTypes = {x.strip() for x in el.get("type", "").split(",")}
            for elType in elTypes:
                if elType not in config.dfnTypes:
                    m.die(
                        f"Unknown type value '{elType}' on {h.outerHTML(el)}",
                        el=el,
                    )
                    elTypes.remove(elType)
        else:
            elTypes = None

        if el.get("data-link-spec"):
            # Yes, this is dumb. Accidental over-firing of a shortcut attribute. >_<
            specs = sorted({x.strip() for x in el.get("data-link-spec", "").split(",")})
            for s in list(specs):
                if s not in doc.refs.specs:
                    m.die(f"Unknown spec name '{s}' on {h.outerHTML(el)}", el=el)
                    specs.remove(s)
        else:
            specs = None

        if el.get("for"):
            fors = {x.strip() for x in el.get("for", "").split(",")}
        else:
            fors = None

        if el.get("export"):
            exportVal = el.get("export", "").lower().strip()
            if exportVal in ["yes", "y", "true", "on"]:
                export = True
            elif exportVal in ["no", "n", "false", "off"]:
                export = False
            else:
                m.die(
                    f"Unknown export value '{exportVal}' (should be boolish) on {h.outerHTML(el)}",
                    el=el,
                )
                export = None
        else:
            export = None

        # Initial filter of the ref database according to the <index> parameters
        possibleRefs = []
        for ref in doc.refs.queryAllRefs(dedupURLs=False, latestOnly=False, ignoreObsoletes=False):
            ref.text = re.sub(r"\s{2,}", " ", ref.text.strip())
            if export is not None and ref.export != export:
                continue
            if specs is not None and ref.spec not in specs:
                continue
            if elTypes is not None and ref.type not in elTypes:
                continue
            if fors is not None and not (set(ref.for_) & fors):
                continue
            possibleRefs.append(ref)

        # Group entries by linking text,
        # ensuring no duplicate disambiguators.
        refsFromText: t.DefaultDict[str, list[r.RefWrapper]] = defaultdict(list)
        for ref in possibleRefs:
            refDisambiguator = disambiguator(ref, elTypes, specs)
            for i, existingRef in enumerate(refsFromText[ref.text]):
                if disambiguator(existingRef, elTypes, specs) != refDisambiguator:
                    continue
                # Whoops, found an identical entry.
                if existingRef.status != ref.status:
                    if status:
                        if existingRef.status == status:
                            # Existing entry matches stated status, do nothing and don't add it.
                            break
                        if ref.status == status:
                            # New entry matches status, update and don't re-add it.
                            refsFromText[ref.text][i] = ref
                            break
                    else:
                        # Default to preferring current specs
                        if existingRef.status == "current":
                            break
                        if ref.status == "current":
                            refsFromText[ref.text][i] = ref
                            break
                else:
                    # Legit dupes. Shouldn't happen in a good spec, but whatever.
                    pass
            else:
                refsFromText[ref.text].append(ref)

        # Group entries by text/type/for,
        # then filter each group for obsolete/oldversions.
        refsFromTtf: t.DefaultDict[tuple[str, str, str | None], list[r.RefWrapper]] = defaultdict(list)
        for text, entries in refsFromText.items():
            for ref in entries:
                ttf = (text, ref.type, "".join(ref.for_) if ref.for_ else None)
                refsFromTtf[ttf].append(ref)
        filteredRefs: t.DefaultDict[str, list[IndexTerm]] = defaultdict(list)
        for ttf, refs in list(refsFromTtf.items()):
            refs = doc.refs.filterObsoletes(refs)
            refs = r.utils.filterOldVersions(refs)
            if refs:
                filteredRefs[ttf[0]].extend(
                    IndexTerm(url=ref.url, disambiguator=disambiguator(ref, elTypes, specs)) for ref in refs
                )

        h.appendChild(el, htmlFromIndexTerms(filteredRefs), allowEmpty=True)
        el.tag = "div"
        h.removeAttr(el, "export", "for", "spec", "status", "type")


@dataclasses.dataclass
class IndexTerm:
    url: str
    disambiguator: str
    label: str | None = None


def htmlFromIndexTerms(entries: t.Mapping[str, list[IndexTerm]]) -> t.ElementT:
    # entries: dict (preferably OrderedDict, if you want stability) of linkText=>{url, label, disambiguator}
    # label is used for the actual link (normally heading level), disambiguator is phrase to use when there are collisions

    def entryKey(x: tuple[str, t.Any]) -> tuple[str, str, str]:
        return (
            # first group by approximating a human-friendly "nearness" of terms
            re.sub(r"[^a-z0-9]", "", x[0].lower()),
            # then within that, by case-ignoring exact text
            x[0].lower(),
            # and finally uniquely by exact text
            x[0],
        )

    entries = OrderedDict(sorted(entries.items(), key=entryKey))

    topList = h.E.ul({"class": "index"})
    for text, items in entries.items():
        if len(items) == 1:
            item = items[0]
            li = h.appendChild(
                topList,
                h.E.li(
                    h.E.a({"href": item.url}, text),
                    h.E.span(_t(", in "), item.label) if item.label else "",
                ),
            )
        else:
            li = h.appendChild(topList, h.E.li(text))
            ul = h.appendChild(li, h.E.ul())
            for item in sorted(items, key=lambda x: x.disambiguator):
                h.appendChild(
                    ul,
                    h.E.li(
                        h.E.a({"href": item.url}, item.disambiguator),
                        h.E.span(_t(", in "), item.label) if item.label else "",
                    ),
                )
    return topList


def addIndexOfExternallyDefinedTerms(doc: t.SpecT, container: t.ElementT) -> None:
    if not doc.externalRefsUsed.hasRefs():
        return

    def makeEntry(ref: t.RefWrapper, contents: t.NodesT) -> t.ElementT:
        return h.E.span({"id": h.uniqueID("external-term", ref.url, ref.text)}, contents)

    ul = h.E.ul({"class": "index"})

    for specName, specData in doc.externalRefsUsed.sorted():
        # Skip entries that are *solely* a biblio entry.
        if not specData.refs:
            continue

        # ref.spec is always lowercase; if the same string shows up in biblio data,
        # use its casing instead.
        biblioRef = specData.biblio or doc.refs.getBiblioRef(specName, quiet=True)
        if biblioRef:
            printableSpec = biblioRef.linkText
        else:
            printableSpec = specName

        attrs = {
            "data-lt": specName,
            "data-link-type": "biblio",
            "data-biblio-type": "informative",
            "data-okay-to-fail": "true",
        }
        specLi = h.appendChild(
            ul,
            h.E.li(h.E.a(attrs, "[", formatBiblioTerm(printableSpec), "]"), " defines the following terms:"),
        )
        termsUl = h.appendChild(specLi, h.E.ul())
        for _, refGroup in specData.sorted():
            if len(refGroup) == 1:
                ref = refGroup.single()
                entry = makeEntry(ref, ref.displayText)
                h.appendChild(termsUl, h.E.li(entry))
                dfnpanels.addExternalDfnPanel(entry, ref, doc)
            else:
                for forVal, ref in refGroup.sorted():
                    if forVal:
                        entry = makeEntry(ref, [ref.displayText, " ", h.E.small({}, f"({_t('for')} {forVal})")])
                    else:
                        entry = makeEntry(ref, ref.displayText)
                    h.appendChild(termsUl, h.E.li(entry))
                    dfnpanels.addExternalDfnPanel(entry, ref, doc)
    h.appendChild(
        container,
        h.E.h3(
            {"class": "no-num no-ref", "id": h.safeID(doc, "index-defined-elsewhere")},
            _t(
                "Terms defined by reference",
            ),
        ),
        ul,
    )


def addPropertyIndex(doc: t.SpecT) -> None:
    # Extract all the data from the propdef and descdef tables

    if len(h.findAll("table.propdef, table.descdef", doc)) == 0:
        return
    html = getFillContainer("property-index", doc=doc, default=True)
    if html is None:
        return

    h.appendChild(
        html,
        h.E.h2(
            {"class": "no-num no-ref", "id": h.safeID(doc, "property-index")},
            _t("Property Index"),
        ),
    )

    def extractKeyValFromRow(row: t.ElementT, table: t.ElementT) -> tuple[str, str]:
        # Extract the key, minus the trailing :
        result = re.match(r"(.*):", h.textContent(row[0]).strip())
        if result is None:
            m.die(
                f"Propdef row headers must be a word followed by a colon. Got:\n{h.textContent(row[0]).strip()}",
                el=table,
            )
            return "", ""
        key = result.group(1).strip().capitalize()
        # Extract the value from the second cell
        val = h.textContent(row[1]).strip()
        return key, val

    # Extract propdef info
    props = []
    for table in h.findAll("table.propdef", doc):
        prop = {}
        names = []
        for row in h.findAll("tr", table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [h.textContent(x) for x in h.findAll("dfn", row[1])]
            else:
                prop[key] = val
        for name in names:
            tempProp = prop.copy()
            tempProp["Name"] = name
            props.append(tempProp)
    props.sort(key=lambda x: x["Name"])
    # Extract descdef info
    atRules = defaultdict(list)
    for table in h.findAll("table.descdef", doc):
        desc = {}
        names = []
        atRule = ""
        for row in h.findAll("tr", table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [h.textContent(x) for x in h.findAll("dfn", row[1])]
            elif key == "For":
                atRule = val
            else:
                desc[key] = val
        for name in names:
            tempDesc = desc.copy()
            tempDesc["Name"] = name
            atRules[atRule].append(tempDesc)
    for descs in atRules.values():
        descs.sort(key=lambda x: x["Name"])

    def createRow(prop: dict[str, str], linkType: str, for_: str | None = None) -> t.ElementT:
        attrs = {"data-link-type": linkType}
        if for_:
            attrs["data-link-for"] = for_
        return h.E.tr(
            h.E.th({"scope": "row"}, h.E.a(attrs, prop["Name"])),
            *[h.E.td(prop.get(column, "")) for column in columns[1:]],
        )

    if len(props) > 0:
        # Set up the initial table columns for properties
        columns = ["Name", "Value", "Initial", "Applies to", "Inherited", "Percentages"]
        # Add any additional keys used in the document.
        allKeys = set()
        for prop in props:
            allKeys |= set(prop.keys())
        columns.extend(sorted(allKeys - set(columns)))
        # Create the table

        def formatColumnName(name: str) -> str:
            if name == "Inherited":
                return "Inh."
            if name == "Percentages":
                return "%ages"
            if name == "Animatable":
                return "Ani\xadmat\xadable"
            if name == "Animation type":
                return "Anim\xadation type"
            if name == "Computed value":
                return "Com\xadputed value"
            return name

        h.appendChild(
            html,
            h.E.div(
                {"class": "big-element-wrapper"},
                h.E.table(
                    {"class": "index"},
                    h.E.thead(h.E.tr(*[h.E.th({"scope": "col"}, formatColumnName(column)) for column in columns])),
                    h.E.tbody(*[createRow(prop, "property") for prop in props]),
                ),
            ),
        )
    else:
        h.appendChild(html, h.E.p("No properties defined."))

    if len(atRules) > 0:
        atRuleNames = sorted(atRules.keys())
        for atRuleName in atRuleNames:
            descs = atRules[atRuleName]
            if atRuleName == "":
                atRuleName = "Miscellaneous"
            columns = ["Name", "Value", "Initial"]
            allKeys = set()
            for desc in descs:
                allKeys |= set(desc.keys())
            columns.extend(sorted(allKeys - set(columns)))
            id = config.simplifyText(atRuleName) + "-descriptor-table"
            if atRuleName:
                h.appendChild(
                    html,
                    h.E.h3(
                        {"class": "no-num no-ref", "id": h.safeID(doc, id)},
                        h.E.a({"data-link-type": "at-rule"}, atRuleName),
                        " Descriptors",
                    ),
                )
            else:
                h.appendChild(
                    html,
                    h.E.h3(
                        {"class": "no-num no-ref", "id": h.safeID(doc, id)},
                        "Miscellaneous Descriptors",
                    ),
                )
            h.appendChild(
                html,
                h.E.div(
                    {"class": "big-element-wrapper"},
                    h.E.table(
                        {"class": "index"},
                        h.E.thead(h.E.tr(*[h.E.th({"scope": "col"}, column) for column in columns])),
                        h.E.tbody(*[createRow(desc, "descriptor", for_=atRuleName) for desc in descs]),
                    ),
                ),
            )


def addIDLSection(doc: t.SpecT) -> None:
    idlBlocks = [x for x in h.findAll("pre.idl, xmp.idl", doc) if h.isNormative(doc, x)]
    if len(idlBlocks) == 0:
        return
    html = getFillContainer("idl-index", doc=doc, default=True)
    if html is None:
        return

    h.appendChild(
        html,
        h.E.h2({"class": "no-num no-ref", "id": h.safeID(doc, "idl-index")}, _t("IDL Index")),
    )

    container = h.appendChild(html, h.E.pre({"class": "idl"}))
    for block in idlBlocks:
        if h.hasClass(doc, block, "extract"):
            continue
        blockCopy = copy.deepcopy(block)
        h.appendContents(container, blockCopy)
        h.appendChild(container, "\n")
    for el in h.findAll("[id]", container):
        if el.tag == "dfn":
            el.tag = "a"
            el.set("href", "#" + el.get("id", ""))
        del el.attrib["id"]
    h.addClass(doc, container, "highlight")


def addTOCSection(doc: t.SpecT) -> None:
    toc = getFillContainer("table-of-contents", doc=doc, default=False)
    if toc is None:
        return
    h.appendChild(
        toc,
        h.E.h2(
            {"class": "no-num no-toc no-ref", "id": h.safeID(doc, "contents")},
            _t("Table of Contents"),
        ),
    )

    # containers[n] holds the current <ol> for inserting each heading's <li> into.
    # containers[1] is initialized with something arbitrary
    # (anything non-int and non-None will do, to avoid tripping error-handling),
    # and containers[2] is initialized with the top-level <ol>
    # (because <h2>s and below are all that should show up in your doc)
    # and whenever we hit a heading of level N,
    # we append an <li> for it to containers[N],
    # and create a new <ol> at containers[N+1] to hold its child sections
    # (nested inside the <li>).
    # We'll clean up empty subsections at the end.
    # There's a containers[0] just to make the levels map directly to indexes,
    # and a containers[7] just to avoid IndexErrors when dealing with <h6>s.
    # Aside from the above initialization,
    # containers[N] is initialized to an int,
    # arbitrarily set to the index just for readability.
    # If a heading specifies it shouldn't be in the ToC,
    # it sets containers[N+1] to None
    # to indicate that no children should go there.
    previousLevel = 1
    containers: list[t.ElementT | None] = [None, None, None, None, None, None, None, None]
    containers[1] = toc
    containers[2] = h.appendChild(toc, h.E.ol({"class": "toc", "role": "directory"}))
    for header in h.findAll("h2, h3, h4, h5, h6", doc):
        level = int(header.tag[-1])
        container = containers[level]
        if isinstance(container, int):
            # Saw a low-level heading without first seeing a higher heading.
            m.die(
                f"Saw an <h{level}> without seeing an <h{level-1}> first. Please order your headings properly.\n{h.outerHTML(header)}",
                el=header,
            )
            return
        if level > previousLevel + 1:
            # Jumping two levels is a no-no.
            m.die(
                f"Heading level jumps more than one level, from h{previousLevel} to h{level}:\n{h.outerHTML(header)}",
                el=header,
            )
            return

        addToTOC = True
        if h.hasClass(doc, header, "no-toc"):
            # Hit a no-toc, suppress the entire section.
            addToTOC = False
        elif container is None:
            addToTOC = False
        elif (level - 1) > (doc.md.maxToCDepth or float("inf")):
            addToTOC = False

        if addToTOC:
            assert container is not None
            li = h.appendChild(
                container,
                h.E.li(
                    h.E.a(
                        {"href": "#" + header.get("id", "")},
                        h.E.span({"class": "secno"}, header.get("data-level", "")),
                        " ",
                        copy.deepcopy(h.find(".content", header)),
                    ),
                ),
            )
            containers[level + 1] = h.appendChild(li, h.E.ol({"class": "toc"}))
        else:
            containers[level + 1] = None
        previousLevel = level

    container = t.cast("t.ElementT", containers[1])
    for el in h.findAll(".content a, .content dfn", container):
        el.tag = "span"
        if "href" in el.attrib:
            del el.attrib["href"]
    for el in h.findAll(".content [id]", container):
        del el.attrib["id"]
    for el in h.findAll("ol:empty", container):
        h.removeNode(el)


def addSpecMetadataSection(doc: t.SpecT) -> None:
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

    def printTranslation(tr: dict[str, str]) -> t.ElementT | None:
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

    def printPreviousVersion(v: dict[str, str]) -> t.ElementT | None:
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

    md: OrderedDict[str, list[MetadataValueT]] = OrderedDict()
    mac = doc.macros
    if "version" in mac:
        md.setdefault("This version", []).append(h.E.a({"href": mac["version"], "class": "u-url"}, mac["version"]))
    if doc.md.TR:
        md.setdefault("Latest published version", []).append(h.E.a({"href": doc.md.TR}, doc.md.TR))
    if doc.md.ED and "TR" in doc.doctype.status.requires:
        md.setdefault("Editor's Draft", []).append(h.E.a({"href": doc.md.ED}, doc.md.ED))
    if doc.md.previousVersions:
        md["Previous Versions"] = [printPreviousVersion(ver) for ver in doc.md.previousVersions]
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
        md["Editor"] = list(map(printEditor, doc.md.editors))
    if doc.md.previousEditors:
        md["Former Editor"] = list(map(printEditor, doc.md.previousEditors))
    if doc.md.translations:
        md["Translations"] = list(map(printTranslation, doc.md.translations))
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
            doc.body,
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
                htmlText = h.parseText(v, h.ParseConfig.fromSpec(doc, context=f"!{k} metadata"))
                parsed.append(h.parseHTML(htmlText))
            else:
                parsed.append(v)
        if k in md:
            md[k].extend(parsed)
        else:
            otherMd[k] = t.cast("list[t.NodesT|None]", parsed)

    el = h.E.div(htmlFromMd(md, otherMd, doc))

    fillWith("spec-metadata", el, doc=doc)


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

    dl = h.E.dl()
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


def addReferencesSection(doc: t.SpecT) -> None:
    if not doc.normativeRefs and not doc.informativeRefs:
        return
    container = getFillContainer("references", doc=doc, default=True)
    if container is None:
        return

    h.appendChild(
        container,
        h.E.h2({"class": "no-num no-ref", "id": h.safeID(doc, "references")}, _t("References")),
    )

    normRefs = sorted(doc.normativeRefs.values(), key=lambda r: r.linkText.lower())
    normRefKeys = {r.linkText.lower() for r in doc.normativeRefs.values()}
    if len(normRefs) > 0:
        dl = h.appendChild(
            container,
            h.E.h3(
                {"class": "no-num no-ref", "id": h.safeID(doc, "normative")},
                _t("Normative References"),
            ),
            h.E.dl(),
        )
        for ref in normRefs:
            id = "biblio-" + config.simplifyText(ref.linkText)
            h.appendChild(
                dl,
                h.E.dt(
                    {"id": h.safeID(doc, id), "data-no-self-link": ""},
                    "[" + formatBiblioTerm(ref.linkText) + "]",
                ),
            )
            h.appendChild(dl, h.E.dd(*ref.toHTML()))

    informRefs = [
        x
        for x in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText.lower())
        if x.linkText.lower() not in normRefKeys
    ]
    if len(informRefs) > 0:
        dl = h.appendChild(
            container,
            h.E.h3(
                {"class": "no-num no-ref", "id": h.safeID(doc, "informative")},
                _t("Informative References"),
            ),
            h.E.dl(),
        )
        for ref in informRefs:
            id = "biblio-" + config.simplifyText(ref.linkText)
            h.appendChild(
                dl,
                h.E.dt(
                    {"id": h.safeID(doc, id), "data-no-self-link": ""},
                    "[" + formatBiblioTerm(ref.linkText) + "]",
                ),
            )
            h.appendChild(dl, h.E.dd(*ref.toHTML()))


def addIssuesSection(doc: t.SpecT) -> None:
    issues = h.findAll(".issue", doc)
    if len(issues) == 0:
        return
    container = getFillContainer("issues-index", doc=doc, default=True)
    if container is None:
        return

    h.appendChild(
        container,
        h.E.h2(
            {"class": "no-num no-ref", "id": h.safeID(doc, "issues-index")},
            _t("Issues Index"),
        ),
    )
    container = h.appendChild(container, h.E.div({"style": "counter-reset:issue"}))
    for issue in issues:
        el = copy.deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre", "xmp"):
            el.tag = "div"
        h.appendChild(container, el)
        h.appendChild(
            el,
            " ",
            h.E.a({"href": "#" + issue.get("id", ""), "class": "issue-return", "title": _t("Jump to section")}, "↵"),
        )
    for idel in h.findAll("[id]", container):
        del idel.attrib["id"]
    for dfnel in h.findAll(config.dfnElementsSelector, container):
        dfnel.tag = "span"


def formatBiblioTerm(linkText: str) -> str:
    """
    If the term is all uppercase, leave it like that.
    If it's all lowercase, uppercase it.
    If it's mixed case, leave it like that.
    """
    if linkText.islower():
        return linkText.upper()
    return linkText


def addDarkmodeIndicators(doc: t.SpecT) -> None:
    # Unless otherwise indicated, Bikeshed docs are assumed
    # to be darkmode-aware.
    if not doc.md.darkMode:
        return

    # If a boilerplate already contains a color-scheme,
    # assume they know what they're doing.
    # Otherwise, add the color-scheme meta to indicate darkmode-ness.
    existingColorScheme = h.find('meta[name="color-scheme"]', doc)
    if existingColorScheme is not None:
        return
    h.appendChild(
        doc.head,
        h.E.meta({"name": "color-scheme", "content": "dark light"}),
    )

    # Specs using the Bikeshed stylesheet will get darkmode colors
    # automatically, but W3C specs don't. Instead, auto-add their
    # darkmode styles.
    w3cStylesheet = h.find('link[href^="https://www.w3.org/StyleSheets/TR"]', doc)
    if w3cStylesheet is not None:
        h.appendChild(
            doc.head,
            h.E.link(
                {
                    "rel": "stylesheet",
                    "href": "https://www.w3.org/StyleSheets/TR/2021/dark.css",
                    "type": "text/css",
                    "media": "(prefers-color-scheme: dark)",
                },
            ),
        )
