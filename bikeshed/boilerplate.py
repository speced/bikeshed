# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import copy
import os
import re
import subprocess
from collections import defaultdict
from .messages import *
from .htmlhelpers import *
from .DefaultOrderedDict import DefaultOrderedDict


def addBikeshedVersion(doc):
    # Adds a <meta> containing the current Bikeshed semver.
    if "generator" not in doc.md.boilerplate:
        return
    head = find("head", doc)
    bikeshedVersion = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=os.path.dirname(__file__)).rstrip()
    appendChild(head,
                E.meta({"name": "generator", "content": "Bikeshed version {0}".format(bikeshedVersion)}))


def addHeaderFooter(doc):
    header = config.retrieveBoilerplateFile(doc, 'header') if "header" in doc.md.boilerplate else ""
    footer = config.retrieveBoilerplateFile(doc, 'footer') if "footer" in doc.md.boilerplate else ""

    doc.html = '\n'.join([header, doc.html, footer])


def fillWith(tag, newElements, doc):
    for el in doc.fillContainers[tag]:
        replaceContents(el, newElements)


def getFillContainer(tag, doc, default=False):
    '''
    Gets the element that should be filled with the stuff corresponding to tag.
    If it returns None, don't generate the section.

    If default=True,
    indicates that this is a "default on" section,
    and will be appended to <body> unless explicitly suppressed.
    Otherwise,
    it'll only be appended if explicitly requested with a data-fill-with attribute.
    '''

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
    html = config.retrieveBoilerplateFile(doc, 'logo')
    html = doc.fixText(html)
    fillWith('logo', parseHTML(html), doc=doc)


def addCopyright(doc):
    html = config.retrieveBoilerplateFile(doc, 'copyright')
    html = doc.fixText(html)
    fillWith('copyright', parseHTML(html), doc=doc)


def addAbstract(doc):
    html = config.retrieveBoilerplateFile(doc, 'abstract')
    html = doc.fixText(html)
    fillWith('abstract', parseHTML(html), doc=doc)


def addStatusSection(doc):
    html = config.retrieveBoilerplateFile(doc, 'status')
    html = doc.fixText(html)
    fillWith('status', parseHTML(html), doc=doc)


def addObsoletionNotice(doc):
    if doc.md.warning:
        html = config.retrieveBoilerplateFile(doc, doc.md.warning[0])
        html = doc.fixText(html)
        fillWith('warning', parseHTML(html), doc=doc)


