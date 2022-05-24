import json
import logging
import re
from collections import Counter, defaultdict, namedtuple
from urllib import parse
from PIL import Image

from . import biblio, config, dfnpanels, h, func, t, messages as m, idl


class MarkdownCodeSpans(func.Functor):
    # Wraps a string, such that the contained text is "safe"
    # and contains no markdown code spans.
    # Thus, functions mapping over the text can freely make substitutions,
    # knowing they won't accidentally replace stuff in a code span.
    def __init__(self, text):
        self.__codeSpanReplacements__ = []
        newText = ""
        mode = "text"
        indexSoFar = 0
        backtickCount = 0
        for match in re.finditer(r"(\\`)|([\w-]*)(`+)", text):
            if mode == "text":
                if match.group(1):
                    newText += text[indexSoFar : match.start()] + match.group(1)[1]
                    indexSoFar = match.end()
                elif match.group(3):
                    mode = "code"
                    newText += text[indexSoFar : match.start()]
                    indexSoFar = match.end()
                    backtickCount = len(match.group(3))
                    tag = match.group(2)
                    literalStart = match.group(0)
            elif mode == "code":
                if match.group(1):
                    pass
                elif match.group(3):
                    if len(match.group(3)) != backtickCount:
                        pass
                    else:
                        mode = "text"
                        innerText = text[indexSoFar : match.start()] + match.group(2)
                        fullText = literalStart + text[indexSoFar : match.start()] + match.group(0)
                        replacement = (tag, innerText, fullText)
                        self.__codeSpanReplacements__.append(replacement)
                        newText += "\ue0ff"
                        indexSoFar = match.end()
        if mode == "text":
            newText += text[indexSoFar:]
        elif mode == "code":
            newText += tag + "`" * backtickCount + text[indexSoFar:]

        super().__init__(newText)

    def map(self, fn):
        x = MarkdownCodeSpans("")
        x.__val__ = fn(self.__val__)
        x.__codeSpanReplacements__ = self.__codeSpanReplacements__
        return x

    def extract(self):
        if self.__codeSpanReplacements__:
            # Reverse the list, so I can use pop() to get them starting from the first.
            repls = self.__codeSpanReplacements__[::-1]

            def codeSpanReviver(_):
                # Match object is the PUA character, which I can ignore.
                repl = repls.pop()
                if repl[0] == "" or repl[0].endswith("-"):
                    # Markdown code span, so massage per CommonMark rules.
                    import string

                    text = h.escapeHTML(repl[1]).strip(string.whitespace)
                    text = re.sub("[" + string.whitespace + "]{2,}", " ", text)
                    return f"{repl[0]}<code data-opaque bs-autolink-syntax='{h.escapeAttr(repl[2])}'>{text}</code>"
                return f"<code data-opaque data-span-tag={repl[0]} bs-autolink-syntax='{h.escapeAttr(repl[2])}'>{h.escapeHTML(repl[1])}</code>"

            return re.sub(r"\ue0ff", codeSpanReviver, self.__val__)
        return self.__val__


def stripBOM(doc: "t.SpecType"):
    if len(doc.lines) >= 1 and doc.lines[0].text[0:1] == "\ufeff":
        doc.lines[0].text = doc.lines[0].text[1:]
        m.warn("Your document has a BOM. There's no need for that, please re-save it without a BOM.")


# Definitions and the like


def fixManualDefTables(doc: "t.SpecType"):
    # Def tables generated via datablocks are guaranteed correct,
    # but manually-written ones often don't link up the names in the first row.
    for table in h.findAll("table.propdef, table.descdef, table.elementdef", doc):
        if h.hasClass(table, "partial"):
            tag = "a"
            attr = "data-link-type"
        else:
            tag = "dfn"
            attr = "data-dfn-type"
        tag = "a" if h.hasClass(table, "partial") else "dfn"
        if h.hasClass(table, "propdef"):
            type = "property"
        elif h.hasClass(table, "descdef"):
            type = "descriptor"
        elif h.hasClass(table, "elementdef"):
            type = "element"
        cell = h.findAll("tr:first-child > :nth-child(2)", table)[0]
        names = [x.strip() for x in h.textContent(cell).split(",")]
        newContents = config.intersperse((h.createElement(tag, {attr: type}, name) for name in names), ", ")
        h.replaceContents(cell, newContents)


def canonicalizeShortcuts(doc: "t.SpecType"):
    # Take all the invalid-HTML shortcuts and fix them.

    attrFixup = {
        "export": "data-export",
        "noexport": "data-noexport",
        "link-spec": "data-link-spec",
        "spec": "data-link-spec",
        "link-status": "data-link-status",
        "status": "data-link-status",
        "dfn-for": "data-dfn-for",
        "link-for": "data-link-for",
        "link-for-hint": "data-link-for-hint",
        "dfn-type": "data-dfn-type",
        "link-type": "data-link-type",
        "dfn-force": "data-dfn-force",
        "force": "data-dfn-force",
        "section": "data-section",
        "attribute-info": "data-attribute-info",
        "dict-member-info": "data-dict-member-info",
        "lt": "data-lt",
        "local-lt": "data-local-lt",
        "algorithm": "data-algorithm",
        "ignore": "data-var-ignore",
    }
    for el in h.findAll(",".join(f"[{attr}]" for attr in attrFixup), doc):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, t.cast(str, el.get(attr)))
                del el.attrib[attr]

    # The next two aren't in the above dict because some of the words conflict with existing attributes on some elements.
    # Instead, limit the search/transforms to the relevant elements.
    for el in h.findAll("dfn, h2, h3, h4, h5, h6", doc):
        for dfnType in config.dfnTypes:
            if el.get(dfnType) == "":
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
                break
    for el in h.findAll("a", doc):
        for linkType in config.linkTypes:
            if el.get(linkType) is not None:
                del el.attrib[linkType]
                el.set("data-link-type", linkType)
                break
    for el in h.findAll(config.dfnElementsSelector + ", a", doc):
        if el.get("for") is None:
            continue
        _for = t.cast(str, el.get("for"))
        del el.attrib["for"]
        if el.tag == "a":
            el.set("data-link-for", _for)
        else:
            el.set("data-dfn-for", _for)


def addImplicitAlgorithms(doc: "t.SpecType"):
    # If a container has an empty `algorithm` attribute,
    # but it contains only a single `<dfn>`,
    # assume that the dfn is a description of the algorithm.
    for el in h.findAll("[data-algorithm='']:not(h1):not(h2):not(h3):not(h4):not(h5):not(h6)", doc):
        dfns = h.findAll("dfn", el)
        if len(dfns) == 1:
            dfnName = config.firstLinkTextFromElement(dfns[0])
            el.set("data-algorithm", dfnName)
            dfnFor = dfns[0].get("data-dfn-for")
            if dfnFor:
                el.set("data-algorithm-for", dfnFor)
        elif len(dfns) == 0:
            m.die(
                "Algorithm container has no name, and there is no <dfn> to infer one from.",
                el=el,
            )
        else:
            m.die(
                "Algorithm container has no name, and there are too many <dfn>s to choose which to infer a name from.",
                el=el,
            )


