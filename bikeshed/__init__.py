# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import re
from collections import defaultdict
from collections import Counter
import io
import os
import sys
import json
import argparse
import urllib
from urllib2 import urlopen
from datetime import date, datetime
from copy import deepcopy
from collections import OrderedDict
import html5lib
import lxml
import cProfile

from . import config
from . import biblio
from . import update
from . import markdown
from . import test
from . import MetadataManager as metadata
from . import HTMLSerializer
from .datablocks import transformDataBlocks
from .ReferenceManager import ReferenceManager
from .ReferenceManager import linkTextsFromElement, splitForValues
from .globalnames import *
from .htmlhelpers import *
from .messages import *
from .widlparser.widlparser import parser
from .DefaultOrderedDict import DefaultOrderedDict
from .config import simplifyText


def main():
    # Hack around argparse's lack of optional subparsers
    if len(sys.argv) == 1:
        sys.argv.append("spec")

    argparser = argparse.ArgumentParser(description="Processes spec source files into valid HTML.")
    argparser.add_argument("-q", "--quiet", dest="quiet", action="store_true",
                            help="Suppresses everything but fatal errors from printing.")
    argparser.add_argument("-f", "--force", dest="debug", action="store_true",
                           help="Force the preprocessor to run to completion; fatal errors don't stop processing.")
    argparser.add_argument("-d", "--dry-run", dest="dryRun", action="store_true",
                           help="Prevents the processor from actually saving anything to disk, but otherwise fully runs.")

    subparsers = argparser.add_subparsers(title="Subcommands", dest='subparserName')

    specParser = subparsers.add_parser('spec', help="Process a spec source file into a valid output file.")
    specParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    specParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")
    specParser.add_argument("--para", dest="paragraphMode", default="markdown",
                            help="Pass 'markdown' for Markdown-style paragraph, or 'html' for normal HTML paragraphs. [default: %(default)s]")
    minifyGroup = specParser.add_argument_group("Minification")
    specParser.set_defaults(minify=True)
    minifyGroup.add_argument("--minify", dest="minify", action="store_true",
                             help="Turn on minification. [default]")
    minifyGroup.add_argument("--no-minify", dest="minify", action="store_false",
                            help="Turn off minification.")

    updateParser = subparsers.add_parser('update', help="Update supporting files (those in /spec-data).", epilog="If no options are specified, everything is downloaded.")
    updateParser.add_argument("--anchors", action="store_true", help="Download crossref anchor data.")
    updateParser.add_argument("--biblio", action="store_true", help="Download biblio data.")
    updateParser.add_argument("--link-defaults", dest="linkDefaults", action="store_true", help="Download link default data.")
    updateParser.add_argument("--test-suites", dest="testSuites", action="store_true", help="Download test suite data.")

    issueParser = subparsers.add_parser('issues-list', help="Process a plain-text issues file into HTML. Call with no args to see an example input text.")
    issueParser.add_argument("-t",
                              dest="printTemplate",
                              action="store_true",
                              help="Output example Issues List template.")
    issueParser.add_argument("infile", nargs="?",
                              default=None,
                              help="Path to the plain-text issue file.")
    issueParser.add_argument("outfile", nargs="?",
                              default=None,
                              help="Path to the output file. Default is file of the same name as input, with .html.")

    debugParser = subparsers.add_parser('debug', help="Run various debugging commands.")
    debugParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    debugCommands = debugParser.add_mutually_exclusive_group(required=True)
    debugCommands.add_argument("--print-exports", dest="printExports", action="store_true",
                               help="Prints those terms that will be exported for cross-ref purposes.")
    debugCommands.add_argument("--print-refs-for", dest="linkText",
                               help="Prints the ref data for a given link text.")
    debugCommands.add_argument("--print", dest="code",
                               help="Runs the specified code and prints it.")
    debugCommands.add_argument("--print-json", dest="jsonCode",
                               help="Runs the specified code and prints it as formatted JSON.")

    refParser = subparsers.add_parser('refs', help="Search Bikeshed's ref database.")
    refParser.add_argument("infile", nargs="?",
                             default=None,
                             help="Path to the source file.")
    refParser.add_argument("--text", dest="text", default=None)
    refParser.add_argument("--type", dest="linkType", default=None)
    refParser.add_argument("--for", dest="linkFor", default=None)
    refParser.add_argument("--spec", dest="spec", default=None)
    refParser.add_argument("--status", dest="status", default=None)
    refParser.add_argument("--exact", dest="exact", action="store_true")

    sourceParser = subparsers.add_parser('source', help="Tools for formatting the *source* document.")
    sourceParser.add_argument("--big-text",
                              dest="bigText",
                              action="store_true",
                              help="Finds HTML comments containing 'Big Text: foo' and turns them into comments containing 'foo' in big text.")
    sourceParser.add_argument("infile", nargs="?",
                            default=None,
                            help="Path to the source file.")
    sourceParser.add_argument("outfile", nargs="?",
                            default=None,
                            help="Path to the output file.")

    testParser = subparsers.add_parser('test', help="Tools for running Bikeshed's testsuite.")
    testParser.add_argument("--rebase",
                            dest="rebaseFiles",
                            default=None,
                            metavar="FILE",
                            nargs="*",
                            help="Rebase the specified files. If called with no args, rebases everything.")

    profileParser = subparsers.add_parser('profile', help="Profiling Bikeshed. Needs graphviz, gprof2dot installed.")
    profileParser.add_argument("--root",
                               dest="root",
                               default=None,
                               metavar="ROOTFUNC",
                               help="Prune the graph to start with the specified root node.")
    profileParser.add_argument("--leaf",
                               dest="leaf",
                               default=None,
                               metavar="LEAFFUNC",
                               help="Prune the graph to only show ancestors of the specified leaf node.")

    options, extras = argparser.parse_known_args()

    config.quiet = options.quiet
    config.debug = options.debug
    config.dryRun = options.dryRun
    config.minify = getattr(options, 'minify', True)

    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, linkDefaults=options.linkDefaults, testSuites=options.testSuites)
    elif options.subparserName == "spec":
        doc = CSSSpec(inputFilename=options.infile, paragraphMode=options.paragraphMode)
        doc.md.addOverrides(extras)
        doc.preprocess()
        doc.finish(outputFilename=options.outfile)
    elif options.subparserName == "debug":
        config.debug = True
        config.quiet = True
        if options.printExports:
            doc = CSSSpec(inputFilename=options.infile)
            doc.preprocess()
            doc.printTargets()
        elif options.jsonCode:
            doc = CSSSpec(inputFilename=options.infile)
            doc.preprocess()
            exec("print json.dumps({0}, indent=2)".format(options.jsonCode))
        elif options.code:
            doc = CSSSpec(inputFilename=options.infile)
            doc.preprocess()
            exec("print {0}".format(options.code))
        elif options.linkText:
            doc = CSSSpec(inputFilename=options.infile)
            doc.preprocess()
            refs = doc.refs.refs[options.linkText] + doc.refs.refs[options.linkText+"\n"]
            config.quiet = options.quiet
            if not config.quiet:
                print "Refs for '{0}':".format(options.linkText)
            # Get ready for JSONing
            for ref in refs:
                ref['level'] = str(ref['level'])
            print json.dumps(refs, indent=2)
    elif options.subparserName == "refs":
        config.debug = True
        config.quiet = True
        doc = CSSSpec(inputFilename=options.infile)
        doc.preprocess()
        refs,_ = list(doc.refs.queryRefs(text=options.text, linkFor=options.linkFor, linkType=options.linkType, status=options.status, spec=options.spec, exact=options.exact))
        print config.printjson(refs)
    elif options.subparserName == "issues-list":
        from . import issuelist as il
        if options.printTemplate:
            il.printHelpMessage()
        else:
            il.printIssueList(options.infile, options.outfile)
    elif options.subparserName == "source":
        if not options.bigText: # If no options are given, do all options.
            options.bigText = True
        if options.bigText:
            from . import fonts
            font = fonts.Font()
            fonts.replaceComments(font=font, inputFilename=options.infile, outputFilename=options.outfile)
    elif options.subparserName == "test":
        if options.rebaseFiles is not None:
            test.rebase(options.rebaseFiles)
        else:
            config.debug = True
            config.quiet = True
            result = test.runAllTests(constructor=CSSSpec)
            sys.exit(0 if result else 1)
    elif options.subparserName == "profile":
        root = "--root=\"{0}\"".format(options.root) if options.root else ""
        leaf = "--leaf=\"{0}\"".format(options.leaf) if options.leaf else ""
        os.system("python -m cProfile -o stat.prof ~/bikeshed/bikeshed.py && gprof2dot -f pstats --skew=.0001 {root} {leaf} stat.prof | dot -Tsvg -o callgraph.svg && rm stat.prof".format(root=root, leaf=leaf))

