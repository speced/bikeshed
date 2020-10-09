# -*- coding: utf-8 -*-


import io
import itertools
import json
import logging
import os
import re
import urllib.parse, urllib.error
from collections import defaultdict, namedtuple
from functools import partial as curry

from . import biblio
from . import config
from . import datablocks
from . import dfnpanels
from . import func
from . import markdown
from .h import *
from .messages import *

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
        for m in re.finditer(r"(\\`)|([\w-]*)(`+)", text):
            if mode == "text":
                if m.group(1):
                    newText += text[indexSoFar:m.start()] + m.group(1)[1]
                    indexSoFar = m.end()
                elif m.group(3):
                    mode = "code"
                    newText += text[indexSoFar:m.start()]
                    indexSoFar = m.end()
                    backtickCount = len(m.group(3))
                    tag = m.group(2)
                    literalStart = m.group(0)
            elif mode == "code":
                if m.group(1):
                    pass
                elif m.group(3):
                    if len(m.group(3)) != backtickCount:
                        pass
                    else:
                        mode = "text"
                        innerText = text[indexSoFar:m.start()] + m.group(2)
                        fullText = literalStart + text[indexSoFar:m.start()] + m.group(0)
                        replacement = (tag, innerText, fullText)
                        self.__codeSpanReplacements__.append(replacement)
                        newText += "\ue0ff"
                        indexSoFar = m.end()
        if mode == "text":
            newText += text[indexSoFar:]
        elif mode == "code":
            newText += tag + "`"*backtickCount + text[indexSoFar:]
        self.__val__ = newText

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
                    t = escapeHTML(repl[1]).strip(string.whitespace)
                    t = re.sub("[" + string.whitespace + "]{2,}", " ", t)
                    return "{2}<code data-opaque bs-autolink-syntax='{1}'>{0}</code>".format(t, escapeAttr(repl[2]), repl[0])
                else:
                    return "<code data-opaque data-span-tag={0} bs-autolink-syntax='{2}'>{1}</code>".format(repl[0], escapeHTML(repl[1]), escapeAttr(repl[2]))
            return re.sub("\ue0ff", codeSpanReviver, self.__val__)
        else:
            return self.__val__


def stripBOM(doc):
    if len(doc.lines) >= 1 and doc.lines[0].text[0:1] == "\ufeff":
        doc.lines[0].text = doc.lines[0].text[1:]
        warn("Your document has a BOM. There's no need for that, please re-save it without a BOM.")


# Definitions and the like

def fixManualDefTables(doc):
    # Def tables generated via datablocks are guaranteed correct,
    # but manually-written ones often don't link up the names in the first row.
    for table in findAll("table.propdef, table.descdef, table.elementdef", doc):
        if hasClass(table, "partial"):
            tag = "a"
            attr = "data-link-type"
        else:
            tag = "dfn"
            attr = "data-dfn-type"
        tag = "a" if hasClass(table, "partial") else "dfn"
        if hasClass(table, "propdef"):
            type = "property"
        elif hasClass(table, "descdef"):
            type = "descriptor"
        elif hasClass(table, "elementdef"):
            type = "element"
        cell = findAll("tr:first-child > :nth-child(2)", table)[0]
        names = [x.strip() for x in textContent(cell).split(',')]
        newContents = config.intersperse((createElement(tag, {attr:type}, name) for name in names), ", ")
        replaceContents(cell, newContents)


def canonicalizeShortcuts(doc):
    # Take all the invalid-HTML shortcuts and fix them.

    attrFixup = {
        "export":"data-export",
        "noexport":"data-noexport",
        "link-spec": "data-link-spec",
        "spec":"data-link-spec",
        "link-status": "data-link-status",
        "status":"data-link-status",
        "dfn-for":"data-dfn-for",
        "link-for":"data-link-for",
        "link-for-hint":"data-link-for-hint",
        "dfn-type":"data-dfn-type",
        "link-type":"data-link-type",
        "dfn-force": "data-dfn-force",
        "force":"data-dfn-force",
        "section":"data-section",
        "attribute-info":"data-attribute-info",
        "dict-member-info":"data-dict-member-info",
        "lt":"data-lt",
        "local-lt":"data-local-lt",
        "algorithm":"data-algorithm",
        "ignore":"data-var-ignore"
    }
    for el in findAll(",".join("[{0}]".format(attr) for attr in attrFixup.keys()), doc):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, el.get(attr))
                del el.attrib[attr]

    # The next two aren't in the above dict because some of the words conflict with existing attributes on some elements.
    # Instead, limit the search/transforms to the relevant elements.
    for el in findAll("dfn, h2, h3, h4, h5, h6", doc):
        for dfnType in config.dfnTypes:
            if el.get(dfnType) == "":
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
                break
    for el in findAll("a", doc):
        for linkType in config.linkTypes:
            if el.get(linkType) is not None:
                del el.attrib[linkType]
                el.set("data-link-type", linkType)
                break
    for el in findAll(config.dfnElementsSelector + ", a", doc):
        if el.get("for") is None:
            continue
        if el.tag == "a":
            el.set("data-link-for", el.get('for'))
        else:
            el.set("data-dfn-for", el.get('for'))
        del el.attrib['for']


def addImplicitAlgorithms(doc):
    # If a container has an empty `algorithm` attribute,
    # but it contains only a single `<dfn>`,
    # assume that the dfn is a description of the algorithm.
    for el in findAll("[data-algorithm='']:not(h1):not(h2):not(h3):not(h4):not(h5):not(h6)", doc):
        dfns = findAll("dfn", el)
        if len(dfns) == 1:
            dfnName = config.firstLinkTextFromElement(dfns[0])
            el.set("data-algorithm", dfnName)
            dfnFor = dfns[0].get('data-dfn-for')
            if dfnFor:
                el.set("data-algorithm-for", dfnFor)
        elif len(dfns) == 0:
            die("Algorithm container has no name, and there is no <dfn> to infer one from.", el=el)
        else:
            die("Algorithm container has no name, and there are too many <dfn>s to choose which to infer a name from.", el=el)