def checkVarHygiene(doc: "t.SpecType"):
    def isAlgo(el):
        return el.get("data-algorithm") is not None

    def nearestAlgo(el):
        # Find the nearest "algorithm" container,
        # either an ancestor with [algorithm] or the nearest heading with same.
        if isAlgo(el):
            return el
        ancestor = h.closestAncestor(el, isAlgo)
        if ancestor is not None:
            return ancestor
        for heading in h.relevantHeadings(el):
            if isAlgo(heading):
                return heading

    def algoName(el):
        # Finds a uniquified algorithm name from an algo container
        algo = nearestAlgo(el)
        if algo is None:
            return None
        algoName = algo.get("data-algorithm")
        algoFor = algo.get("data-algorithm-for")
        return f"'{algoName}'" + (f" for {algoFor}" if algoFor else "")

    # Look for vars that only show up once. These are probably typos.
    varCounts: t.DefaultDict[t.Tuple[str, str], int] = defaultdict(lambda: 0)
    for el in h.findAll("var:not([data-var-ignore])", doc):
        key = (h.foldWhitespace(h.textContent(el)).strip(), algoName(el))
        varCounts[key] += 1
    foldedVarCounts: t.DefaultDict[t.Tuple[str, str], int] = defaultdict(lambda: 0)
    atLeastOneAlgo = False
    for (var, algo), count in varCounts.items():
        if algo:
            atLeastOneAlgo = True
        if count > 1:
            continue
        if var.lower() in doc.md.ignoredVars:
            continue
        key = var, algo
        foldedVarCounts[key] += 1
    varLines = []
    for (var, algo), count in foldedVarCounts.items():
        if count == 1:
            if algo:
                varLines.append(f"  '{var}', in algorithm {algo}")
            else:
                varLines.append(f"  '{var}'")
    if varLines:
        m.warn(
            "The following <var>s were only used once in the document:\n"
            + "\n".join(varLines)
            + "\nIf these are not typos, please add an ignore='' attribute to the <var>."
        )

    if atLeastOneAlgo:
        addVarClickHighlighting(doc)

    # Look for algorithms that show up twice; these are errors.
    for algo, count in Counter(algoName(el) for el in h.findAll("[data-algorithm]", doc)).items():
        if count > 1:
            m.die(f"Multiple declarations of the {algo} algorithm.")
            return


def addVarClickHighlighting(doc: "t.SpecType"):
    if doc.md.slimBuildArtifact:
        return
    doc.extraStyles[
        "style-var-click-highlighting"
    ] = """
    var { cursor: pointer; }
    var.selected0 { background-color: #F4D200; box-shadow: 0 0 0 2px #F4D200; }
    var.selected1 { background-color: #FF87A2; box-shadow: 0 0 0 2px #FF87A2; }
    var.selected2 { background-color: #96E885; box-shadow: 0 0 0 2px #96E885; }
    var.selected3 { background-color: #3EEED2; box-shadow: 0 0 0 2px #3EEED2; }
    var.selected4 { background-color: #EACFB6; box-shadow: 0 0 0 2px #EACFB6; }
    var.selected5 { background-color: #82DDFF; box-shadow: 0 0 0 2px #82DDFF; }
    var.selected6 { background-color: #FFBCF2; box-shadow: 0 0 0 2px #FFBCF2; }
    """
    # Colors were chosen in Lab using https://nixsensor.com/free-color-converter/
    # D50 2deg illuminant, L in [0,100], a and b in [-128, 128]
    # 0 = lab(85,0,85)
    # 1 = lab(85,80,30)
    # 2 = lab(85,-40,40)
    # 3 = lab(85,-50,0)
    # 4 = lab(85,5,15)
    # 5 = lab(85,-10,-50)
    # 6 = lab(85,35,-15)

    # Color-choosing design.
    # Start with 1, increment as new ones get selected.
    # Specifically: find lowest-indexed color with lowest usage.
    # (Usually this'll be zero, but if you click too many vars in same algo, can repeat.)
    # If you unclick then click again on same var, it should get same color if possible.
    doc.extraScripts[
        "script-var-click-highlighting"
    ] = r"""
    document.addEventListener("click", e=>{
        if(e.target.nodeName == "VAR") {
            highlightSameAlgoVars(e.target);
        }
    });
    {
        const indexCounts = new Map();
        const indexNames = new Map();
        function highlightSameAlgoVars(v) {
            // Find the algorithm container.
            let algoContainer = null;
            let searchEl = v;
            while(algoContainer == null && searchEl != document.body) {
                searchEl = searchEl.parentNode;
                if(searchEl.hasAttribute("data-algorithm")) {
                    algoContainer = searchEl;
                }
            }

            // Not highlighting document-global vars,
            // too likely to be unrelated.
            if(algoContainer == null) return;

            const algoName = algoContainer.getAttribute("data-algorithm");
            const varName = getVarName(v);
            const addClass = !v.classList.contains("selected");
            let highlightClass = null;
            if(addClass) {
                const index = chooseHighlightIndex(algoName, varName);
                indexCounts.get(algoName)[index] += 1;
                indexNames.set(algoName+"///"+varName, index);
                highlightClass = nameFromIndex(index);
            } else {
                const index = previousHighlightIndex(algoName, varName);
                indexCounts.get(algoName)[index] -= 1;
                highlightClass = nameFromIndex(index);
            }

            // Find all same-name vars, and toggle their class appropriately.
            for(const el of algoContainer.querySelectorAll("var")) {
                if(getVarName(el) == varName) {
                    el.classList.toggle("selected", addClass);
                    el.classList.toggle(highlightClass, addClass);
                }
            }
        }
        function getVarName(el) {
            return el.textContent.replace(/(\s|\xa0)+/, " ").trim();
        }
        function chooseHighlightIndex(algoName, varName) {
            let indexes = null;
            if(indexCounts.has(algoName)) {
                indexes = indexCounts.get(algoName);
            } else {
                // 7 classes right now
                indexes = [0,0,0,0,0,0,0];
                indexCounts.set(algoName, indexes);
            }

            // If the element was recently unclicked,
            // *and* that color is still unclaimed,
            // give it back the same color.
            const lastIndex = previousHighlightIndex(algoName, varName);
            if(indexes[lastIndex] === 0) return lastIndex;

            // Find the earliest index with the lowest count.
            const minCount = Math.min.apply(null, indexes);
            let index = null;
            for(var i = 0; i < indexes.length; i++) {
                if(indexes[i] == minCount) {
                    return i;
                }
            }
        }
        function previousHighlightIndex(algoName, varName) {
            return indexNames.get(algoName+"///"+varName);
        }
        function nameFromIndex(index) {
            return "selected" + index;
        }
    }
    """


