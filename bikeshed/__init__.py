# -*- coding: utf-8 -*-

from __future__ import division
import re
from collections import defaultdict
import os
import sys
import json
import argparse
import urllib
from urllib2 import urlopen
from datetime import date, datetime
import html5lib
import lxml

from . import config
from . import biblio
from . import update
from .fuckunicode import u
from .ReferenceManager import ReferenceManager
from .ReferenceManager import linkTextsFromElement
from .globalnames import *
from .MetadataManager import MetadataManager
from .htmlhelpers import *
from .messages import *
from .widlparser.widlparser import parser


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

    issueParser = subparsers.add_parser('issues-list', help="Process a plain-text issues file into HTML. Call with no args to see an example input text.")
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

    options = argparser.parse_args()

    config.quiet = options.quiet
    config.debug = options.debug
    config.dryRun = options.dryRun
    config.minify = getattr(options, 'minify', True)

    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, linkDefaults=options.linkDefaults)
    elif options.subparserName == "spec":
        config.doc = CSSSpec(inputFilename=options.infile, paragraphMode=options.paragraphMode)
        config.doc.preprocess()
        config.doc.finish(outputFilename=options.outfile)
    elif options.subparserName == "debug":
        config.debug = True
        config.quiet = True
        if options.printExports:
            config.doc = CSSSpec(inputFilename=options.infile)
            config.doc.preprocess()
            config.doc.printTargets()
        elif options.jsonCode:
            config.doc = CSSSpec(inputFilename=options.infile)
            config.doc.preprocess()
            exec("print json.dumps({0}, indent=2)".format(options.jsonCode))
        elif options.code:
            config.doc = CSSSpec(inputFilename=options.infile)
            config.doc.preprocess()
            exec("print {0}".format(options.code))
        elif options.linkText:
            config.doc = CSSSpec(inputFilename=options.infile)
            config.doc.preprocess()
            refs = config.doc.refs.refs[options.linkText]
            config.quiet = options.quiet
            if not config.quiet:
                print "Refs for '{0}':".format(options.linkText)
            print json.dumps(refs, indent=2)
    elif options.subparserName == "issues-list":
        from . import issuelist as il
        il.printIssueList(options.infile, options.outfile)


def replaceTextMacros(text):
    # Replace the [FOO] things.
    for tag, replacement in config.textMacros.items():
        text = u(text).replace(u"[{0}]".format(u(tag.upper())), u(replacement))
    text = fixTypography(text)
    # Replace the <<production>> shortcuts, because they won't survive the HTML parser.
    # <'foo'> is a link to the 'foo' property
    text = re.sub(r"<<'([\w-]+)'>>", r'<a data-link-type="propdesc" title="\1" class="production">&lt;&lsquo;\1&rsquo;></a>', text)
    # <foo()> is a link to the 'foo' function
    text = re.sub(r"<<([\w-]+\(\))>>", r'<a data-link-type="function" title="\1" class="production">&lt;\1></a>', text)
    # <@foo> is a link to the @foo rule
    text = re.sub(r"<<(@[\w-]+)>>", r'<a data-link-type="at-rule" title="\1" class="production">&lt;\1></a>', text)
    # Otherwise, it's a link to a type.
    text = re.sub(r"<<([\w-]+)>>", r'<a data-link-type="type" class="production">&lt;\1></a>', text)
    # Replace the ''maybe link'' shortcuts.
    # They'll survive the HTML parser, but they don't match if they contain an element.
    # (The other shortcuts are "atomic" and can't contain elements.)
    text = re.sub(r"''([^=\n]+?)''", r'<span data-link-type="maybe" class="css">\1</span>', text)
    return text


def fixTypography(text):
    # Replace straight aposes with curly quotes for possessives and contractions.
    text = re.sub(r"([\w])'([\w])", ur"\1’\2", text)
    text = re.sub(r"(</[\w]+>)'([\w])", ur"\1’\2", text)
    # Fix line-ending em dashes, or --, by moving the previous line up, so no space.
    text = re.sub(ur"([^<][^!])(—|--)\r?\n\s+(\S)", ur"\1—<wbr>\3", text)
    return text


def transformMarkdownParagraphs(doc):
    # This converts Markdown-style paragraphs into actual paragraphs.
    # Any line that is preceded by a blank line,
    # and which starts with either text or an inline element,
    # will have a <p> inserted at its beginning.
    #
    # It also auto-recognizes paragraphs that start with "Note: " or "Note, "
    # and instead inserts a "<p class='note'>".
    inDataBlock = False
    previousLineBlank = False
    # Elements whose contents should be skipped when looking for paragraphs.
    opaqueBlocks = "pre|xmp|script|style"
    # Elements which are allowed to start a markdown paragraph.
    allowedStartElements = "em|strong|i|b|u|dfn|a|code|var"
    for (i, line) in enumerate(doc.lines):
        if not inDataBlock and re.match("\s*<({0})".format(opaqueBlocks), line):
            inDataBlock = True
        if inDataBlock and re.search("</({0})".format(opaqueBlocks), line):
            inDataBlock = False
            continue
        if inDataBlock:
            continue
        if (re.match("\s*[^<\s]", line) or re.match("\s*<({0})".format(allowedStartElements), line)) and previousLineBlank and not inDataBlock:
            if re.match("\s*Note(:|,) ", line):
                doc.lines[i] = "<p class='note'>" + line
            else:
                doc.lines[i] = "<p>" + line

        previousLineBlank = re.match("^\s*$", line)


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
        'metadata': transformMetadata,
        'railroad': transformRailroad,
        'pre': transformPre
    }
    blockType = ""
    tagName = ""
    startLine = 0
    replacements = []
    for (i, line) in enumerate(doc.lines):
        # Look for the start of a block.
        match = re.match("\s*<(pre|xmp)(.*)", line, re.I)
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
        match = re.match("(.*)</"+tagName+">(.*)", line, re.I)
        if match and inBlock:
            inBlock = False
            if startLine == i:
                # Single-line <pre>.
                match = re.match("\s*(<{0}[^>]*>)(.+)</{0}>(.*)".format(tagName), line, re.I)
                doc.lines[i] = match.group(3)
                replacements.append({
                    'start': i,
                    'end': i,
                    'value': blockTypes[blockType](
                        lines=[match.group(2)],
                        tagName=tagName,
                        firstLine=match.group(1),
                        doc=doc)})
            elif re.match("^\s*$", match.group(1)):
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
    prefix = re.match("\s*", firstLine).group(0)
    for (i, line) in enumerate(lines):
        # Remove the whitespace prefix from each line.
        match = re.match(prefix+"(.*)", line, re.DOTALL)
        if match:
            lines[i] = match.group(1)
        # Use tabs in the source, but spaces in the output,
        # because tabs are ginormous in HTML.
        # Also, it means lines in processed files will never
        # accidentally match a prefix.
        lines[i] = lines[i].replace("\t", "  ")
    lines.insert(0, firstLine)
    lines.append("</"+tagName+">")
    return lines