def checkVarHygiene(doc):
    def isAlgo(el):
        return el.get("data-algorithm") is not None
    def nearestAlgo(el):
        # Find the nearest "algorithm" container,
        # either an ancestor with [algorithm] or the nearest heading with same.
        if isAlgo(el):
            return el
        ancestor = closestAncestor(el, isAlgo)
        if ancestor is not None:
            return ancestor
        for h in relevantHeadings(el):
            if isAlgo(h):
                return h
    def algoName(el):
        # Finds a uniquified algorithm name from an algo container
        algo = nearestAlgo(el)
        if algo is None:
            return None
        algoName = algo.get("data-algorithm")
        algoFor = algo.get("data-algorithm-for")
        return f"'{algoName}'" + (f" for {algoFor}" if algoFor else "")

    # Look for vars that only show up once. These are probably typos.
    singularVars = []
    varCounts = defaultdict(lambda: 0)
    for el in findAll("var:not([data-var-ignore])", doc):
        key = (foldWhitespace(textContent(el)).strip(), algoName(el))
        varCounts[key] += 1
    foldedVarCounts = defaultdict(lambda: 0)
    atLeastOneAlgo = False
    for (var,algo),count in varCounts.items():
        if algo:
            atLeastOneAlgo = True
        if count > 1:
            continue
        if var.lower() in doc.md.ignoredVars:
            continue
        key = var, algo
        foldedVarCounts[key] += 1
    varLines = []
    for (var, algo),count in foldedVarCounts.items():
        if count == 1:
            if algo:
                varLines.append(f"  '{var}', in algorithm {algo}")
            else:
                varLines.append(f"  '{var}'")
    if varLines:
        warn("The following <var>s were only used once in the document:\n{0}\nIf these are not typos, please add an ignore='' attribute to the <var>.", "\n".join(varLines))

    if atLeastOneAlgo:
        addVarClickHighlighting(doc)

    # Look for algorithms that show up twice; these are errors.
    for algo, count in Counter(algoName(el) for el in findAll("[data-algorithm]", doc)).items():
        if count > 1:
            die(f"Multiple declarations of the {algo} algorithm.")
            return


def addVarClickHighlighting(doc):
    if doc.md.slimBuildArtifact:
        return
    doc.extraStyles["style-var-click-highlighting"] = '''
    var { cursor: pointer; }
    var.selected0 { background-color: #F4D200; box-shadow: 0 0 0 2px #F4D200; }
    var.selected1 { background-color: #FF87A2; box-shadow: 0 0 0 2px #FF87A2; }
    var.selected2 { background-color: #96E885; box-shadow: 0 0 0 2px #96E885; }
    var.selected3 { background-color: #3EEED2; box-shadow: 0 0 0 2px #3EEED2; }
    var.selected4 { background-color: #EACFB6; box-shadow: 0 0 0 2px #EACFB6; }
    var.selected5 { background-color: #82DDFF; box-shadow: 0 0 0 2px #82DDFF; }
    var.selected6 { background-color: #FFBCF2; box-shadow: 0 0 0 2px #FFBCF2; }
    '''
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
    doc.extraScripts["script-var-click-highlighting"] = '''
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
    '''


def fixIntraDocumentReferences(doc):
    ids = {el.get('id'):el for el in findAll("[id]", doc)}
    headingIDs = {el.get('id'):el for el in findAll("[id].heading", doc)}
    for el in findAll("a[href^='#']:not([href='#']):not(.self-link):not([data-link-type])", doc):
        targetID = urllib.parse.unquote(el.get("href")[1:])
        if el.get('data-section') is not None and targetID not in headingIDs:
            die("Couldn't find target document section {0}:\n{1}", targetID, outerHTML(el), el=el)
            continue
        elif targetID not in ids:
            die("Couldn't find target anchor {0}:\n{1}", targetID, outerHTML(el), el=el)
            continue
        if isEmpty(el):
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            target = ids[targetID]
            content = find(".content", target)
            if content is None:
                die("Tried to generate text for a section link, but the target isn't a heading:\n{0}", outerHTML(el), el=el)
                continue
            text = textContent(content).strip()
            if target.get('data-level') is not None:
                text = "§\u202f{1} {0}".format(text, target.get('data-level'))
            appendChild(el, text)


def fixInterDocumentReferences(doc):
    for el in findAll("[spec-section]", doc):
        spec = el.get('data-link-spec').lower()
        section = el.get('spec-section', '')
        if spec is None:
            die("Spec-section autolink doesn't have a 'spec' attribute:\n{0}", outerHTML(el), el=el)
            continue
        if section is None:
            die("Spec-section autolink doesn't have a 'spec-section' attribute:\n{0}", outerHTML(el), el=el)
            continue
        if spec in doc.refs.specs:
            # Bikeshed recognizes the spec
            fillInterDocumentReferenceFromShepherd(doc, el, spec, section)
            continue
        if not re.search(r"\d$", spec):
            # Unnumbered, check if there's a numbered variant in Shepherd
            vNames = doc.refs.vNamesFromSpecNames(spec)
            if len(vNames):
                fillInterDocumentReferenceFromShepherd(doc, el, vNames[0], section)
                if len(vNames) > 1:
                    die("Section autolink {2} attempts to link to unversioned spec name '{0}', "+
                         "but that spec is versioned as {1}. "+
                         "Please choose a versioned spec name.",
                        spec,
                        config.englishFromList("'{0}'".format(x) for x in vNames),
                        outerHTML(el),
                        el=el)
                continue
        if doc.refs.getBiblioRef(spec):
            # Bikeshed doesn't know the spec, but it's in biblio
            fillInterDocumentReferenceFromSpecref(doc, el, spec, section)
            continue
        # Unknown spec
        die("Spec-section autolink tried to link to non-existent '{0}' spec:\n{1}", spec, outerHTML(el), el=el)