def fixIntraDocumentReferences(doc: "t.SpecType"):
    ids = {el.get("id"): el for el in h.findAll("[id]", doc)}
    headingIDs = {el.get("id"): el for el in h.findAll("[id].heading", doc)}
    for el in h.findAll("a[href^='#']:not([href='#']):not(.self-link):not([data-link-type])", doc):
        href = t.cast(str, el.get("href"))
        targetID = parse.unquote(href[1:])
        if el.get("data-section") is not None and targetID not in headingIDs:
            m.die(f"Couldn't find target document section {targetID}:\n{h.outerHTML(el)}", el=el)
            continue
        if targetID not in ids:
            m.die(f"Couldn't find target anchor {targetID}:\n{h.outerHTML(el)}", el=el)
            continue
        if h.isEmpty(el):
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            target = ids[targetID]
            content = h.find(".content", target)
            if content is None:
                m.die(
                    f"Tried to generate text for a section link, but the target isn't a heading:\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            text = h.textContent(content).strip()
            if target.get("data-level") is not None:
                text = f"§\u202f{target.get('data-level')} {text}"
            h.appendChild(el, text)


def fixInterDocumentReferences(doc: "t.SpecType"):
    for el in h.findAll("[spec-section]", doc):
        if el.get("data-link-spec") is None:
            m.die(
                f"Spec-section autolink doesn't have a 'spec' attribute:\n{h.outerHTML(el)}",
                el=el,
            )
            continue
        spec = el.get("data-link-spec", "").lower()
        if el.get("spec-section") is None:
            m.die(
                f"Spec-section autolink doesn't have a 'spec-section' attribute:\n{h.outerHTML(el)}",
                el=el,
            )
            continue
        section = el.get("spec-section", "")
        if spec in doc.refs.specs:
            # Bikeshed recognizes the spec
            fillInterDocumentReferenceFromShepherd(doc, el, spec, section)
            continue
        if not re.search(r"\d$", spec):
            # Unnumbered, check if there's a numbered variant in Shepherd
            vNames = doc.refs.vNamesFromSpecNames(spec)
            if len(vNames) > 0:
                fillInterDocumentReferenceFromShepherd(doc, el, vNames[0], section)
                if len(vNames) > 1:
                    m.die(
                        f"Section autolink {h.outerHTML(el)} attempts to link to unversioned spec name '{spec}', "
                        + "but that spec is versioned as {}. ".format(config.englishFromList(f"'{x}'" for x in vNames))
                        + "Please choose a versioned spec name.",
                        el=el,
                    )
                continue
        if doc.refs.getBiblioRef(spec):
            # Bikeshed doesn't know the spec, but it's in biblio
            fillInterDocumentReferenceFromSpecref(doc, el, spec, section)
            continue
        # Unknown spec
        m.die(
            f"Spec-section autolink tried to link to non-existent '{spec}' spec:\n{h.outerHTML(el)}",
            el=el,
        )


def fillInterDocumentReferenceFromShepherd(doc: "t.SpecType", el, specName, section):
    headingData = doc.refs.fetchHeadings(specName)
    if section in headingData:
        heading = headingData[section]
    else:
        m.die(
            f"Couldn't find section '{section}' in spec '{specName}':\n{h.outerHTML(el)}",
            el=el,
        )
        return
    if isinstance(heading, list):
        # Multipage spec
        if len(heading) == 1:
            # only one heading of this name, no worries
            heading = headingData[heading[0]]
        else:
            # multiple headings of this id, user needs to disambiguate
            m.die(
                f"Multiple headings with id '{section}' for spec '{specName}'. Please specify:\n"
                + "\n".join(f"  [[{specName + x}]]" for x in heading),
                el=el,
            )
            return
    if doc.md.status == "current":
        # FIXME: doc.md.status is not these values
        if "current" in heading:
            heading = heading["current"]
        else:
            heading = heading["snapshot"]
    else:
        if "snapshot" in heading:
            heading = heading["snapshot"]
        else:
            heading = heading["current"]
    el.tag = "a"
    el.set("href", heading["url"])
    if h.isEmpty(el):
        h.appendChild(el, h.E.cite("{spec}".format(**heading)))
        h.appendChild(el, " §\u202f{number} {text}".format(**heading))
    h.removeAttr(el, "data-link-spec", "spec-section")

    # Mark this as a used biblio ref
    specData = doc.refs.specs[specName]
    bib = biblio.SpecBasedBiblioEntry(specData)
    registerBiblioUsage(doc, bib, el=el)


def fillInterDocumentReferenceFromSpecref(doc: "t.SpecType", el, spec, section):
    bib = doc.refs.getBiblioRef(spec)
    if isinstance(bib, biblio.StringBiblioEntry):
        m.die(f"Can't generate a cross-spec section ref for '{spec}', because the biblio entry has no url.", el=el)
        return
    el.tag = "a"
    el.set("href", bib.url + section)
    if h.isEmpty(el):
        el.text = bib.title + " §\u202f" + section[1:]
    h.removeAttr(el, "data-link-spec", "spec-section")

    # Mark this as a used biblio ref
    registerBiblioUsage(doc, bib, el=el)


def processDfns(doc: "t.SpecType"):
    dfns = h.findAll(config.dfnElementsSelector, doc)
    classifyDfns(doc, dfns)
    h.fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get("id") is not None)


def determineDfnType(dfn, inferCSS=False):
    # 1. Look at data-dfn-type
    if dfn.get("data-dfn-type"):
        return dfn.get("data-dfn-type")
    # 2. Look for a prefix on the id
    if dfn.get("id"):
        id = dfn.get("id")
        for prefix, type in config.dfnClassToType.items():
            if id.startswith(prefix):
                return type
    # 3. Look for a class or data-dfn-type on the ancestors
    for ancestor in dfn.iterancestors():
        if ancestor.get("data-dfn-type"):
            return ancestor.get("data-dfn-type")
        for cls, type in config.dfnClassToType.items():
            if h.hasClass(ancestor, cls):
                return type
            if h.hasClass(ancestor, "idl") and not h.hasClass(ancestor, "extract"):
                return "interface"
    # 4. Introspect on the text
    if inferCSS:
        text = h.textContent(dfn)
        if text[0:1] == "@":
            return "at-rule"
        if (
            len(dfn) == 1
            and dfn[0].get("data-link-type") == "maybe"
            and h.emptyText(dfn.text)
            and h.emptyText(dfn[0].tail)
        ):
            return "value"
        if text[0:1] == "<" and text[-1:] == ">":
            return "type"
        if text[0:1] == ":":
            return "selector"
        if re.match(r"^[\w-]+\(.*\)$", text) and not (dfn.get("id") or "").startswith("dom-"):
            return "function"
    # 5. Assume it's a "dfn"
    return "dfn"


