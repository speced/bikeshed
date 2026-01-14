from __future__ import annotations

import copy
import dataclasses
import re
from collections import OrderedDict, defaultdict

from .. import config, dfnpanels, h, t
from .. import messages as m
from .. import refs as r
from ..translate import _t
from . import main


@dataclasses.dataclass
class IndexTerm:
    url: str
    disambiguator: str
    label: str | None = None


def addIndexSection(doc: t.SpecT, body: t.ElementT) -> None:
    hasLocalDfns = len(h.collectDfns(body)) > 0
    hasExternalDfns = doc.externalRefsUsed.hasRefs()
    if not hasLocalDfns and not hasExternalDfns:
        return

    container = main.getFillContainer("index", doc=doc, tree=body, default=body)
    if container is None:
        return
    h.appendChild(container, h.E.h2({"class": "no-num no-ref", "id": h.safeID(doc, "index")}, _t("Index")))

    if hasLocalDfns:
        addIndexOfLocallyDefinedTerms(doc, container)

    if hasExternalDfns:
        addIndexOfExternallyDefinedTerms(doc, container)


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


def addIndexOfLocallyDefinedTerms(doc: t.SpecT, container: t.ElementT) -> None:
    h.appendChild(
        container,
        h.E.h3(
            {"class": "no-num no-ref", "id": h.safeID(doc, "index-defined-here")},
            _t("Terms defined by this specification"),
        ),
    )

    indexEntries = defaultdict(list)
    for el in h.collectDfns(doc.body):
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


def addExplicitIndexes(doc: t.SpecT, body: t.ElementT) -> None:
    # Explicit indexes can be requested for specs with <index spec="example-spec-1"></index>

    for el in h.findAll("index", body):
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


def addPropertyIndex(doc: t.SpecT, body: t.ElementT) -> None:
    # Extract all the data from the propdef and descdef tables

    if len(h.findAll("table.propdef, table.descdef", body)) == 0:
        return
    container = main.getFillContainer("property-index", doc=doc, tree=body, default=body)
    if container is None:
        return

    h.appendChild(
        container,
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
    for table in h.findAll("table.propdef", body):
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
    for table in h.findAll("table.descdef", body):
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
            container,
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
        h.appendChild(container, h.E.p("No properties defined."))

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
                    container,
                    h.E.h3(
                        {"class": "no-num no-ref", "id": h.safeID(doc, id)},
                        h.E.a({"data-link-type": "at-rule"}, atRuleName),
                        " Descriptors",
                    ),
                )
            else:
                h.appendChild(
                    container,
                    h.E.h3(
                        {"class": "no-num no-ref", "id": h.safeID(doc, id)},
                        "Miscellaneous Descriptors",
                    ),
                )
            h.appendChild(
                container,
                h.E.div(
                    {"class": "big-element-wrapper"},
                    h.E.table(
                        {"class": "index"},
                        h.E.thead(h.E.tr(*[h.E.th({"scope": "col"}, column) for column in columns])),
                        h.E.tbody(*[createRow(desc, "descriptor", for_=atRuleName) for desc in descs]),
                    ),
                ),
            )


def addIDLSection(doc: t.SpecT, body: t.ElementT) -> None:
    idlBlocks = [x for x in h.findAll("pre.idl, xmp.idl", body) if h.isNormative(doc, x)]
    if len(idlBlocks) == 0:
        return
    html = main.getFillContainer("idl-index", doc=doc, tree=body, default=body)
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


def addCDDLSection(doc: t.SpecT, body: t.ElementT) -> None:
    allCddlBlocks = [x for x in h.findAll("pre.cddl, xmp.cddl", body) if h.isNormative(doc, x)]
    if len(allCddlBlocks) == 0:
        return
    html = main.getFillContainer("cddl-index", doc=doc, tree=body, default=body)
    if html is None:
        return

    h.appendChild(
        html,
        h.E.h2({"class": "no-num no-ref", "id": h.safeID(doc, "cddl-index")}, _t("CDDL Index")),
    )

    # Specs such as WebDriver BiDi define two sets of CDDL definitions for
    # the local and remote ends of the protocol. These modules need to be
    # defined with a dfn of type "cddl-module". CDDL blocks can then reference
    # one or more modules through a "data-cddl-module" attribute.
    # When modules are defined, CDDL blocks that do not reference a module
    # are considered to apply to all modules. In particular, they do not create
    # a "default" module
    cddlModules = [
        (x.get("id", ""), x.get("data-lt", x.text or "").split("|"))
        for x in h.findAll("dfn[data-dfn-type=cddl-module]", body)
    ]
    if len(cddlModules) == 0:
        cddlModules = [("", [""])]
    for module in cddlModules:
        cddlBlocks = []
        for block in allCddlBlocks:
            forModules = [x.strip() for x in block.get("data-cddl-module", "").split(",")]
            if (len(forModules) == 1 and forModules[0] == "") or any(name in forModules for name in module[1]):
                cddlBlocks.append(block)
        if len(cddlBlocks) == 0:
            continue
        if module[1][0] != "":
            h.appendChild(
                html,
                h.E.h3(
                    {"class": "no-num no-ref", "id": h.safeID(doc, "cddl-index-" + module[0])},
                    _t(module[1][0].capitalize()),
                ),
            )
        container = h.appendChild(html, h.E.pre({"class": "cddl"}))
        for block in cddlBlocks:
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


def addReferencesSection(doc: t.SpecT, body: t.ElementT) -> None:
    if not doc.normativeRefs and not doc.informativeRefs:
        return
    container = main.getFillContainer("references", doc=doc, tree=body, default=body)
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


def formatBiblioTerm(linkText: str) -> str:
    """
    If the term is all uppercase, leave it like that.
    If it's all lowercase, uppercase it.
    If it's mixed case, leave it like that.
    """
    if linkText.islower():
        return linkText.upper()
    return linkText


def addIssuesSection(doc: t.SpecT, body: t.ElementT) -> None:
    issues = h.findAll(".issue", doc)
    if len(issues) == 0:
        return
    container = main.getFillContainer("issues-index", doc=doc, tree=body, default=body)
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
    for dfnel in h.collectDfns(container):
        dfnel.tag = "span"