def fillInterDocumentReferenceFromShepherd(doc, el, spec, section):
    specData = doc.refs.fetchHeadings(spec)
    if section in specData:
        heading = specData[section]
    else:
        die("Couldn't find section '{0}' in spec '{1}':\n{2}", section, spec, outerHTML(el), el=el)
        return
    if isinstance(heading, list):
        # Multipage spec
        if len(heading) == 1:
            # only one heading of this name, no worries
            heading = specData[heading[0]]
        else:
            # multiple headings of this id, user needs to disambiguate
            die("Multiple headings with id '{0}' for spec '{1}'. Please specify:\n{2}", section, spec, "\n".join("  [[{0}]]".format(spec + x) for x in heading), el=el)
            return
    if doc.md.status == "current":
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
    el.set("href", heading['url'])
    if isEmpty(el):
        el.text = "{spec} §{number} {text}".format(**heading)
    removeAttr(el, 'data-link-spec', 'spec-section')

def fillInterDocumentReferenceFromSpecref(doc, el, spec, section):
    bib = doc.refs.getBiblioRef(spec)
    if isinstance(bib, biblio.StringBiblioEntry):
        die("Can't generate a cross-spec section ref for '{0}', because the biblio entry has no url.", spec, el=el)
        return
    el.tag = "a"
    el.set("href", bib.url + section)
    if isEmpty(el):
        el.text = bib.title + " §" + section[1:]
    removeAttr(el, 'data-link-spec', 'spec-section')





def processDfns(doc):
    dfns = findAll(config.dfnElementsSelector, doc)
    classifyDfns(doc, dfns)
    fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)


def determineDfnType(dfn, inferCSS=False):
    # 1. Look at data-dfn-type
    if dfn.get('data-dfn-type'):
        return dfn.get('data-dfn-type')
    # 2. Look for a prefix on the id
    if dfn.get('id'):
        id = dfn.get('id')
        for prefix, type in config.dfnClassToType.items():
            if id.startswith(prefix):
                return type
    # 3. Look for a class or data-dfn-type on the ancestors
    for ancestor in dfn.iterancestors():
        if ancestor.get('data-dfn-type'):
            return ancestor.get('data-dfn-type')
        for cls, type in config.dfnClassToType.items():
            if hasClass(ancestor, cls):
                return type
            if hasClass(ancestor, "idl") and not hasClass(ancestor, "extract"):
                return "interface"
    # 4. Introspect on the text
    if inferCSS:
        text = textContent(dfn)
        if text[0:1] == "@":
            return "at-rule"
        elif len(dfn) == 1 and dfn[0].get('data-link-type') == "maybe" and emptyText(dfn.text) and emptyText(dfn[0].tail):
            return "value"
        elif text[0:1] == "<" and text[-1:] == ">":
            return "type"
        elif text[0:1] == ":":
            return "selector"
        elif re.match(r"^[\w-]+\(.*\)$", text) and not (dfn.get('id') or '').startswith("dom-"):
            return "function"
    # 5. Assume it's a "dfn"
    return "dfn"