def transformPropdef(lines, doc, firstLine, **kwargs):
    vals = {}
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        if(match is None):
            die(u"Incorrectly formatted propdef line for '{0}':\n{1}", vals.get("Name", "???"), line)
            continue
        key = match.group(1).strip().capitalize()
        val = match.group(2).strip()
        if key == "Value" and "Value" in vals:
            vals[key] += " "+val
        else:
            vals[key] = val
    # The required keys are specified in the order they should show up in the propdef table.
    if "partial" in firstLine or "New values" in vals:
        requiredKeys = ["Name", "New values"]
        ret = ["<table class='definition propdef partial'>"]
    else:
        requiredKeys = ["Name", "Value", "Initial", "Applies to", "Inherited", "Media", "Computed value"]
        ret = ["<table class='definition propdef'>"]
    for key in requiredKeys:
        if key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
        else:
            die("The propdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret


def transformDescdef(lines, doc, firstLine, **kwargs):
    vals = {}
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        if(match is None):
            die(u"Incorrectly formatted descdef line for '{0}':\n{1}", vals.get("Name", "???"), u(line))
            continue
        key = match.group(1).strip().capitalize()
        val = match.group(2).strip()
        if key == "Value" and "Value" in vals:
            vals[key] += " "+val
        else:
            vals[key] = val
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
            ret.append("<tr><th>{0}:<td><a at-rule>{1}</a>".format(key, vals[key]))
        elif key in vals:
            ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
        else:
            die("The descdef for '{0}' is missing a '{1}' line.", vals.get("Name", "???"), key)
            continue
    for key in vals.viewkeys() - requiredKeys:
        ret.append("<tr><th>{0}:<td>{1}".format(key, vals[key]))
    ret.append("</table>")
    return ret


def transformMetadata(lines, doc, **kwargs):
    for line in lines:
        line = line.strip()
        if line == "":
            continue
        match = re.match(u"([^:]+):\s*(.*)", u(line))
        if(match is None):
            die(u"Incorrectly formatted metadata line:\n{0}", u(line))
            continue
        doc.md.addData(match.group(1), match.group(2))
    # Remove the metadata block from the generated document.
    return []

def loadDefaultMetadata(doc):
    data = doc.getInclusion('defaults', error=False)
    try:
        defaults = json.loads(data)
    except Exception, e:
        if data != "":
            die("Error loading defaults:\n{0}", str(e))
        return
    for key,val in defaults.items():
        doc.md.addDefault(key, val)

def initializeTextMacros(doc):
    longstatuses = {
        "ED": u"Editor's Draft",
        "WD": u"W3C Working Draft",
        "LCWD": u"W3C Last Call Working Draft",
        "CR": u"W3C Candidate Recommendation",
        "PR": u"W3C Proposed Recommendation",
        "REC": u"W3C Recommendation",
        "PER": u"W3C Proposed Edited Recommendation",
        "NOTE": u"W3C Working Group Note",
        "MO": u"W3C Member-only Draft",
        "UD": u"Unofficial Proposal Draft",
        "DREAM": u"A Collection of Interesting Ideas"
    }
    if doc.md.title:
        config.textMacros["title"] = doc.md.title
    config.textMacros["shortname"] = doc.md.shortname
    if doc.md.status:
        config.textMacros["statusText"] = doc.md.statusText
    config.textMacros["vshortname"] = u"{0}-{1}".format(doc.md.shortname, doc.md.level)
    if doc.md.status in longstatuses:
        config.textMacros["longstatus"] = longstatuses[doc.md.status]
    else:
        die(u"Unknown status '{0}' used.",doc.md.status)
    if doc.md.status == "LCWD":
        config.textMacros["status"] = u"WD"
    else:
        config.textMacros["status"] = doc.md.status
    config.textMacros["latest"] = doc.md.TR or u"???"
    config.textMacros["abstract"] = "<p>".join(doc.md.abstracts) or u"???"
    config.textMacros["abstractattr"] = escapeAttr("  ".join(doc.md.abstracts).replace(u"<<",u"<").replace(u">>",u">")) or u"???"
    config.textMacros["year"] = u(doc.md.date.year)
    config.textMacros["date"] = doc.md.date.strftime(u"{0} %B %Y".format(doc.md.date.day))
    config.textMacros["cdate"] = doc.md.date.strftime(u"%Y%m%d")
    config.textMacros["isodate"] = doc.md.date.strftime(u"%Y-%m-%d")
    if doc.md.deadline:
        config.textMacros["deadline"] = doc.md.deadline.strftime(u"{0} %B %Y".format(doc.md.deadline.day))
    if doc.md.status == "ED":
        config.textMacros["version"] = doc.md.ED
    else:
        config.textMacros["version"] = u"http://www.w3.org/TR/{3}/{0}-{1}-{2}/".format(config.textMacros["status"],
                                                                                       config.textMacros["vshortname"],
                                                                                       config.textMacros["cdate"],
                                                                                       config.textMacros["year"])
    # Now we have enough data to set all the relevant stuff in ReferenceManager
    doc.refs.setSpecData(doc)


def verifyRequiredMetadata(doc):
    if not doc.md.hasMetadata:
        die("The document requires at least one metadata block.")
        return

    requiredSingularKeys = [
        ('status', 'Status'),
        ('ED', 'ED'),
        ('shortname', 'Shortname'),
        ('level', 'Level')
    ]
    requiredMultiKeys = [
        ('abstracts', 'Abstract'),
        ('editors', 'Editor')
    ]
    errors = []
    for attr, name in requiredSingularKeys:
        if getattr(doc.md, attr) is None:
            errors.append(u"    Missing a '{0}' entry.".format(u(name)))
    for attr, name in requiredMultiKeys:
        if len(getattr(doc.md, attr)) == 0:
            errors.append(u"    Must provide at least one '{0}' entry.".format(u(name)))
    if errors:
        die(u"Not all required metadata was provided:\n{0}", u"\n".join(errors))
        return


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


def transformAutolinkShortcuts(doc):
    # Can't do the simple thing of just running the replace over the doc's contents.
    # Need to protect attributes, contents of <pre>, etc.
    def transformThings(text):
        if text is None:
            return None
        # Function takes raw text, but then adds HTML,
        # and the result is put directly into raw HTML.
        # So, escape the text, so it turns back into "raw HTML".
        text = escapeHTML(text)
        # Handle biblio links, [[FOO]] and [[!FOO]]
        while re.search(ur"\[\[(!?)([A-Za-z0-9-]+)\]\]", text):
            match = re.search(ur"\[\[(!?)([A-Za-z0-9-]+)\]\]", text)

            if match.group(1) == "!":
                biblioType = u"normative"
            else:
                biblioType = u"informative"

            text = u(text.replace(
                        match.group(0),
                        u'<a title="{0}" data-link-type="biblio" data-biblio-type="{1}">[{0}]</a>'.format(
                            u(match.group(2)),
                            biblioType)))
        text = re.sub(ur"'([*-]*[a-zA-Z][a-zA-Z0-9_*/-]*)'", ur'<a data-link-type="propdesc" class="property" title="\1">\1</a>', text)
        return u(text)

    def fixElementText(el):
        # Don't transform anything in some kinds of elements.
        processContents = el.tag not in ("pre", "code", "style", "script")

        if processContents:
            # Pull out el.text, replace stuff (may introduce elements), parse.
            newtext = transformThings(u(el.text))
            if el.text != newtext:
                temp = parseHTML(u'<div>'+u(newtext)+u'</div>')[0]
                # Change the .text, empty out the temp children.
                el.text = u(temp.text)
                for child in temp.iterchildren(tag="*", reversed=True):
                    el.insert(0, child)

        # Same for tail.
        newtext = transformThings(el.tail)
        if el.tail != newtext:
            temp = parseHTML(u'<div>'+u(newtext)+u'</div>')[0]
            el.tail = u''
            for child in temp.iterchildren(tag="*", reversed=True):
                el.addnext(child)
            el.tail = u(temp.text)

        if processContents:
            # Recurse over children.
            for child in el.iterchildren(tag="*"):
                fixElementText(child)

    fixElementText(doc.document.getroot())


def buildBibliolinkDatabase(doc):
    biblioLinks = findAll("a[data-link-type='biblio']")
    for el in biblioLinks:
        if el.get('title'):
            linkText = u(el.get('title'))
        else:
            # Assume the text is of the form "[NAME]"
            linkText = textContent(el)[1:-1]
            el.set('title', linkText)
        if linkText not in doc.biblios:
            die(u"Couldn't find '{0}' in bibliography data.", linkText)
            continue
        biblioEntry = doc.biblios[linkText]
        if el.get('data-biblio-type') == "normative":
            doc.normativeRefs.add(biblioEntry)
        elif el.get('data-biblio-type') == "informative":
            doc.informativeRefs.add(biblioEntry)
        else:
            die(u"Unknown data-biblio-type value '{0}' on {1}. Only 'normative' and 'informative' allowed.", u(el.get('data-biblio-type')), outerHTML(el))















# Headings Stuff

def processHeadings(doc):
    for el in findAll('h2, h3, h4, h5, h6'):
        addClass(el, 'heading')
    headings = findAll(".heading:not(.settled)")
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
        return u'.'.join(u(x) for x in headerLevel if x > 0)

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
            secno.text = header.get('data-level') + u' '
            header.insert(0, secno)


















# Definitions and the like

def formatPropertyNames(doc):
    for table in findAll("table.propdef, table.descdef"):
        tag = "a" if hasClass(table, "partial") else "dfn"
        type = "property" if hasClass(table, "propdef") else "descriptor"
        for cell in findAll("tr:first-child > td", table):
            names = [u(x.strip()) for x in textContent(cell).split(u',')]
            html = u', '.join(u"<{tag} {type}>{0}</{tag}>".format(name, tag=tag, type=type) for name in names)
            replaceContents(cell, parseHTML(html))


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
        "force":"data-dfn-force"
    }
    for el in findAll(",".join("[{0}]".format(attr) for attr in attrFixup.keys())):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, el.get(attr))
                del el.attrib[attr]

    for el in findAll("dfn"):
        for dfnType in config.dfnTypes.union(["dfn"]):
            if el.get(dfnType) == "":
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
    for el in findAll("a"):
        for linkType in (config.linkTypes | set("dfn")):
            if el.get(linkType) is not None:
                del el.attrib[linkType]
                el.set("data-link-type", linkType)
    for el in findAll("dfn[for], a[for]"):
        if el.tag == "dfn":
            el.set("data-dfn-for", el.get('for'))
        else:
            el.set("data-link-for", el.get('for'))
        del el.attrib['for']



