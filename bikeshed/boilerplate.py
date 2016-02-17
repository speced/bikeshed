# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import copy
from collections import defaultdict
from .messages import *
from .htmlhelpers import *
from .DefaultOrderedDict import DefaultOrderedDict


def addBikeshedVersion(doc):
    # Adds a <meta> containing the current Bikeshed semver.
    head = find("head", doc)
    appendChild(head,
        E.meta({"name": "generator", "content": "Bikeshed 1.0.0"}))

def addHeaderFooter(doc):
    header = config.retrieveBoilerplateFile(doc, 'header') if "header" not in doc.md.boilerplate['omitSections'] else ""
    footer = config.retrieveBoilerplateFile(doc, 'footer') if "footer" not in doc.md.boilerplate['omitSections'] else ""

    doc.html = '\n'.join([header, doc.html, footer])


def fillWith(tag, newElements, doc):
    for el in findAll("[data-fill-with='{0}']".format(tag), doc):
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
    if tag in doc.md.boilerplate['omitSections']:
        return None

    # If a fill-with is found, fill that
    if find("[data-fill-with='{0}']".format(tag), doc) is not None:
        return find("[data-fill-with='{0}']".format(tag), doc)

    # Otherwise, append to the end of the document
    if default:
        return find("body", doc)


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
        html += "<li>"+doc.fixText(feature)
    html += "</ul><p>“At-risk” is a W3C Process term-of-art, and does not necessarily imply that the feature is in danger of being dropped or delayed. It means that the WG believes the feature may have difficulting being interoperably implemented in a timely manner, and marking it as such allows the WG to drop the feature if necessary when transitioning to the Proposed Rec stage, without having to publish a new Candidate Rec without the feature first."
    fillWith('at-risk', parseHTML(html), doc=doc)

def addStyles(doc):
    el = getFillContainer('stylesheet', doc)
    if el is not None:
        fillWith('stylesheet', config.retrieveBoilerplateFile(doc, 'stylesheet'), doc=doc)

def addCustomBoilerplate(doc):
    for el in findAll('[boilerplate]', doc):
        bType = el.get('boilerplate')
        target = find('[data-fill-with="{0}"]'.format(bType), doc)
        if target is not None:
            replaceContents(target, el)
            removeNode(el)

def removeUnwantedBoilerplate(doc):
    for el in findAll('[data-fill-with]', doc):
        tag = el.get('data-fill-with')
        if tag in doc.md.boilerplate['omitSections']:
            removeNode(el)

def addAnnotations(doc):
    if (doc.md.vshortname in doc.testSuites):
        html = config.retrieveBoilerplateFile(doc, 'annotations')
        html = doc.fixText(html)
        appendContents(find("head", doc), parseHTML(html))

def addIndexSection(doc):
    if len(findAll(config.dfnElementsSelector, doc)) == 0 and len(doc.externalRefsUsed.keys()) == 0:
        return
    container = getFillContainer('index', doc=doc, default=True)
    if container is None:
        return
    appendChild(container,
        E.h2({"class":"no-num", "id":"index"}, "Index"))

    if len(findAll(config.dfnElementsSelector, doc)):
        addIndexOfLocallyDefinedTerms(doc, container)

    if len(doc.externalRefsUsed.keys()):
        addIndexOfExternallyDefinedTerms(doc, container)

def addIndexOfLocallyDefinedTerms(doc, container):
    appendChild(container,
        E.h3({"class":"no-num", "id":"index-defined-here"}, "Terms defined by this specification"))

    indexEntries = defaultdict(list)
    for el in findAll(",".join(x+"[id]" for x in config.dfnElements), doc):
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
                'url':"#"+id,
                'label':"§" + headingLevel,
                'disambiguator':disambiguator
                }
            indexEntries[linkText].append(entry)

    # Now print the indexes
    indexHTML = htmlFromIndexTerms(indexEntries)
    appendChild(container, indexHTML)