def classifyDfns(doc, dfns):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el, inferCSS=doc.md.inferCSSDfns)
        if dfnType not in config.dfnTypes:
            die("Unknown dfn type '{0}' on:\n{1}", dfnType, outerHTML(el), el=el)
            continue
        dfnFor = treeAttr(el, "data-dfn-for")
        primaryDfnText = config.firstLinkTextFromElement(el)
        if primaryDfnText is None:
            die("Dfn has no linking text:\n{0}", outerHTML(el), el=el)
            continue
        if len(primaryDfnText) > 300:
            # Almost certainly accidentally missed the end tag
            warn("Dfn has extremely long text - did you forget the </dfn> tag?\n{0}", outerHTML(el), el=el)
        # Check for invalid fors, as it's usually some misnesting.
        if dfnFor and dfnType in config.typesNotUsingFor:
            die("'{0}' definitions don't use a 'for' attribute, but this one claims it's for '{1}' (perhaps inherited from an ancestor). This is probably a markup error.\n{2}", dfnType, dfnFor, outerHTML(el), el=el)
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        # Push the for value too.
        if dfnFor:
            el.set('data-dfn-for', dfnFor)
        elif dfnType in config.typesUsingFor:
            die("'{0}' definitions need to specify what they're for.\nAdd a 'for' attribute to {1}, or add 'dfn-for' to an ancestor.", dfnType, outerHTML(el), el=el)
            continue
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.search(r"\(.*\)$", primaryDfnText):
                die("Function/methods must end with a () arglist in their linking text. Got '{0}'.", primaryDfnText, el=el)
                continue
            if not re.match(r"^[\w\[\]-]+\s*\(", primaryDfnText):
                die("Function/method names can only contain alphanums, underscores, dashes, or []. Got '{0}'.", primaryDfnText, el=el)
                continue
            elif el.get('data-lt') is None:
                if dfnType == "function":
                    # CSS function, define it with no args in the text
                    primaryDfnText = re.match(r"^([\w\[\]-]+)\(.*\)$", primaryDfnText).group(1) + "()"
                    el.set('data-lt', primaryDfnText)
                elif dfnType in config.idlTypes:
                    # IDL methodish construct, ask the widlparser what it should have.
                    # If the method isn't in any IDL, this tries its best to normalize it anyway.
                    names = list(doc.widl.normalized_method_names(primaryDfnText, el.get('data-dfn-for')))
                    primaryDfnText = names[0]
                    el.set('data-lt', "|".join(names))
                else:
                    die("BIKESHED ERROR: Unhandled functionish type '{0}' in classifyDfns. Please report this to Bikeshed's maintainer.", dfnType, el=el)
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get('data-dfn-for') is None:
            parent = el.getparent()
            parentFor = parent.get('data-dfn-for')
            if parent.get('data-dfn-type') in config.functionishTypes and parentFor is not None:
                dfnFor = ", ".join(parentFor + "/" + name for name in doc.widl.normalized_method_names(textContent(parent), parentFor))
            elif treeAttr(el, "data-dfn-for") is None:
                die("'argument' dfns need to specify what they're for, or have it be inferrable from their parent. Got:\n{0}", outerHTML(el), el=el)
                continue
        # Automatically fill in id if necessary.
        if el.get('id') is None:
            if dfnFor:
                singleFor = config.splitForValues(dfnFor)[0]
            if dfnType in config.functionishTypes.intersection(config.idlTypes):
                id = config.simplifyText("{_for}-{id}".format(_for=singleFor, id=re.match(r"[^(]*", primaryDfnText).group(0) + "()"))
                el.set("data-alternate-id", config.simplifyText("dom-{_for}-{id}".format(_for=singleFor, id=primaryDfnText)))
                if primaryDfnText.startswith("[["):
                    # Slots get their identifying [] stripped from their ID,
                    # so gotta dedup them some other way.
                    id += "-slot"
                    el.set("data-alternate-id", "{0}-slot".format(el.get("data-alternate-id")))
            else:
                if dfnFor:
                    id = config.simplifyText("{_for}-{id}".format(_for=singleFor, id=primaryDfnText))
                else:
                    id = config.simplifyText(primaryDfnText)
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                pass
            elif dfnType == "event":
                # Special case 'event' because it needs a different format from IDL types
                id = config.simplifyText("{type}-{id}".format(type=dfnTypeToPrefix[dfnType], _for=singleFor, id=id))
            elif dfnType == "attribute" and primaryDfnText.startswith("[["):
                # Slots get their identifying [] stripped from their ID, so gotta dedup them some other way.
                id = config.simplifyText("dom-{id}-slot".format(_for=singleFor, id=id))
            elif dfnType in config.idlTypes.intersection(config.typesUsingFor):
                id = config.simplifyText("dom-{id}".format(id=id))
            else:
                id = "{type}-{id}".format(type=dfnTypeToPrefix[dfnType], id=id)
            el.set('id', safeID(doc, id))
        # Set lt if it's not set,
        # and doing so won't mess with anything else.
        if el.get('data-lt') is None and "|" not in primaryDfnText:
            el.set('data-lt', primaryDfnText)
        # Push export/noexport down to the definition
        if el.get('data-export') is None and el.get('data-noexport') is None:
            attr,_ = closestAttr(el, "data-export", "data-noexport")
            if attr is not None:
                el.set(attr, "")
            else:
                if dfnType == "dfn":
                    el.set('data-noexport', 'by-default')
                else:
                    el.set('data-export', 'by-default')
        # If it's an code-ish type such as IDL,
        # and doesn't already have a sole <code> child,
        # wrap the contents in a <code>.
        if config.linkTypeIn(dfnType, "codelike"):
            child = hasOnlyChild(el)
            if child is not None and child.tag == "code":
                continue
            if el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                # Don't wrap headings, it looks bad.
                continue
            wrapContents(el, E.code())


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    if linkType:
        if linkType in config.linkTypes:
            return linkType
        die("Unknown link type '{0}' on:\n{1}", linkType, outerHTML(el), el=el)
        return "unknown-type"
    # 2. Introspect on the text
    text = textContent(el)
    if config.typeRe["at-rule"].match(text):
        return "at-rule"
    elif config.typeRe["type"].match(text):
        return "type"
    elif config.typeRe["selector"].match(text):
        return "selector"
    elif config.typeRe["function"].match(text):
        return "functionish"
    else:
        return "dfn"


def determineLinkText(el):
    linkType = el.get('data-link-type')
    contents = textContent(el)
    if el.get('data-lt'):
        linkText = el.get('data-lt')
    elif config.linkTypeIn(linkType, "function") and re.match(r"^[\w-]+\(.*\)$", contents):
        # Remove arguments from CSS function autolinks,
        # as they should always be defined argument-less
        # (and this allows filled-in examples to still autolink).
        linkText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1) + "()"
    else:
        linkText = contents
    linkText = foldWhitespace(linkText)
    if len(linkText) == 0:
        die("Autolink {0} has no linktext.", outerHTML(el), el=el)
    return linkText


def classifyLink(el):
    linkType = determineLinkType(el)
    el.set('data-link-type', linkType)

    linkText = determineLinkText(el)
    el.set('data-lt', linkText)

    for attr in ["data-link-status", "data-link-for", "data-link-spec", "data-link-for-hint"]:
        val = treeAttr(el, attr)
        if val is not None:
            el.set(attr, val)
    return el

# Additional Processing