def stripBOM(doc):
    if doc.lines[0][0:1] == "\ufeff":
        doc.lines[0] = doc.lines[0][1:]
        warn("Your document has a BOM. There's no need for that, please re-save it without a BOM.")






# Headings Stuff

def processHeadings(doc, scope="doc"):
    # scope arg can be "doc" or "all"
    # "doc" ignores things that are part of boilerplate
    for el in findAll('h2, h3, h4, h5, h6', doc):
        addClass(el, 'heading')
    headings = []
    for el in findAll(".heading:not(.settled)", doc):
        if scope == "doc" and treeAttr(el, "boilerplate"):
            continue
        headings.append(el)
    resetHeadings(doc, headings)
    determineHeadingLevels(doc, headings)
    addHeadingIds(doc, headings)
    dedupIds(doc, headings)
    addHeadingBonuses(doc, headings)
    for el in headings:
        addClass(el, 'settled')

def resetHeadings(doc, headings):
    for header in headings:
        # Reset to base, if this is a re-run
        if find(".content", header) is not None:
            content = find(".content", header)
            moveContents(header, content)

        # Insert current header contents into a <span class='content'>
        content = lxml.etree.Element('span', {"class":"content"})
        moveContents(content, header)
        appendChild(header, content)

def addHeadingIds(doc, headings):
    neededIds = set()
    for header in headings:
        if header.get('id') is None:
            neededIds.add(header)
            header.set('id', simplifyText(textContent(find(".content", header)), convertDashes=True))
    if len(neededIds) > 0:
        warn("You should manually provide IDs for your headings:\n{0}",
            "\n".join("  "+outerHTML(el) for el in neededIds))

def determineHeadingLevels(doc, headings):
    headerLevel = [0,0,0,0,0]
    def incrementLevel(level):
        headerLevel[level-2] += 1
        for i in range(level-1, 5):
            headerLevel[i] = 0
    def printLevel():
        return '.'.join(unicode(x) for x in headerLevel if x > 0)

    skipLevel = float('inf')
    for header in headings:
        # Add the heading number.
        level = int(header.tag[-1])

        # Reset, if this is a re-run.
        if(header.get('data-level')):
            del header.attrib['data-level']

        # If we encounter a no-num, don't number it or any in the same section.
        if hasClass(header, "no-num"):
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue
        else:
            skipLevel = float('inf')

        incrementLevel(level)
        header.set('data-level', printLevel())

def addHeadingBonuses(doc, headings):
    for header in headings:
        if header.get("data-level") is not None:
            secno = lxml.etree.Element('span', {"class":"secno"})
            secno.text = header.get('data-level') + '. '
            header.insert(0, secno)


















# Definitions and the like

def formatPropertyNames(doc):
    for table in findAll("table.propdef, table.descdef, table.elementdef", doc):
        tag = "a" if hasClass(table, "partial") else "dfn"
        if hasClass(table, "propdef"):
            type = "property"
        elif hasClass(table, "descdef"):
            type = "descriptor"
        elif hasClass(table, "elementdef"):
            type = "element"
        cell = findAll("tr:first-child > :nth-child(2)", table)[0]
        names = [x.strip() for x in textContent(cell).split(',')]
        newContents = config.intersperse((createElement(tag, {type:""}, name) for name in names), ", ")
        replaceContents(cell, newContents)


def canonicalizeShortcuts(doc):
    # Take all the invalid-HTML shortcuts and fix them.

    attrFixup = {
        "export":"data-export",
        "noexport":"data-noexport",
        "spec":"data-link-spec",
        "status":"data-link-status",
        "dfn-for":"data-dfn-for",
        "link-for":"data-link-for",
        "dfn-type":"data-dfn-type",
        "link-type":"data-link-type",
        "force":"data-dfn-force",
        "section":"data-section",
        "attribute-info":"data-attribute-info",
        "dict-member-info":"data-dict-member-info",
        "lt":"data-lt",
        "local-lt":"data-local-lt"
    }
    for el in findAll(",".join("[{0}]".format(attr) for attr in attrFixup.keys()), doc):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, el.get(attr))
                del el.attrib[attr]

    for el in findAll("dfn", doc):
        for dfnType in config.dfnTypes.union(["dfn"]):
            if el.get(dfnType) == "":
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
                break
    for el in findAll("a", doc):
        for linkType in (config.linkTypes | set("dfn")):
            if el.get(linkType) is not None:
                del el.attrib[linkType]
                el.set("data-link-type", linkType)
                break
    for el in findAll("dfn[for], a[for]", doc):
        if el.tag == "dfn":
            el.set("data-dfn-for", el.get('for'))
        else:
            el.set("data-link-for", el.get('for'))
        del el.attrib['for']

def fixIntraDocumentReferences(doc):
    ids = {el.get('id'):el for el in findAll("[id]", doc)}
    headingIDs = {el.get('id'):el for el in findAll("[id].heading", doc)}
    for el in findAll("a[href^='#']:not([href='#']):not(.self-link):not([data-link-type])", doc):
        targetID = el.get("href")[1:]
        if el.get('data-section') is not None and targetID not in headingIDs:
            die("Couldn't find target document section {0}:\n{1}", targetID, outerHTML(el))
            continue
        elif targetID not in ids:
            die("Couldn't find target anchor {0}:\n{1}", targetID, outerHTML(el))
            continue
        if (el.text is None or el.text.strip() == '') and len(el) == 0:
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            target = ids[targetID]
            content = find(".content", target)
            if content is None:
                die("Tried to generate text for a section link, but the target isn't a heading:\n{0}", outerHTML(el))
                continue
            text = textContent(content)
            if target.get('data-level') is not None:
                text = "§{1} {0}".format(text, target.get('data-level'))
            appendChild(el, text)

def fillAttributeInfoSpans(doc):
    # Auto-add <span attribute-info> to <dt><dfn> when it's an attribute or dict-member.
    for dt in findAll("dt", doc):
        if find("span[data-attribute-info]", dt) is not None:
            # Already has one, no need to do any work here
            continue
        dfn = find("dfn", dt)
        if dfn is None:
            continue
        dfnType = dfn.get("data-dfn-type")
        if dfnType == "attribute":
            attrName = "data-attribute-info"
        elif dfnType == "dict-member":
            attrName = "data-dict-member-info"
        else:
            continue
        spanFor = determineDfnText(dfn).split('|')[0]
        if dfn.get("data-dfn-for"):
            spanFor = dfn.get("data-dfn-for") + "/" + spanFor
        insertAfter(dfn,
            ", ",
            E.span({attrName:"", "for":spanFor}))

    for el in findAll("span[data-attribute-info], span[data-dict-member-info]", doc):
        if el.get('data-attribute-info') is not None:
            refType = "attribute"
        else:
            refType = "dict-member"
        if (el.text is None or el.text.strip() == '') and len(el) == 0:
            referencedAttribute = el.get("for")
            if referencedAttribute is None or referencedAttribute == "":
                die("Missing for reference in attribute info span.")
                continue
            if "/" in referencedAttribute:
                interface, referencedAttribute = referencedAttribute.split("/")
                target = findAll('[data-link-type={2}][data-lt="{0}"][data-link-for="{1}"]'.format(referencedAttribute, interface, refType), doc)
            else:
                target = findAll('[data-link-type={1}][data-lt="{0}"]'.format(referencedAttribute, refType), doc)
            if len(target) == 0:
                die("Couldn't find target {1} '{0}':\n{2}", referencedAttribute, refType, outerHTML(el))
                continue
            elif len(target) > 1:
                die("Multiple potential target {1}s '{0}':\n{2}", referencedAttribute, refType, outerHTML(el))
                continue
            target = target[0]
            datatype = target.get("data-type").strip()
            default = target.get("data-default");
            decorations = []
            if target.get("data-readonly") is not None:
                decorations.append(", readonly")
            if datatype[-1] == "?":
                decorations.append(", nullable")
                datatype = datatype[:-1]
            if default is not None:
                decorations.append(", defaulting to ")
                decorations.append(E.code(default))
            if "<" in datatype:
                match = re.match(r"(\w+)<(\w+)>", datatype)
                appendChild(el,
                    " of type ",
                    match.group(1),
                    "<",
                    E.a({"data-link-type":"idl-name"}, match.group(2)),
                    ">",
                    *decorations)
            else:
                appendChild(el,
                    " of type ",
                    E.a({"data-link-type":"idl-name"}, datatype),
                    *decorations)