def processDfns(doc):
    dfns = findAll("dfn")
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
    elif text[:1] == u"〈" and text[-1:] == u"〉":
        return "token"
    elif text[0:1] == ":":
        return "selector"
    elif re.match("^[\w-]+\(.*\)$", text) and not (dfn.get('id') or '').startswith("dom-"):
        return "function"
    else:
        return "dfn"

def determineDfnText(el):
    dfnType = el.get('data-dfn-type')
    contents = textContent(el)
    if el.get('title'):
        dfnText = el.get('title')
    elif dfnType in config.functionishTypes and re.match("^[\w-]+\(.*\)$", contents):
        dfnText = re.match("^([\w-]+)\(.*\)$", contents).group(1)+"()"
    else:
        dfnText = contents
    return dfnText

def classifyDfns(doc, dfns):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(el)
        dfnText = linkTextsFromElement(el)[0]
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.match("^[\w-]+\(.*\)$", dfnText):
                die("Functions/methods must end with () in their linking text, got '{0}'.", dfnText)
                continue
            elif el.get('title') is None:
                # Make sure that functionish dfns have their title set up right.
                # Need to fix this to use the idl parser instead.
                el.set('title', re.match("^([\w-]+)\(.*\)$", dfnText).group(1)+"()")
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
                pass
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
                id = simplifyText("dom-{0}-{1}".format(el.get("data-dfn-for"), id))
            else:
                id = "{0}-{1}".format(dfnTypeToPrefix[dfnType], id)
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
    def findId(id):
        return find("#"+id) is not None
    for el in els:
        id = el.get('id')
        if id is None:
            die("No id to dedup: {0}", outerHTML(el))
            id = "giant-error"
            el.set('id', id)
        del el.attrib['id']
        if findId(id):
            # Try to de-dup the id by appending an integer after it.
            import itertools as iter
            for x in iter.imap(str, iter.count(0)):
                if not findId(id+x):
                    id = id+x
                    break
        el.set('id', id)