def processBiblioLinks(doc):
    biblioLinks = findAll("a[data-link-type='biblio']", doc)
    for el in biblioLinks:
        biblioType = el.get('data-biblio-type')
        if biblioType == "normative":
            storage = doc.normativeRefs
        elif biblioType == "informative":
            storage = doc.informativeRefs
        else:
            die("Unknown data-biblio-type value '{0}' on {1}. Only 'normative' and 'informative' allowed.", biblioType, outerHTML(el), el=el)
            continue

        linkText = determineLinkText(el)
        if linkText[0] == "[" and linkText[-1] == "]":
            linkText = linkText[1:-1]

        refStatus = treeAttr(el, "data-biblio-status") or doc.md.defaultRefStatus

        okayToFail = el.get('data-okay-to-fail') is not None

        ref = doc.refs.getBiblioRef(linkText, status=refStatus, generateFakeRef=okayToFail, quiet=okayToFail, el=el)
        if not ref:
            if not okayToFail:
                closeBiblios = biblio.findCloseBiblios(doc.refs.biblioKeys, linkText)
                die("Couldn't find '{0}' in bibliography data. Did you mean:\n{1}", linkText, '\n'.join("  " + b for b in closeBiblios), el=el)
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
                die("The biblio refs [[{0}]] and [[{1}]] are both aliases of the same base reference [[{2}]]. Please choose one name and use it consistently.", linkText, ref.linkText, ref.originalLinkText, el=el)
                # I can keep going, tho - no need to skip this ref
        else:
            # This is the first time I've reffed this particular biblio.
            # Register this as the preferred name...
            doc.refs.preferredBiblioNames[ref.linkText] = linkText
            # Use it on the current ref. Future ones will use the preferred name automatically.
            ref.linkText = linkText
        storage[ref.linkText] = ref

        id = config.simplifyText(ref.linkText)
        el.set('href', '#biblio-' + id)

        biblioDisplay = el.get("data-biblio-display", doc.md.defaultBiblioDisplay)
        if biblioDisplay == "inline":
            replaceContents(el, ref.title)



def verifyUsageOfAllLocalBiblios(doc):
    '''
    Verifies that all the locally-declared biblios
    (those written inline in a <pre class=biblio> block,
    and thus given order=1)
    were used in the spec,
    so you can remove entries when they're no longer necessary.
    '''
    usedBiblioKeys = set(x.lower() for x in list(doc.normativeRefs.keys()) + list(doc.informativeRefs.keys()))
    localBiblios = [b["linkText"].lower() for bs in doc.refs.biblios.values() for b in bs if b['order'] == 1]
    unusedBiblioKeys = []
    for b in localBiblios:
        if b not in usedBiblioKeys:
            unusedBiblioKeys.append(b)
    if unusedBiblioKeys:
        warn("The following locally-defined biblio entries are unused and can be removed:\n{0}",
             "\n".join("  * {0}".format(b) for b in unusedBiblioKeys))


def processAutolinks(doc):
    # An <a> without an href is an autolink.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # We exclude bibliographical links, as those are processed in `processBiblioLinks`.
    query = "a:not([href]):not([data-link-type='biblio'])"
    if doc.md.useIAutolinks:
        warn("Use <i> Autolinks is deprecated and will be removed. Please switch to using <a> elements.")
        query += ", i"
    autolinks = findAll(query, doc)
    for el in autolinks:
        # Explicitly empty linking text indicates this shouldn't be an autolink.
        if el.get('data-lt') == '':
            continue

        classifyLink(el)
        linkType = el.get('data-link-type')
        linkText = el.get('data-lt')

        # Properties and descriptors are often written like 'foo-*'. Just ignore these.
        if linkType in ("property", "descriptor", "propdesc") and "*" in linkText:
            continue

        # Links can have multiple for values in cases like IDL constructors,
        # where there are several valid ways to set up the dfn
        # and my autogenerated links want to make sure that they'll link successfully
        # to any variant that the spec author uses.
        linkFors = config.splitForValues(el.get('data-link-for'))

        # Status used to use ED/TR, so convert those if they appear,
        # and verify
        status = el.get('data-link-status')
        if status == "ED":
            status = "current"
        elif status == "TR":
            status = "snapshot"
        elif status in config.linkStatuses or status is None:
            pass
        else:
            die("Unknown link status '{0}' on {1}", status, outerHTML(el))
            continue

        ref = doc.refs.getRef(linkType, linkText,
                              spec=el.get('data-link-spec'),
                              status=status,
                              linkFor=linkFors,
                              linkForHint=el.get('data-link-for-hint'),
                              explicitFor=doc.md.assumeExplicitFor,
                              el=el,
                              error=(linkText.lower() not in doc.md.ignoredTerms))
        # Capture the reference (and ensure we add a biblio entry) if it
        # points to an external specification. We check the spec name here
        # rather than checking `status == "local"`, as "local" refs include
        # those defined in `<pre class="anchor">` datablocks, which we do
        # want to capture here.
        if ref and ref.spec and doc.refs.spec and ref.spec.lower() != doc.refs.spec.lower():
            spec = ref.spec.lower()
            key = ref.for_[0] if ref.for_ else ""
            if isNormative(el, doc):
                biblioStorage = doc.normativeRefs
            else:
                biblioStorage = doc.informativeRefs
            biblioRef = doc.refs.getBiblioRef(ref.spec, status=doc.md.defaultRefStatus, generateFakeRef=True, quiet=True)
            if biblioRef:
                biblioStorage[biblioRef.linkText] = biblioRef
                spec = biblioRef.linkText.lower()
            doc.externalRefsUsed[spec][ref.text][key] = ref

        if ref:
            el.set('href', ref.url)
            el.tag = "a"
            decorateAutolink(doc, el, linkType=linkType, linkText=linkText, ref=ref)
        else:
            if linkType == "maybe":
                el.tag = "css"
                if el.get("data-link-type"):
                    del el.attrib["data-link-type"]
                if el.get("data-lt"):
                    del el.attrib["data-lt"]
    dedupIDs(doc)


def decorateAutolink(doc, el, linkType, linkText, ref):
    # Add additional effects to autolinks.
    if doc.md.slimBuildArtifact:
        return

    # Put an ID on every reference, so I can link to references to a term.
    if el.get('id') is None:
        _,_,id = ref.url.partition("#")
        if id:
            el.set('id', "ref-for-{0}".format(id))
            el.set('data-silently-dedup', '')

    # Get all the values that the type expands to, add it as a title.
    if linkType == "type":
        titleText = None
        if linkText in doc.typeExpansions:
            titleText = doc.typeExpansions[linkText]
        else:
            refs = doc.refs.queryAllRefs(linkFor=linkText, ignoreObsoletes=True)
            texts = sorted({ref.text for ref in refs})
            if refs:
                titleText = "Expands to: " + ' | '.join(texts)
                doc.typeExpansions[linkText] = titleText
        if titleText:
            el.set('title', titleText)


