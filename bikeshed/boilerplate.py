import copy
import os
import re
import subprocess
from collections import OrderedDict, defaultdict
from datetime import datetime

from . import conditional, config, dfnpanels
from .DefaultOrderedDict import DefaultOrderedDict
from .h import *
from .messages import *
from .refs import utils as refUtils


def boilerplateFromHtml(doc, htmlString):
    htmlString = doc.fixText(htmlString)
    bp = E.div({}, parseHTML(htmlString))
    conditional.processConditionals(bp, doc)
    return childNodes(bp, clear=True)


def loadBoilerplate(doc, filename, bpname=None):
    if bpname is None:
        bpname = filename
    html = config.retrieveBoilerplateFile(doc, filename)
    el = boilerplateFromHtml(doc, html)
    fillWith(bpname, el, doc=doc)


def addBikeshedVersion(doc):
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
            raise Exception()
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
        bikeshedVersion = doc.dataFile.fetch(
            "bikeshed-version.txt", type="readonly", str=True
        ).strip()
    appendChild(doc.head, E.meta({"name": "generator", "content": bikeshedVersion}))


def addCanonicalURL(doc):
    # Adds a <link rel=canonical> to the configured canonical url
    if doc.md.canonicalURL:
        appendChild(doc.head, E.link({"rel": "canonical", "href": doc.md.canonicalURL}))


def addFavicon(doc):
    # Adds a <link rel=icon> to the configured favicon url
    if doc.md.favicon:
        appendChild(doc.head, E.link({"rel": "icon", "href": doc.md.favicon}))


def addSpecVersion(doc):
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
                subprocess.check_output(
                    "git rev-parse HEAD", stderr=fnull, shell=True, cwd=source_dir
                )
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
        appendChild(
            doc.head, E.meta({"name": "document-revision", "content": revision})
        )


def addHeaderFooter(doc):
    header = (
        config.retrieveBoilerplateFile(doc, "header")
        if "header" in doc.md.boilerplate
        else ""
    )
    footer = (
        config.retrieveBoilerplateFile(doc, "footer")
        if "footer" in doc.md.boilerplate
        else ""
    )

    doc.html = "\n".join([header, doc.html, footer])


def fillWith(tag, newElements, doc):
    for el in doc.fillContainers[tag]:
        replaceContents(el, newElements)


def getFillContainer(tag, doc, default=False):
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
    if doc.md.group == "byos":
        return None
    if default:
        return doc.body


def addLogo(doc):
    loadBoilerplate(doc, "logo")


def addCopyright(doc):
    loadBoilerplate(doc, "copyright")


def addAbstract(doc):
    if not doc.md.noAbstract:
        loadBoilerplate(doc, "abstract")
    else:
        container = getFillContainer("abstract", doc, default=False)
        if container is not None:
            removeNode(container)


def addStatusSection(doc):
    loadBoilerplate(doc, "status")


def addExpiryNotice(doc):
    if doc.md.expires is None:
        return
    if doc.md.date >= doc.md.expires or datetime.utcnow().date() >= doc.md.expires:
        boilerplate = "warning-expired"
    else:
        boilerplate = "warning-expires"
        doc.extraScripts["script-expires"] = expiryScript
    loadBoilerplate(doc, boilerplate, "warning")
    addClass(doc.body, boilerplate)


expiryScript = """
const warning = document.querySelector('#expiry-notice');
const expiresOn = warning.dataset.expires;
const today = new Date().toISOString();
if(expires < today) {
    warning.setAttribute("open", "");
    for(const swap of warning.querySelectorAll("[data-after-expiry]")) {
        swap.textContent = swap.dataset.afterExpiry;
    }
}
"""


def addObsoletionNotice(doc):
    if doc.md.warning:
        loadBoilerplate(doc, doc.md.warning[0], "warning")