def addExplicitIndexes(doc):
    # Explicit indexes can be requested for specs with <index for="example-spec-1"></index>

    for container in findAll("index", doc):
        indexEntries = defaultdict(list)
        if container.get('for') is None:
            die("<index> elements need a for='' attribute specifying one or more specs.")
            continue
        if container.get('type'):
            types = [x.strip() for x in container.get('type').split(',')]
        else:
            types = None
        status = container.get('status')
        if status and status not in ["TR", "ED"]:
            die("<index> has unknown value '{0}' for status. Must be TR or ED.", status)
            continue
        if container.get('for').strip() == "*":
            specs = None
        else:
            specs = set(x.strip() for x in container.get('for').split(','))
        seenSpecs = set()
        for text, refs in doc.refs.refs.items():
            text = text.strip()
            for ref in refs:
                if not ref['export']:
                    continue
                if specs is not None and ref['spec'].strip() not in specs:
                    continue
                if types and ref['type'].strip() not in types:
                    continue
                seenSpecs.add(ref['spec'].strip())
                label = None # TODO: Record section numbers, use that instead
                disambInfo = []
                if types is None or len(types) > 1:
                    disambInfo.append(ref['type'].strip())
                if specs is None or len(specs) > 1:
                    disambInfo.append("in " + ref['spec'].strip())
                if ref['for']:
                    try:
                        disambInfo.append("for {0}".format(', '.join(x.strip() for x in ref['for'])))
                    except:
                        # todo: The TR version of Position triggers this
                        pass
                disambiguator = ", ".join(disambInfo)
                entry = {'url': ref['url'].strip(), 'disambiguator': disambiguator, 'label': label, 'status': ref['status'].strip()}
                for i,existingEntry in enumerate(indexEntries[text]):
                    if existingEntry['disambiguator'] != disambiguator or existingEntry['label'] != label:
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
                            # Default to preferring EDs
                            if existingEntry['status'] == "ED":
                                break
                            elif entry['status'] == "ED":
                                indexEntries[text][i] = entry
                                break
                    else:
                        # Legit dupes. Shouldn't happen in a good spec, but whatever.
                        pass
                else:
                    indexEntries[text].append(entry)
        if specs is not None and specs - seenSpecs:
            warn("Couldn't find any refs for {0} when generating an index.", ' or '.join("'{0}'".format(x) for x in specs - seenSpecs))
        appendChild(container, htmlFromIndexTerms(indexEntries))
        container.tag = "div"
        removeAttr(container, "for")
        removeAttr(container, "status")


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
    for spec, refs in sorted(doc.externalRefsUsed.items(), key=lambda x:x[0]):
        # ref.spec is always lowercase; if the same string shows up in biblio data,
        # use its casing instead.
        biblioRef = doc.refs.getBiblioRef(spec, status="normative")
        if biblioRef:
            printableSpec = biblioRef.linkText
        else:
            printableSpec = spec
        attrs = {"data-lt":spec, "data-link-type":"biblio", "data-biblio-type":"normative", "data-okay-to-fail": "true"}
        specLi = appendChild(ul,
            E.li(
                E.a(attrs, "[", printableSpec, "]"), " defines the following terms:"))
        termsUl = appendChild(specLi, E.ul())
        for title, ref in sorted(refs.items(), key=lambda x:x[0]):
            appendChild(termsUl, E.li(E.a({"href":ref.url}, title)))

    appendChild(container,
        E.h3({"class":"no-num", "id":"index-defined-elsewhere"}, "Terms defined by reference"))
    appendChild(container, ul)