def removeMultipleLinks(doc):
    # If there are multiple autolinks to the same thing in a paragraph,
    # only keep the first.
    if not doc.md.removeMultipleLinks:
        return
    paras = defaultdict(lambda:defaultdict(list))
    for el in findAll("a[data-link-type]", doc):
        if hasAncestor(el, lambda x:x.tag in ["pre", "xmp"]):
            # Don't strip out repeated links from opaque elements
            continue
        paras[parentElement(el)][el.get("href")].append(el)
    for linkGroups in paras.values():
        for href,links in linkGroups.items():
            if len(links) > 1:
                for el in links[1:]:
                    el.tag = "span"
                    removeAttr(el, "href", "data-link-type")

def processIssuesAndExamples(doc):
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues and
    # examples, and link to remote issues if possible:
    for el in findAll(".issue:not([id])", doc):
        el.set('id', safeID(doc, "issue-" + hashContents(el)))
        remoteIssueID = el.get('data-remote-issue-id')
        if remoteIssueID:
            del el.attrib['data-remote-issue-id']
            # Eventually need to support a way to trigger other repo url structures,
            # but defaulting to GH is fine for now.
            githubMatch = re.match(r"\s*([\w-]+)/([\w-]+)#(\d+)\s*$", remoteIssueID)
            numberMatch = re.match(r"\s*(\d+)\s*$", remoteIssueID)
            remoteIssueURL = None
            if githubMatch:
                remoteIssueURL = "https://github.com/{0}/{1}/issues/{2}".format(*githubMatch.groups())
                if doc.md.inlineGithubIssues:
                    el.set("data-inline-github", "{0} {1} {2}".format(*githubMatch.groups()))
            elif numberMatch and doc.md.repository.type == "github":
                remoteIssueURL = doc.md.repository.formatIssueUrl(numberMatch.group(1))
                if doc.md.inlineGithubIssues:
                    el.set("data-inline-github", "{0} {1} {2}".format(doc.md.repository.user, doc.md.repository.repo, numberMatch.group(1)))
            elif doc.md.issueTrackerTemplate:
                remoteIssueURL = doc.md.issueTrackerTemplate.format(remoteIssueID)
            if remoteIssueURL:
                appendChild(el, " ", E.a({"href": remoteIssueURL}, "<" + remoteIssueURL + ">"))
    for el in findAll(".example:not([id])", doc):
        el.set('id', safeID(doc, "example-" + hashContents(el)))
    fixupIDs(doc, findAll(".issue, .example", doc))


def addSelfLinks(doc):
    if doc.md.slimBuildArtifact:
        return
    def makeSelfLink(el):
        return E.a({"href": "#" + escapeUrlFrag(el.get('id', '')), "class":"self-link"})

    dfnElements = findAll(config.dfnElementsSelector, doc)

    foundFirstNumberedSection = False
    for el in findAll("h2, h3, h4, h5, h6", doc):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get('data-level') is not None)
        if foundFirstNumberedSection:
            appendChild(el, makeSelfLink(el))
    for el in findAll(".issue[id], .example[id], .note[id], li[id], dt[id]", doc):
        if list(el.iterancestors("figure")):
            # Skipping - element is inside a figure and is part of an example.
            continue
        if el.get("data-no-self-link") is not None:
            continue
        if el.tag == "details":
            summary = find("summary", el)
            if summary is not None:
                insertAfter(summary, makeSelfLink(el))
                continue
        prependChild(el, makeSelfLink(el))
    if doc.md.useDfnPanels:
        dfnpanels.addDfnPanels(doc, dfnElements)
    else:
        for el in dfnElements:
            if list(el.iterancestors("a")):
                warn("Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {0}", outerHTML(el), el=el)
                continue
            appendChild(el, makeSelfLink(el))