def simplifyText(text):
    # Remove anything that's not a name character.
    return re.sub(u"[^a-z0-9_-]", u"", text.replace(u" ", u"-").lower())


def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    text = textContent(el)
    # ''foo: bar'' is a propdef for 'foo'
    if linkType == "maybe" and re.match("^[\w-]+\s*:\s*\S", text):
        el.set('title', re.match("^\s*([\w-]+)\s*:\s*\S", text).group(1))
        return "propdesc"
    if linkType:
        if linkType in config.linkTypes:
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
    elif linkType in config.functionishTypes.union(["functionish"]) and re.match("^[\w-]+\(.*\)$", contents):
        linkText = re.match("^([\w-]+)\(.*\)$", contents).group(1)+"()"
        # Need to fix this using the idl parser.
    else:
        linkText = contents
    linkText = re.sub(u"\s+", u" ", linkText.lower())
    if len(linkText) == 0:
        die(u"Autolink {0} has no linktext.", outerHTML(el))
    return linkText


def classifyLink(el):
    linkType = determineLinkType(el)
    el.set('data-link-type', linkType)
    linkText = determineLinkText(el)
    if linkType == "maybe" and re.match(r"([\w/-]+)/([\w-]+)", linkText):
        match = re.match(r"^([\w/-]+)/([\w-]+)$", linkText)
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


def processAutolinks(doc):
    # An <a> without an href is an autolink.
    # For re-run, if you have a [data-link-type] property, we'll regen your href anyway.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # Maybe autolinks can be any element.  If it links up, we change it into an <a>.
    autolinks = findAll("a:not([href]), a[data-link-type], i, [data-link-type='maybe']")
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

        if linkType == u"biblio":
            # Move biblio management into ReferenceManager later
            el.set('href', '#'+simplifyText(linkText))
            continue

        url = doc.refs.getRef(linkType, linkText,
                              spec=el.get('data-link-spec'),
                              status=el.get('data-link-status'),
                              linkFor=el.get('data-link-for'),
                              el=el,
                              error=(linkText not in doc.md.ignoredTerms))
        if url is not None:
            el.set('href', url)
            el.tag = "a"


def processIssues(doc):
    import hashlib
    # Add an auto-genned and stable-against-changes-elsewhere id to all issues.
    for el in findAll(".issue:not([id])"):
        el.set('id', "issue-"+hashlib.md5(innerHTML(el).strip().encode("ascii", "xmlcharrefreplace")).hexdigest()[0:8])
    dedupIds(doc, findAll(".issue"))


def addSelfLinks(doc):
    def makeSelfLink(el):
        selflink = lxml.etree.Element(
            'a', {"href": "#" + urllib.quote(el.get('id', '')), "class":"self-link"});
        return selflink

    foundFirstNumberedSection = False
    for el in findAll("h2, h3, h4, h5, h6"):
        foundFirstNumberedSection = foundFirstNumberedSection or (el.get('data-level') is not None)
        if foundFirstNumberedSection:
            appendChild(el, makeSelfLink(el))
    for el in findAll(".issue[id], .example[id], .note[id], li[id], dt[id]"):
        prependChild(el, makeSelfLink(el))
    for el in findAll("dfn"):
        if len([x for x in el.iterancestors("a")]):
            warn("Found <a> ancestor, skipping self-link. Swap <dfn>/<a> order?\n  {0}", outerHTML(el))
            continue
        appendChild(el, makeSelfLink(el))


