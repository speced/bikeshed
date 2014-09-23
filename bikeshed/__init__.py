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
import html5lib
import lxml
import cProfile

from . import config
from . import biblio
from . import update
from . import markdown
from . import test
from . import MetadataManager as metadata
from .ReferenceManager import ReferenceManager
from .ReferenceManager import linkTextsFromElement
from .globalnames import *
from .htmlhelpers import *
from .messages import *
from .widlparser.widlparser import parser
from .DefaultOrderedDict import DefaultOrderedDict


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

    options = argparser.parse_args()

    config.quiet = options.quiet
    config.debug = options.debug
    config.dryRun = options.dryRun
    config.minify = getattr(options, 'minify', True)

    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, linkDefaults=options.linkDefaults, testSuites=options.testSuites)
    elif options.subparserName == "spec":
        doc = CSSSpec(inputFilename=options.infile, paragraphMode=options.paragraphMode)
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
            refs = doc.refs.refs[options.linkText]
            config.quiet = options.quiet
            if not config.quiet:
                print "Refs for '{0}':".format(options.linkText)
            # Get ready for JSONing
            for ref in refs:
                ref['level'] = str(ref['level'])
            print json.dumps(refs, indent=2)
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
            test.runAllTests(constructor=CSSSpec)
    elif options.subparserName == "profile":
        root = "--root=\"{0}\"".format(options.root) if options.root else ""
        leaf = "--leaf=\"{0}\"".format(options.leaf) if options.leaf else ""
        os.system("python -m cProfile -o stat.prof ~/bikeshed/bikeshed.py && gprof2dot -f pstats --skew=.0001 {root} {leaf} stat.prof | dot -Tsvg -o callgraph.svg && rm stat.prof".format(root=root, leaf=leaf))



def stripBOM(doc):
    if doc.lines[0][0] == "\ufeff":
        doc.lines[0] = doc.lines[0][1:]
        warn("Your document has a BOM. There's no need for that, please re-save it without a BOM.")


# This function does a single pass through the doc,
# finding all the "data blocks" and processing them.
# A "data block" is any <pre> or <xmp> element.
#
# When a data block is found, the *contents* of the block
# are passed to the appropriate processing function as an
# array of lines.  The function should return a new array
# of lines to replace the *entire* block.
#
# That is, we give you the insides, but replace the whole
# thing.
#
# Additionally, we pass in the tag-name used (pre or xmp)
# and the line with the content, in case it has useful data in it.
def transformDataBlocks(doc):
    inBlock = False
    blockTypes = {
        'propdef': transformPropdef,
        'descdef': transformDescdef,
        'elementdef': transformElementdef,
        'railroad': transformRailroad,
        'biblio': transformBiblio,
        'pre': transformPre
    }
    blockType = ""
    tagName = ""
    startLine = 0
    replacements = []
    for (i, line) in enumerate(doc.lines):
        # Look for the start of a block.
        match = re.match(r"\s*<(pre|xmp)(.*)", line, re.I)
        if match and not inBlock:
            inBlock = True
            startLine = i
            tagName = match.group(1)
            typeMatch = re.search("|".join(blockTypes.keys()), match.group(2))
            if typeMatch:
                blockType = typeMatch.group(0)
            else:
                blockType = "pre"
        # Look for the end of a block.
        match = re.match(r"(.*)</"+tagName+">(.*)", line, re.I)
        if match and inBlock:
            inBlock = False
            if startLine == i:
                # Single-line <pre>.
                match = re.match(r"\s*(<{0}[^>]*>)(.+)</{0}>(.*)".format(tagName), line, re.I)
                doc.lines[i] = match.group(3)
                replacements.append({
                    'start': i,
                    'end': i,
                    'value': blockTypes[blockType](
                        lines=[match.group(2)],
                        tagName=tagName,
                        firstLine=match.group(1),
                        doc=doc)})
            elif re.match(r"^\s*$", match.group(1)):
                # End tag was the first tag on the line.
                # Remove the tag from the line.
                doc.lines[i] = match.group(2)
                replacements.append({
                    'start': startLine,
                    'end': i,
                    'value': blockTypes[blockType](
                        lines=doc.lines[startLine+1:i],
                        tagName=tagName,
                        firstLine=doc.lines[startLine],
                        doc=doc)})
            else:
                # End tag was at the end of line of useful content.
                # Trim this line to be only the block content.
                doc.lines[i] = match.group(1)
                # Put the after-tag content on the next line.
                doc.lines.insert(i+1, match.group(2))
                replacements.append({
                    'start': startLine,
                    'end': i+1,
                    'value': blockTypes[blockType](
                        lines=doc.lines[startLine+1:i+1],
                        tagName=tagName,
                        firstLine=doc.lines[startLine],
                        doc=doc)})
            tagName = ""
            blockType = ""

    # Make the replacements, starting from the bottom up so I
    # don't have to worry about offsets becoming invalid.
    for rep in reversed(replacements):
        doc.lines[rep['start']:rep['end']] = rep['value']