def addAtRisk(doc):
    if len(doc.md.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.md.atRisk:
        html += "<li>" + doc.fixText(feature)
    html += "</ul><p>“At-risk” is a W3C Process term-of-art, and does not necessarily imply that the feature is in danger of being dropped or delayed. It means that the WG believes the feature may have difficulty being interoperably implemented in a timely manner, and marking it as such allows the WG to drop the feature if necessary when transitioning to the Proposed Rec stage, without having to publish a new Candidate Rec without the feature first."
    fillWith('at-risk', parseHTML(html), doc=doc)


def addStyles(doc):
    el = getFillContainer('stylesheet', doc)
    if el is not None:
        el.text = config.retrieveBoilerplateFile(doc, 'stylesheet')


def addCustomBoilerplate(doc):
    for el in findAll('[boilerplate]', doc):
        tag = el.get('boilerplate')
        if doc.fillContainers[tag]:
            replaceContents(doc.fillContainers[tag][0], el)
            removeNode(el)


def removeUnwantedBoilerplate(doc):
    for tag,els in doc.fillContainers.items():
        if tag not in doc.md.boilerplate:
            for el in els:
                removeNode(el)


def addAnnotations(doc):
    if doc.md.vshortname in doc.testSuites and not doc.md.prepTR:
        html = config.retrieveBoilerplateFile(doc, 'annotations')
        html = doc.fixText(html)
        appendContents(find("head", doc), parseHTML(html))


def addBikeshedBoilerplate(doc):
    for k,v in doc.extraStyles.items():
        if k not in doc.md.doc.md.boilerplate:
            continue
        container = getFillContainer(k, doc)
        if container is None:
            container = getFillContainer("bs-styles", doc, default=True)
        if container is not None:
            appendChild(container,
                        E.style("/* {0} */\n".format(k) + v))
    for k,v in doc.extraScripts.items():
        if k not in doc.md.doc.md.boilerplate:
            continue
        container = getFillContainer(k, doc)
        if container is None:
            container = getFillContainer("bs-scripts", doc, default=True)
        if container is not None:
            appendChild(container,
                        E.script("/* {0} */\n".format(k) + v))


def addIndexSection(doc):
    if len(findAll(config.dfnElementsSelector, doc)) == 0 and len(doc.externalRefsUsed.keys()) == 0:
        return
    container = getFillContainer('index', doc=doc, default=True)
    if container is None:
        return
    appendChild(container,
                E.h2({"class":"no-num no-ref", "id":"index"}, "Index"))

    if len(findAll(config.dfnElementsSelector, doc)):
        addIndexOfLocallyDefinedTerms(doc, container)

    if len(doc.externalRefsUsed.keys()):
        addIndexOfExternallyDefinedTerms(doc, container)


def addIndexOfLocallyDefinedTerms(doc, container):
    appendChild(container,
                E.h3({"class":"no-num no-ref", "id":"index-defined-here"}, "Terms defined by this specification"))

    indexEntries = defaultdict(list)
    for el in findAll(config.dfnElementsSelector, doc):
        if el.get('id') is None or el.get('data-dfn-type') is None:
            continue
        linkTexts = config.linkTextsFromElement(el)
        headingLevel = headingLevelOfElement(el) or "Unnumbered section"
        type = el.get('data-dfn-type')
        if type == "argument":
            # Don't generate index entries for arguments.
            continue
        if el.get('data-dfn-for') is not None:
            disambiguator = "{0} for {1}".format(el.get('data-dfn-type'), ', '.join(config.splitForValues(el.get('data-dfn-for'))))
        elif type == "dfn":
            disambiguator = "definition of"
        else:
            disambiguator = "({0})".format(el.get('data-dfn-type'))

        id = el.get('id')
        for linkText in linkTexts:
            entry = {
                'url':"#" + id,
                'label':"§" + headingLevel,
                'disambiguator':disambiguator
            }
            indexEntries[linkText].append(entry)

    # Now print the indexes
    indexHTML = htmlFromIndexTerms(indexEntries)
    appendChild(container, indexHTML)


def addExplicitIndexes(doc):
    # Explicit indexes can be requested for specs with <index spec="example-spec-1"></index>

    for el in findAll("index", doc):
        indexEntries = defaultdict(list)
        status = el.get('status')
        if status and status not in config.specStatuses:
            die("<index> has unknown value '{0}' for status. Must be {1}.", status, config.englishFromList(config.specStatuses), el=el)
            continue
        if el.get('type'):
            types = set(x.strip() for x in el.get('type').split(','))
            for t in types:
                if t not in config.dfnTypes:
                    die("Unknown type value '{0}' on {1}".format(t, outerHTML(el)), el=el)
                    types.remove(t)
        else:
            types = None
        if el.get('spec'):
            specs = set(x.strip() for x in el.get('spec').split(','))
            for s in specs:
                if s not in doc.refs.specs:
                    die("Unknown spec name '{0}' on {1}".format(s, outerHTML(el)), el=el)
                    specs.remove(s)
        else:
            specs = None
        if el.get('for'):
            fors = set(x.strip() for x in el.get('for').split(','))
        else:
            fors = None
        if el.get('export'):
            exportVal = el.get('export').lower().strip()
            if exportVal in ["yes", "y", "true", "on"]:
                export = True
            elif exportVal in ["no", "n", "false", "off"]:
                export = False
            else:
                die("Unknown export value '{0}' (should be boolish) on {1}".format(exportVal, outerHTML(el)), el=el)
                export = None
        else:
            export = None
        for ref in doc.refs.queryAllRefs():
            text = ref.text.strip()
            if export is not None and ref.export != export:
                continue
            if specs is not None and ref.spec not in specs:
                continue
            if types is not None and ref.type not in types:
                continue
            if fors is not None and not (set(ref.for_) & fors):
                continue
            disambInfo = []
            if types is None or len(types) > 1:
                disambInfo.append(ref.type)
            if specs is None or len(specs) > 1:
                disambInfo.append("in " + ref.spec)
            if ref.for_:
                try:
                    disambInfo.append("for {0}".format(', '.join(x.strip() for x in ref.for_)))
                except:
                    # todo: The TR version of Position triggers this
                    pass
            disambiguator = ", ".join(disambInfo)
            entry = {'url': ref.url, 'disambiguator': disambiguator, 'label': None, 'status': ref.status}
            # TODO: This is n^2, iterating over all the entries on every new addition.
            for i,existingEntry in enumerate(indexEntries[text]):
                if existingEntry['disambiguator'] != disambiguator:
                    continue
                # Whoops, found an identical entry.
                if existingEntry['status'] != entry['status']:
                    if status:
                        if existingEntry['status'] == status:
                            # Existing entry matches stated status, do nothing and don't add it.
                            break
                        elif entry['status'] == status:
                            # New entry matches status, update and don't re-add it.
                            indexEntries[text][i] = entry
                            break
                    else:
                        # Default to preferring current specs
                        if existingEntry['status'] == "current":
                            break
                        elif entry['status'] == "current":
                            indexEntries[text][i] = entry
                            break
                else:
                    # Legit dupes. Shouldn't happen in a good spec, but whatever.
                    pass
            else:
                indexEntries[text].append(entry)
        appendChild(el, htmlFromIndexTerms(indexEntries))
        el.tag = "div"
        removeAttr(el, "export")
        removeAttr(el, "for")
        removeAttr(el, "spec")
        removeAttr(el, "status")
        removeAttr(el, "type")


def htmlFromIndexTerms(entries):
    # entries: dict (preferably OrderedDict, if you want stability) of linkText=>{url, label, disambiguator}
    # label is used for the actual link (normally heading level), disambiguator is phrase to use when there are collisions

    from collections import OrderedDict
    entries = OrderedDict(sorted(entries.items(), key=lambda x:re.sub(r'[^a-z0-9]', '', x[0].lower())))

    topList = E.ul({"class":"index"})
    for text, items in entries.items():
        if len(items) == 1:
            item = items[0]
            li = appendChild(topList,
                             E.li(
                                 E.a({"href":item['url']}, text),
                                 E.span(", in ", item['label']) if item['label'] else ""))
        else:
            li = appendChild(topList, E.li(text))
            ul = appendChild(li, E.ul())
            for item in items:
                appendChild(ul,
                            E.li(
                                E.a({"href":item['url']}, item['disambiguator']),
                                E.span(", in ", item['label']) if item['label'] else ""))
    return topList


def addIndexOfExternallyDefinedTerms(doc, container):
    if not doc.externalRefsUsed:
        return

    ul = E.ul({"class": "index"})
    for spec, refGroups in sorted(doc.externalRefsUsed.items(), key=lambda x:x[0]):
        # ref.spec is always lowercase; if the same string shows up in biblio data,
        # use its casing instead.
        biblioRef = doc.refs.getBiblioRef(spec, status="normative")
        if biblioRef:
            printableSpec = biblioRef.linkText
        else:
            printableSpec = spec
        attrs = {"data-lt":spec, "data-link-type":"biblio", "data-biblio-type":"informative", "data-okay-to-fail": "true"}
        specLi = appendChild(ul,
                             E.li(
                                 E.a(attrs, "[", printableSpec, "]"), " defines the following terms:"))
        termsUl = appendChild(specLi, E.ul())
        for text,refs in sorted(refGroups.items(), key=lambda x:x[0]):
            if len(refs) == 1:
                ref = refs.values()[0]
                appendChild(termsUl,
                            E.li(E.a({"href":ref.url}, ref.text)))
            else:
                for key,ref in sorted(refs.items(), key=lambda x:x[0]):
                    if key:
                        link = E.a({"href":ref.url},
                                   ref.text,
                                   " ",
                                   E.small({}, "(for {0})".format(key)))
                    else:
                        link = E.a({"href":ref.url},
                                   ref.text)
                    appendChild(termsUl, E.li(link))
    appendChild(container,
                E.h3({"class":"no-num no-ref", "id":"index-defined-elsewhere"}, "Terms defined by reference"),
                ul)


def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables

    if len(findAll("table.propdef, table.descdef", doc)) == 0:
        return
    html = getFillContainer('property-index', doc=doc, default=True)
    if html is None:
        return

    appendChild(html,
                E.h2({"class":"no-num no-ref", "id":"property-index"}, "Property Index"))

    def extractKeyValFromRow(tr, table):
        # Extract the key, minus the trailing :
        result = re.match(r'(.*):', textContent(row[0]).strip())
        if result is None:
            die("Propdef row headers must be a word followed by a colon. Got:\n{0}", textContent(row[0]).strip(), el=table)
            return '',''
        key = result.group(1).strip().capitalize()
        # Extract the value from the second cell
        val = textContent(row[1]).strip()
        return key, val
    # Extract propdef info
    props = []
    for table in findAll('table.propdef', doc):
        prop = {}
        names = []
        for row in findAll('tr', table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [textContent(x) for x in findAll('dfn', row[1])]
            else:
                prop[key] = val
        for name in names:
            tempProp = prop.copy()
            tempProp['Name'] = name
            props.append(tempProp)
    # Extract descdef info
    atRules = defaultdict(list)
    for table in findAll('table.descdef', doc):
        desc = {}
        names = []
        atRule = ""
        for row in findAll('tr', table):
            key, val = extractKeyValFromRow(row, table)
            if key == "Name":
                names = [textContent(x) for x in findAll('dfn', row[1])]
            elif key == "For":
                atRule = val
            else:
                desc[key] = val
        for name in names:
            tempDesc = desc.copy()
            tempDesc['Name'] = name
            atRules[atRule].append(tempDesc)

    def createRow(prop, linkType):
        return E.tr(
            E.th({"scope":"row"},
                 E.a({"data-link-type":linkType}, prop['Name'])),
            *[E.td(prop.get(column,"")) for column in columns[1:]])
    if len(props):
        # Set up the initial table columns for properties
        columns = ["Name", "Value", "Initial", "Applies to", "Inherited", "Percentages", "Media"]
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
        appendChild(html,
                    E.div({"class":"big-element-wrapper"},
                          E.table({"class":"index"},
                                  E.thead(
                              E.tr(
                                  *[E.th({"scope":"col"}, formatColumnName(column)) for column in columns])),
                                  E.tbody(
                              *[createRow(prop, "property") for prop in props]))))
    else:
        appendChild(html, E.p("No properties defined."))

    if len(atRules):
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
            appendChild(html,
                        E.h3({"class":"no-num no-ref", "id":config.simplifyText(atRuleName) + "-descriptor-table"},
                             E.a({"data-link-type":"at-rule"}, atRuleName),
                             " Descriptors"))
            appendChild(html,
                        E.div({"class":"big-element-wrapper"},
                              E.table({"class":"index"},
                                      E.thead(
                                  E.tr(
                                      *[E.th({"scope":"col"}, column) for column in columns])),
                                      E.tbody(
                                  *[createRow(desc, "descriptor") for desc in descs]))))


def addIDLSection(doc):
    idlBlocks = filter(isNormative, findAll("pre.idl", doc))
    if len(idlBlocks) == 0:
        return
    html = getFillContainer('idl-index', doc=doc, default=True)
    if html is None:
        return

    appendChild(html,
                E.h2({"class":"no-num no-ref", "id":"idl-index"}, "IDL Index"))

    container = appendChild(html, E.pre({"class":"idl"}))
    for block in idlBlocks:
        blockCopy = copy.deepcopy(block)
        appendContents(container, blockCopy)
        appendChild(container, "\n")
    for dfn in findAll("dfn[id]", container):
        dfn.tag = "a"
        dfn.set("href", "#" + dfn.get("id"))
        del dfn.attrib["id"]


def addTOCSection(doc):
    toc = getFillContainer("table-of-contents", doc=doc, default=False)
    if toc is None:
        return
    appendChild(toc,
                E.h2({"class": "no-num no-toc no-ref", "id":"contents"}, "Table of Contents"))

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
    containers[2] = appendChild(containers[1], E.ol({"class":"toc", "role":"directory"}))
    for header in findAll('h2, h3, h4, h5, h6', doc):
        level = int(header.tag[-1])
        container = containers[level]
        if isinstance(container, int):
            # Saw a low-level heading without first seeing a higher heading.
            die("Saw an <h{0}> without seeing an <h{1}> first. Please order your headings properly.\n{2}", level, level - 1, outerHTML(header), el=header)
            return
        if level > previousLevel + 1:
            # Jumping two levels is a no-no.
            die("Heading level jumps more than one level, from h{0} to h{1}:\n  {2}", previousLevel, level, textContent(header).replace("\n", " "), el=header)
            return

        addToTOC = True
        if hasClass(header, "no-toc"):
            # Hit a no-toc, suppress the entire section.
            addToTOC = False
        elif container is None:
            addToTOC = False
        elif (level-1) > doc.md.maxToCDepth:
            addToTOC = False

        if addToTOC:
            li = appendChild(container,
                             E.li(
                                 E.a({"href":"#" + header.get('id')},
                                     E.span({"class":"secno"},header.get('data-level', '')),
                                     " ",
                                     copy.deepcopy(find(".content", header)))))
            containers[level + 1] = appendChild(li, E.ol({"class":"toc"}))
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
        dd = E.dd({"class":"editor p-author h-card vcard"})
        if editor['w3cid']:
            dd.attrib['data-editor-id'] = editor['w3cid']
        if editor['link']:
            appendChild(dd, E.a({"class":"p-name fn u-url url", "href":editor['link']}, editor['name']))
        elif editor['email']:
            appendChild(dd, E.a({"class":"p-name fn u-email email", "href":"mailto:" + editor['email']}, editor['name']))
        else:
            appendChild(dd, E.span({"class":"p-name fn"}, editor['name']))
        if editor['org']:
            if editor['orglink']:
                el = E.a({"class":"p-org org", "href":editor['orglink']}, editor['org'])
            else:
                el = E.span({"class":"p-org org"}, editor['org'])
            appendChild(dd, " (", el, ")")
        if editor['email'] and editor['link']:
            appendChild(dd,
                        " ",
                        E.a({"class":"u-email email", "href":"mailto:" + editor['email']}, editor['email']))
        return dd

    def printTranslation(tr):
        lang = tr['lang-code']
        # canonicalize the lang-code structure
        lang = lang.lower().replace("_", "-")
        name = tr['name']
        nativeName = tr['native-name']
        url = tr['url']
        missingInfo = False
        if name is None:
            if lang in doc.languages:
                name = doc.languages[lang]['name']
            else:
                missingInfo = True
        if nativeName is None:
            if lang in doc.languages:
                nativeName = doc.languages[lang]['native-name']
            else:
                missingInfo = True
        if missingInfo:
            warn("Bikeshed doesn't have all the translation info for '{0}'. Please add to bikeshed/spec-data/readonly/languages.json and submit a PR!", lang)
        if nativeName:
            return E.span({"title": name or lang},
                          E.a({"href": url, "hreflang": lang, "rel": "alternate", "lang": lang},
                              nativeName))
        elif name:
            return E.a({"href": url, "hreflang": lang, "rel": "alternate", "title": lang},
                       name)
        else:
            return E.a({"href": url, "hreflang": lang, "rel": "alternate"},
                       lang)

    md = DefaultOrderedDict(list)
    mac = doc.macros
    if mac.get('version'):
        md["This version"].append(E.a({"href":mac['version'], "class":"u-url"}, mac['version']))
    if doc.md.TR:
        md["Latest published version"].append(E.a({"href": doc.md.TR}, doc.md.TR))
    if doc.md.ED and doc.md.status in config.snapshotStatuses:
        md["Editor's Draft"].append(E.a({"href": doc.md.ED}, doc.md.ED))
    if len(doc.md.previousVersions):
        md["Previous Versions"] = [E.a({"href":ver, "rel":"previous"}, ver) for ver in doc.md.previousVersions]
    if len(doc.md.versionHistory):
        md["Version History"] = [E.a({"href":vh}, vh) for vh in doc.md.versionHistory]
    if doc.md.mailingList:
        span = E.span(
            E.a({"href":"mailto:" + doc.md.mailingList + "?subject=%5B" + mac['shortname'] + "%5D%20YOUR%20TOPIC%20HERE"}, doc.md.mailingList),
            " with subject line “",
            E.kbd(
                "[",
                mac['shortname'],
                "] ",
                E.i({"lt":""}, "… message topic …")),
            "”")
        if doc.md.mailingListArchives:
            appendChild(span,
                        " (",
                        E.a({"rel":"discussion", "href":doc.md.mailingListArchives}, "archives"),
                        ")")
        md["Feedback"].append(span)
    if doc.md.testSuite is not None:
        md["Test Suite"].append(E.a({"href":doc.md.testSuite}, doc.md.testSuite))
    elif (doc.md.vshortname in doc.testSuites) and (doc.testSuites[doc.md.vshortname]['url'] is not None):
        url = doc.testSuites[doc.md.vshortname]['url']
        md["Test Suite"].append(E.a({"href":url}, url))
    if len(doc.md.issues):
        md["Issue Tracking"] = [E.a({"href":href}, text) for text,href in doc.md.issues]
    if len(doc.md.editors):
        editorTerm = doc.md.editorTerm['singular']
        md[editorTerm] = map(printEditor, doc.md.editors)
    if len(doc.md.previousEditors):
        editorTerm = doc.md.editorTerm['singular']
        md["Former " + editorTerm] = map(printEditor, doc.md.previousEditors)
    if len(doc.md.translations):
        md["Translations"] = map(printTranslation, doc.md.translations)
    if len(doc.md.audience):
        md["Audience"] = [", ".join(doc.md.audience)]
    if doc.md.toggleDiffs:
        md["Toggle Diffs"] = [E.label({"for": "hidedel", "id": "hidedel-label"}, "Hide deleted text")]
        prependChild(find("body", doc),
                     E.input({"type": "checkbox",
                              "id": "hidedel",
                              "style": "display:none"}))
        doc.extraStyles['style-hidedel'] = """
            #hidedel:checked ~ del, #hidedel:checked ~ * del { display:none; }
            #hidedel ~ #hidedel-label::before, #hidedel ~ * #hidedel-label::before { content: "☐ "; }
            #hidedel:checked ~ #hidedel-label::before, #hidedel:checked ~ * #hidedel-label::before { content: "☑ "; }
        """
    for key, vals in doc.md.otherMetadata.items():
        md[key].extend(parseHTML("<span>" + doc.fixText(val) + "</span>")[0] for val in vals)

    pluralization = {
        "Previous Version": "Previous Versions",
        "Test Suite": "Test Suites",
        doc.md.editorTerm['singular']: doc.md.editorTerm['plural'],
        "Former " + doc.md.editorTerm['singular']: "Former " + doc.md.editorTerm['plural']
    }

    dl = E.dl()
    for key, vals in md.items():
        # Pluralize appropriate words
        if len(vals) > 1 and key in pluralization:
            displayKey = pluralization[key]
        else:
            displayKey = key
        if key in ("Editor", "Former Editor"):
            # A bunch of Microformats stuff is preloading on the <dd>s,
            # so this prevents code from genning an extra wrapper <dd>.
            appendChild(dl,
                        E.dt({"class": "editor"}, displayKey, ":"),
                        *vals)
        elif key == "Translations":
            appendChild(dl,
                        E.dt(displayKey, " ",
                             E.small("(non-normative and likely out-of-date)"),
                             ":"),
                        *[E.dd(val) for val in vals])
        else:
            appendChild(dl,
                        E.dt(displayKey, ":"),
                        *[E.dd(val) for val in vals])
    fillWith('spec-metadata', E.div(dl), doc=doc)


def addReferencesSection(doc):
    if not doc.normativeRefs and not doc.informativeRefs:
        return
    container = getFillContainer('references', doc=doc, default=True)
    if container is None:
        return

    def formatBiblioTerm(linkText):
        '''
        If the term is all uppercase, leave it like that.
        If it's all lowercase, uppercase it.
        If it's mixed case, leave it like that.
        '''
        if linkText.islower():
            return linkText.upper()
        return linkText

    appendChild(container,
                E.h2({"class":"no-num no-ref", "id":"references"}, "References"))

    normRefs = sorted(doc.normativeRefs.values(), key=lambda r: r.linkText.lower())
    if len(normRefs):
        dl = appendChild(container,
                         E.h3({"class":"no-num no-ref", "id":"normative"}, "Normative References"),
                         E.dl())
        for ref in normRefs:
            appendChild(dl, E.dt({"id":"biblio-" + config.simplifyText(ref.linkText), "data-no-self-link":""}, "[" + formatBiblioTerm(ref.linkText) + "]"))
            appendChild(dl, E.dd(*ref.toHTML()))

    informRefs = [x for x in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText.lower()) if x.linkText not in doc.normativeRefs]
    if len(informRefs):
        dl = appendChild(container,
                         E.h3({"class":"no-num no-ref", "id":"informative"}, "Informative References"),
                         E.dl())
        for ref in informRefs:
            appendChild(dl, E.dt({"id":"biblio-" + config.simplifyText(ref.linkText), "data-no-self-link":""}, "[" + formatBiblioTerm(ref.linkText) + "]"))
            appendChild(dl, E.dd(*ref.toHTML()))


def addIssuesSection(doc):
    issues = findAll('.issue', doc)
    if len(issues) == 0:
        return
    container = getFillContainer('issues-index', doc=doc, default=True)
    if container is None:
        return

    appendChild(container,
                E.h2({"class":"no-num no-ref", "id":"issues-index"}, "Issues Index"))
    container = appendChild(container,
                            E.div({"style":"counter-reset:issue"}))
    for issue in issues:
        el = copy.deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre",):
            el.tag = "div"
        appendChild(container, el)
        appendChild(el,
                    E.a({"href":"#" + issue.get('id')}, " ↵ "))
    for idel in findAll("[id]", container):
        del idel.attrib['id']
    for dfnel in findAll(config.dfnElementsSelector, container):
        dfnel.tag = "span"