def cleanupHTML(doc):
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
            die("<style scoped> is no longer part of HTML. Ensure your styles can apply document-globally and remove the scoped attribute.", el=el)
            styleScoped.append(el)

        # Convert the technically-invalid <nobr> element to an appropriate <span>
        if el.tag == "nobr":
            el.tag = "span"
            el.set("style", el.get('style', '') + ";white-space:nowrap")

        # And convert <xmp> to <pre>
        if el.tag == "xmp":
            el.tag = "pre"

        # If we accidentally recognized an autolink shortcut in SVG, kill it.
        if el.tag == "{http://www.w3.org/2000/svg}a" and el.get("data-link-type") is not None:
            removeAttr(el, "data-link-type")
            el.tag = "{http://www.w3.org/2000/svg}tspan"

        # Add .algorithm to [algorithm] elements, for styling
        if el.get("data-algorithm") is not None and not hasClass(el, "algorithm"):
            addClass(el, "algorithm")

        # Allow MD-generated lists to be surrounded by HTML list containers,
        # so you can add classes/etc without an extraneous wrapper.
        if el.tag in ["ol", "ul", "dl"]:
            onlyChild = hasOnlyChild(el)
            if onlyChild is not None and el.tag == onlyChild.tag and el.get("data-md") is None and onlyChild.get("data-md") is not None:
                # The md-generated list container is featureless,
                # so we can just throw it away and move its children into its parent.
                nestedLists.append(onlyChild)
            else:
                # Remove any lingering data-md attributes on lists that weren't using this container replacement thing.
                removeAttr(el, "data-md")

        # Mark pre.idl blocks as .def, for styling
        if el.tag == "pre" and hasClass(el, "idl") and not hasClass(el, "def"):
            addClass(el, "def")

        # Tag classes on wide types of dfns/links
        if el.tag in config.dfnElements:
            if el.get("data-dfn-type") in config.idlTypes:
                addClass(el, "idl-code")
            if el.get("data-dfn-type") in config.maybeTypes.union(config.linkTypeToDfnType['propdesc']):
                if not hasAncestor(el, lambda x:x.tag=="pre"):
                    addClass(el, "css")
        if el.tag == "a":
            if el.get("data-link-type") in config.idlTypes:
                addClass(el, "idl-code")
            if el.get("data-link-type") in config.maybeTypes.union(config.linkTypeToDfnType['propdesc']):
                if not hasAncestor(el, lambda x:x.tag=="pre"):
                    addClass(el, "css")

        # Remove duplicate linking texts.
        if el.tag in config.anchorishElements and el.get("data-lt") is not None and el.get("data-lt") == textContent(el, exact=True):
            removeAttr(el, "data-lt")

        # Transform the <css> fake tag into markup.
        # (Used when the ''foo'' shorthand doesn't work.)
        if el.tag == "css":
            el.tag = "span"
            addClass(el, "css")

        # Transform the <assert> fake tag into a span with a unique ID based on its contents.
        # This is just used to tag arbitrary sections with an ID so you can point tests at it.
        # (And the ID will be guaranteed stable across publications, but guaranteed to change when the text changes.)
        if el.tag == "assert":
            el.tag = "span"
            el.set("id", safeID(doc, "assert-" + hashContents(el)))

        # Add ARIA role of "note" to class="note" elements
        if el.tag in ["div", "p"] and hasClass(el, doc.md.noteClass):
            el.set("role", "note")

        # Look for nested <a> elements, and warn about them.
        if el.tag == "a" and hasAncestor(el, lambda x:x.tag=="a"):
            warn("The following (probably auto-generated) link is illegally nested in another link:\n{0}", outerHTML(el), el=el)

        # If the <h1> contains only capital letters, add a class=allcaps for styling hook
        if el.tag == "h1":
            for letter in textContent(el):
                if letter.isalpha() and letter.islower():
                    break
            else:
                addClass(el, "allcaps")

        # If a markdown-generated <dt> contains only a single paragraph,
        # remove that paragraph so it just contains naked text.
        if el.tag == "dt" and el.get("data-md") is not None:
            child = hasOnlyChild(el)
            if child is not None and child.tag == "p" and emptyText(el.text) and emptyText(child.tail):
                flattenEls.append(el)

        # Remove a bunch of attributes
        if el.get("data-attribute-info") is not None or el.get("data-dict-member-info") is not None:
            removeAttr(el, 'data-attribute-info', 'data-dict-member-info', 'for')
        if el.tag in ["a", "span"]:
            removeAttr(el, 'data-link-for', 'data-link-for-hint', 'data-link-status', 'data-link-spec', 'data-section', 'data-biblio-type', 'data-biblio-status', 'data-okay-to-fail', 'data-lt')
        if el.tag != "a":
            removeAttr(el, 'data-link-for', 'data-link-type')
        if el.tag not in config.dfnElements:
            removeAttr(el, 'data-dfn-for', 'data-dfn-type', 'data-export', 'data-noexport')
        if el.tag == "var":
            removeAttr(el, 'data-var-ignore')
        removeAttr(el, 'bs-autolink-syntax', 'data-alternate-id', 'highlight', 'nohighlight', 'line-numbers', 'data-opaque', 'data-no-self-link', "line-number", "caniuse", "data-silently-dedup", "nocrossorigin")

        # Remove the internal-use-only detail of whether export/noexport is manual or default
        if el.get("data-export"):
            el.set("data-export", "")
        if el.get("data-noexport"):
            el.set("data-noexport", "")

        if doc.md.slimBuildArtifact:
            # Remove *all* data- attributes.
            for attrName in el.attrib:
                if attrName.startswith("data-"):
                    removeAttr(el, attrName)
    for el in strayHeadEls:
        head.append(el)
    for el in styleScoped:
        parent = parentElement(el)
        prependChild(parent, el)
    for el in nestedLists:
        children = childNodes(el, clear=True)
        parent = parentElement(el)
        clearContents(parent)
        appendChild(parent, *children)
    for el in flattenEls:
        moveContents(fromEl=el[0], toEl=el)


def finalHackyCleanup(text):
    # For hacky last-minute string-based cleanups of the rendered html.

    return text


def hackyLineNumbers(lines):
    # Hackily adds line-number information to each thing that looks like an open tag.
    # This is just regex text-munging, so potentially dangerous!
    for line in lines:
        line.text = re.sub(r"(^|[^<])(<[\w-]+)([ >])", r"\1\2 line-number={0}\3".format(line.i), line.text)
    return lines


def correctH1(doc):
    # If you provided an <h1> manually, use that element rather than whatever the boilerplate contains.
    h1s = [h1 for h1 in findAll("h1", doc) if isNormative(h1, doc)]
    if len(h1s) == 2:
        replaceNode(h1s[0], h1s[1])


def formatElementdefTables(doc):
    for table in findAll("table.elementdef", doc):
        elements = findAll("tr:first-child dfn", table)
        elementsFor = ' '.join(textContent(x) for x in elements)
        for el in findAll("a[data-element-attr-group]", table):
            groupName = textContent(el).strip()
            groupAttrs = sorted(doc.refs.queryAllRefs(linkType="element-attr", linkFor=groupName), key=lambda x:x.text)
            if len(groupAttrs) == 0:
                die("The element-attr group '{0}' doesn't have any attributes defined for it.", groupName, el=el)
                continue
            el.tag = "details"
            clearContents(el)
            removeAttr(el, "data-element-attr-group", "data-dfn-type")
            ul = appendChild(el,
                             E.summary(
                                 E.a({"data-link-type":"dfn"}, groupName)),
                             E.ul())
            for ref in groupAttrs:
                id = "element-attrdef-" + config.simplifyText(textContent(elements[0])) + "-" + ref.text
                appendChild(ul,
                            E.li(
                                E.dfn({"id": safeID(doc, id), "for":elementsFor, "data-dfn-type":"element-attr"},
                                      E.a({"data-link-type":"element-attr", "for":groupName},
                                          ref.text.strip()))))