def processDfns(doc):
    dfns = findAll("dfn", doc)
    classifyDfns(doc, dfns)
    dedupIds(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)


def determineDfnType(dfn):
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
        classList = ancestor.get('class') or ''
        for cls, type in config.dfnClassToType.items():
            if hasClass(ancestor, cls):
                return type
            if hasClass(ancestor, "idl") and not hasClass(ancestor, "extract"):
                return "interface"
    # 4. Introspect on the text
    text = textContent(dfn)
    if text[0:1] == "@":
        return "at-rule"
    elif len(dfn) == 1 and dfn[0].get('data-link-type') == "maybe":
        return "value"
    elif text[0:1] == "<" and text[-1:] == ">":
        return "type"
    elif text[0:1] == ":":
        return "selector"
    elif re.match(r"^[\w-]+\(.*\)$", text) and not (dfn.get('id') or '').startswith("dom-"):
        return "function"
    else:
        return "dfn"

def determineDfnText(el):
    dfnType = el.get('data-dfn-type')
    contents = textContent(el)
    if el.get('data-lt'):
        dfnText = el.get('data-lt')
    elif dfnType in config.functionishTypes and re.match(r"^[\w-]+\(.*\)$", contents):
        dfnText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1)+"()"
    else:
        dfnText = contents
    return dfnText

def classifyDfns(doc, dfns):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el)
        # TODO Why am I using linkTextsFromElement here, but determineDfnText further down?
        dfnTexts = linkTextsFromElement(el)
        if len(dfnTexts):
            primaryDfnText = dfnTexts[0]
        else:
            die("Dfn has no linking text:\n{0}", outerHTML(el))
            continue
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.match(r"^[\w-]+\(.*\)$", primaryDfnText):
                die("Functions/methods must end with () in their linking text, got '{0}'.", primaryDfnText)
                continue
            elif el.get('data-lt') is None:
                # Make sure that functionish dfns have their linking text set up right.
                # Need to fix this to use the idl parser instead.
                el.set('data-lt', re.match(r"^([\w-]+)\(.*\)$", primaryDfnText).group(1)+"()")
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get('data-dfn-for') is None:
            parent = el.getparent()
            if parent.get('data-dfn-type') in config.functionishTypes and parent.get('data-dfn-for') is not None:
                el.set('data-dfn-for', "{0}/{1} {1}".format(parent.get('data-dfn-for'), linkTextsFromElement(parent)[0]))
            elif treeAttr(el, "data-dfn-for") is None:
                die("'argument' dfns need to specify what they're for, or have it be inferrable from their parent. Got:\n{0}", outerHTML(el))
                continue
        if dfnType in config.typesUsingFor:
            if el.get('data-dfn-for'):
                dfnFor = el.get('data-dfn-for')
            else:
                dfnFor = treeAttr(el, "data-dfn-for")
                if dfnFor:
                    el.set('data-dfn-for', dfnFor)
                else:
                    die("'{0}' definitions need to specify what they're for.\nAdd a 'for' attribute to {1}, or add 'dfn-for' to an ancestor.", dfnType, outerHTML(el))
                    continue
        else:
            # Types that aren't forced to use 'for' can still optionally use it.
            dfnFor = treeAttr(el, "data-dfn-for")
            if dfnFor:
                el.set('data-dfn-for', dfnFor)
        # Automatically fill in id if necessary.
        if el.get('id') is None:
            convertDashes = dfnType == "dfn"
            id = simplifyText(determineDfnText(el).split('|')[0], convertDashes=convertDashes)
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                pass
            elif dfnType in config.idlTypes.intersection(config.typesUsingFor):
                id = simplifyText("dom-{_for}-{id}".format(_for=dfnFor, id=id))
            elif dfnType in config.typesUsingFor:
                # Prepend property name to value to avoid ID duplication
                id = simplifyText("{type}-{_for}-{id}".format(type=dfnTypeToPrefix[dfnType], _for=dfnFor, id=id))
            else:
                id = "{type}-{id}".format(type=dfnTypeToPrefix[dfnType], id=id)
            el.set('id', id)
        # Push export/noexport down to the definition
        if el.get('data-export') is None and el.get('data-noexport') is None:
            for ancestor in el.iterancestors():
                if ancestor.get('data-export') is not None:
                    el.set('data-export', '')
                    break
                elif ancestor.get('data-noexport') is not None:
                    el.set('data-noexport', '')
                    break
            else:
                if dfnType == "dfn":
                    el.set('data-noexport', '')
                else:
                    el.set('data-export', '')


def dedupIds(doc, els):
    import itertools as iter
    def findId(id):
        return find("#"+id, doc) is not None
    ids = Counter(el.get('id') for el in findAll("[id]", doc))
    dupes = [id for id,count in ids.items() if count > 1]
    for dupe in dupes:
        warnAboutDupes = True
        if re.match(r"issue-[0-9a-fA-F]{8}$", dupe):
            # Don't warn about issues, it's okay if they have the same ID because they're identical text.
            warnAboutDupes = False
        els = findAll("#"+dupe, doc)
        ints = iter.imap(str, iter.count(0))
        for el in els[1:]:
            # Try to de-dup the id by appending an integer after it.
            if warnAboutDupes:
                warn("Multiple elements have the same ID '{0}'.\nDeduping, but this ID may not be stable across revisions.", dupe)
            for x in ints:
                if not findId(dupe+x):
                    el.set("id", dupe+x)
                    break


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    text = textContent(el)
    if linkType:
        if linkType in config.linkTypes.union(["dfn"]):
            return linkType
        die("Unknown link type '{0}' on:\n{1}", linkType, outerHTML(el))
        return "unknown-type"
    # 2. Introspect on the text
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
    elif linkType in config.functionishTypes.union(["functionish"]) and re.match(r"^[\w-]+\(.*\)$", contents):
        linkText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1)+"()"
        # Need to fix this using the idl parser.
    else:
        linkText = contents
    linkText = re.sub("\s+", " ", linkText)
    if len(linkText) == 0:
        die("Autolink {0} has no linktext.", outerHTML(el))
    return linkText


def classifyLink(el):
    linkType = determineLinkType(el)
    el.set('data-link-type', linkType)
    linkText = determineLinkText(el)

    el.set('data-lt', linkText)
    for attr in ["data-link-status", "data-link-for", "data-link-spec"]:
        val = treeAttr(el, attr)
        if val is not None:
            el.set(attr, val)
    return el













# Additional Processing


def processBiblioLinks(doc):
    biblioLinks = findAll("a[data-link-type='biblio']", doc)
    for el in biblioLinks:
        type = el.get('data-biblio-type')
        if type == "normative":
            storage = doc.normativeRefs
        elif type == "informative":
            storage = doc.informativeRefs
        else:
            die("Unknown data-biblio-type value '{0}' on {1}. Only 'normative' and 'informative' allowed.", type, outerHTML(el))
            continue

        linkText = determineLinkText(el)
        if linkText[0] == "[" and linkText[-1] == "]":
            linkText = linkText[1:-1]

        biblioStatus = treeAttr(el, "data-biblio-status")
        if not biblioStatus:
            biblioStatus = doc.md.defaultBiblioStatus

        ref = doc.refs.getBiblioRef(linkText, status=biblioStatus, el=el)
        if not ref:
            die("Couldn't find '{0}' in bibliography data.", linkText)
            el.tag = "span"
            continue

        id = simplifyText(linkText)
        el.set('href', '#biblio-'+id)
        storage[ref.linkText] = ref


def processAutolinks(doc):
    # An <a> without an href is an autolink.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    if doc.md.useIAutolinks:
        autolinks = findAll("a:not([href]), i", doc)
    else:
        autolinks = findAll("a:not([href])", doc)
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

        url = doc.refs.getRef(linkType, linkText,
                              spec=el.get('data-link-spec'),
                              status=el.get('data-link-status'),
                              linkFor=el.get('data-link-for'),
                              el=el,
                              error=(linkText.lower() not in doc.md.ignoredTerms))
        if url is not None:
            el.set('href', url)
            el.tag = "a"
        else:
            if linkType == "maybe":
                el.tag = "css"
                if el.get("data-link-type"):
                    del el.attrib["data-link-type"]
                if el.get("data-lt"):
                    del el.attrib["data-lt"]