def classifyDfns(doc: "t.SpecType", dfns):
    dfnTypeToPrefix = {v: k for k, v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el, inferCSS=doc.md.inferCSSDfns)
        if dfnType not in config.dfnTypes:
            m.die(f"Unknown dfn type '{dfnType}':\n{h.outerHTML(el)}", el=el)
            continue
        dfnFor = h.treeAttr(el, "data-dfn-for")
        primaryDfnText = config.firstLinkTextFromElement(el)
        if primaryDfnText is None:
            m.die(f"Dfn has no linking text:\n{h.outerHTML(el)}", el=el)
            continue
        if len(primaryDfnText) > 300:
            # Almost certainly accidentally missed the end tag
            m.warn(
                f"Dfn has extremely long text - did you forget the </dfn> tag?\n{h.outerHTML(el)}",
                el=el,
            )
        # Check for invalid fors, as it's usually some misnesting.
        if dfnFor and dfnType in config.typesNotUsingFor:
            m.die(
                f"'{dfnType}' definitions don't use a 'for' attribute, but this one claims it's for '{dfnFor}' (perhaps inherited from an ancestor). This is probably a markup error.\n{h.outerHTML(el)}",
                el=el,
            )
        # Push the dfn type down to the <dfn> itself.
        if el.get("data-dfn-type") is None:
            el.set("data-dfn-type", dfnType)
        # Push the for value too.
        if dfnFor:
            el.set("data-dfn-for", dfnFor)
        elif dfnType in config.typesUsingFor:
            m.die(
                f"'{dfnType}' definitions need to specify what they're for.\nAdd a 'for' attribute to {h.outerHTML(el)}, or add 'dfn-for' to an ancestor.",
                el=el,
            )
            continue
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.search(r"\(.*\)$", primaryDfnText):
                m.die(
                    f"Function/methods must end with a () arglist in their linking text. Got '{primaryDfnText}'.\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            if not re.match(r"^[\w\[\]-]+\s*\(", primaryDfnText):
                m.die(
                    f"Function/method names can only contain alphanums, underscores, dashes, or []. Got '{primaryDfnText}'.\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            if el.get("data-lt") is None:
                match = re.match(r"^([\w\[\]-]+)\(.*\)$", primaryDfnText)
                if dfnType == "function" and match:
                    # CSS function, define it with no args in the text
                    primaryDfnText = match.group(1) + "()"
                    el.set("data-lt", primaryDfnText)
                elif dfnType in config.idlTypes:
                    # IDL methodish construct, ask the widlparser what it should have.
                    # If the method isn't in any IDL, this tries its best to normalize it anyway.
                    names = list(doc.widl.normalized_method_names(primaryDfnText, el.get("data-dfn-for")))
                    primaryDfnText = names[0]
                    el.set("data-lt", "|".join(names))
                else:
                    m.die(
                        f"BIKESHED ERROR: Unhandled functionish type '{dfnType}' in classifyDfns. Please report this to Bikeshed's maintainer.",
                        el=el,
                    )
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get("data-dfn-for") is None:
            parent = el.getparent()
            parentFor = parent.get("data-dfn-for")
            if parent.get("data-dfn-type") in config.functionishTypes and parentFor is not None:
                dfnFor = ", ".join(
                    parentFor + "/" + name
                    for name in doc.widl.normalized_method_names(h.textContent(parent), parentFor)
                )
            elif h.treeAttr(el, "data-dfn-for") is None:
                m.die(
                    f"'argument' dfns need to specify what they're for, or have it be inferrable from their parent. Got:\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
        # Automatically fill in id if necessary.
        if el.get("id") is None:
            if dfnFor:
                singleFor = config.splitForValues(dfnFor)[0]
            if dfnType in config.functionishTypes.intersection(config.idlTypes):
                match = re.match(r"[^(]*", primaryDfnText)
                if match:
                    parenlessID = match.group(0)
                else:
                    parenlessID = primaryDfnText
                id = config.simplifyText(
                    "{_for}-{id}".format(
                        _for=singleFor,
                        id=parenlessID + "()",
                    )
                )
                el.set(
                    "data-alternate-id",
                    config.simplifyText(f"dom-{singleFor}-{primaryDfnText}"),
                )
                if primaryDfnText.startswith("[["):
                    # Slots get their identifying [] stripped from their ID,
                    # so gotta dedup them some other way.
                    id += "-slot"
                    el.set(
                        "data-alternate-id",
                        "{}-slot".format(el.get("data-alternate-id")),
                    )
            else:
                if dfnFor:
                    id = config.simplifyText(f"{singleFor}-{primaryDfnText}")
                else:
                    id = config.simplifyText(primaryDfnText)
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                pass
            elif dfnType == "event":
                # Special case 'event' because it needs a different format from IDL types
                id = config.simplifyText(f"{dfnTypeToPrefix[dfnType]}-{id}")
            elif dfnType == "attribute" and primaryDfnText.startswith("[["):
                # Slots get their identifying [] stripped from their ID, so gotta dedup them some other way.
                id = config.simplifyText(f"dom-{id}-slot")
            elif dfnType in config.idlTypes.intersection(config.typesUsingFor):
                id = config.simplifyText(f"dom-{id}")
            else:
                id = f"{dfnTypeToPrefix[dfnType]}-{id}"
            el.set("id", h.safeID(doc, id))
        # Set lt if it's not set,
        # and doing so won't mess with anything else.
        if el.get("data-lt") is None and "|" not in primaryDfnText:
            el.set("data-lt", primaryDfnText)
        # Push export/noexport down to the definition
        if el.get("data-export") is None and el.get("data-noexport") is None:
            attr, _ = h.closestAttr(el, "data-export", "data-noexport")
            if attr is not None:
                el.set(attr, "")
            else:
                if dfnType == "dfn":
                    el.set("data-noexport", "by-default")
                else:
                    el.set("data-export", "by-default")
        # If it's an code-ish type such as IDL,
        # and doesn't already have a sole <code> child,
        # wrap the contents in a <code>.
        if config.linkTypeIn(dfnType, "codelike"):
            child = h.hasOnlyChild(el)
            if child is not None and child.tag == "code":
                continue
            if el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                # Don't wrap headings, it looks bad.
                continue
            h.wrapContents(el, h.E.code())


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = h.treeAttr(el, "data-link-type")
    if linkType:
        if linkType in config.linkTypes:
            return linkType
        m.die(f"Unknown link type '{linkType}':\n{h.outerHTML(el)}", el=el)
        return "unknown-type"
    # 2. Introspect on the text
    text = h.textContent(el)
    if config.typeRe["at-rule"].match(text):
        return "at-rule"
    if config.typeRe["type"].match(text):
        return "type"
    if config.typeRe["selector"].match(text):
        return "selector"
    if config.typeRe["function"].match(text):
        return "functionish"
    return "dfn"


def determineLinkText(el):
    linkType = el.get("data-link-type")
    contents = h.textContent(el)
    if el.get("data-lt"):
        linkText = el.get("data-lt")
    elif config.linkTypeIn(linkType, "function") and re.match(r"^[\w-]+\(.*\)$", contents):
        # Remove arguments from CSS function autolinks,
        # as they should always be defined argument-less
        # (and this allows filled-in examples to still autolink).
        linkText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1) + "()"
    else:
        linkText = contents
    linkText = h.foldWhitespace(linkText)
    if len(linkText) == 0:
        m.die(f"Autolink {h.outerHTML(el)} has no linktext.", el=el)
    return linkText


def classifyLink(el):
    linkType = determineLinkType(el)
    el.set("data-link-type", linkType)

    linkText = determineLinkText(el)
    el.set("data-lt", linkText)

    for attr in [
        "data-link-status",
        "data-link-for",
        "data-link-spec",
        "data-link-for-hint",
    ]:
        val = h.treeAttr(el, attr)
        if val is not None:
            el.set(attr, val)
    return el


# Additional Processing


def processBiblioLinks(doc: "t.SpecType"):
    biblioLinks = h.findAll("a[data-link-type='biblio']", doc)
    for el in biblioLinks:

        linkText = determineLinkText(el)
        if linkText[0] == "[" and linkText[-1] == "]":
            linkText = linkText[1:-1]

        refStatus = h.treeAttr(el, "data-biblio-status") or doc.md.defaultRefStatus

        okayToFail = el.get("data-okay-to-fail") is not None

        allowObsolete = el.get("data-biblio-obsolete") is not None

        ref = doc.refs.getBiblioRef(
            linkText,
            status=refStatus,
            allowObsolete=allowObsolete,
            generateFakeRef=okayToFail,
            quiet=okayToFail,
            el=el,
        )
        if not ref:
            if not okayToFail:
                closeBiblios = biblio.findCloseBiblios(doc.refs.biblioKeys, linkText)
                m.die(
                    f"Couldn't find '{linkText}' in bibliography data. Did you mean:\n"
                    + "\n".join("  " + b for b in closeBiblios),
                    el=el,
                )
            el.tag = "span"
            continue

        # Need to register that I have a preferred way to refer to this biblio,
        # in case aliases show up - they all need to use my preferred key!
        if ref.originalLinkText:
            # Okay, so this particular ref has been reffed before...
            if linkText == ref.linkText:
                # Whew, and with the same name I'm using now. Ship it.
                pass
            else:
                # Oh no! I'm using two different names to refer to the same biblio!
                m.die(
                    f"The biblio refs [[{linkText}]] and [[{ref.linkText}]] are both aliases of the same base reference [[{ref.originalLinkText}]]. Please choose one name and use it consistently.",
                    el=el,
                )
                # I can keep going, tho - no need to skip this ref
        else:
            # This is the first time I've reffed this particular biblio.
            # Register this as the preferred name...
            doc.refs.preferredBiblioNames[ref.linkText] = linkText
            # Use it on the current ref. Future ones will use the preferred name automatically.
            ref.linkText = linkText
        registerBiblioUsage(doc, ref, el=el, type=el.get("data-biblio-type"))

        id = config.simplifyText(ref.linkText)
        el.set("href", "#biblio-" + id)

        biblioDisplay = el.get("data-biblio-display", doc.md.defaultBiblioDisplay)
        if biblioDisplay == "inline":
            if (
                el.text == f"[{linkText}]"
            ):  # False if it's already been replaced by an author supplied text using the [[FOOBAR inline|custom text]] syntax.
                h.clearContents(el)
                h.appendChild(el, h.E.cite(ref.title))
        if biblioDisplay in ("inline", "direct"):
            if ref.url is not None:
                el.set("href", ref.url)


def verifyUsageOfAllLocalBiblios(doc: "t.SpecType"):
    """
    Verifies that all the locally-declared biblios
    (those written inline in a <pre class=biblio> block,
    and thus given order=1)
    were used in the spec,
    so you can remove entries when they're no longer necessary.
    """
    usedBiblioKeys = {x.upper() for x in list(doc.normativeRefs.keys()) + list(doc.informativeRefs.keys())}
    localBiblios = [b["linkText"].upper() for bs in doc.refs.biblios.values() for b in bs if b["order"] == 1]
    unusedBiblioKeys = []
    for b in localBiblios:
        if b not in usedBiblioKeys:
            unusedBiblioKeys.append(b)
    if unusedBiblioKeys:
        m.warn(
            "The following locally-defined biblio entries are unused and can be removed:\n"
            + "\n".join(f"  * {b}" for b in unusedBiblioKeys),
        )


def processAutolinks(doc: "t.SpecType"):
    # An <a> without an href is an autolink.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # We exclude bibliographical links, as those are processed in `processBiblioLinks`.
    query = "a:not([href]):not([data-link-type='biblio'])"
    if doc.md.useIAutolinks:
        m.warn("Use <i> Autolinks is deprecated and will be removed. Please switch to using <a> elements.")
        query += ", i"
    autolinks = h.findAll(query, doc)
    for el in autolinks:
        # Explicitly empty linking text indicates this shouldn't be an autolink.
        if el.get("data-lt") == "":
            continue

        classifyLink(el)
        linkType = t.cast(str, el.get("data-link-type"))
        linkText = t.cast(str, el.get("data-lt"))

        # Properties and descriptors are often written like 'foo-*'. Just ignore these.
        if linkType in ("property", "descriptor", "propdesc") and "*" in linkText:
            continue

        # Links can have multiple for values in cases like IDL constructors,
        # where there are several valid ways to set up the dfn
        # and my autogenerated links want to make sure that they'll link successfully
        # to any variant that the spec author uses.
        linkFors = config.splitForValues(el.get("data-link-for"))

        # Status used to use ED/TR, so convert those if they appear,
        # and verify
        status = el.get("data-link-status")
        if status == "ED":
            status = "current"
        elif status == "TR":
            status = "snapshot"
        elif status in config.linkStatuses or status is None:
            pass
        else:
            m.die(f"Unknown link status '{status}' on {h.outerHTML(el)}")
            continue

        # Some links are okay to fail, and so should do so silently.
        okayToFail = el.get("data-okay-to-fail") is not None
        ignorable = linkText.lower() in doc.md.ignoredTerms

        ref = doc.refs.getRef(
            linkType,
            linkText,
            spec=el.get("data-link-spec"),
            status=status,
            linkFor=linkFors,
            linkForHint=el.get("data-link-for-hint"),
            explicitFor=doc.md.assumeExplicitFor,
            el=el,
            error=not okayToFail and not ignorable,
        )
        # Capture the reference (and ensure we add a biblio entry) if it
        # points to an external specification. We check the spec name here
        # rather than checking `status == "local"`, as "local" refs include
        # those defined in `<pre class="anchor">` datablocks, which we do
        # want to capture here.
        if ref and ref.spec and doc.refs.spec and ref.spec.upper() != doc.refs.spec.upper():
            spec = ref.spec.upper()
            key = ref.for_[0] if ref.for_ else ""

            # If the ref is from an anchor block, it knows what it's doing.
            # Don't follow obsoletion chains.
            allowObsolete = ref.status == "anchor-block"

            biblioRef = doc.refs.getBiblioRef(
                ref.spec,
                status=doc.md.defaultRefStatus,
                generateFakeRef=True,
                quiet=False,
                allowObsolete=allowObsolete,
            )
            if biblioRef:
                spec = biblioRef.linkText.upper()
                registerBiblioUsage(doc, biblioRef, el=el)
                doc.externalRefsUsed[spec]["_biblio"] = biblioRef
            doc.externalRefsUsed[spec][ref.text][key] = ref

        if ref:
            el.set("href", ref.url)
            el.tag = "a"
            decorateAutolink(doc, el, linkType=linkType, linkText=linkText, ref=ref)
        else:
            if linkType == "maybe":
                el.tag = "css"
                if el.get("data-link-type"):
                    del el.attrib["data-link-type"]
                if el.get("data-lt"):
                    del el.attrib["data-lt"]
    h.dedupIDs(doc)


def registerBiblioUsage(
    doc: "t.SpecType", ref: biblio.BiblioEntry, el: t.ElementT, type: t.Optional[str] = None
) -> None:
    if type is None:
        if h.isNormative(el, doc):
            type = "normative"
        else:
            type = "informative"
    if type == "normative":
        biblioStorage = doc.normativeRefs
    elif type == "informative":
        biblioStorage = doc.informativeRefs
    else:
        m.die(f"Unknown biblio type {type}.", el=el)
        return
    biblioStorage[ref.linkText.upper()] = ref


def decorateAutolink(doc: "t.SpecType", el, linkType, linkText, ref):
    # Add additional effects to autolinks.
    if doc.md.slimBuildArtifact:
        return

    # Put an ID on every reference, so I can link to references to a term.
    if el.get("id") is None:
        _, _, id = ref.url.partition("#")
        if id:
            el.set("id", f"ref-for-{id}")
            el.set("data-silently-dedup", "")

    # Get all the values that the type expands to, add it as a title.
    if linkType == "type":
        titleText = None
        if linkText in doc.typeExpansions:
            titleText = doc.typeExpansions[linkText]
        else:
            refs = doc.refs.queryAllRefs(linkFor=linkText, ignoreObsoletes=True)
            texts = sorted({ref.text for ref in refs})
            if refs:
                titleText = "Expands to: " + " | ".join(texts)
                doc.typeExpansions[linkText] = titleText
        if titleText:
            el.set("title", titleText)


def removeMultipleLinks(doc: "t.SpecType"):
    # If there are multiple autolinks to the same thing in a paragraph,
    # only keep the first.
    if not doc.md.removeMultipleLinks:
        return
    paras: t.DefaultDict[t.Any, t.DefaultDict[str, t.List[t.Any]]]
    paras = defaultdict(lambda: defaultdict(list))
    for el in h.findAll("a[data-link-type]", doc):
        if h.hasAncestor(el, lambda x: x.tag in ["pre", "xmp"]):
            # Don't strip out repeated links from opaque elements
            continue
        paras[h.parentElement(el)][el.get("href", "")].append(el)
    for linkGroups in paras.values():
        for _, links in linkGroups.items():
            if len(links) > 1:
                for el in links[1:]:
                    el.tag = "span"
                    h.removeAttr(el, "href", "data-link-type")


def processIssuesAndExamples(doc: "t.SpecType"):
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues and
    # examples, and link to remote issues if possible:
    for el in h.findAll(".issue:not([id])", doc):
        el.set("id", h.safeID(doc, "issue-" + h.hashContents(el)))
        remoteIssueID = el.get("data-remote-issue-id")
        if remoteIssueID:
            del el.attrib["data-remote-issue-id"]
            # Eventually need to support a way to trigger other repo url structures,
            # but defaulting to GH is fine for now.
            githubMatch = re.match(r"\s*([\w-]+)/([\w-]+)#(\d+)\s*$", remoteIssueID)
            numberMatch = re.match(r"\s*(\d+)\s*$", remoteIssueID)
            remoteIssueURL = None
            if githubMatch:
                remoteIssueURL = "https://github.com/{}/{}/issues/{}".format(*githubMatch.groups())
                if doc.md.inlineGithubIssues:
                    el.set(
                        "data-inline-github",
                        "{} {} {}".format(*githubMatch.groups()),
                    )
            elif numberMatch and doc.md.repository.type == "github":
                remoteIssueURL = doc.md.repository.formatIssueUrl(numberMatch.group(1))
                if doc.md.inlineGithubIssues:
                    el.set(
                        "data-inline-github",
                        "{} {} {}".format(
                            doc.md.repository.user,
                            doc.md.repository.repo,
                            numberMatch.group(1),
                        ),
                    )
            elif doc.md.issueTrackerTemplate:
                remoteIssueURL = doc.md.issueTrackerTemplate.format(remoteIssueID)
            if remoteIssueURL:
                h.appendChild(el, " ", h.E.a({"href": remoteIssueURL}, "[Issue #" + remoteIssueID + "]"))
    for el in h.findAll(".example:not([id])", doc):
        el.set("id", h.safeID(doc, "example-" + h.hashContents(el)))
    h.fixupIDs(doc, h.findAll(".issue, .example", doc))


def addSelfLinks(doc: "t.SpecType"):
    if doc.md.slimBuildArtifact:
        return

    def makeSelfLink(el):
        return h.E.a({"href": "#" + h.escapeUrlFrag(el.get("id", "")), "class": "self-link"})

    dfnElements = h.findAll(config.dfnElementsSelector, doc)

    foundFirstNumberedSection = False
    for el in h.findAll("h2, h3, h4, h5, h6", doc):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get("data-level") is not None)
        if foundFirstNumberedSection:
            h.appendChild(el, makeSelfLink(el))
    for el in h.findAll(".issue[id], .example[id], .note[id], li[id], dt[id]", doc):
        if list(el.iterancestors("figure")):
            # Skipping - element is inside a figure and is part of an example.
            continue
        if el.get("data-no-self-link") is not None:
            continue
        if el.tag == "details":
            summary = h.find("summary", el)
            if summary is not None:
                h.insertAfter(summary, makeSelfLink(el))
                continue
        h.prependChild(el, makeSelfLink(el))
    if doc.md.useDfnPanels:
        dfnpanels.addDfnPanels(doc, dfnElements)
    else:
        for el in dfnElements:
            if list(el.iterancestors("a")):
                m.warn(
                    f"Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {h.outerHTML(el)}",
                    el=el,
                )
                continue
            h.appendChild(el, makeSelfLink(el))


def cleanupHTML(doc: "t.SpecType"):
    # Cleanup done immediately before serialization.

    head = None
    inBody = False
    strayHeadEls = []
    styleScoped = []
    nestedLists = []
    flattenEls = []
    for el in doc.document.iter():
        if head is None and el.tag == "head":
            head = el
            continue
        if el.tag == "body":
            inBody = True

        # Move any stray <link>, <meta>, or <style> into the <head>.
        if inBody and el.tag in ["link", "meta", "style"]:
            strayHeadEls.append(el)

        if el.tag == "style" and el.get("scoped") is not None:
            m.die(
                "<style scoped> is no longer part of HTML. Ensure your styles can apply document-globally and remove the scoped attribute.",
                el=el,
            )
            styleScoped.append(el)

        # Convert the technically-invalid <nobr> element to an appropriate <span>
        if el.tag == "nobr":
            el.tag = "span"
            el.set("style", el.get("style", "") + ";white-space:nowrap")

        # And convert <xmp> to <pre>
        if el.tag == "xmp":
            el.tag = "pre"

        # If we accidentally recognized an autolink shortcut in SVG, kill it.
        if el.tag == "{http://www.w3.org/2000/svg}a" and el.get("data-link-type") is not None:
            h.removeAttr(el, "data-link-type")
            el.tag = "{http://www.w3.org/2000/svg}tspan"

        # Add .algorithm to [algorithm] elements, for styling
        if el.get("data-algorithm") is not None and not h.hasClass(el, "algorithm"):
            h.addClass(el, "algorithm")

        # Allow MD-generated lists to be surrounded by HTML list containers,
        # so you can add classes/etc without an extraneous wrapper.
        if el.tag in ["ol", "ul", "dl"] and el.get("data-md") is None:
            if el.tag in ["ol", "ul"]:
                onlyChild = h.hasOnlyChild(el)
                if onlyChild is not None and el.tag == onlyChild.tag and onlyChild.get("data-md") is not None:
                    # The md-generated list container is featureless,
                    # so we can just throw it away and move its children into its parent.
                    nestedLists.append(onlyChild)
            else:
                # dls can contain both dt/dds
                # (which'll make an md-generated dl)
                # and divs, so I need to account for multiple children
                for child in h.childElements(el):
                    if child.tag == "dl" and child.get("data-md") is not None:
                        nestedLists.append(child)
                    elif child.tag == "div":
                        pass
                    elif child.tag in ["dt", "dd"]:
                        pass
                    else:
                        # misnested element; leave alone for now
                        pass

        # HTML allows dt/dd to be grouped by a div, so recognize
        # when a markdown-generated dl has a div parent and dl grandparent
        # and remove it.
        if (
            h.tagName(el) == "dl"
            and el.get("data-md") is not None
            and h.tagName(h.parentElement(el)) == "div"
            and h.tagName(h.parentElement(el, 2)) == "dl"
        ):
            # Also featureless and can be safely thrown away
            # with its children merged into the parent div
            nestedLists.append(el)

        # Remove any lingering data-md attributes on lists
        if el.tag in ["ol", "ul", "dl"] and el.get("data-md") is not None:
            h.removeAttr(el, "data-md")

        # Mark pre.idl blocks as .def, for styling
        if el.tag == "pre" and h.hasClass(el, "idl") and not h.hasClass(el, "def"):
            h.addClass(el, "def")

        # Tag classes on wide types of dfns/links
        if el.tag in config.dfnElements:
            if el.get("data-dfn-type") in config.idlTypes:
                h.addClass(el, "idl-code")
            if el.get("data-dfn-type") in config.maybeTypes.union(config.linkTypeToDfnType["propdesc"]):
                if not h.hasAncestor(el, lambda x: x.tag == "pre"):
                    h.addClass(el, "css")
        if el.tag == "a":
            if el.get("data-link-type") in config.idlTypes:
                h.addClass(el, "idl-code")
            if el.get("data-link-type") in config.maybeTypes.union(config.linkTypeToDfnType["propdesc"]):
                if not h.hasAncestor(el, lambda x: x.tag == "pre"):
                    h.addClass(el, "css")

        # Remove duplicate linking texts.
        if (
            el.tag in config.anchorishElements
            and el.get("data-lt") is not None
            and el.get("data-lt") == h.textContent(el, exact=True)
        ):
            h.removeAttr(el, "data-lt")

        # Transform the <css> fake tag into markup.
        # (Used when the ''foo'' shorthand doesn't work.)
        if el.tag == "css":
            el.tag = "span"
            h.addClass(el, "css")

        # Transform the <assert> fake tag into a span with a unique ID based on its contents.
        # This is just used to tag arbitrary sections with an ID so you can point tests at it.
        # (And the ID will be guaranteed stable across publications, but guaranteed to change when the text changes.)
        if el.tag == "assert":
            el.tag = "span"
            el.set("id", h.safeID(doc, "assert-" + h.hashContents(el)))

        # Add ARIA role of "note" to class="note" elements
        if el.tag in ["div", "p"] and h.hasClass(el, doc.md.noteClass):
            el.set("role", "note")

        # Look for nested <a> elements, and warn about them.
        if el.tag == "a" and h.hasAncestor(el, lambda x: x.tag == "a"):
            m.warn(
                f"The following (probably auto-generated) link is illegally nested in another link:\n{h.outerHTML(el)}",
                el=el,
            )

        # If the <h1> contains only capital letters, add a class=allcaps for styling hook
        if el.tag == "h1":
            for letter in h.textContent(el):
                if letter.isalpha() and letter.islower():
                    break
            else:
                h.addClass(el, "allcaps")

        # If a markdown-generated <dt> contains only a single paragraph,
        # remove that paragraph so it just contains naked text.
        if el.tag == "dt" and el.get("data-md") is not None:
            child = h.hasOnlyChild(el)
            if child is not None and child.tag == "p" and h.emptyText(el.text) and h.emptyText(child.tail):
                flattenEls.append(el)

        # Remove a bunch of attributes
        if el.get("data-attribute-info") is not None or el.get("data-dict-member-info") is not None:
            h.removeAttr(el, "data-attribute-info", "data-dict-member-info", "for")
        if el.tag in ["a", "span"]:
            h.removeAttr(
                el,
                "data-link-for",
                "data-link-for-hint",
                "data-link-status",
                "data-link-spec",
                "data-section",
                "data-biblio-type",
                "data-biblio-status",
                "data-okay-to-fail",
                "data-lt",
            )
        if el.tag != "a":
            h.removeAttr(el, "data-link-for", "data-link-type")
        if el.tag not in config.dfnElements:
            h.removeAttr(el, "data-dfn-for", "data-dfn-type", "data-export", "data-noexport")
        if el.tag == "var":
            h.removeAttr(el, "data-var-ignore")
        # Strip the control attributes
        if el.tag == "pre":
            h.removeAttr(
                el,
                "path",
                "highlight",
                "line-start",
                "data-code-show",
                "line-highlight",
                "line-numbers",
            )
        h.removeAttr(
            el,
            "bs-autolink-syntax",
            "data-alternate-id",
            "highlight",
            "nohighlight",
            "line-numbers",
            "data-opaque",
            "data-no-self-link",
            "line-number",
            "caniuse",
            "data-silently-dedup",
            "nocrossorigin",
        )

        # Remove the internal-use-only detail of whether export/noexport is manual or default
        if el.get("data-export"):
            el.set("data-export", "")
        if el.get("data-noexport"):
            el.set("data-noexport", "")

        if doc.md.slimBuildArtifact:
            # Remove *all* data- attributes.
            for attrName in el.attrib:
                if attrName.startswith("data-"):
                    h.removeAttr(el, attrName)
    if head is not None:
        for el in strayHeadEls:
            head.append(el)
    for el in styleScoped:
        parent = h.parentElement(el)
        if parent is not None:
            h.prependChild(parent, el)
    for el in nestedLists:
        h.replaceWithContents(el)
    for el in flattenEls:
        h.moveContents(fromEl=el[0], toEl=el)


def finalHackyCleanup(text):
    # For hacky last-minute string-based cleanups of the rendered html.

    return text


def hackyLineNumbers(lines):
    # Hackily adds line-number information to each thing that looks like an open tag.
    # This is just regex text-munging, so potentially dangerous!
    for line in lines:
        line.text = re.sub(
            r"(^|[^<])(<[\w-]+)([ >])",
            rf"\1\2 line-number={line.i}\3",
            line.text,
        )
    return lines


def correctFrontMatter(doc: "t.SpecType"):
    # Detect and move around some bits of information,
    # if you provided them in your
    # If you provided an <h1> manually, use that element rather than whatever the boilerplate contains.
    h1s = [h1 for h1 in h.findAll("h1", doc) if h.isNormative(h1, doc)]
    if len(h1s) == 2:
        h.replaceNode(h1s[0], h1s[1])


def formatElementdefTables(doc: "t.SpecType"):
    for table in h.findAll("table.elementdef", doc):
        elements = h.findAll("tr:first-child dfn", table)
        elementsFor = " ".join(h.textContent(x) for x in elements)
        for el in h.findAll("a[data-element-attr-group]", table):
            groupName = h.textContent(el).strip()
            groupAttrs = sorted(
                doc.refs.queryAllRefs(linkType="element-attr", linkFor=groupName),
                key=lambda x: x.text,
            )
            if len(groupAttrs) == 0:
                m.die(
                    f"The element-attr group '{groupName}' doesn't have any attributes defined for it.",
                    el=el,
                )
                continue
            el.tag = "details"
            h.clearContents(el)
            h.removeAttr(el, "data-element-attr-group", "data-dfn-type")
            ul = h.appendChild(el, h.E.summary(h.E.a({"data-link-type": "dfn"}, groupName)), h.E.ul())
            for ref in groupAttrs:
                id = "element-attrdef-" + config.simplifyText(h.textContent(elements[0])) + "-" + ref.text
                h.appendChild(
                    ul,
                    h.E.li(
                        h.E.dfn(
                            {
                                "id": h.safeID(doc, id),
                                "for": elementsFor,
                                "data-dfn-type": "element-attr",
                            },
                            h.E.a(
                                {"data-link-type": "element-attr", "for": groupName},
                                ref.text.strip(),
                            ),
                        )
                    ),
                )


def formatArgumentdefTables(doc: "t.SpecType"):
    for table in h.findAll("table.argumentdef", doc):
        forMethod = doc.widl.normalized_method_names(table.get("data-dfn-for"))
        method = doc.widl.find(table.get("data-dfn-for"))
        if not method:
            m.die(f"Can't find method '{forMethod}'.", el=table)
            continue
        for i, tr in enumerate(h.findAll("tbody > tr", table)):
            try:
                argCell, typeCell, nullCell, optCell, _ = h.findAll("td", tr)
            except ValueError:
                m.die(
                    f"In the argumentdef table for '{method.full_name}', row {i} is misformatted, with {len(h.findAll('td', tr))} cells instead of 5.",
                    el=table,
                )
                continue
            argName = h.textContent(argCell).strip()
            arg = method.find_argument(argName)
            if arg:
                h.appendChild(typeCell, idl.nodesFromType(arg.type))
                if str(arg.type).strip().endswith("?"):
                    h.appendChild(nullCell, h.E.span({"class": "yes"}, "✔"))
                else:
                    h.appendChild(nullCell, h.E.span({"class": "no"}, "✘"))
                if arg.optional:
                    h.appendChild(optCell, h.E.span({"class": "yes"}, "✔"))
                else:
                    h.appendChild(optCell, h.E.span({"class": "no"}, "✘"))
            else:
                m.die(
                    f"Can't find the '{argName}' argument of method '{method.full_name}' in the argumentdef block.",
                    el=table,
                )
                continue


def inlineRemoteIssues(doc: "t.SpecType"):
    # Finds properly-marked-up "remote issues",
    # and inlines their contents into the issue.

    # Right now, only github inline issues are supported.
    # More can be supported when someone cares.

    # Collect all the inline issues in the document
    inlineIssues = []
    GitHubIssue = namedtuple("GitHubIssue", ["user", "repo", "num", "el"])
    for el in h.findAll("[data-inline-github]", doc):
        user, repo, num = el.get("data-inline-github", "").split()
        inlineIssues.append(GitHubIssue(user, repo, num, el=el))
        h.removeAttr(el, "data-inline-github")
    if not inlineIssues:
        return

    import requests

    logging.captureWarnings(True)

    responses = json.loads(doc.dataFile.fetch("github-issues.json", str=True))
    for i, issue in enumerate(inlineIssues):
        issueUserRepo = "{}/{}".format(*issue)
        key = f"{issueUserRepo}/{issue.num}"
        href = "https://github.{}/{}/issues/{}".format(doc.md.repository.ns, issueUserRepo, issue.num)
        url = "{}/repos/{}/issues/{}".format(doc.md.repository.api, issueUserRepo, issue.num)
        m.say("Fetching issue {:-3d}/{:d}: {:s}".format(i + 1, len(inlineIssues), key))

        # Fetch the issues
        headers = {"Accept": "application/vnd.github.v3.html+json"}
        if doc.token is not None:
            headers["Authorization"] = "token " + doc.token
        if key in responses:
            # Have a cached response, see if it changed
            headers["If-None-Match"] = responses[key]["ETag"]

        res = None
        try:
            res = requests.get(url, headers=headers)
        except requests.exceptions.ConnectionError:
            # Offline or something, recover if possible
            if key in responses:
                data = responses[key]
            else:
                m.warn(f"Connection error fetching issue #{issue.num}")
                continue
        if res is None:
            # Already handled in the except block
            pass
        elif res.status_code == 304:
            # Unchanged, I can use the cache
            data = responses[key]
        elif res.status_code == 200:
            # Fresh data, prep it for storage
            data = res.json()
            data["ETag"] = res.headers["ETag"]
        elif res.status_code == 401:
            error = res.json()
            if error["message"] == "Bad credentials":
                m.die(f"'{doc.token}' is not a valid GitHub OAuth token. See https://github.com/settings/tokens")
            else:
                m.die(
                    "401 error when fetching GitHub Issues:\n" + config.printjson(error),
                )
            continue
        elif res.status_code == 403:
            error = res.json()
            if error["message"].startswith("API rate limit exceeded"):
                m.die(
                    "GitHub Issues API rate limit exceeded. Get an OAuth token from https://github.com/settings/tokens to increase your limit, or just wait an hour for your limit to refresh; Bikeshed has cached all the issues so far and will resume from where it left off."
                )
            else:
                m.die(
                    "403 error when fetching GitHub Issues:\n" + config.printjson(error),
                )
            continue
        elif res.status_code >= 400:
            try:
                error = config.printjson(res.json())
            except ValueError:
                error = "First 100 characters of error:\n" + res.text[0:100]
            m.die(f"{res.status_code} error when fetching GitHub Issues:\n" + error)
            continue
        responses[key] = data
        # Put the issue data into the DOM
        el = issue.el
        data = responses[key]
        h.clearContents(el)
        if doc.md.inlineGithubIssues == "title":
            h.appendChild(
                el,
                h.E.a(
                    {"href": href, "class": "marker", "style": "text-transform:none"},
                    key,
                ),
                h.E.a({"href": href}, data["title"]),
            )
            h.addClass(el, "no-marker")
        else:
            h.appendChild(
                el,
                h.E.a(
                    {"href": href, "class": "marker"},
                    f"Issue #{data['number']} on GitHub: “{data['title']}”",
                ),
                *h.parseHTML(data["body_html"]),
            )
            h.addClass(el, "no-marker")
        if el.tag == "p":
            el.tag = "div"
    # Save the cache for later
    try:
        with open(config.scriptPath("spec-data", "github-issues.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(responses, ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as e:
        m.warn(f"Couldn't save GitHub Issues cache to disk.\n{e}")
    return


def addNoteHeaders(doc: "t.SpecType"):
    # Finds <foo heading="bar"> and turns it into a marker-heading
    for el in h.findAll("[heading]", doc):
        h.addClass(el, "no-marker")
        if h.hasClass(el, "note"):
            preText = "NOTE: "
        elif h.hasClass(el, "issue"):
            preText = "ISSUE: "
        elif h.hasClass(el, "example"):
            preText = "EXAMPLE: "
        else:
            preText = ""
        h.prependChild(el, h.E.div({"class": "marker"}, preText, *h.parseHTML(el.get("heading", ""))))
        h.removeAttr(el, "heading")


def locateFillContainers(doc: "t.SpecType"):
    fillContainers = defaultdict(list)
    for el in h.findAll("[data-fill-with]", doc):
        fillContainers[el.get("data-fill-with")].append(el)
    return fillContainers


def forceCrossorigin(doc: "t.SpecType"):
    if not doc.md.forceCrossorigin:
        return
    for el in h.findAll("link, script[src], audio, video, img", doc):
        if el.get("crossorigin") is not None or h.treeAttr(el, "nocrossorigin") is not None:
            continue
        el.set("crossorigin", "")


def addImageSize(doc: "t.SpecType"):
    if doc.md.imgAutoSize is False:
        return
    imgElements = h.findAll("img", doc)
    for el in imgElements:
        if el.get("width") or el.get("height"):
            continue
        if el.get("no-autosize") is not None:
            h.removeAttr(el, "no-autosize")
            continue
        src = el.get("src")
        srcset = el.get("srcset")
        res = 1
        if src is None and srcset is None:
            m.warn(
                "<img> elements must have at least one of src or srcset.",
                el=el,
            )
            continue
        elif src is not None and srcset is not None:
            continue
        elif src is None:
            match = re.match(r"^[ \t\n]*([^ \t\n]+)[ \t\n]+(\d+)x[ \t\n]*$", srcset or "")
            if match is None:
                m.die(
                    f"Couldn't parse 'srcset' attribute: \"{srcset}\"\n"
                    + "Bikeshed only supports a single image followed by an integer resolution. If not targeting Bikeshed specifically, HTML requires a 'src' attribute (and probably a 'width' and 'height' attribute too). This warning can also be suppressed by adding a 'no-autosize' attribute.",
                    el=el,
                )
                continue
            else:
                src = match.group(1)
                el.set("src", src)
                res = int(match.group(2) or "1")
        assert src is not None
        if not doc.inputSource.cheaplyExists(""):
            # If the input source can't tell whether a file cheaply exists,
            # PIL very likely can't use it either.
            m.warn(
                f"At least one <img> doesn't have its size set ({h.outerHTML(el)}), but given the type of input document, Bikeshed can't figure out what the size should be.\nEither set 'width'/'height' manually, or opt out of auto-detection by setting the 'no-autosize' attribute.",
                el=el,
            )
            return
        if re.match(r"^(https?:/)?/", src):
            m.warn(
                f"Autodetection of image dimensions is only supported for local files, skipping this image: {h.outerHTML(el)}\nConsider setting 'width' and 'height' manually or opting out of autodetection by setting the 'no-autosize' attribute.",
                el=el,
            )
            continue
        imgPath = doc.inputSource.relative(src).sourceName
        try:
            im = Image.open(imgPath)
            width, height = im.size
        except Exception as e:
            m.warn(
                f"Couldn't determine width and height of this image: {src}\n{e}",
                el=el,
            )
            continue
        if width % res == 0:
            el.set("width", str(int(width / res)))
        else:
            m.warn(
                f"The width ({width}px) of this image is not a multiple of the declared resolution ({res}): {src}\nConsider fixing the image so its width is a multiple of the resolution, or setting its 'width' and 'height' attribute manually.",
                el=el,
            )
        if height % res == 0:
            el.set("height", str(int(height / res)))
        else:
            m.warn(
                f"The height ({height}px) of this image is not a multiple of the declared resolution ({res}): {src}\nConsider fixing the image so its height is a multiple of the resolution, or setting its 'width' and 'height' attribute manually.",
                el=el,
            )


def processIDL(doc):
    localDfns = set()
    for pre in h.findAll("pre.idl, xmp.idl", doc):
        if pre.get("data-no-idl") is not None:
            continue
        if not h.isNormative(pre, doc):
            continue
        localDfns.update(idl.markupIDLBlock(pre, doc))

    dfns = h.findAll("pre.idl:not([data-no-idl]) dfn, xmp.idl:not([data-no-idl]) dfn", doc) + list(localDfns)
    classifyDfns(doc, dfns)
    h.fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get("id") is not None)