def transformPre(lines, tagName, firstLine, **kwargs):
    indent = float("inf")
    for (i, line) in enumerate(lines):
        # Use tabs in the source, but spaces in the output,
        # because tabs are ginormous in HTML.
        # Also, it means lines in processed files will never
        # accidentally match a prefix.
        lines[i] = lines[i].replace("\t", "  ")

        # Find the line with the shortest whitespace prefix.
        # (It might not be the first!)
        if line.strip() != "":
            indent = min(indent, len(re.match(r" *", lines[i]).group(0)))

    if indent == float("inf"):
        indent = 0

    # Strip off the whitespace prefix from each line
    for (i, line) in enumerate(lines):
        lines[i] = lines[i][indent:]
    # Put the first/last lines back into the results.
    lines.insert(0, firstLine)
    lines.append("</"+tagName+">")
    return lines


def transformPropdef(lines, doc, firstLine, **kwargs):
    vals = parseDefBlock(lines, "propdef")
    # The required keys are specified in the order they should show up in the propdef table.
    if "partial" in firstLine or "New values" in vals:
        requiredKeys = ["Name", "New values"]
        ret = ["<table class='definition propdef partial'>"]
    else:
        requiredKeys = ["Name", "Value", "Initial", "Applies to", "Inherited", "Media", "Computed value"]
        ret = ["<table class='definition propdef'>"]
    for key in requiredKeys:
        if key == "Value":
            ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, vals.get(key,'')))
        elif key.lower() == "new values":
            ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, vals.get(key,'')))
        elif key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals.get(key,'')))
        else:
            die("The propdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret


def transformDescdef(lines, doc, firstLine, **kwargs):
    vals = parseDefBlock(lines, "descdef")
    if "partial" in firstLine or "New values" in vals:
        requiredKeys = ["Name", "For"]
        ret = ["<table class='definition descdef partial' data-dfn-for='{0}'>".format(vals.get("For", ""))]
    if "mq" in firstLine:
        requiredKeys = ["Name", "For", "Value"]
        ret = ["<table class='definition descdef mq' data-dfn-for='{0}'>".format(vals.get("For",""))]
    else:
        requiredKeys = ["Name", "For", "Value", "Initial"]
        ret = ["<table class='definition descdef' data-dfn-for='{0}'>".format(vals.get("For", ""))]
    for key in requiredKeys:
        if key == "For":
            ret.append("<tr><th>{0}:<td><a at-rule>{1}</a>".format(key, vals.get(key,'')))
        elif key == "Value":
            ret.append("<tr><th>{0}:<td class='prod'>{1}".format(key, vals.get(key,'')))
        elif key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals.get(key,'')))
        else:
            die("The descdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret

def transformElementdef(lines, doc, **kwargs):
    vals = parseDefBlock(lines, "elementdef")
    requiredKeys = ["Name", "Categories", "Contexts", "Content model", "Attributes"]
    ret = ["<table class='definition elementdef'>"]
    for key in requiredKeys:
        if key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
        else:
            die("The elementdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret



def parseDefBlock(lines, type):
    vals = {}
    for (i, line) in enumerate(lines):
        match = re.match(r"\s*([^:]+):\s*(.*)", line)
        if(match is None):
            die("Incorrectly formatted {2} line for '{0}':\n{1}", vals.get("Name", "???"), line, type)
            continue
        key = match.group(1).strip().capitalize()
        val = match.group(2).strip()
        if key == "Value" and "Value" in vals:
            vals[key] += " "+val
        else:
            vals[key] = val
    return vals

def transformRailroad(lines, doc, **kwargs):
    import StringIO
    import railroadparser
    ret = [
        "<div class='railroad'>",
        "<style>svg.railroad-diagram{background-color:hsl(30,20%,95%);}svg.railroad-diagram path{stroke-width:3;stroke:black;fill:rgba(0,0,0,0);}svg.railroad-diagram text{font:bold 14px monospace;text-anchor:middle;}svg.railroad-diagram text.label{text-anchor:start;}svg.railroad-diagram text.comment{font:italic 12px monospace;}svg.railroad-diagram rect{stroke-width:3;stroke:black;fill:hsl(120,100%,90%);}</style>"]
    code = ''.join(lines)
    diagram = railroadparser.parse(code)
    temp = StringIO.StringIO()
    diagram.writeSvg(temp.write)
    ret.append(temp.getvalue())
    temp.close()
    ret.append("</div>")
    return ret

def transformBiblio(lines, doc, **kwargs):
    biblio.processSpecrefBiblioFile(''.join(lines), doc.refs.biblios, order=1)
    return []















# Headings Stuff

def processHeadings(doc):
    for el in findAll('h2, h3, h4, h5, h6', doc):
        addClass(el, 'heading')
    headings = findAll(".heading:not(.settled)", doc)
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
            header.set('id', simplifyText(textContent(find(".content", header))))
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
            secno.text = header.get('data-level') + ' '
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
        "local-title":"data-local-title"
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
    for el in findAll("a[data-section]", doc):
        if el.text is None or el.text.strip() == '':
            sectionID = el.get("href")
            if sectionID is None or sectionID == "" or sectionID[0] != '#':
                die("Missing/invalid href {0} in section link.", sectionID)
                continue
            targets = findAll("{0}.heading".format(sectionID), doc)
            if len(targets) == 0:
                die("Couldn't find target document section {0}:\n{1}", sectionID, outerHTML(el))
                continue
            target = targets[0]
            # TODO Allow this to respect "safe" markup (<sup>, etc) in the title
            text = textContent(findAll(".content", target)[0])
            if target.get('data-level') is not None:
                level = target.get('data-level')
                replaceContents(el, parseHTML("§{1} {0}".format(text, level)))
            else:
                replaceContents(el, parseHTML(text))

def fillAttributeInfoSpans(doc):
    for el in findAll("span[data-attribute-info]", doc):
        if el.text is None or el.text.strip() == '':
            referencedAttribute = el.get("for")
            if referencedAttribute is None or referencedAttribute == "":
                die("Missing for reference in attribute info span.")
                continue
            if "/" in referencedAttribute:
                interface, referencedAttribute = referencedAttribute.split("/")
                target = findAll('[data-link-type=attribute][title="{0}"][data-link-for="{1}"]'.format(referencedAttribute, interface), doc)
            else:
                target = findAll('[data-link-type=attribute][title="{0}"]'.format(referencedAttribute), doc)
            if len(target) == 0:
                die("Couldn't find target attribute {0}:\n{1}", referencedAttribute, outerHTML(el))
                continue
            if len(target) > 1:
                die("Multiple potential target attributes {0}:\n{1}", referencedAttribute, outerHTML(el))
                continue
            target = target[0]
            datatype = target.get("data-type").strip()
            default = target.get("data-default");
            decorations = ""
            if target.get("data-readonly") is not None:
                decorations += ", readonly"
            if datatype[-1] == "?":
                decorations += ", nullable"
                datatype = datatype[:-1]
            if default is not None:
              decorations += ", defaulting to {0}".format(default);
            replaceContents(el, parseHTML("of type <a data-link-type=idl-name>{0}</a>{1}".format(datatype, decorations)))
            # FIXME: Is there a nicer way to force a leading space here?
            el.text = ' ' + el.text

def processDfns(doc):
    dfns = findAll("dfn", doc)
    classifyDfns(doc, dfns)
    dedupIds(doc, dfns)
    doc.refs.addLocalDfns(dfns)


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
    if el.get('title'):
        dfnText = el.get('title')
    elif dfnType in config.functionishTypes and re.match(r"^[\w-]+\(.*\)$", contents):
        dfnText = re.match(r"^([\w-]+)\(.*\)$", contents).group(1)+"()"
    else:
        dfnText = contents
    return dfnText

def classifyDfns(doc, dfns):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el)
        dfnText = linkTextsFromElement(el, preserveCasing=True)[0]
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.match(r"^[\w-]+\(.*\)$", dfnText):
                die("Functions/methods must end with () in their linking text, got '{0}'.", dfnText)
                continue
            elif el.get('title') is None:
                # Make sure that functionish dfns have their title set up right.
                # Need to fix this to use the idl parser instead.
                el.set('title', re.match(r"^([\w-]+)\(.*\)$", dfnText).group(1)+"()")
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get('data-dfn-for') is None:
            parent = el.getparent()
            if parent.get('data-dfn-type') in config.functionishTypes and parent.get('data-dfn-for') is not None:
                el.set('data-dfn-for', "{0}/{1} {1}".format(parent.get('data-dfn-for'), linkTextsFromElement(parent, preserveCasing=True)[0]))
            else:
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
        # Automatically fill in id if necessary.
        if el.get('id') is None:
            id = simplifyText(determineDfnText(el).split('|')[0])
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                id = "dom-" + id
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
        if re.match(r"issue-[0-9a-fA-F]{8}$", dupe):
            # Don't warn about issues, it's okay if they have the same ID because they're identical text.
            continue
        els = findAll("#"+id, doc)
        ints = iter.imap(str, iter.count(0))
        for el in els[1:]:
            # Try to de-dup the id by appending an integer after it.
            warn("Multiple elements have the same ID '{0}'.\nDeduping, but this ID may not be stable across revisions.", id)
            for x in ints:
                if not findId(id+x):
                    id = id+x
                    break


def simplifyText(text):
    # Remove anything that's not a name character.
    text = text.strip()
    text = re.sub(r"[\s/]+", "-", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9_-]", "", text)
    return text


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    text = textContent(el)
    # ''foo: bar'' is a propdef for 'foo'
    if linkType == "maybe" and re.match(r"^[\w-]+\s*:\s+\S", text):
        el.set('title', re.match(r"^\s*([\w-]+)\s*:\s+\S", text).group(1))
        return "propdesc"
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
    if el.get('title'):
        linkText = el.get('title')
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

    # Fix up "for" text shorthands
    if linkType in ('propdesc', 'descriptor'):
        match = re.match(r"^(@[\w-]+)/([\w-]+)$", linkText)
        if match:
            el.set('data-link-for', match.group(1))
            clearContents(el)
            linkText = match.group(2)
            el.text = linkText
    elif linkType == "maybe":
        match = re.match(r"^([\w/@<>-]+)/([\w-]+)$", linkText)
        if match:
            el.set('data-link-for', match.group(1))
            clearContents(el)
            linkText = match.group(2)
            el.text = linkText
    elif linkType == "idl":
        match = re.match(r"^(.+)/([^/]+)$", linkText)
        if match:
            el.set('data-link-for', match.group(1))
            clearContents(el)
            linkText = match.group(2)
            el.text = linkText

    el.set('title', linkText)
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
        ref = doc.refs.getBiblioRef(linkText, el=el)
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
    # Maybe autolinks can be any element.  If it links up, we change it into an <a>.
    autolinks = findAll("a:not([href]), i", doc)
    for el in autolinks:
        # Explicitly empty title indicates this shouldn't be an autolink.
        if el.get('title') == '':
            continue

        classifyLink(el)
        linkType = el.get('data-link-type')
        linkText = el.get('title')

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
                if el.get("title"):
                    del el.attrib["title"]


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


class IDLMarker(object):
    def markupConstruct(self, text, construct):
        return (None, None)

    def markupType(self, text, construct):
        return (None, None)

    def markupTypeName(self, text, construct):
        return ('<a data-link-type="idl">', '</a>')

    def markupName(self, text, construct):
        if construct.idlType not in config.idlTypes:
            return (None,None)

        if construct.idlType == "constructor":
            idlType = "method"
        else:
            idlType = construct.idlType

        if idlType == "method":
            title = parser.Parser().normalizedMethodName(text)
        else:
            title = text

        def getForValues(construct):
            if construct.idlType in ("method", "constructor"):
                myForValue = parser.Parser().normalizedMethodName(construct.name)
            else:
                myForValue = construct.name
            if construct.parent:
                forValues = getForValues(construct.parent)
                forValues.append(myForValue)
                return forValues
            else:
                return [myForValue]

        if idlType == "attribute":
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
            extraParameters = 'data-type="{0}"'.format(construct.type);
            if construct.default is not None:
              value = escapeAttr("{0}".format(construct.default.value));
              extraParameters += ' data-default="{0}"'.format(value);
            idlType = 'attribute';
        else:
            extraParameters = ''

        if idlType in config.typesUsingFor:
            idlFor = "data-idl-for='{0}'".format('/'.join(getForValues(construct.parent)))
        else:
            idlFor = ""
        return ('<idl title="{0}" data-idl-type="{1}" {2} {3}>'.format(title, idlType, idlFor, extraParameters), '</idl>')

    def encode(self, text):
        return escapeHTML(text)

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
        forcedDfns = GlobalNames(text=treeAttr(pre, "data-dfn-force"))
        for el in findAll("idl", pre):
            idlType = el.get('data-idl-type')
            idlText = el.get('title')
            url = doc.refs.getRef(idlType, idlText.lower(),
                                  linkFor=el.get('data-idl-for'),
                                  el=el,
                                  error=False)
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
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-link-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
    dfns = findAll("pre.idl dfn", doc)
    classifyDfns(doc, dfns)
    dedupIds(doc, dfns)
    doc.refs.addLocalDfns(dfns)



def cleanupHTML(doc):
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

    # Remove duplicate titles.
    for el in findAll("dfn[title]", doc):
        if el.get('title') == textContent(el):
            del el.attrib['title']

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


def finalHackyCleanup(text):
    # For hacky last-minute string-based cleanups of the rendered html.

    # Remove the </wbr> end tag until the serializer is fixed.
    text = re.sub("</wbr>", "", text)

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
                self.date = datetime.today()
            else:
                self.lines = io.open(inputFilename, 'r', encoding="utf-8").readlines()
                self.date = datetime.fromtimestamp(os.path.getmtime(inputFilename))
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", inputFilename)
            return
        except IOError:
            die("Couldn't open the input file '{0}'.", inputFilename)
            return


        self.refs.initializeRefs();
        self.refs.initializeBiblio();

        self.testSuites = json.loads(
                            unicode(
                                config.retrieveCachedFile(cacheLocation=config.scriptPath+"/spec-data/test-suites.json", type="test suite list", quiet=True).read(),
                                encoding="utf-8"))

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
                        "title": "Custom Spec Link for {0}".format(specName),
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
        self.refs.setSpecData(self.md)

        # Deal with further <pre> blocks, and markdown
        transformDataBlocks(self)
        if self.paragraphMode == "markdown":
            self.lines = markdown.parse(self.lines, self.md.indent)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(self.lines)
        fillInBoilerplate(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = parseDocument(self.html)

        # Fill in and clean up a bunch of data
        addStatusSection(self)
        addLogo(self)
        addCopyright(self)
        addSpecMetadataSection(self)
        addAbstract(self)
        addObsoletionNotice(self)
        addAtRisk(self)
        self.transformAutolinkShortcuts()
        self.transformProductionGrammars()
        formatPropertyNames(self)
        processHeadings(self)
        canonicalizeShortcuts(self)
        fixIntraDocumentReferences(self)
        processIssues(self)
        markupIDL(self)


        # Handle all the links
        processDfns(self)
        processIDL(self)
        fillAttributeInfoSpans(self)
        processBiblioLinks(self)
        processAutolinks(self)

        addPropertyIndex(self)
        addReferencesSection(self)
        addIndexSection(self)
        addIssuesSection(self)
        processHeadings(self) # again
        addTOCSection(self)
        addSelfLinks(self)
        processAutolinks(self)
        addCustomBoilerplate(self)

        addAnnotations(self)

        # Any final HTML cleanups
        cleanupHTML(self)

        return self


    def serialize(self):
        rendered = html5lib.serialize(self.document, tree="lxml", alphabetical_attributes=True)
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
        for tag, replacement in self.macros.items():
            text = text.replace("[{0}]".format(tag.upper()), replacement)
        text = fixTypography(text)
        # Replace the <<production>> shortcuts, because they won't survive the HTML parser.
        # <'foo'> is a link to the 'foo' property or descriptor
        text = re.sub(r"<<'([\w-]+)'>>", r'<a data-link-type="propdesc" title="\1" class="production">&lt;&lsquo;\1&rsquo;></a>', text)
        # <'@foo/bar'> is a link to the 'bar' descriptor for the @foo at-rule
        text = re.sub(r"<<'(@[\w-]+)/([\w-]+)'>>", r'<a data-link-type="descriptor" title="\2" for="\1" class="production">&lt;&lsquo;\2&rsquo;></a>', text)
        # <foo()> is a link to the 'foo' function
        text = re.sub(r"<<([\w-]+\(\))>>", r'<a data-link-type="function" title="\1" class="production">&lt;\1></a>', text)
        # <@foo> is a link to the @foo rule
        text = re.sub(r"<<(@[\w-]+)>>", r'<a data-link-type="at-rule" title="\1" class="production">&lt;\1></a>', text)
        # Otherwise, it's a link to a type.
        text = re.sub(r"<<([\w-]+)>>", r'<a data-link-type="type" class="production">&lt;\1></a>', text)
        # Replace the ''maybe link'' shortcuts.
        # They'll survive the HTML parser, but they don't match if they contain an element.
        # (The other shortcuts are "atomic" and can't contain elements.)
        text = re.sub(r"''([^=\n]+?)''", r'<a data-link-type="maybe" class="css">\1</a>', text)
        return text

    def transformAutolinkShortcuts(doc):
        # Do the remaining textual replacements
        def transformThings(text):
            if text is None:
                return None
            if not ("[[" in text or "{{" in text or "'" in text):
                return None
            # Function takes raw text, but then adds HTML,
            # and the result is put directly into raw HTML.
            # So, escape the text, so it turns back into "raw HTML".
            text = escapeHTML(text)

            # Handle biblio links, [[FOO]] and [[!FOO]]
            def biblioReplacer(match):
                if match.group(1) is not None:
                    return match.group(0)[1:]
                if match.group(2) == "!":
                    type = "normative"
                else:
                    type = "informative"
                return r'<a title="{term}" data-link-type="biblio" data-biblio-type="{type}">[{term}]</a>'.format(term=match.group(3), type=type)
            text = re.sub(r"(\\)?\[\[(!)?([\w-]+)\]\]", biblioReplacer, text)

            # Handle section links, [[#foo]].
            text = re.sub(r"\[\[(#[\w-]+)\]\]", r'<a section href="\1"></a>', text)

            # Handle propdesc links, like 'width'.
            text = re.sub(r"'([-]?[\w@*][\w@*/-]*)'", r'<a data-link-type="propdesc" class="property" title="\1">\1</a>', text)

            # Handle IDL links, like {{FooBar}}
            text = re.sub(r"{{(([^ }]|,\s)+)}}", r'<code class="idl"><a data-link-type="idl" title="\1">\1</a></code>', text)

            return text

        def fixElementText(el):
            # Don't transform anything in some kinds of elements.
            processContents = isElement(el) and not isOpaqueElement(el)

            if processContents:
                originalChildren = [c for c in childElements(el)]
                # Pull out el.text, replace stuff (may introduce elements), parse.
                newtext = transformThings(el.text)
                if newtext is not None and el.text != newtext:
                    temp = parseHTML('<div>'+newtext+'</div>')[0]
                    # Change the .text, empty out the temp children.
                    el.text = temp.text
                    for child in childElements(temp, reversed=True):
                        el.insert(0, child)

            # Same for tail.
            newtext = transformThings(el.tail)
            if newtext is not None and el.tail != newtext:
                temp = parseHTML('<div>'+newtext+'</div>')[0]
                el.tail = ''
                for child in childElements(temp, reversed=True):
                    el.addnext(child)
                el.tail = temp.text

            if processContents:
                # Recurse over children.
                for child in originalChildren:
                    fixElementText(child)

        fixElementText(doc.document.getroot())
        for el in findAll("[text-fixed]", doc):
            del el.attrib['text-fixed']


    def transformProductionGrammars(doc):
        # Link up the various grammar symbols in CSS grammars to their definitions.

        def transformElement(parentEl):
            children = childNodes(parentEl, clear=True)
            newChildren = []
            for el in children:
                if isinstance(el, basestring):
                    newChildren.extend(transformText(el))
                elif isElement(el):
                    if el.tag != "a":
                        transformElement(el)
                    newChildren.append(el)
            appendChild(parentEl, *newChildren)

        def transformText(text):
            # alternates between normal text and the grammar productions
            splits = re.split(r"(\?|!|#|\*|\+|\|\||\||&amp;&amp;|,)", text)
            for i, p in enumerate(splits):
                if i%2 == 0:
                    continue
                splits[i] = E.a({"grammar":"", "class":"prod-punc"}, p)
            return splits

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
        if os.path.isfile("{0}/{1}-{2}-{3}.include".format(pathprefix, name, group, status)):
            filename = "{0}/{1}-{2}-{3}.include".format(pathprefix, name, group, status)
        elif os.path.isfile("{0}/{1}-{2}.include".format(pathprefix, name, group)):
            filename = "{0}/{1}-{2}.include".format(pathprefix, name, group)
        elif os.path.isfile("{0}/{1}-{2}.include".format(pathprefix, name, status)):
            filename = "{0}/{1}-{2}.include".format(pathprefix, name, status)
        elif os.path.isfile("{0}/{1}.include".format(pathprefix, name)):
            filename = "{0}/{1}.include".format(pathprefix, name)
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














def fillInBoilerplate(doc):
    # If you start your spec with an <h1>, I'll take it as the spec's title and remove it.
    # (It gets added back in the header file.)
    match = re.match(r"^<h1>([^<]+)</h1>", doc.html)
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
    from collections import OrderedDict
    indexEntries = defaultdict(list)
    attemptedForRefs = defaultdict(list)
    seenGlobalNames = set()
    for el in findAll("dfn", doc):
        linkTexts = linkTextsFromElement(el, preserveCasing=True)
        headingLevel = headingLevelOfElement(el) or "Unnumbered section"
        if el.get('data-dfn-for') is not None:
            disambiguator = "{0} for {1}".format(el.get('data-dfn-type'), ', '.join(el.get('data-dfn-for').split()))
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
    container = E.div()
    html = appendChild(container, E.ul({"class":"indexlist"}))
    for text, items in sortedEntries.items():
        if len(items) == 1:
            item = items[0]
            li = appendChild(html,
                E.li(item['text'], ", ",
                    E.a({"href":"#"+item['id'], "title":"section "+item['level']}, item['level'])))
            if item['type'] == "property":
                reffingDfns = []
                for globalName in item['globalNames']:
                    reffingDfns += attemptedForRefs[globalName]
                if reffingDfns:
                    dl = appendChild(li, E.dl(E.dt("Property Values:")))
                    for r in reffingDfns:
                        appendChild(dl,
                            E.dd(r.text, ", ",
                                E.a({"href":"#"+r['id'], "title":"section "+r['level']}, r['level'])))
        else:
            li = appendChild(html, E.li(items[0]['text']))
            ul = appendChild(li, E.ul())
            for item in items:
                appendChild(ul,
                    E.li(item['disambiguator'], ", ",
                        E.a({"href":"#"+item['id'], "title":"section "+item['level']}, item['level'])))
    fillWith("index", container, doc=doc)



def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables
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

    html = E.div()

    # TODO: Move the heading generation into this function.

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
            appendChild(html,
                E.table({"class":"proptable data"},
                    E.thead(
                        E.tr(
                            *[E.tr({"scope":"col"}, column) for column in columns])),
                    E.tbody(
                        E.tr(
                            E.th({"scope":"row"},
                                E.a({"data-link-type":"descriptor"}, desc['Name'])),
                            *[E.td(desc.get(column, "")) for column in columns[1:]]))))

    fillWith("property-index", html, doc=doc)


def addTOCSection(doc):

    skipLevel = float('inf')
    previousLevel = 1
    containers = [0, 1, 2, 3, 4, 5, 6, 7]
    containers[1] = E.div()
    containers[2] = appendChild(containers[1], E.ul({"class":"toc"}))
    for header in findAll('h2, h3, h4, h5, h6', doc):
        level = int(header.tag[-1])
        container = containers[level]

        if level > previousLevel + 1:
            # Jumping two levels is a no-no.
            die("Heading level jumps more than one level, from h{0} to h{1}:\n  {2}", previousLevel, level, textContent(header).replace("\n", " "))

        # Hit a no-toc, suppress the entire section.
        if hasClass(header, "no-toc"):
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue
        else:
            skipLevel = float('inf')

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
            appendChild(div,
                " (",
                E.span({"class":"p-org org"}, editor['org']),
                ")")
        if editor['email'] and editor['link']:
            appendChild(div,
                " ",
                E.a({"class":"u-email email", "href":"mailto:"+editor['email']}, editor['email']))
        return div

    md = DefaultOrderedDict(list)
    mac = doc.macros
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
            E.a({"href":"mailto:"+doc.md.mailingList+"?subject=["+mac['shortname']+"] feedback"}, doc.md.mailingList),
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
    if len(doc.md.editors):
        md["Editor" if len(doc.md.editors) == 1 else "Editors"] = map(printEditor, doc.md.editors)
    if len(doc.md.previousEditors):
        md["Former Editor" if len(doc.md.editors) == 1 else "Former Editors"] = map(printEditor, doc.md.previousEditors)
    for key, vals in doc.md.otherMetadata.items():
        md[key].extend(parseHTML("<span>"+doc.fixText(val)+"</span>")[0] for val in vals)

    dl = E.dl()
    for key, vals in md.items():
        appendChild(dl,
            E.dt(key, ":"),
            *[E.dd(val) for val in vals])
    fillWith('spec-metadata', E.div(dl), doc=doc)


def addReferencesSection(doc):
    dl = E.dl()
    for ref in sorted(doc.normativeRefs.values(), key=lambda r: r.linkText):
        appendChild(dl, E.dt({"id":"biblio-"+simplifyText(ref.linkText), "title":ref.linkText}, "["+ref.linkText+"]"))
        appendChild(dl, E.dd(*ref.toHTML()))
    fillWith("normative-references", E.div(dl), doc=doc)

    dl = E.dl()
    for ref in sorted(doc.informativeRefs.values(), key=lambda r: r.linkText):
        # If the same doc is referenced as both normative and informative, normative wins.
        if ref.linkText in doc.normativeRefs:
            continue
        appendChild(dl, E.dt({"id":"biblio-"+simplifyText(ref.linkText), "title":ref.linkText}, "["+ref.linkText+"]"))
        appendChild(dl, E.dd(*ref.toHTML()))
    fillWith("informative-references", E.div(dl), doc=doc)

def addIssuesSection(doc):
    issues = findAll('.issue', doc)
    if len(issues) == 0:
        return
    header = find("#issues-index", doc)
    if not header:
        header = lxml.etree.Element('h2', {'id':"issues-index", 'class':"no-num"})
        header.text = "Issues Index"
        appendChild(find("body", doc), header)
    container = lxml.etree.Element('div', {'style':"counter-reset: issue"})
    insertAfter(header, container)
    for issue in issues:
        el = deepcopy(issue)
        el.tail = None
        if el.tag not in ("pre",):
            el.tag = "div"
        appendChild(container, el)
        issuelink = lxml.etree.Element('a', {'href':'#'+issue.get('id')})
        issuelink.text = " ↵ "
        appendChild(el, issuelink)
    for idel in findAll("[id]", container):
        del idel.attrib['id']
    for dfnel in findAll("dfn", container):
        dfnel.tag = "span"