def processIssues(doc):
    import hashlib
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues.
    for el in findAll(".issue:not([id])", doc):
        el.set('id', "issue-"+hashContents(el))
    dedupIds(doc, findAll(".issue", doc))


def addSelfLinks(doc):
    def makeSelfLink(el):
        return E.a({"href": "#" + urllib.quote(el.get('id', '')), "class":"self-link"})

    foundFirstNumberedSection = False
    for el in findAll("h2, h3, h4, h5, h6", doc):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get('data-level') is not None)
        if foundFirstNumberedSection:
            appendChild(el, makeSelfLink(el))
    for el in findAll(".issue[id], .example[id], .note[id], li[id], dt[id]", doc):
        if list(el.iterancestors("figure")):
            # Skipping - element is inside a figure and is part of an example.
            continue
        prependChild(el, makeSelfLink(el))
    for el in findAll("dfn", doc):
        if list(el.iterancestors("a")):
            warn("Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {0}", outerHTML(el))
            continue
        appendChild(el, makeSelfLink(el))


class DebugMarker(object):
    # Debugging tool for IDL markup

    def markupConstruct(self, text, construct):
        return ('<' + construct.idlType + '>', '</' + construct.idlType + '>')

    def markupType(self, text, construct):
        return ('<TYPE for=' + construct.idlType + '>', '</TYPE>')

    def markupTypeName(self, text, construct):
        return ('<TYPE-NAME for=' + construct.idlType + '>', '</TYPE-NAME>')

    def markupName(self, text, construct):
        return ('<NAME for=' + construct.idlType + '>', '</NAME>')

    def markupKeyword(self, text, construct):
        return ('<KEYWORD for=' + construct.idlType + '>', '</KEYWORD>')

class IDLMarker(object):
    def markupConstruct(self, text, construct):
        # Fires for every 'construct' in the WebIDL.
        # Some things are "productions", not "constructs".
        return (None, None)

    def markupType(self, text, construct):
        # Fires for entire type definitions.
        # It'll contain keywords or names, or sometimes more types.
        # For example, a "type" wrapper surrounds an entire union type,
        # as well as its component types.
        return (None, None)

    def markupTypeName(self, text, construct):
        # Fires for non-defining type names, such as arg types.
        return ('<a data-link-type="idl-name">', '</a>')

    def markupKeyword(self, text, construct):
        # Fires on the various "keywords" of WebIDL -
        # words that are part of the WebIDL syntax,
        # rather than names exposed to JS.
        # Examples: "interface", "stringifier", the IDL-defined type names like "DOMString" and "long".
        if text == "stringifier":
            if construct.name is None:
                # If no name was defined, you're required to define stringification behavior.
                return ("<a dfn for='{0}' data-lt='stringification behavior'>".format(construct.parent.fullName), "</a>")
            else:
                # Otherwise, you *can* point to/dfn stringification behavior if you want.
                return ("<idl data-idl-type=dfn data-idl-for='{0}' data-lt='stringification behavior' id='{0}-stringification-behavior'>".format(construct.parent.fullName), "</idl>")
        return (None, None)

    def markupName(self, text, construct):
        # Fires for defining names: method names, arg names, interface names, etc.
        if construct.idlType not in config.idlTypes:
            return (None,None)

        idlType = construct.idlType
        extraParameters = ''
        idlTitle = construct.normalName
        if idlType in config.functionishTypes:
            idlTitle = '|'.join(self.methodLinkingTexts(construct))
        elif idlType == "attribute":
            if hasattr(construct.member, "rest"):
                rest = construct.member.rest
            elif hasattr(construct.member, "attribute"):
                rest = construct.member.attribute
            else:
                die("Can't figure out how to construct attribute-info from:\n  {0}", construct)
            if rest.readonly is not None:
                readonly = 'data-readonly'
            else:
                readonly = ''
            extraParameters = '{0} data-type="{1}"'.format(readonly, rest.type)
        elif idlType == "dict-member":
            extraParameters = 'data-type="{0}"'.format(construct.type)
            if construct.default is not None:
                value = escapeAttr("{0}".format(construct.default.value))
                extraParameters += ' data-default="{0}"'.format(value)

        if idlType in config.typesUsingFor:
            idlFor = "data-idl-for='{0}'".format(construct.parent.fullName)
        else:
            idlFor = ""
        return ('<idl data-lt="{0}" data-idl-type="{1}" {2} {3}>'.format(idlTitle, idlType, idlFor, extraParameters), '</idl>')

    def encode(self, text):
        return escapeHTML(text)

    def methodLinkingTexts(self, method):
        '''
        Given a method-ish widlparser Construct,
        finds all possible linking texts.
        The full linking text is "foo(bar, baz)";
        beyond that, any optional or variadic arguments can be omitted.
        So, if both were optional,
        "foo(bar)" and "foo()" would both also be valid linking texts.
        '''
        if getattr(method, "arguments", None) is None:
            return [method.normalName]
        for i,arg in enumerate(method.arguments):
            if arg.optional or arg.variadic:
                optStart = i
                break
        else:
            # No optionals, so no work to be done
            return [method.normalName]
        prefix = method.name + "("
        texts = []
        for i in range(optStart, len(method.arguments)):
            argText = ', '.join(arg.name for arg in method.arguments[:i])
            texts.append(prefix + argText + ")")
        texts.append(method.normalName)
        return reversed(texts)

class IDLUI(object):
    def warn(self, msg):
        die("{0}", msg)

def markupIDL(doc):
    for el in findAll("pre.idl", doc):
        if el.get("data-no-idl") is not None:
            continue
        widl = parser.Parser(textContent(el), IDLUI())
        text = unicode(widl.markup(IDLMarker()))
        replaceContents(el, parseHTML(text))


def processIDL(doc):
    for pre in findAll("pre.idl", doc):
        if pre.get("data-no-idl") is not None:
            continue
        forcedDfns = GlobalNames(text=treeAttr(pre, "data-dfn-force"))
        for el in findAll("idl", pre):
            idlType = el.get('data-idl-type')
            url = None
            for idlText in el.get('data-lt').split('|'):
                url = doc.refs.getRef(idlType, idlText,
                                      linkFor=el.get('data-idl-for'),
                                      el=el,
                                      error=False)
                if url:
                    break
            globalNames = GlobalNames.fromEl(el)
            el.set("data-global-name", str(globalNames))
            if url is None or globalNames.matches(forcedDfns):
                el.tag = "dfn"
                el.set('data-dfn-type', idlType)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-dfn-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
            else:
                el.tag = "a"
                el.set('data-link-type', idlType)
                el.set('data-lt', idlText)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-link-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
                if el.get('id'):
                    # ID was defensively added by the Marker.
                    del el.attrib['id']
    dfns = findAll("pre.idl:not([data-no-idl]) dfn", doc)
    classifyDfns(doc, dfns)
    dedupIds(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)



def addSyntaxHighlighting(doc):
    # Find what langs are requesting syntax highlighting
    langs = set()
    for el in findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search("(?:lang|language)-(\w+)", el.get("class"))
        if match:
            langs.add(match.group(1))
    if not langs:
        return
    langs.discard("none")

    # If any of the langs have prereqs, put them in too.
    dependencies = {
        "aspnet": "markup",
        "bash": "clike",
        "c": "clike",
        "coffeescript": "javascript",
        "cpp": "c",
        "csharp": "clike",
        "go": "clike",
        "groovy": "clike",
        "java": "clike",
        "javascript": "clike",
        "objectivec": "c",
        "php": "clike",
        "ruby": "clike",
        "scala": "java",
        "scss": "css",
        "swift": "clike"
    }
    langlist = list(langs)
    prereqs = set()
    while langs:
        for lang in langs:
            if lang in dependencies:
                prereqs.add(dependencies[lang])
        langlist = list(prereqs) + langlist
        langs = prereqs
        prereqs = set()

    # Put together all the scripts and insert them.
    pathPrefix = config.scriptPath + "/../prism/"
    script = ""
    style = ""
    def read(filename):
        return io.open(pathPrefix + filename, 'r', encoding="utf-8").read()
    try:
        script += read("prism.js")
        style += read("prism.css")
    except Exception, e:
        die("Couldn't find the syntax highlighting files.\n{0}", e)
        return
    for lang in langlist:
        try:
            script += read(lang+".lang.js")
        except Exception, e:
            die("Can't find the language file for '{0}'.\n{1}", lang, e)
    body = find("body", doc)
    appendChild(body,
        E.script(script),
        E.style(style))