def formatArgumentdefTables(doc):
    for table in findAll("table.argumentdef", doc):
        forMethod = doc.widl.normalized_method_names(table.get("data-dfn-for"))
        method = doc.widl.find(table.get("data-dfn-for"))
        if not method:
            die("Can't find method '{0}'.", forMethod, el=table)
            continue
        for tr in findAll("tbody > tr", table):
            tds = findAll("td", tr)
            argName = textContent(tds[0]).strip()
            arg = method.find_argument(argName)
            if arg:
                appendChild(tds[1], str(arg.type))
                if str(arg.type).strip().endswith("?"):
                    appendChild(tds[2],
                                E.span({"class":"yes"}, "✔"))
                else:
                    appendChild(tds[2],
                                E.span({"class":"no"}, "✘"))
                if arg.optional:
                    appendChild(tds[3],
                                E.span({"class":"yes"}, "✔"))
                else:
                    appendChild(tds[3],
                                E.span({"class":"no"}, "✘"))
            else:
                die(f"Can't find the '{argName}' argument of method '{method.full_name}' in the argumentdef block.", el=table)
                continue


def inlineRemoteIssues(doc):
    # Finds properly-marked-up "remote issues",
    # and inlines their contents into the issue.

    # Right now, only github inline issues are supported.
    # More can be supported when someone cares.

    # Collect all the inline issues in the document
    inlineIssues = []
    GitHubIssue = namedtuple('GitHubIssue', ['user', 'repo', 'num', 'el'])
    for el in findAll("[data-inline-github]", doc):
        inlineIssues.append(GitHubIssue(*el.get('data-inline-github').split(), el=el))
        removeAttr(el, "data-inline-github")
    if not inlineIssues:
        return

    import requests

    logging.captureWarnings(True)

    responses = json.loads(doc.dataFile.fetch("github-issues.json", str=True))
    for i,issue in enumerate(inlineIssues):
        issueUserRepo = "{0}/{1}".format(*issue)
        key = "{0}/{1}".format(issueUserRepo, issue.num)
        href = "https://github.{0}/{1}/issues/{2}".format(doc.md.repository.ns, issueUserRepo, issue.num)
        url = "{0}/repos/{1}/issues/{2}".format(doc.md.repository.api, issueUserRepo, issue.num)
        say("Fetching issue {:-3d}/{:d}: {:s}".format(i+1, len(inlineIssues), key))

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
                warn("Connection error fetching issue #{0}", issue.num)
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
                die("'{0}' is not a valid GitHub OAuth token. See https://github.com/settings/tokens", doc.token)
            else:
                die("401 error when fetching GitHub Issues:\n{0}", config.printjson(error))
            continue
        elif res.status_code == 403:
            error = res.json()
            if error["message"].startswith("API rate limit exceeded"):
                die("GitHub Issues API rate limit exceeded. Get an OAuth token from https://github.com/settings/tokens to increase your limit, or just wait an hour for your limit to refresh; Bikeshed has cached all the issues so far and will resume from where it left off.")
            else:
                die("403 error when fetching GitHub Issues:\n{0}", config.printjson(error))
            continue
        elif res.status_code >= 400:
            try:
                error = config.printjson(res.json())
            except:
                error = "First 100 characters of error:\n" + res.text[0:100]
            die("{0} error when fetching GitHub Issues:\n{1}", res.status_code, error)
            continue
        responses[key] = data
        # Put the issue data into the DOM
        el = issue.el
        data = responses[key]
        clearContents(el)
        if doc.md.inlineGithubIssues == 'title':
            appendChild(el,
                    E.a({"href":href, "class":"marker", "style":"text-transform:none"}, key),
                    E.a({"href":href}, data['title']))
            addClass(el, "no-marker")
        else:
            appendChild(el,
                    E.a({"href":href, "class":"marker"},
                    "Issue #{0} on GitHub: “{1}”".format(data['number'], data['title'])),
                    *parseHTML(data['body_html']))
            addClass(el, "no-marker")
        if el.tag == "p":
            el.tag = "div"
    # Save the cache for later
    try:
        with io.open(config.scriptPath("spec-data", "github-issues.json"), 'w', encoding="utf-8") as f:
            f.write(json.dumps(responses, ensure_ascii=False, indent=2, sort_keys=True))
    except Exception as e:
        warn("Couldn't save GitHub Issues cache to disk.\n{0}", e)
    return


def addNoteHeaders(doc):
    # Finds <foo heading="bar"> and turns it into a marker-heading
    for el in findAll("[heading]", doc):
        addClass(el, "no-marker")
        if hasClass(el, "note"):
            preText = "NOTE: "
        elif hasClass(el, "issue"):
            preText = "ISSUE: "
        elif hasClass(el, "example"):
            preText = "EXAMPLE: "
        else:
            preText = ""
        prependChild(el,
                     E.div({"class":"marker"}, preText, *parseHTML(el.get('heading'))))
        removeAttr(el, "heading")


def locateFillContainers(doc):
    fillContainers = defaultdict(list)
    for el in findAll("[data-fill-with]", doc):
        fillContainers[el.get("data-fill-with")].append(el)
    return fillContainers


def forceCrossorigin(doc):
    if not doc.md.forceCrossorigin:
        return
    for el in findAll("link, script[src], audio, video, img", doc):
        if el.get("crossorigin") is not None or treeAttr(el, "nocrossorigin") is not None:
            continue
        el.set("crossorigin", "")