class IDLMarker(object):
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

        if idlType in config.typesUsingFor:
            idlFor = "data-idl-for='{0}'".format('/'.join(getForValues(construct.parent)))
        else:
            idlFor = ""
        return ('<idl title="{0}" data-idl-type="{1}" {2}>'.format(title, idlType, idlFor), '</idl>')

    def encode(self, text):
        return escapeHTML(text)

class IDLUI(object):
    def warn(self, msg):
        die("{0}", msg)

def markupIDL(doc):
    for el in findAll('pre.idl'):
        if el.get("data-no-idl") is not None:
            continue
        widl = parser.Parser(textContent(el), IDLUI())
        text = unicode(widl.markup(IDLMarker()))
        replaceContents(el, parseHTML(text))


def processIDL(doc):
    for pre in findAll("pre.idl"):
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
    dfns = findAll("pre.idl dfn")
    classifyDfns(doc, dfns)
    dedupIds(doc, dfns)
    doc.refs.addLocalDfns(dfns)



def cleanupHTML(doc):
    # Find <style> in body, add scoped='', move to be first child.
    for el in findAll("body style"):
        parent = el.getparent()
        parent.insert(0, el)
        el.set('scoped', '')

    # Move any stray <link>, <script>, or <meta> into the <head>.
    head = find("head")
    for el in findAll("body link, body script, body meta"):
        head.append(el)

    # If we accidentally recognized an autolink shortcut in SVG, kill it.
    for el in findAll("svg|a[data-link-type]"):
        del el.attrib["data-link-type"]
        el.tag = "{http://www.w3.org/2000/svg}tspan"

    # Tag classes on wide types of dfns/links
    def selectorForTypes(types):
        return ",".join("dfn[data-dfn-type={0}],a[data-link-type={0}]".format(type) for type in types)
    for el in findAll(selectorForTypes(config.idlTypes)):
        addClass(el, 'idl-code')
    for el in findAll(selectorForTypes(config.maybeTypes.union(config.linkTypeToDfnType['propdesc']))):
        addClass(el, 'css-code')

    # Remove comments from the generated HTML, maybe.
    if config.minify:
        comments = list(doc.document.iter(lxml.etree.Comment))
        for comment in comments:
            removeNode(comment)

    # Remove duplicate titles.
    for el in findAll("dfn[title]"):
        if el.get('title') == textContent(el):
            del el.attrib['title']


def retrieveCachedFile(cacheLocation, type, fallbackurl=None, quiet=False, force=False):
    try:
        if force:
            raise IOError("Skipping cache lookup, because this is a forced retrieval.")
        fh = open(cacheLocation, 'r')
    except IOError:
        if fallbackurl is None:
            die(u"Couldn't find the {0} cache file at the specified location '{1}'.", type, cacheLocation)
        else:
            if not quiet:
                warn(u"Couldn't find the {0} cache file at the specified location '{1}'.\nAttempting to download it from '{2}'...", type, cacheLocation, fallbackurl)
            try:
                fh = urlopen(fallbackurl)
            except:
                die(u"Couldn't retrieve the {0} file from '{1}'.", type, fallbackurl)
            try:
                if not quiet:
                    say(u"Attempting to save the {0} file to cache...", type)
                if not dryRun:
                    outfh = open(cacheLocation, 'w')
                    outfh.write(fh.read())
                    fh.close()
                fh = open(cacheLocation, 'r')
                if not quiet:
                    say("Successfully saved the {0} file to cache.", type)
            except:
                if not quiet:
                    warn("Couldn't save the {0} file to cache. Proceeding...", type)
    return fh
