def cleanupHTML(doc):
    # Cleanup done immediately before serialization.

    # Move any stray <link>, <script>, <meta>, or <style> into the <head>.
    head = find("head", doc)
    for el in findAll("body link, body script, body meta, body style:not([scoped])", doc):
        head.append(el)

    # If we accidentally recognized an autolink shortcut in SVG, kill it.
    for el in findAll("svg|a[data-link-type]", doc):
        del el.attrib["data-link-type"]
        el.tag = "{http://www.w3.org/2000/svg}tspan"

    # Tag classes on wide types of dfns/links
    def selectorForTypes(types):
        return ",".join("dfn[data-dfn-type={0}],a[data-link-type={0}]".format(type) for type in types)
    for el in findAll(selectorForTypes(config.idlTypes), doc):
        addClass(el, 'idl-code')
    for el in findAll(selectorForTypes(config.maybeTypes.union(config.linkTypeToDfnType['propdesc'])), doc):
        addClass(el, 'css')
    # Correct over-application of the .css class
    for el in findAll("pre .css", doc):
        removeClass(el, 'css')

    # Remove comments from the generated HTML
    if config.minify:
        comments = list(doc.document.iter(lxml.etree.Comment))
        for comment in comments:
            removeNode(comment)

    # Remove duplicate linking texts.
    for el in findAll("dfn[data-lt], a[data-lt]", doc):
        if el.get('data-lt') == textContent(el):
            del el.attrib['data-lt']

    # Transform the <css> fake tag into markup.
    # (Used when the ''foo'' shorthand doesn't work.)
    for el in findAll("css", doc):
        el.tag = "span"
        addClass(el, "css")

    # Transform the <assert> fake tag into a span with a unique ID based on its contents.
    # This is just used to tag arbitrary sections with an ID so you can point tests at it.
    # (And the ID will be guaranteed stable across publications, but guaranteed to change when the text changes.)
    for el in findAll("assert", doc):
        el.tag = "span"
        el.set("id", "assert-" + hashContents(el))

    # Add ARIA role of "note" to class="note" elements
    for el in findAll(".note", doc):
        el.set("role", "note")

    # Look for nested <a> elements, and warn about them.
    for el in findAll("a a", doc):
        warn("The following (probably auto-generated) link is illegally nested in another link:\n{0}", outerHTML(el))

    # If the <h1> contains only capital letters, add a class=allcaps for styling hook
    h1 = find("h1", doc)
    for letter in textContent(h1):
        if letter.isalpha() and letter.islower():
            break
    else:
        addClass(h1, "allcaps")

    # Remove a bunch of attributes
    for el in findAll("[data-attribute-info], [data-dict-member-info]", doc):
        removeAttr(el, 'data-attribute-info')
        removeAttr(el, 'data-dict-member-info')
        removeAttr(el, 'for')
    for el in findAll("a", doc):
        removeAttr(el, 'data-link-for')
        removeAttr(el, 'data-link-status')
        removeAttr(el, 'data-link-spec')
        removeAttr(el, 'data-section')
        removeAttr(el, 'data-biblio-type')
        removeAttr(el, 'data-biblio-status')
        removeAttr(el, 'data-lt')
    for el in findAll("[data-link-for]:not(a), [data-link-type]:not(a), [data-dfn-for]:not(dfn), [data-dfn-type]:not(dfn)", doc):
        removeAttr(el, 'data-link-for')
        removeAttr(el, 'data-link-type')
        removeAttr(el, 'data-dfn-for')
        removeAttr(el, 'data-dfn-type')
    for el in findAll("[data-export]:not(dfn), [data-noexport]:not(dfn)", doc):
        removeAttr(el, 'data-export')
        removeAttr(el, 'data-noexport')


def finalHackyCleanup(text):
    # For hacky last-minute string-based cleanups of the rendered html.

    return text
