def addAtRisk(doc):
    if len(doc.md.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.md.atRisk:
        html += "<li>" + doc.fixText(feature)
    html += (
        "</ul><p>“At-risk” is a W3C Process term-of-art, and does not necessarily imply that the feature is in danger of being dropped or delayed. "
        "It means that the WG believes the feature may have difficulty being interoperably implemented in a timely manner, "
        "and marking it as such allows the WG to drop the feature if necessary when transitioning to the Proposed Rec stage, "
        "without having to publish a new Candidate Rec without the feature first."
    )
    fillWith("at-risk", parseHTML(html), doc=doc)


def addStyles(doc):
    el = getFillContainer("stylesheet", doc)
    if el is not None:
        el.text = config.retrieveBoilerplateFile(doc, "stylesheet")


def addCustomBoilerplate(doc):
    for el in findAll("[boilerplate]", doc):
        tag = el.get("boilerplate")
        if doc.fillContainers[tag]:
            replaceContents(doc.fillContainers[tag][0], el)
            removeNode(el)


def removeUnwantedBoilerplate(doc):
    for tag, els in doc.fillContainers.items():
        if tag not in doc.md.boilerplate:
            for el in els:
                removeNode(el)


def addAnnotations(doc):
    if doc.md.vshortname in doc.testSuites:
        html = config.retrieveBoilerplateFile(doc, "annotations")
        el = boilerplateFromHtml(doc, html)
        appendContents(find("head", doc), el)


def w3cStylesheetInUse(doc):
    return doc.md.prepTR or doc.md.status in config.snapshotStatuses


def keyFromStyles(kv):
    k = kv[0]
    if k == "style-darkmode":
        prio = 2
    else:
        prio = 1

    return (prio, k)


def addBikeshedBoilerplate(doc):
    w3cStylesheet = w3cStylesheetInUse(doc)
    for k, v in sorted(doc.extraStyles.items(), key=keyFromStyles):
        if k not in doc.md.boilerplate:
            continue
        if w3cStylesheet and k in ["style-colors", "style-darkmode"]:
            # These are handled by the /TR stylesheet, so don't output them
            continue
        container = getFillContainer(k, doc)
        if container is None:
            container = getFillContainer("bs-styles", doc, default=True)
        if container is not None:
            appendChild(container, E.style(f"/* {k} */\n{v}"))
    for k, v in sorted(doc.extraScripts.items()):
        if k not in doc.md.boilerplate:
            continue
        container = getFillContainer(k, doc)
        if container is None:
            container = getFillContainer("bs-scripts", doc, default=True)
        if container is not None:
            appendChild(container, E.script(f"/* {k} */\n{v}"))


def addIndexSection(doc):
    if (
        len(findAll(config.dfnElementsSelector, doc)) == 0
        and len(list(doc.externalRefsUsed.keys())) == 0
    ):
        return
    container = getFillContainer("index", doc=doc, default=True)
    if container is None:
        return
    appendChild(
        container, E.h2({"class": "no-num no-ref", "id": safeID(doc, "index")}, "Index")
    )

    if len(findAll(config.dfnElementsSelector, doc)) > 0:
        addIndexOfLocallyDefinedTerms(doc, container)

    if len(list(doc.externalRefsUsed.keys())) > 0:
        addIndexOfExternallyDefinedTerms(doc, container)


def addIndexOfLocallyDefinedTerms(doc, container):
    appendChild(
        container,
        E.h3(
            {"class": "no-num no-ref", "id": safeID(doc, "index-defined-here")},
            "Terms defined by this specification",
        ),
    )

    indexEntries = defaultdict(list)
    for el in findAll(config.dfnElementsSelector, doc):
        if el.get("id") is None or el.get("data-dfn-type") is None:
            continue
        linkTexts = config.linkTextsFromElement(el)
        headingLevel = headingLevelOfElement(el) or "Unnumbered section"
        type = el.get("data-dfn-type")
        if type == "argument":
            # Don't generate index entries for arguments.
            continue
        if el.get("data-dfn-for") is not None:
            disambiguator = "{} for {}".format(
                el.get("data-dfn-type"),
                ", ".join(config.splitForValues(el.get("data-dfn-for"))),
            )
        elif type == "dfn":
            disambiguator = "definition of"
        else:
            disambiguator = "({})".format(el.get("data-dfn-type"))

        id = el.get("id")
        for linkText in linkTexts:
            entry = {
                "url": "#" + id,
                "label": "§\u202f" + headingLevel,
                "disambiguator": disambiguator,
            }
            indexEntries[linkText].append(entry)

    # Now print the indexes
    indexHTML = htmlFromIndexTerms(indexEntries)
    appendChild(container, indexHTML)


def disambiguator(ref, types, specs):
    disambInfo = []
    if types is None or len(types) > 1:
        disambInfo.append(ref.type)
    if specs is None or len(specs) > 1:
        disambInfo.append("in " + ref.spec)
    if ref.for_:
        disambInfo.append("for {}".format(", ".join(x.strip() for x in ref.for_)))
    return ", ".join(disambInfo)


def addExplicitIndexes(doc):
    # Explicit indexes can be requested for specs with <index spec="example-spec-1"></index>

    for el in findAll("index", doc):

        status = el.get("status")
        if status and status not in config.specStatuses:
            die(
                "<index> has unknown value '{0}' for status. Must be {1}.",
                status,
                config.englishFromList(config.specStatuses),
                el=el,
            )
            continue

        if el.get("type"):
            types = {x.strip() for x in el.get("type").split(",")}
            for t in types:
                if t not in config.dfnTypes:
                    die(
                        "Unknown type value '{}' on {}".format(t, outerHTML(el)),
                        el=el,
                    )
                    types.remove(t)
        else:
            types = None

        if el.get("data-link-spec"):
            # Yes, this is dumb. Accidental over-firing of a shortcut attribute. >_<
            specs = {x.strip() for x in el.get("data-link-spec").split(",")}
            for s in list(specs):
                if s not in doc.refs.specs:
                    die("Unknown spec name '{}' on {}".format(s, outerHTML(el)), el=el)
                    specs.remove(s)
        else:
            specs = None

        if el.get("for"):
            fors = {x.strip() for x in el.get("for").split(",")}
        else:
            fors = None

        if el.get("export"):
            exportVal = el.get("export").lower().strip()
            if exportVal in ["yes", "y", "true", "on"]:
                export = True
            elif exportVal in ["no", "n", "false", "off"]:
                export = False
            else:
                die(
                    "Unknown export value '{}' (should be boolish) on {}".format(
                        exportVal, outerHTML(el)
                    ),
                    el=el,
                )
                export = None
        else:
            export = None

        # Initial filter of the ref database according to the <index> parameters
        possibleRefs = []
        for ref in doc.refs.queryAllRefs(
            dedupURLs=False, latestOnly=False, ignoreObsoletes=False
        ):
            ref.text = re.sub(r"\s{2,}", " ", ref.text.strip())
            if export is not None and ref.export != export:
                continue
            if specs is not None and ref.spec not in specs:
                continue
            if types is not None and ref.type not in types:
                continue
            if fors is not None and not (set(ref.for_) & fors):
                continue
            possibleRefs.append(ref)

        # Group entries by linking text,
        # ensuring no duplicate disambiguators.
        refsFromText = defaultdict(list)
        for ref in possibleRefs:
            refDisambiguator = disambiguator(ref, types, specs)
            for i, existingRef in enumerate(refsFromText[ref.text]):
                if disambiguator(existingRef, types, specs) != refDisambiguator:
                    continue
                # Whoops, found an identical entry.
                if existingRef.status != ref.status:
                    if status:
                        if existingRef.status == status:
                            # Existing entry matches stated status, do nothing and don't add it.
                            break
                        if ref.status == status:
                            # New entry matches status, update and don't re-add it.
                            refsFromText[text][i] = ref
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
        refsFromTtf = defaultdict(list)
        for text, entries in refsFromText.items():
            for ref in entries:
                ttf = (text, ref.type, "".join(ref.for_) if ref.for_ else None)
                refsFromTtf[ttf].append(ref)
        filteredRefs = defaultdict(list)
        for ttf, refs in list(refsFromTtf.items()):
            refs = doc.refs.filterObsoletes(refs)
            refs = refUtils.filterOldVersions(refs)
            if refs:
                filteredRefs[ttf[0]].extend(
                    {"url": ref.url, "disambiguator": disambiguator(ref, types, specs)}
                    for ref in refs
                )

        appendChild(el, htmlFromIndexTerms(filteredRefs))
        el.tag = "div"
        removeAttr(el, "export", "for", "spec", "status", "type")


def htmlFromIndexTerms(entries):
    # entries: dict (preferably OrderedDict, if you want stability) of linkText=>{url, label, disambiguator}
    # label is used for the actual link (normally heading level), disambiguator is phrase to use when there are collisions

    def entryKey(x):
        return (
            # first group by approximating a human-friendly "nearness" of terms
            re.sub(r"[^a-z0-9]", "", x[0].lower()),
            # then within that, by case-ignoring exact text
            x[0].lower(),
            # and finally uniquely by exact text
            x[0],
        )

    entries = OrderedDict(sorted(entries.items(), key=entryKey))

    topList = E.ul({"class": "index"})
    for text, items in entries.items():
        if len(items) == 1:
            item = items[0]
            li = appendChild(
                topList,
                E.li(
                    E.a({"href": item["url"]}, text),
                    E.span(", in ", item["label"]) if item.get("label") else "",
                ),
            )
        else:
            li = appendChild(topList, E.li(text))
            ul = appendChild(li, E.ul())
            for item in sorted(items, key=lambda x: x["disambiguator"]):
                appendChild(
                    ul,
                    E.li(
                        E.a({"href": item["url"]}, item["disambiguator"]),
                        E.span(", in ", item["label"]) if item.get("label") else "",
                    ),
                )
    return topList


def addIndexOfExternallyDefinedTerms(doc, container):
    if not doc.externalRefsUsed:
        return

    def makeLink(*contents):
        return E.span({}, *contents)

    ul = E.ul({"class": "index"})
    # Gather all the <a href> in the document, for use in the dfn-panels
    elsFromHref = DefaultOrderedDict(list)
    for a in findAll("a", doc):
        href = a.get("href")
        if href is None:
            continue
        if href.startswith("#"):
            continue
        elsFromHref[href].append(a)
    atLeastOnePanel = False
    for spec, refGroups in sorted(
        doc.externalRefsUsed.items(), key=lambda x: x[0].upper()
    ):
        # ref.spec is always lowercase; if the same string shows up in biblio data,
        # use its casing instead.
        biblioRef = doc.refs.getBiblioRef(spec, quiet=True)
        if biblioRef:
            printableSpec = biblioRef.linkText
        else:
            printableSpec = spec
        attrs = {
            "data-lt": spec,
            "data-link-type": "biblio",
            "data-biblio-type": "informative",
            "data-okay-to-fail": "true",
        }
        specLi = appendChild(
            ul,
            E.li(E.a(attrs, "[", printableSpec, "]"), " defines the following terms:"),
        )
        termsUl = appendChild(specLi, E.ul())
        for _, refs in sorted(refGroups.items(), key=lambda x: x[0]):
            if len(refs) == 1:
                ref = list(refs.values())[0]
                link = makeLink(ref.text)
            else:
                for key, ref in sorted(refs.items(), key=lambda x: x[0]):
                    if key:
                        link = makeLink(ref.text, " ", E.small({}, f"(for {key})"))
                    else:
                        link = makeLink(ref.text)
            appendChild(termsUl, E.li(link))
            atLeastOnePanel = True
            dfnpanels.addExternalDfnPanel(link, ref, elsFromHref, doc)
    if atLeastOnePanel:
        dfnpanels.addExternalDfnPanelStyles(doc)
    appendChild(
        container,
        E.h3(
            {"class": "no-num no-ref", "id": safeID(doc, "index-defined-elsewhere")},
            "Terms defined by reference",
        ),
        ul,
    )


def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables

    if len(findAll("table.propdef, table.descdef", doc)) == 0:
        return
    html = getFillContainer("property-index", doc=doc, default=True)
    if html is None:
        return

    appendChild(
        html,
        E.h2(
            {"class": "no-num no-ref", "id": safeID(doc, "property-index")},
            "Property Index",
        ),
    )

    def extractKeyValFromRow(row, table):
        # Extract the key, minus the trailing :
        result = re.match(r"(.*):", textContent(row[0]).strip())
        if result is None:
            die(
                "Propdef row headers must be a word followed by a colon. Got:\n{0}",
                textContent(row[0]).strip(),
                el=table,
            )
            return "", ""
        key = result.group(1).strip().capitalize()
        # Extract the value from the second cell
        val = textContent(row[1]).strip()
        return key, val

    # Extract propdef info
    props = []
    for table in findAll("table.propdef", doc):
        prop = {}
        names = []
        for row in findAll("tr", table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [textContent(x) for x in findAll("dfn", row[1])]
            else:
                prop[key] = val
        for name in names:
            tempProp = prop.copy()
            tempProp["Name"] = name
            props.append(tempProp)
    props.sort(key=lambda x: x["Name"])
    # Extract descdef info
    atRules = defaultdict(list)
    for table in findAll("table.descdef", doc):
        desc = {}
        names = []
        atRule = ""
        for row in findAll("tr", table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [textContent(x) for x in findAll("dfn", row[1])]
            elif key == "For":
                atRule = val
            else:
                desc[key] = val
        for name in names:
            tempDesc = desc.copy()
            tempDesc["Name"] = name
            atRules[atRule].append(tempDesc)
    for desc in atRules.values():
        desc.sort(key=lambda x: x["Name"])

    def createRow(prop, linkType, for_=None):
        attrs = {"data-link-type": linkType}
        if for_:
            attrs["data-link-for"] = for_
        return E.tr(
            E.th({"scope": "row"}, E.a(attrs, prop["Name"])),
            *[E.td(prop.get(column, "")) for column in columns[1:]],
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

        def formatColumnName(name):
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

        appendChild(
            html,
            E.div(
                {"class": "big-element-wrapper"},
                E.table(
                    {"class": "index"},
                    E.thead(
                        E.tr(
                            *[
                                E.th({"scope": "col"}, formatColumnName(column))
                                for column in columns
                            ]
                        )
                    ),
                    E.tbody(*[createRow(prop, "property") for prop in props]),
                ),
            ),
        )
    else:
        appendChild(html, E.p("No properties defined."))

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
                appendChild(
                    html,
                    E.h3(
                        {"class": "no-num no-ref", "id": safeID(doc, id)},
                        E.a({"data-link-type": "at-rule"}, atRuleName),
                        " Descriptors",
                    ),
                )
            else:
                appendChild(
                    html,
                    E.h3(
                        {"class": "no-num no-ref", "id": safeID(doc, id)},
                        "Miscellaneous Descriptors",
                    ),
                )
            appendChild(
                html,
                E.div(
                    {"class": "big-element-wrapper"},
                    E.table(
                        {"class": "index"},
                        E.thead(
                            E.tr(
                                *[E.th({"scope": "col"}, column) for column in columns]
                            )
                        ),
                        E.tbody(
                            *[
                                createRow(desc, "descriptor", for_=atRuleName)
                                for desc in descs
                            ]
                        ),
                    ),
                ),
            )


def addIDLSection(doc):
    idlBlocks = [x for x in findAll("pre.idl, xmp.idl", doc) if isNormative(x, doc)]
    if len(idlBlocks) == 0:
        return
    html = getFillContainer("idl-index", doc=doc, default=True)
    if html is None:
        return

    appendChild(
        html,
        E.h2({"class": "no-num no-ref", "id": safeID(doc, "idl-index")}, "IDL Index"),
    )

    container = appendChild(html, E.pre({"class": "idl"}))
    for block in idlBlocks:
        if hasClass(block, "extract"):
            continue
        blockCopy = copy.deepcopy(block)
        appendContents(container, blockCopy)
        appendChild(container, "\n")
    for el in findAll("[id]", container):
        if el.tag == "dfn":
            el.tag = "a"
            el.set("href", "#" + el.get("id"))
        del el.attrib["id"]
    addClass(container, "highlight")


def addTOCSection(doc):
    toc = getFillContainer("table-of-contents", doc=doc, default=False)
    if toc is None:
        return
    appendChild(
        toc,
        E.h2(
            {"class": "no-num no-toc no-ref", "id": safeID(doc, "contents")},
            "Table of Contents",
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
    containers = [0, 1, 2, 3, 4, 5, 6, 7]
    containers[1] = toc
    containers[2] = appendChild(
        containers[1], E.ol({"class": "toc", "role": "directory"})
    )
    for header in findAll("h2, h3, h4, h5, h6", doc):
        level = int(header.tag[-1])
        container = containers[level]
        if isinstance(container, int):
            # Saw a low-level heading without first seeing a higher heading.
            die(
                "Saw an <h{0}> without seeing an <h{1}> first. Please order your headings properly.\n{2}",
                level,
                level - 1,
                outerHTML(header),
                el=header,
            )
            return
        if level > previousLevel + 1:
            # Jumping two levels is a no-no.
            die(
                "Heading level jumps more than one level, from h{0} to h{1}:\n  {2}",
                previousLevel,
                level,
                textContent(header).replace("\n", " "),
                el=header,
            )
            return

        addToTOC = True
        if hasClass(header, "no-toc"):
            # Hit a no-toc, suppress the entire section.
            addToTOC = False
        elif container is None:
            addToTOC = False
        elif (level - 1) > doc.md.maxToCDepth:
            addToTOC = False

        if addToTOC:
            li = appendChild(
                container,
                E.li(
                    E.a(
                        {"href": "#" + header.get("id")},
                        E.span({"class": "secno"}, header.get("data-level", "")),
                        " ",
                        copy.deepcopy(find(".content", header)),
                    )
                ),
            )
            containers[level + 1] = appendChild(li, E.ol({"class": "toc"}))
        else:
            containers[level + 1] = None
        previousLevel = level

    container = containers[1]
    for el in findAll(".content a, .content dfn", container):
        el.tag = "span"
        if "href" in el.attrib:
            del el.attrib["href"]
    for el in findAll(".content [id]", container):
        del el.attrib["id"]
    for el in findAll("ol:empty", container):
        removeNode(el)


def addSpecMetadataSection(doc):
    def printEditor(editor):
        dd = E.dd({"class": "editor p-author h-card vcard"})
        if editor["w3cid"]:
            dd.attrib["data-editor-id"] = editor["w3cid"]
        if editor["link"]:
            appendChild(
                dd,
                E.a(
                    {"class": "p-name fn u-url url", "href": editor["link"]},
                    editor["name"],
                ),
            )
        elif editor["email"]:
            appendChild(
                dd,
                E.a(
                    {
                        "class": "p-name fn u-email email",
                        "href": "mailto:" + editor["email"],
                    },
                    editor["name"],
                ),
            )
        else:
            appendChild(dd, E.span({"class": "p-name fn"}, editor["name"]))
        if editor["org"]:
            if editor["orglink"]:
                el = E.a(
                    {"class": "p-org org", "href": editor["orglink"]}, editor["org"]
                )
            else:
                el = E.span({"class": "p-org org"}, editor["org"])
            appendChild(dd, " (", el, ")")
        if editor["email"] and editor["link"]:
            appendChild(
                dd,
                " ",
                E.a(
                    {"class": "u-email email", "href": "mailto:" + editor["email"]},
                    editor["email"],
                ),
            )
        return dd

    def printTranslation(tr):
        lang = tr["lang-code"]
        # canonicalize the lang-code structure
        lang = lang.lower().replace("_", "-")
        name = tr["name"]
        nativeName = tr["native-name"]
        url = tr["url"]
        missingInfo = False
        if name is None:
            if lang in doc.languages:
                name = doc.languages[lang]["name"]
            else:
                missingInfo = True
        if nativeName is None:
            if lang in doc.languages:
                nativeName = doc.languages[lang]["native-name"]
            else:
                missingInfo = True
        if missingInfo:
            warn(
                "Bikeshed doesn't have all the translation info for '{0}'. Please add to bikeshed/spec-data/readonly/languages.json and submit a PR!",
                lang,
            )
        if nativeName:
            return E.span(
                {"title": name or lang},
                E.a(
                    {"href": url, "hreflang": lang, "rel": "alternate", "lang": lang},
                    nativeName,
                ),
            )
        if name:
            return E.a(
                {"href": url, "hreflang": lang, "rel": "alternate", "title": lang}, name
            )
        return E.a({"href": url, "hreflang": lang, "rel": "alternate"}, lang)

    def printPreviousVersion(v):
        if v["type"] == "url":
            return E.a({"href": v["value"], "rel": "prev"}, v["value"])
        if v["type"] == "from-biblio":
            key = v["value"]
        else:  # "from-biblio-implicit"
            key = doc.md.vshortname
        dated = doc.refs.getLatestBiblioRef(key)
        if not dated:
            die(
                f"While trying to generate a Previous Version line, couldn't find a dated biblio reference for {key}."
            )
            return
        return E.a({"href": dated.url, "rel": "prev"}, dated.url)

    md = DefaultOrderedDict(list)
    mac = doc.macros
    if "version" in mac:
        md["This version"].append(
            E.a({"href": mac["version"], "class": "u-url"}, mac["version"])
        )
    if doc.md.TR:
        md["Latest published version"].append(E.a({"href": doc.md.TR}, doc.md.TR))
    if doc.md.ED and doc.md.status in config.snapshotStatuses:
        md["Editor's Draft"].append(E.a({"href": doc.md.ED}, doc.md.ED))
    if doc.md.previousVersions:
        md["Previous Versions"] = [
            printPreviousVersion(ver) for ver in doc.md.previousVersions
        ]
    if doc.md.versionHistory:
        md["Version History"] = [E.a({"href": vh}, vh) for vh in doc.md.versionHistory]
    if doc.md.mailingList:
        span = E.span(
            E.a(
                {
                    "href": "mailto:"
                    + doc.md.mailingList
                    + "?subject=%5B"
                    + mac["shortname"]
                    + "%5D%20YOUR%20TOPIC%20HERE"
                },
                doc.md.mailingList,
            ),
            " with subject line “",
            E.kbd("[", mac["shortname"], "] ", E.i({"lt": ""}, "… message topic …")),
            "”",
        )
        if doc.md.mailingListArchives:
            appendChild(
                span,
                " (",
                E.a(
                    {"rel": "discussion", "href": doc.md.mailingListArchives},
                    "archives",
                ),
                ")",
            )
        md["Feedback"].append(span)
    if doc.md.implementationReport is not None:
        md["Implementation Report"].append(
            E.a({"href": doc.md.implementationReport}, doc.md.implementationReport)
        )
    if doc.md.testSuite is not None:
        md["Test Suite"].append(E.a({"href": doc.md.testSuite}, doc.md.testSuite))
    elif (doc.md.vshortname in doc.testSuites) and (
        doc.testSuites[doc.md.vshortname]["url"] is not None
    ):
        url = doc.testSuites[doc.md.vshortname]["url"]
        md["Test Suite"].append(E.a({"href": url}, url))
    if doc.md.issues:
        md["Issue Tracking"] = [
            E.a({"href": href}, text) for text, href in doc.md.issues
        ]
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
            E.label(
                {"for": safeID(doc, "hidedel"), "id": safeID(doc, "hidedel-label")},
                "Hide deleted text",
            )
        ]
        prependChild(
            doc.body,
            E.input(
                {
                    "type": "checkbox",
                    "id": safeID(doc, "hidedel"),
                    "style": "display:none",
                }
            ),
        )
        doc.extraStyles[
            "style-hidedel"
        ] = """
            #hidedel:checked ~ del, #hidedel:checked ~ * del { display:none; }
            #hidedel ~ #hidedel-label::before, #hidedel ~ * #hidedel-label::before { content: "☐ "; }
            #hidedel:checked ~ #hidedel-label::before, #hidedel:checked ~ * #hidedel-label::before { content: "☑ "; }
        """

    def createMdEntry(key, vals):
        vals = list(filter(lambda x: x is not None, vals))
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
            "Former "
            + doc.md.editorTerm["singular"]: "Former "
            + doc.md.editorTerm["plural"],
        }
        if len(vals) > 1 and displayKey in pluralization:
            displayKey = pluralization[displayKey]
        # Handle some custom <dt> structures
        if key in ("Editor", "Former Editor"):
            ret = [E.dt({"class": "editor"}, displayKey, ":")]
        elif key == "Translations":
            ret = [E.dt(displayKey, " ", E.small("(non-normative)"), ":")]
        else:
            ret = [E.dt(displayKey, ":")]
        # Add all the values, wrapping in a <dd> if necessary.
        for val in vals:
            if isElement(val) and val.tag == "dd":
                ret.append(val)
            else:
                ret.append(E.dd({}, val))
        return ret

    # Merge "custom" metadata into non-custom, when they match up
    otherMd = OrderedDict()
    for k, vs in doc.md.otherMetadata.items():
        if k in md:
            md[k].extend(parseHTML(doc.fixText(v)) for v in vs)
        else:
            otherMd[k] = [parseHTML(doc.fixText(v)) for v in vs]

    dl = E.dl()
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
                appendChild(dl, *createMdEntry(k, vs))
        elif key == "!*":
            # Do all the non-explicit custom keys
            for k, vs in otherMd.items():
                if k in doc.md.metadataOrder:
                    continue
                if k not in doc.md.metadataInclude:
                    continue
                appendChild(dl, *createMdEntry(k, vs))
        elif key not in doc.md.metadataInclude:
            # Key explicitly excluded
            continue
        elif key in md:
            appendChild(dl, *createMdEntry(key, md[key]))
        elif key in otherMd:
            appendChild(dl, *createMdEntry(key, otherMd[key]))
    fillWith("spec-metadata", E.div(dl), doc=doc)


def addReferencesSection(doc):
    if not doc.normativeRefs and not doc.informativeRefs:
        return
    container = getFillContainer("references", doc=doc, default=True)
    if container is None:
        return

    def formatBiblioTerm(linkText):
        """
        If the term is all uppercase, leave it like that.
        If it's all lowercase, uppercase it.
        If it's mixed case, leave it like that.
        """
        if linkText.islower():
            return linkText.upper()
        return linkText

    appendChild(
        container,
        E.h2({"class": "no-num no-ref", "id": safeID(doc, "references")}, "References"),
    )

    normRefs = sorted(doc.normativeRefs.values(), key=lambda r: r.linkText.lower())
    if len(normRefs) > 0:
        dl = appendChild(
            container,
            E.h3(
                {"class": "no-num no-ref", "id": safeID(doc, "normative")},
                "Normative References",
            ),
            E.dl(),
        )
        for ref in normRefs:
            id = "biblio-" + config.simplifyText(ref.linkText)
            appendChild(
                dl,
                E.dt(
                    {"id": safeID(doc, id), "data-no-self-link": ""},
                    "[" + formatBiblioTerm(ref.linkText) + "]",
                ),
            )
            appendChild(dl, E.dd(*ref.toHTML()))

    informRefs = [
        x
        for x in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText.lower())
        if x.linkText not in doc.normativeRefs
    ]
    if len(informRefs) > 0:
        dl = appendChild(
            container,
            E.h3(
                {"class": "no-num no-ref", "id": safeID(doc, "informative")},
                "Informative References",
            ),
            E.dl(),
        )
        for ref in informRefs:
            id = "biblio-" + config.simplifyText(ref.linkText)
            appendChild(
                dl,
                E.dt(
                    {"id": safeID(doc, id), "data-no-self-link": ""},
                    "[" + formatBiblioTerm(ref.linkText) + "]",
                ),
            )
            appendChild(dl, E.dd(*ref.toHTML()))


def addIssuesSection(doc):
    issues = findAll(".issue", doc)
    if len(issues) == 0:
        return
    container = getFillContainer("issues-index", doc=doc, default=True)
    if container is None:
        return

    appendChild(
        container,
        E.h2(
            {"class": "no-num no-ref", "id": safeID(doc, "issues-index")},
            "Issues Index",
        ),
    )
    container = appendChild(container, E.div({"style": "counter-reset:issue"}))
    for issue in issues:
        el = copy.deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre", "xmp"):
            el.tag = "div"
        appendChild(container, el)
        appendChild(el, E.a({"href": "#" + issue.get("id")}, " ↵ "))
    for idel in findAll("[id]", container):
        del idel.attrib["id"]
    for dfnel in findAll(config.dfnElementsSelector, container):
        dfnel.tag = "span"