class CSSSpec(object):
    # internal state
    normativeRefs = set()
    informativeRefs = set()
    refs = ReferenceManager()
    md = MetadataManager()
    biblios = {}
    paragraphMode = "markdown"
    inputSource = None

    def __init__(self, inputFilename, paragraphMode="markdown"):
        if inputFilename is None:
            # Default the path to something sensible.
            import glob
            possibleInputs = glob.glob("*.src.html")
            if possibleInputs:
                inputFilename = possibleInputs[0]
            else:
                inputFilename = "-"
        self.inputSource = inputFilename
        try:
            if inputFilename == "-":
                self.lines = sys.stdin.readlines()
                self.date = datetime.today()
            else:
                self.lines = open(inputFilename, 'r').readlines()
                self.date = datetime.fromtimestamp(os.path.getmtime(inputFilename))
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", inputFilename)
            return
        except IOError:
            die("Couldn't open the input file '{0}'.", inputFilename)
            return

        bibliofh = retrieveCachedFile(cacheLocation=config.scriptPath + "/spec-data/biblio.refer",
                                      fallbackurl="http://dev.w3.org/csswg/biblio.ref",
                                      type="bibliography")
        self.biblios = biblio.processReferBiblioFile(bibliofh)
        bibliofh.close()

        # Get local bibliography data
        try:
            bibliofh = open("biblio.json", 'r')
        except:
            pass
        else:
            self.biblios.update(biblio.processSpecrefBiblioFile(bibliofh))
            bibliofh.close()

        # Load up the xref data
        self.refs.specs = json.load(retrieveCachedFile(cacheLocation=config.scriptPath+"/spec-data/specs.json",
                                      type="spec list", quiet=True))
        self.refs.refs = defaultdict(list, json.load(retrieveCachedFile(cacheLocation=config.scriptPath+"/spec-data/anchors.json",
                                      type="anchor data", quiet=True)))
        self.refs.defaultSpecs = defaultdict(list, json.load(retrieveCachedFile(cacheLocation=config.scriptPath+"/spec-data/link-defaults.json",
                                      type="link defaults", quiet=True)))
        if "css21Replacements" in self.refs.defaultSpecs:
            self.refs.css21Replacements = set(self.refs.defaultSpecs["css21Replacements"])
            del self.refs.defaultSpecs["css21Replacements"]
        if "ignoredSpecs" in self.refs.defaultSpecs:
            self.refs.ignoredSpecs = set(self.refs.defaultSpecs["ignoredSpecs"])
            del self.refs.defaultSpecs["ignoredSpecs"]
        if "customDfns" in self.refs.defaultSpecs:
            for specName, specUrl, dfnText, dfnType, dfnUrl in self.refs.defaultSpecs["customDfns"]:
                if specName not in self.refs.specs:
                    levelMatch = re.match("(.*)-(\d+)", specName)
                    if levelMatch:
                        shortname = levelMatch.group(1)
                        level = levelMatch.group(2)
                    else:
                        shortname = specName
                        level = "1"
                    self.refs.specs[specName] = {
                        "description": "Custom Spec Link for {0}".format(specName),
                        "title": "Custom Spec Link for {0}".format(specName),
                        "level": int(level),
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
        transformDataBlocks(self)
        loadDefaultMetadata(self)
        verifyRequiredMetadata(self)
        initializeTextMacros(self)
        if self.paragraphMode == "markdown":
            transformMarkdownParagraphs(self)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(self.lines)
        fillInBoilerplate(self)
        self.html = replaceTextMacros(self.html)

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
        transformAutolinkShortcuts(self)
        formatPropertyNames(self)
        processHeadings(self)
        canonicalizeShortcuts(self)
        processIssues(self)
        markupIDL(self)


        # Handle all the links
        processDfns(self)
        processIDL(self)
        buildBibliolinkDatabase(self)
        processAutolinks(self)

        addPropertyIndex(self)
        addReferencesSection(self)
        addIndexSection(self)
        addIssuesSection(self)
        processHeadings(self) # again
        addTOCSection(self)
        addSelfLinks(self)

        # Any final HTML cleanups
        cleanupHTML(self)

        return self

    def finish(self, outputFilename):
        if outputFilename is None:
            # More sensible defaults!
            if self.inputSource.endswith(".src.html"):
                outputFilename = self.inputSource[0:-9] + ".html"
            elif self.inputSource == "-":
                outputFilename = "-"
            else:
                outputFilename = "-"
        walker = html5lib.treewalkers.getTreeWalker("lxml")
        s = html5lib.serializer.htmlserializer.HTMLSerializer(alphabetical_attributes=True)
        rendered = s.render(walker(self.document), encoding='utf-8')
        if not config.dryRun:
            try:
                if outputFilename == "-":
                    outputFile = sys.stdout.write(rendered)
                else:
                    with open(outputFilename, "w") as f:
                        f.write(rendered)
            except:
                die("Something prevented me from saving the output document to {0}.", outputFilename)

    def printTargets(self):
        def targetText(el):
            return el.get('title') or textContent(el)
        exportedTerms = set(targetText(el) for el in findAll('dfn[data-export]'))
        ignoredTerms = set(targetText(el) for el in findAll('dfn[data-noexport]'))
        print "Exported terms:"
        for term in exportedTerms:
            print u"  {0}".format(term)
        print "Unexported terms:"
        for term in ignoredTerms:
            print u"  {0}".format(term)

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
            with open(filename, 'r') as fh:
                return fh.read()
        except IOError:
            if error:
                die("The include file for {0} disappeared underneath me.", name)
















def fillInBoilerplate(doc):
    # Arbitrarily-chosen signal for whether there's already boilerplate.
    if doc.html.startswith("<!DOCTYPE html>"):
        return

    # Otherwise, if you start your spec with an <h1>, I'll take it as the spec's title and remove it.
    # (It gets added back in the header file.)
    match = re.match("^<h1>([^<]+)</h1>", doc.html)
    if match:
        doc.md.title = match.group(1)
        config.textMacros['title'] = doc.md.title
        doc.html = doc.html[len(match.group(0)):]

    if not doc.md.title:
        die("Can't generate the spec without a title.\nAdd a 'Title' metadata entry, or an <h1> on the first line.")

    header = doc.getInclusion('header')
    footer = doc.getInclusion('footer')

    doc.html = '\n'.join([header, doc.html, footer])


def fillWith(tag, newElements):
    for el in findAll(u"[data-fill-with='{0}']".format(u(tag))):
        replaceContents(el, newElements)


def addLogo(doc):
    html = doc.getInclusion('logo')
    fillWith('logo', parseHTML(html))


def addCopyright(doc):
    html = doc.getInclusion('copyright')
    html = replaceTextMacros(html)
    fillWith('copyright', parseHTML(html))


def addAbstract(doc):
    html = doc.getInclusion('abstract')
    html = replaceTextMacros(html)
    fillWith('abstract', parseHTML(html))


def addStatusSection(doc):
    html = doc.getInclusion('status')
    html = replaceTextMacros(html)
    fillWith('status', parseHTML(html))


def addObsoletionNotice(doc):
    if doc.md.warning:
        html = doc.getInclusion(doc.md.warning)
        html = replaceTextMacros(html)
        fillWith('warning', parseHTML(html))

def addAtRisk(doc):
    if len(doc.md.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.md.atRisk:
        html += "<li>"+replaceTextMacros(feature)
    fillWith('at-risk', parseHTML(html))


def addIndexSection(doc):
    from collections import OrderedDict
    indexEntries = defaultdict(list)
    attemptedForRefs = defaultdict(list)
    seenGlobalNames = set()
    for el in findAll("dfn"):
        linkTexts = linkTextsFromElement(el, preserveCasing=True)
        headingLevel = headingLevelOfElement(el) or u"Unnumbered section"
        if el.get('data-dfn-for') is not None:
            disambiguator = u"{0} for {1}".format(el.get('data-dfn-type'), ', '.join(el.get('data-dfn-for').split()))
        else:
            type = el.get('data-dfn-type')
            if type == "dfn":
                disambiguator = "definition of"
            else:
                disambiguator = u"({0})".format(el.get('data-dfn-type'))
        id = el.get('id')
        seenGlobalNames.update(GlobalNames.fromEl(el))
        for linkText in linkTexts:
            sort = re.sub(r'[^a-z0-9]', '', linkText.lower())
            entry = {
                'text':u(escapeHTML(linkText)),
                'type':el.get('data-dfn-type'),
                'id':u(id),
                'level':u(headingLevel),
                'disambiguator':u(escapeHTML(disambiguator)),
                'sort':sort,
                'globalNames': GlobalNames.fromEl(el)
                }
            indexEntries[linkText].append(entry)
            for ref in GlobalNames.refsFromEl(el):
                attemptedForRefs[ref].append(entry)
    unseenForRefs = set(attemptedForRefs.viewkeys()).difference(seenGlobalNames)

    # Now print the indexes
    sortedEntries = OrderedDict(sorted(indexEntries.items(), key=lambda x:x[1][0]['sort']))
    html = u"<ul class='indexlist'>\n"
    for text, items in sortedEntries.items():
        if len(items) == 1:
            item = items[0]
            html += u"<li>{text}, <a href='#{id}' title='section {level}'>{level}</a>\n".format(**item)
            if item['type'] == "property":
                reffingDfns = []
                for globalName in item['globalNames']:
                    reffingDfns += attemptedForRefs[globalName]
                if reffingDfns:
                    html += u"<dl><dt>Property Values:"
                    for reffingDfn in reffingDfns:
                        html += u"<dd>{text}, <a href='#{id}' title='section {level}'>{level}</a>\n".format(**reffingDfn)
                    html += u"</dl>"
        else:
            html += u"<li>{text}<ul>".format(**items[0])
            for item in items:
                html += u"<li>{disambiguator}, <a href='#{id}' title='section {level}'>{level}</a>\n".format(**item)
            html += u"</ul>"
    html += u"</ul>"
    fillWith("index", parseHTML(html))



def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables
    def extractKeyValFromRow(tr):
        # Extract the key, minus the trailing :
        result = re.match(u'(.*):', textContent(row[0]).strip())
        if result is None:
            die("Propdef row headers need be a word followed by a colon. Got:\n{0}", textContent(row[0]).strip())
            return '',''
        key = result.group(1).strip().capitalize()
        # Extract the value from the second cell
        val = textContent(row[1]).strip()
        return key, val
    # Extract propdef info
    props = []
    for table in findAll('table.propdef'):
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
    for table in findAll('table.descdef'):
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

    html = u""

    if len(props):
        # Set up the initial table columns for properties
        columns = ["Name", "Value", "Initial", "Applies to", "Inherited", "Percentages", "Media"]
        # Add any additional keys used in the document.
        allKeys = set()
        for prop in props:
            allKeys |= set(prop.keys())
        columns.extend(sorted(allKeys - set(columns)))
        # Create the table
        html += u"<table class='proptable data'><thead><tr>"
        for column in columns:
            if column == "Inherited":
                html += u"<th scope=col>Inh."
            elif column == "Percentages":
                html += u"<th scope=col>%ages"
            else:
                html += u"<th scope=col>"+escapeHTML(u(column))
        html += u"<tbody>"
        for prop in props:
            html += u"\n<tr><th scope=row><a data-property>{0}</a>".format(escapeHTML(u(prop['Name'])))
            for column in columns[1:]:
                html += u"<td>" + u(escapeHTML(prop.get(column, "")))
        html += u"</table>"
    else:
        html += u"<p>No properties defined."

    if len(atRules):
        atRuleNames = sorted(atRules.keys())
        for atRuleName in atRuleNames:
            descs = atRules[atRuleName]
            if atRuleName == "":
                atRuleName = u"Miscellaneous"
            columns = ["Name", "Value", "Initial"]
            allKeys = set()
            for desc in descs:
                allKeys |= set(desc.keys())
            columns.extend(sorted(allKeys - set(columns)))
            html += u"<h3 class='no-num' id='{1}-descriptor-table'>{0} Descriptors</h3>".format(u(atRuleName), simplifyText(u(atRuleName)))
            html += u"<table class=proptable><thead><tr>"
            for column in columns:
                html += u"<th scope=col>{0}".format(escapeHTML(u(column)))
            html += u"<tbody>"
            for desc in descs:
                html += u"\n<tr><th scope-row><a data-property>{0}</a>".format(escapeHTML(u(desc['Name'])))
                for column in columns[1:]:
                    html += u"<td>" + escapeHTML(u(desc.get(column, "")))
            html += u"</table>"

    fillWith("property-index", parseHTML(html))


def addTOCSection(doc):
    def removeBadToCElements(html):
        # Several elements which can occur in headings shouldn't be copied over into the ToC.

        # ToC text is wrapped in an <a>, but the HTML parser doesn't like nested <a>s.
        html = re.sub(r'<(/?)a\b', r'<\1span', html)

        # Remove any <dfn>s, so they don't get duplicated in the ToC.
        html = re.sub(u'(<dfn[^>]*>)|(</dfn>)', '', html)

        return html

    skipLevel = float('inf')
    previousLevel = 0
    html = u''
    for header in findAll('h2, h3, h4, h5, h6'):
        level = int(header.tag[-1])

        # Same deal - hit a no-toc, suppress the entire section.
        if hasClass(header, "no-toc"):
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue
        else:
            skipLevel = float('inf')

        if level > previousLevel:
            html += u"<ul class='toc'>"
        elif level < previousLevel:
            html += u"</ul>" * (previousLevel - level)
        contents = removeBadToCElements(innerHTML(find(".content", header)))
        # Add section number
        contents = "<span class='secno'>{0}</span>".format(header.get('data-level') or u'') + contents
        html += u"<li><a href='#{0}'>{1}</a>".format(u(header.get('id')), contents)
        previousLevel = level
    fillWith("table-of-contents", parseHTML(html))
    for badSpan in findAll(".toc span[href]"):
        del badSpan.attrib['href']

def addSpecMetadataSection(doc):
    def printEditor(editor):
        str = u"<dd class='p-author h-card vcard'>"
        if(editor['link']):
            if(editor['link'][0:4] == "http"):
                str += u"<a class='p-name fn u-url url' href='{0}'>{1}</a>".format(editor['link'], editor['name'])
            else:
                # Link is assumed to be an email address
                str += u"<a class='p-name fn u-email email' href='mailto:{0}'>{1}</a>".format(editor['link'], editor['name'])
        else:
            str += u"<span class='p-name fn'>{0}</span>".format(editor['name'])
        if(editor['org'].strip() != ''):
            str += u" (<span class='p-org org'>{0}</span>)".format(editor['org'])
        return str

    header = u"<dl>"
    header += u"<dt>This version:<dd><a href='[VERSION]' class='u-url'>[VERSION]</a>"
    if doc.md.TR:
        header += u"<dt>Latest version:<dd><a href='{0}'>{0}</a>".format(doc.md.TR)
    if doc.md.ED:
        header += u"<dt>Editor's Draft:<dd><a href='{0}'>{0}</a>".format(doc.md.ED)
    if len(doc.md.previousVersions):
        header += u"<dt>Previous Versions:" + u''.join(map(u"<dd><a href='{0}' rel='previous'>{0}</a>".format, doc.md.previousVersions))
    if doc.md.mailingList:
        header += u"""
    <dt>Feedback:</dt>
        <dd><a href="mailto:{0}?subject=%5B[SHORTNAME]%5D%20feedback">{0}</a>
            with subject line
            &ldquo;<kbd>[[SHORTNAME]] <var>&hellip; message topic &hellip;</var></kbd>&rdquo;""".format(doc.md.mailingList)
        if doc.md.mailingListArchives:
            header += u"""(<a rel="discussion" href="{0}">archives</a>)""".format(doc.md.mailingListArchives)
    if doc.md.testSuite is not None:
        header += u"<dt>Test Suite:<dd><a href='{0}'>{0}</a>".format(doc.md.testSuite)
    else:
        header += u"<dt>Test Suite:<dd>None Yet"
    if len(doc.md.editors):
        header += u"<dt>Editors:\n"
        for editor in doc.md.editors:
            header += printEditor(editor)
    else:
        header += u"<dt>Editors:<dd>???"
    if len(doc.md.previousEditors):
        header += "<dt>Former Editors:\n"
        for editor in doc.md.previousEditors:
            header += printEditor(editor)
    if len(doc.md.otherMetadata):
        for key, vals in doc.md.otherMetadata.items():
            header += u"<dt>{0}:".format(key)
            for val in vals:
                header += u"<dd>"+val
    header += u"</dl>"
    header = replaceTextMacros(header)
    fillWith('spec-metadata', parseHTML(header))


def addReferencesSection(doc):
    text = u"<dl>"
    for ref in sorted(doc.normativeRefs, key=lambda r: r.linkText):
        text += u"<dt id='{1}' title='{0}'>[{0}]</dt>".format(ref.linkText, simplifyText(ref.linkText))
        text += u"<dd>"+u(ref)+u"</dd>"
    text += u"</dl>"
    fillWith("normative-references", parseHTML(text))

    text = u"<dl>"
    # If the same doc is referenced as both normative and informative, normative wins.
    for ref in sorted(doc.informativeRefs - doc.normativeRefs, key=lambda r: r.linkText):
        text += u"<dt id='{1}' title='{0}'>[{0}]</dt>".format(ref.linkText, simplifyText(ref.linkText))
        text += u"<dd>"+u(ref)+u"</dd>"
    text += u"</dl>"
    fillWith("informative-references", parseHTML(text))

def addIssuesSection(doc):
    from copy import deepcopy
    issues = findAll('.issue')
    if len(issues) == 0:
        return
    header = find("#issues-index")
    if not header:
        header = lxml.etree.Element('h2', {'id':"issues-index", 'class':"no-num"})
        header.text = "Issues Index"
        appendChild(find("body"), header)
    container = lxml.etree.Element('div', {'style':"counter-reset: issue"})
    insertAfter(header, container)
    for issue in issues:
        el = deepcopy(issue)
        if el.tag not in ("pre",):
            el.tag = "div"
        appendChild(container, el)
        issuelink = lxml.etree.Element('a', {'href':'#'+issue.get('id')})
        issuelink.text = u" ↵ "
        appendChild(el, issuelink)
    for idel in findAll("[id]", container):
        del idel.attrib['id']
    for dfnel in findAll("dfn", container):
        dfnel.tag = "span"