class CSSSpec(object):

    def __init__(self, inputFilename, paragraphMode="markdown"):
        # internal state
        self.normativeRefs = {}
        self.informativeRefs = {}
        self.refs = ReferenceManager()
        self.md = metadata.MetadataManager(doc=self)
        self.biblios = {}
        self.paragraphMode = "markdown"
        self.inputSource = None
        self.macros = defaultdict(lambda x: "???")

        if inputFilename is None:
            # Default to looking for a *.bs file.
            # Otherwise, look for a *.src.html file.
            # Otherwise, use standard input.
            import glob
            if glob.glob("*.bs"):
                inputFilename = glob.glob("*.bs")[0]
            elif glob.glob("*.src.html"):
                inputFilename = glob.glob("*.src.html")[0]
            else:
                inputFilename = "-"
        self.inputSource = inputFilename
        try:
            if inputFilename == "-":
                self.lines = [unicode(line, encoding="utf-8") for line in sys.stdin.readlines()]
                self.md.date = datetime.today()
            else:
                self.lines = io.open(inputFilename, 'r', encoding="utf-8").readlines()
                self.md.date = datetime.fromtimestamp(os.path.getmtime(inputFilename))
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", inputFilename)
            return
        except IOError:
            die("Couldn't open the input file '{0}'.", inputFilename)
            return


        self.refs.initializeRefs(self);
        self.refs.initializeBiblio();

        self.testSuites = json.loads(config.retrieveCachedFile("test-suites.json", quiet=True, str=True))

        if "css21Replacements" in self.refs.defaultSpecs:
            self.refs.css21Replacements = set(self.refs.defaultSpecs["css21Replacements"])
            del self.refs.defaultSpecs["css21Replacements"]
        if "ignoredSpecs" in self.refs.defaultSpecs:
            self.refs.ignoredSpecs = set(self.refs.defaultSpecs["ignoredSpecs"])
            del self.refs.defaultSpecs["ignoredSpecs"]
        if "customDfns" in self.refs.defaultSpecs:
            for specName, specUrl, dfnText, dfnType, dfnUrl in self.refs.defaultSpecs["customDfns"]:
                if specName not in self.refs.specs:
                    levelMatch = re.match(r"(.*)-(\d+)", specName)
                    if levelMatch:
                        shortname = levelMatch.group(1)
                        level = levelMatch.group(2)
                    else:
                        shortname = specName
                        level = "1"
                    self.refs.specs[specName] = {
                        "description": "Custom Spec Link for {0}".format(specName),
                        "data-lt": "Custom Spec Link for {0}".format(specName),
                        "level": config.HierarchicalNumber(level),
                        "TR": specUrl,
                        "shortname": shortname,
                        "vshortname": specName
                    }
                spec = self.refs.specs[specName]
                self.refs.refs[dfnText].append({
                    "status": "TR",
                    "export": True,
                    "for": [],
                    "level": spec['level'],
                    "url": specUrl + dfnUrl,
                    "normative": True,
                    "shortname": spec['shortname'],
                    "spec": spec['vshortname'],
                    "type": dfnType
                })
            del self.refs.defaultSpecs["customDfns"]

        self.paragraphMode = paragraphMode

    def preprocess(self):
        # Textual hacks
        stripBOM(self)

        # Extract and process metadata
        self.lines = metadata.parse(md = self.md, lines=self.lines)
        self.loadDefaultMetadata()
        self.md.finish()
        self.md.fillTextMacros(self.macros, doc=self)

        # Deal with further <pre> blocks, and markdown
        transformDataBlocks(self)
        if self.paragraphMode == "markdown":
            self.lines = markdown.parse(self.lines, self.md.indent)

        self.refs.setSpecData(self.md)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(self.lines)
        fillInBoilerplate(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = parseDocument(self.html)
        metadata.parseDoc(self)

        # Fill in and clean up a bunch of data
        addStatusSection(self)
        addLogo(self)
        addCopyright(self)
        addSpecMetadataSection(self)
        addAbstract(self)
        addObsoletionNotice(self)
        addAtRisk(self)
        self.transformProductionPlaceholders()
        self.transformMaybePlaceholders()
        self.transformAutolinkShortcuts()
        self.transformProductionGrammars()
        formatPropertyNames(self)
        processHeadings(self)
        canonicalizeShortcuts(self)
        processIssues(self)
        markupIDL(self)


        # Handle all the links
        temporaryCheckForExcessiveTitle(self)
        processDfns(self)
        processIDL(self)
        fillAttributeInfoSpans(self)
        formatElementdefTables(self)
        processBiblioLinks(self)
        processAutolinks(self)

        addReferencesSection(self)
        addIndexSection(self)
        addPropertyIndex(self)
        addIDLSection(self)
        addIssuesSection(self)
        addCustomBoilerplate(self)
        processHeadings(self, "all") # again
        addTOCSection(self)
        addSelfLinks(self)
        processAutolinks(self)
        addAnnotations(self)
        addSyntaxHighlighting(self)
        fixIntraDocumentReferences(self)

        # Any final HTML cleanups
        cleanupHTML(self)

        return self


    def serialize(self):
        rendered = HTMLSerializer.HTMLSerializer(self.document).serialize()
        rendered = finalHackyCleanup(rendered)
        return rendered


    def finish(self, outputFilename):
        if outputFilename is None:
            # More sensible defaults!
            if self.inputSource.endswith(".bs"):
                outputFilename = self.inputSource[0:-3] + ".html"
            elif self.inputSource.endswith(".src.html"):
                outputFilename = self.inputSource[0:-9] + ".html"
            elif self.inputSource == "-":
                outputFilename = "-"
            else:
                outputFilename = "-"
        rendered = self.serialize()
        if not config.dryRun:
            try:
                if outputFilename == "-":
                    outputFile = sys.stdout.write(rendered)
                else:
                    with io.open(outputFilename, "w", encoding="utf-8") as f:
                        f.write(rendered)
            except Exception, e:
                die("Something prevented me from saving the output document to {0}:\n{1}", outputFilename, e)

    def loadDefaultMetadata(self):
        data = self.getInclusion('defaults', error=False)
        try:
            defaults = json.loads(data)
        except Exception, e:
            if data != "":
                die("Error loading defaults:\n{0}", str(e))
            return
        for key,val in defaults.items():
            self.md.addDefault(key, val)

    def fixText(self, text):
        # Do several textual replacements that need to happen *before* the document is parsed as HTML.

        # Replace the [FOO] things.
        #for tag, replacement in self.macros.items():
        #    text = text.replace("[{0}]".format(tag.upper()), replacement)
        def macroReplacer(match):
            fullText = match.group(0)
            innerText = match.group(2) or ""
            if fullText.startswith("\\"):
                # Escaped
                return fullText[1:]
            if fullText.startswith("[["):
                # Actually a biblio link
                return fullText
            if innerText.isdigit():
                # No refs are all-digits (this is probably JS code).
                return fullText
            if innerText.lower() in self.macros:
                # For some reason I store all the macros in lowercase,
                # despite requiring them to be spelled with uppercase.
                return self.macros[innerText.lower()]
            die("Found unmatched text macro {0}. Correct the macro, or escape it with a leading backslash.", fullText)
            return fullText
        text = re.sub(r"(\\|\[)?\[([A-Z0-9-]+)\]", macroReplacer, text)
        text = fixTypography(text)
        if "css" in self.md.markupShorthands:
            # Replace the <<production>> shortcuts, because they won't survive the HTML parser.
            text = re.sub("<<([^>\s]+)>>", r"<fake-production-placeholder class=production>\1</fake-production-placeholder>", text)
            # Replace the ''maybe link'' shortcuts.
            # They'll survive the HTML parser, but they don't match if they contain an element.
            # (The other shortcuts are "atomic" and can't contain elements.)
            text = re.sub(r"''([^=\n]+?)''", r'<fake-maybe-placeholder>\1</fake-maybe-placeholder>', text)
        return text

    def transformProductionPlaceholders(doc):
        propdescRe = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")
        funcRe = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
        atruleRe = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
        typeRe = re.compile(r"^(?:(\S*)/)?([\w-]+)$")
        for el in findAll("fake-production-placeholder", doc):
            text = textContent(el)
            clearContents(el)
            match = propdescRe.match(text)
            if match:
                if match.group(3) is None:
                    linkType = "propdesc"
                elif match.group(3) in ("property", "descriptor"):
                    linkType = match.group(2)
                else:
                    die("Shorthand <<{0}>> gives type as '{1}', but only 'property' and 'descriptor' are allowed.", match.group(0), match.group(3))
                    el.tag = "span"
                    el.text = "<‘" + text[1:-1] + "’>"
                    continue
                el.tag = "a"
                el.set("data-link-type", linkType)
                el.set("data-lt", match.group(2))
                if match.group(1) is not None:
                    el.set("for", match.group(1))
                el.text = "<‘" + match.group(2) + "’>"
                continue
            match = funcRe.match(text)
            if match:
                el.tag = "a"
                el.set("data-link-type", "function")
                el.set("data-lt", match.group(2))
                if match.group(1) is not None:
                    el.set("for", match.group(1))
                el.text = "<" + match.group(2) + ">"
                continue
            match = atruleRe.match(text)
            if match:
                el.tag = "a"
                el.set("data-link-type", "at-rule")
                el.set("data-lt", match.group(2))
                if match.group(1) is not None:
                    el.set("for", match.group(1))
                el.text = "<" + match.group(2) + ">"
                continue
            match = typeRe.match(text)
            if match:
                el.tag = "a"
                el.set("data-link-type", "type")
                if match.group(1) is not None:
                    el.set("for", match.group(1))
                el.text = "<" + match.group(2) + ">"
                continue
            die("Shorthand <<{0}>> does not match any recognized shorthand grammar.", text)
            continue

    def transformMaybePlaceholders(doc):
        propRe = re.compile(r"^([\w-]+): .+")
        valRe = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")
        for el in findAll("fake-maybe-placeholder", doc):
            text = textContent(el)
            clearContents(el)
            match = propRe.match(text)
            if match:
                el.tag = "a"
                el.set("class", "css")
                el.set("data-link-type", "propdesc")
                el.set("data-lt", match.group(1))
                el.text = text
                continue
            match = valRe.match(text)
            if match:
                if match.group(3) is None:
                    linkType = "maybe"
                elif match.group(3) in config.maybeTypes:
                    linkType = match.group(3)
                else:
                    die("Shorthand ''{0}'' gives type as '{1}', but only “maybe” types are allowed.", match.group(0), match.group(3))
                    el.tag = "css"
                    continue
                el.tag = "a"
                el.set("class", "css")
                el.set("data-link-type", linkType)
                el.set("data-lt", match.group(2))
                if match.group(1) is not None:
                    el.set("for", match.group(1))
                el.text = match.group(2)
                continue
            el.tag="css"
            el.text = text

    def transformAutolinkShortcuts(doc):
        # Do the remaining textual replacements

        biblioRe = re.compile(r"(\\)?\[\[(!)?([\w-]+)((?: +current)|(?: +dated))?\]\]")
        def biblioReplacer(match):
            # Allow escaping things that aren't actually biblio links, by preceding with a \
            if match.group(1) is not None:
                return match.group(0)[1:]
            if match.group(2) == "!":
                type = "normative"
            else:
                type = "informative"
            term = match.group(3)
            attrs = {"data-lt":term, "data-link-type":"biblio", "data-biblio-type":type}
            if match.group(4) is not None:
                attrs['data-biblio-status'] = match.group(4).strip()
            return E.a(attrs,
                "[",
                term,
                "]")

        sectionRe = re.compile(r"\[\[(#[\w-]+)\]\]")
        def sectionReplacer(match):
            return E.a({"section":"", "href":match.group(1)})

        propdescRe = re.compile(r"'(?:([^\s']*)/)?([\w*-]+)(?:!!([\w-]+))?'")
        def propdescReplacer(match):
            if match.group(2) == "-":
                return "'-'"
            if match.group(3) is None:
                linkType = "propdesc"
            elif match.group(3) in ("property", "descriptor"):
                linkType = match.group(3)
            else:
                die("Shorthand {0} gives type as '{1}', but only 'property' and 'descriptor' are allowed.", match.group(0), match.group(3))
                return E.span(match.group(0))
            return E.a({"data-link-type":linkType, "class":"property", "for": match.group(1)}, match.group(2))

        idlRe = re.compile(r"{{(?:([^ }]*)/)?((?:[^ }]|,\s)+?)(?:!!([\w-]+))?}}")
        def idlReplacer(match):
            if match.group(3) is None:
                linkType = "idl"
            elif match.group(3) in config.idlTypes:
                linkType = match.group(3)
            else:
                die("Shorthand {0} gives type as '{1}', but only IDL types are allowed.", match.group(0), match.group(3))
                return E.span(match.group(0))
            return E.code({"class":"idl"},
                E.a({"data-link-type":linkType, "for": match.group(1)}, match.group(2)))

        elementRe = re.compile(r"<{(?:([\w-]+)/)?([\w-]+)}>")
        def elementReplacer(match):
            linkType = "element" if match.group(1) is None else "element-attr"
            return E.code({},
                E.a({"data-link-type":linkType, "for": match.group(1)}, match.group(2)))

        def transformElement(parentEl):
            processContents = isElement(parentEl) and not isOpaqueElement(parentEl)
            if not processContents:
                return
            children = childNodes(parentEl, clear=True)
            newChildren = []
            for el in children:
                if isinstance(el, basestring):
                    newChildren.extend(transformText(el))
                elif isElement(el):
                    transformElement(el)
                    newChildren.append(el)
            appendChild(parentEl, *newChildren)

        def transformText(text):
            nodes = [text]
            if "css" in doc.md.markupShorthands:
                config.processTextNodes(nodes, propdescRe, propdescReplacer)
            if "idl" in doc.md.markupShorthands:
                config.processTextNodes(nodes, idlRe, idlReplacer)
            if "markup" in doc.md.markupShorthands:
                config.processTextNodes(nodes, elementRe, elementReplacer)
            if "biblio" in doc.md.markupShorthands:
                config.processTextNodes(nodes, biblioRe, biblioReplacer)
                config.processTextNodes(nodes, sectionRe, sectionReplacer)
            return nodes

        transformElement(doc.document.getroot())


    def transformProductionGrammars(doc):
        # Link up the various grammar symbols in CSS grammars to their definitions.
        if "css" not in doc.md.markupShorthands:
            return

        hashMultRe = re.compile(r"#{\s*\d+(\s*,(\s*\d+)?)?\s*}")
        def hashMultReplacer(match):
            return E.a({"data-link-type":"grammar", "data-lt": "#", "for":""}, match.group(0))

        multRe = re.compile(r"{\s*\d+\s*}")
        def multReplacer(match):
            return E.a({"data-link-type":"grammar", "data-lt": "{A}", "for":""}, match.group(0))

        multRangeRe = re.compile(r"{\s*\d+\s*,(\s*\d+)?\s*}")
        def multRangeReplacer(match):
            return E.a({"data-link-type":"grammar", "data-lt": "{A,B}", "for":""}, match.group(0))

        simpleRe = re.compile(r"\?|!|#|\*|\+|\|\||\||&amp;&amp;|,")
        def simpleReplacer(match):
            return E.a({"data-link-type":"grammar", "data-lt": match.group(0), "for":""}, match.group(0))

        def transformElement(parentEl):
            children = childNodes(parentEl, clear=True)
            newChildren = []
            for el in children:
                if isinstance(el, basestring):
                    newChildren.extend(transformText(el))
                elif isElement(el):
                    transformElement(el)
                    newChildren.append(el)
            appendChild(parentEl, *newChildren)

        def transformText(text):
            nodes = [text]
            config.processTextNodes(nodes, hashMultRe, hashMultReplacer)
            config.processTextNodes(nodes, multRe, multReplacer)
            config.processTextNodes(nodes, multRangeRe, multRangeReplacer)
            config.processTextNodes(nodes, simpleRe, simpleReplacer)
            return nodes

        for el in findAll(".prod", doc):
            transformElement(el)

    def printTargets(self):
        print "Exported terms:"
        for el in findAll("dfn[data-export]", doc):
            for term in  linkTextsFromElement(el):
                print "  ", term
        print "Unexported terms:"
        for el in findAll("dfn[data-noexport]", doc):
            for term in  linkTextsFromElement(el):
                print "  ", term

    def getInclusion(self, name, group=None, status=None, error=True):
        # First looks for a file specialized on the group and status.
        # If that fails, specializes only on the group.
        # If that fails, specializes only on the status.
        # If that fails, grabs the most general file.
        # Filenames must be of the format NAME-GROUP-STATUS.include
        if group is None:
            group = self.md.group
        if status is None:
            status = self.md.status

        pathprefix = config.scriptPath + "/include"
        for filename in [
            "{0}/{1}.include".format(os.path.dirname(os.path.abspath(self.inputSource)), name),
            "{0}/{1}-{2}-{3}.include".format(pathprefix, name, group, status),
            "{0}/{1}-{2}.include".format(pathprefix, name, group),
            "{0}/{1}-{2}.include".format(pathprefix, name, status),
            "{0}/{1}.include".format(pathprefix, name),
        ]:
            if os.path.isfile(filename):
                break
        else:
            if error:
                die("Couldn't find an appropriate include file for the {0} inclusion, given group='{1}' and status='{2}'.", name, group, status)
            filename = "/dev/null"

        try:
            with io.open(filename, 'r', encoding="utf-8") as fh:
                return fh.read()
        except IOError:
            if error:
                die("The include file for {0} disappeared underneath me.", name)

config.specClass = CSSSpec













def formatElementdefTables(doc):
    for table in findAll("table.elementdef", doc):
        elements = findAll("tr:first-child dfn", table)
        elementsFor = ' '.join(textContent(x) for x in elements)
        for el in findAll("a[data-element-attr-group]", table):
            groupName = textContent(el).strip()
            groupFor = re.sub("\s+", "-", groupName)
            groupAttrs = sorted(doc.refs.queryRefs(linkType="element-attr", linkFor=groupFor), key=lambda x:x[1])
            if len(groupAttrs) == 0:
                die("The element-attr group '{0}' doesn't have any attributes defined for it.", groupName)
                continue
            el.tag = "details"
            clearContents(el)
            del el.attrib["data-element-attr-group"]
            del el.attrib["dfn"]
            ul = appendChild(el,
                E.summary(
                    E.a({"data-link-type":"dfn"}, groupName)),
                E.ul())
            for attrName,ref in groupAttrs:
                appendChild(ul,
                    E.li(
                        E.dfn({"id":"element-attrdef-"+simplifyText(textContent(elements[0]))+"-"+attrName, "for":elementsFor, "data-dfn-type":"element-attr"},
                            E.a({"data-link-type":"element-attr", "for":groupFor},
                                attrName.strip()))))



def fillInBoilerplate(doc):
    # If you start your spec with an <h1>, I'll take it as the spec's title and remove it.
    # (It gets added back in the header file.)
    match = re.match(r"^<h1>(.+?)</h1>", doc.html)
    if match:
        doc.md.title = match.group(1)
        doc.macros['title'] = doc.md.title
        doc.html = doc.html[len(match.group(0)):]

    if not doc.md.title:
        die("Can't generate the spec without a title.\nAdd a 'Title' metadata entry, or an <h1> on the first line.")

    header = doc.getInclusion('header') if "header" not in doc.md.boilerplate['omitSections'] else ""
    footer = doc.getInclusion('footer') if "footer" not in doc.md.boilerplate['omitSections'] else ""

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
    html = doc.getInclusion('logo')
    html = doc.fixText(html)
    fillWith('logo', parseHTML(html), doc=doc)


def addCopyright(doc):
    html = doc.getInclusion('copyright')
    html = doc.fixText(html)
    fillWith('copyright', parseHTML(html), doc=doc)


def addAbstract(doc):
    html = doc.getInclusion('abstract')
    html = doc.fixText(html)
    fillWith('abstract', parseHTML(html), doc=doc)


def addStatusSection(doc):
    html = doc.getInclusion('status')
    html = doc.fixText(html)
    fillWith('status', parseHTML(html), doc=doc)


def addObsoletionNotice(doc):
    if doc.md.warning:
        html = doc.getInclusion(doc.md.warning[0])
        html = doc.fixText(html)
        fillWith('warning', parseHTML(html), doc=doc)

def addAtRisk(doc):
    if len(doc.md.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.md.atRisk:
        html += "<li>"+doc.fixText(feature)
    fillWith('at-risk', parseHTML(html), doc=doc)

def addCustomBoilerplate(doc):
    for el in findAll('[boilerplate]', doc):
        bType = el.get('boilerplate')
        target = find('[data-fill-with="{0}"]'.format(bType), doc)
        if target is not None:
            replaceContents(target, el)
            removeNode(el)

def addAnnotations(doc):
    if (doc.md.vshortname in doc.testSuites):
        html = doc.getInclusion('annotations')
        html = doc.fixText(html)
        appendContents(find("head", doc), parseHTML(html))

def addIndexSection(doc):
    if len(findAll("dfn", doc)) == 0:
        return
    container = getFillContainer('index', doc=doc, default=True)
    if container is None:
        return
    appendChild(container,
        E.h2({"class":"no-num", "id":"index"}, "Index"))

    from collections import OrderedDict
    indexEntries = defaultdict(list)
    attemptedForRefs = defaultdict(list)
    seenGlobalNames = set()
    for el in findAll("dfn[id]", doc):
        linkTexts = linkTextsFromElement(el)
        headingLevel = headingLevelOfElement(el) or "Unnumbered section"
        if el.get('data-dfn-for') is not None:
            disambiguator = "{0} for {1}".format(el.get('data-dfn-type'), ', '.join(splitForValues(el.get('data-dfn-for'))))
        else:
            type = el.get('data-dfn-type')
            if type == "dfn":
                disambiguator = "definition of"
            else:
                disambiguator = "({0})".format(el.get('data-dfn-type'))
        id = el.get('id')
        seenGlobalNames.update(GlobalNames.fromEl(el))
        for linkText in linkTexts:
            sort = re.sub(r'[^a-z0-9]', '', linkText.lower())
            entry = {
                'text':linkText,
                'type':el.get('data-dfn-type'),
                'id':id,
                'level':headingLevel,
                'disambiguator':disambiguator,
                'sort':sort,
                'globalNames': GlobalNames.fromEl(el)
                }
            indexEntries[linkText].append(entry)
            for ref in GlobalNames.refsFromEl(el):
                attemptedForRefs[ref].append(entry)
    unseenForRefs = set(attemptedForRefs.viewkeys()).difference(seenGlobalNames)

    # Now print the indexes
    sortedEntries = OrderedDict(sorted(indexEntries.items(), key=lambda x:x[1][0]['sort']))
    topList = appendChild(container, E.ul({"class":"indexlist"}))
    for text, items in sortedEntries.items():
        if len(items) == 1:
            item = items[0]
            li = appendChild(topList,
                E.li(item['text'], ", ",
                    E.a({"href":"#"+item['id']}, item['level'])))
            if item['type'] == "property":
                reffingDfns = []
                for globalName in item['globalNames']:
                    reffingDfns += attemptedForRefs[globalName]
                if reffingDfns:
                    dl = appendChild(li, E.dl(E.dt("Property Values:")))
                    for r in reffingDfns:
                        appendChild(dl,
                            E.dd(r.text, ", ",
                                E.a({"href":"#"+r['id']}, r['level'])))
        else:
            li = appendChild(topList, E.li(items[0]['text']))
            ul = appendChild(li, E.ul())
            for item in items:
                appendChild(ul,
                    E.li(item['disambiguator'], ", ",
                        E.a({"href":"#"+item['id']}, item['level'])))



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
            die("Propdef row headers need be a word followed by a colon. Got:\n{0}", textContent(row[0]).strip())
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
            return name
        def createPropRow(prop):
            return E.tr(
                E.th({"scope":"row"},
                    E.a({"data-link-type":"property"}, prop['Name'])),
                *[E.td(prop.get(column,"")) for column in columns[1:]])
        appendChild(html,
            E.table({"class":"proptable data"},
                E.thead(
                    E.tr(
                        *[E.th({"scope":"col"}, formatColumnName(column)) for column in columns])),
                E.tbody(
                    *[createPropRow(prop) for prop in props])))
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
                E.h3({"class":"no-num", "id":simplifyText(atRuleName)+"-descriptor-table"},
                    E.a({"data-link-type":"at-rule"}, atRuleName),
                    " Descriptors"))
            tbody = appendChild(html,
                E.table({"class":"proptable data"},
                    E.thead(
                        E.tr(
                            *[E.th({"scope":"col"}, column) for column in columns])),
                    E.tbody()))
            for desc in descs:
                appendChild(tbody,
                    E.tr(
                        E.th({"scope":"row"},
                            E.a({"data-link-type":"descriptor"}, desc['Name'])),
                        *[E.td(desc.get(column, "")) for column in columns[1:]]))


def addIDLSection(doc):
    from copy import deepcopy
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
        copy = deepcopy(block)
        appendContents(container, copy)
        appendChild(container, "\n")
    for dfn in findAll("dfn[id]", container):
        dfn.tag = "a"
        dfn.set("href", "#"+dfn.get("id"))
        del dfn.attrib["id"]


def addTOCSection(doc):
    skipLevel = float('inf')
    previousLevel = 1
    containers = [0, 1, 2, 3, 4, 5, 6, 7]
    containers[1] = E.div()
    containers[2] = appendChild(containers[1], E.ul({"class":"toc", "role":"directory"}))
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
                        deepcopy(find(".content", header)))))
            containers[level+1] = appendChild(li, E.ul({"class":"toc"}))
        previousLevel = level

    container = containers[1]
    for el in findAll(".content a, .content dfn", container):
        el.tag = "span"
        if "href" in el.attrib:
            del el.attrib["href"]
    for el in findAll(".content [id]", container):
        del el.attrib["id"]
    for el in findAll("ul:empty", container):
        removeNode(el)
    fillWith("table-of-contents", container, doc=doc)