def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables

    if len(findAll("table.propdef, table.descdef", doc)) == 0:
        return
    html = getFillContainer('property-index', doc=doc, default=True)
    if html is None:
        return

    appendChild(html,
        E.h2({"class":"no-num", "id":"property-index"}, "Property Index"))

    def extractKeyValFromRow(tr):
        # Extract the key, minus the trailing :
        result = re.match(r'(.*):', textContent(row[0]).strip())
        if result is None:
            die("Propdef row headers must be a word followed by a colon. Got:\n{0}", textContent(row[0]).strip())
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
            key, val = extractKeyValFromRow(row)
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
            key, val = extractKeyValFromRow(row)
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
                E.h3({"class":"no-num", "id":config.simplifyText(atRuleName)+"-descriptor-table"},
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
    idlBlocks = findAll("pre.idl", doc)
    if len(idlBlocks) == 0:
        return
    html = getFillContainer('idl-index', doc=doc, default=True)
    if html is None:
        return

    appendChild(html,
        E.h2({"class":"no-num", "id":"idl-index"}, "IDL Index"))

    container = appendChild(html, E.pre({"class":"idl"}))
    for block in idlBlocks:
        blockCopy = copy.deepcopy(block)
        appendContents(container, blockCopy)
        appendChild(container, "\n")
    for dfn in findAll("dfn[id]", container):
        dfn.tag = "a"
        dfn.set("href", "#"+dfn.get("id"))
        del dfn.attrib["id"]


def addTOCSection(doc):
    toc = getFillContainer("table-of-contents", doc=doc, default=False)
    if toc is None:
        return
    appendChild(toc,
        E.h2({"class": "no-num no-toc no-ref", "id":"contents"}, "Table of Contents"))

    skipLevel = float('inf')
    previousLevel = 1
    containers = [0, 1, 2, 3, 4, 5, 6, 7]
    containers[1] = toc
    containers[2] = appendChild(containers[1], E.ol({"class":"toc", "role":"directory"}))
    for header in findAll('h2, h3, h4, h5, h6', doc):
        level = int(header.tag[-1])
        container = containers[level]

        if level > previousLevel + 1:
            # Jumping two levels is a no-no.
            die("Heading level jumps more than one level, from h{0} to h{1}:\n  {2}", previousLevel, level, textContent(header).replace("\n", " "))

        # Hit a no-toc, suppress the entire section.
        addToTOC = True
        if hasClass(header, "no-toc"):
            skipLevel = min(level, skipLevel)
            addToTOC = False
        if skipLevel < level:
            addToTOC = False
        else:
            skipLevel = float('inf')

        if addToTOC:
            li = appendChild(container,
                E.li(
                    E.a({"href":"#"+header.get('id')},
                        E.span({"class":"secno"},header.get('data-level', '')),
                        " ",
                        copy.deepcopy(find(".content", header)))))
            containers[level+1] = appendChild(li, E.ol({"class":"toc"}))
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
        if editor['id']:
            dd.attrib['data-editor-id'] = editor['id']
        if editor['link']:
            appendChild(dd, E.a({"class":"p-name fn u-url url", "href":editor['link']}, editor['name']))
        elif editor['email']:
            appendChild(dd, E.a({"class":"p-name fn u-email email", "href":"mailto:"+editor['email']}, editor['name']))
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
                E.a({"class":"u-email email", "href":"mailto:"+editor['email']}, editor['email']))
        return dd

    md = DefaultOrderedDict(list)
    mac = doc.macros
    if mac.get('version'):
        md["This version"].append(E.a({"href":mac['version'], "class":"u-url"}, mac['version']))
    if doc.md.TR:
        md["Latest version"].append(E.a({"href": doc.md.TR}, doc.md.TR))
    if doc.md.ED and doc.md.status in config.TRStatuses:
        md["Editor's Draft"].append(E.a({"href": doc.md.ED}, doc.md.ED))
    if len(doc.md.previousVersions):
        md["Previous Versions"] = [E.a({"href":ver, "rel":"previous"}, ver) for ver in doc.md.previousVersions]
    if len(doc.md.versionHistory):
        md["Version History"] = [E.a({"href":vh}, vh) for vh in doc.md.versionHistory]
    if doc.md.mailingList:
        span = E.span(
            E.a({"href":"mailto:"+doc.md.mailingList+"?subject=%5B"+mac['shortname']+"%5D%20YOUR%20TOPIC%20HERE"}, doc.md.mailingList),
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
        md["Issue Tracking"] = [E.a({"href":url}, text) for text,url in doc.md.issues]
    if len(doc.md.editors):
        md["Editor"] = map(printEditor, doc.md.editors)
    if len(doc.md.previousEditors):
        md["Former Editor"] = map(printEditor, doc.md.previousEditors)
    if len(doc.md.translations):
        md["Translation" if len(doc.md.translations) == 1 else "Translations"] = [E.a({"href":url}, text) for text,url in doc.md.translations]
    for key, vals in doc.md.otherMetadata.items():
        md[key].extend(parseHTML("<span>"+doc.fixText(val)+"</span>")[0] for val in vals)

    pluralization = {
        "Previous Version": "Previous Versions",
        "Test Suite": "Test Suites",
        "Editor": "Editors",
        "Former Editor": "Former Editors"
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
        elif key == "Translation":
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
    if len(doc.normativeRefs) == 0 and len(doc.informativeRefs) is None:
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
        E.h2({"class":"no-num", "id":"references"}, "References"))

    normRefs = sorted(doc.normativeRefs.values(), key=lambda r: r.linkText)
    if len(normRefs):
        dl = appendChild(container,
            E.h3({"class":"no-num", "id":"normative"}, "Normative References"),
            E.dl())
        for ref in normRefs:
            appendChild(dl, E.dt({"id":"biblio-"+config.simplifyText(ref.linkText)}, "["+formatBiblioTerm(ref.linkText)+"]"))
            appendChild(dl, E.dd(*ref.toHTML()))

    informRefs = [x for x in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText) if x.linkText not in doc.normativeRefs]
    if len(informRefs):
        dl = appendChild(container,
            E.h3({"class":"no-num", "id":"informative"}, "Informative References"),
            E.dl())
        for ref in informRefs:
            appendChild(dl, E.dt({"id":"biblio-"+config.simplifyText(ref.linkText)}, "["+formatBiblioTerm(ref.linkText)+"]"))
            appendChild(dl, E.dd(*ref.toHTML()))

def addIssuesSection(doc):
    issues = findAll('.issue', doc)
    if len(issues) == 0:
        return
    container = getFillContainer('issues-index', doc=doc, default=True)
    if container is None:
        return

    appendChild(container,
        E.h2({"class":"no-num", "id":"issues-index"}, "Issues Index"))
    container = appendChild(container,
        E.div({"style":"counter-reset:issue"}))
    for issue in issues:
        el = copy.deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre",):
            el.tag = "div"
        appendChild(container, el)
        appendChild(el,
            E.a({"href":"#"+issue.get('id')}, " ↵ "))
    for idel in findAll("[id]", container):
        del idel.attrib['id']
    for dfnel in findAll(config.dfnElementsSelector, container):
        dfnel.tag = "span"