def addSpecMetadataSection(doc):
    def printEditor(editor):
        div = E.div({"class":"p-author h-card vcard"})
        if editor['link']:
            appendChild(div, E.a({"class":"p-name fn u-url url", "href":editor['link']}, editor['name']))
        elif editor['email']:
            appendChild(div, E.a({"class":"p-name fn u-email email", "href":"mailto:"+editor['email']}, editor['name']))
        else:
            appendChild(div, E.span({"class":"p-name fn"}, editor['name']))
        if editor['org']:
            if editor['orglink']:
                el = E.a({"class":"p-org org", "href":editor['orglink']}, editor['org'])
            else:
                el = E.span({"class":"p-org org"}, editor['org'])
            appendChild(div, " (", el, ")")
        if editor['email'] and editor['link']:
            appendChild(div,
                " ",
                E.a({"class":"u-email email", "href":"mailto:"+editor['email']}, editor['email']))
        return div

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
    if doc.md.versionHistory:
        md["Version History"].append(E.a({"href":doc.md.versionHistory}, doc.md.versionHistory))
    if doc.md.mailingList:
        span = E.span(
            E.a({"href":"mailto:"+doc.md.mailingList+"?subject=%5B"+mac['shortname']+"%5D%20feedback"}, doc.md.mailingList),
            " with subject line “",
            E.kbd(
                "[",
                mac['shortname'],
                "] ",
                E.var(
                    "… message topic …")),
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
        md["Editor" if len(doc.md.editors) == 1 else "Editors"] = map(printEditor, doc.md.editors)
    if len(doc.md.previousEditors):
        md["Former Editor" if len(doc.md.editors) == 1 else "Former Editors"] = map(printEditor, doc.md.previousEditors)
    for key, vals in doc.md.otherMetadata.items():
        md[key].extend(parseHTML("<span>"+doc.fixText(val)+"</span>")[0] for val in vals)

    dl = E.dl()
    for key, vals in md.items():
        attrs = {}
        if key in ("Editor", "Editors"):
            attrs["class"] = "editor"
        appendChild(dl,
            E.dt(attrs, key, ":"),
            *[E.dd(attrs, val) for val in vals])
    fillWith('spec-metadata', E.div(dl), doc=doc)


def addReferencesSection(doc):
    if len(doc.normativeRefs) == 0 and len(doc.informativeRefs) is None:
        return
    container = getFillContainer('references', doc=doc, default=True)
    if container is None:
        return

    appendChild(container,
        E.h2({"class":"no-num", "id":"references"}, "References"))

    normRefs = sorted(doc.normativeRefs.values(), key=lambda r: r.linkText)
    if len(normRefs):
        dl = appendChild(container,
            E.h3({"class":"no-num", "id":"normative"}, "Normative References"),
            E.dl())
        for ref in normRefs:
            appendChild(dl, E.dt({"id":"biblio-"+simplifyText(ref.linkText)}, "["+ref.linkText+"]"))
            appendChild(dl, E.dd(*ref.toHTML()))

    informRefs = [x for x in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText) if x.linkText not in doc.normativeRefs]
    if len(informRefs):
        dl = appendChild(container,
            E.h3({"class":"no-num", "id":"informative"}, "Informative References"),
            E.dl())
        for ref in informRefs:
            appendChild(dl, E.dt({"id":"biblio-"+simplifyText(ref.linkText)}, "["+ref.linkText+"]"))
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
        el = deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre",):
            el.tag = "div"
        appendChild(container, el)
        appendChild(el,
            E.a({"href":"#"+issue.get('id')}, " ↵ "))
    for idel in findAll("[id]", container):
        del idel.attrib['id']
    for dfnel in findAll("dfn", container):
        dfnel.tag = "span"


def temporaryCheckForExcessiveTitle(doc):
    # This function is a migration aid, to help warn a spec if it uses a bunch of title attributes.
    if len(findAll("dfn[title]:not([data-lt]), a[title]:not([data-lt])", doc)) > 0:
        warn("Bikeshed now prefers you specify alternate linking texts with the 'lt' attribute, not 'title'. Please change your source.")
