#!/usr/bin/python
# -*- coding: utf-8 -*-

# Dependencies:
# * python 2.7
# * python-dev, libxml2-dev, libxslt1-dev
# * html5lib - "pip install html5lib"
# * lxml - "pip install lxml"
# * cssselect "pip install cssselect"
#
# OSX setup:
# $ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
# $ sudo python get-pip.py
# $ sudo pip install html5lib
# $ sudo pip install lxml
# $ sudo pip install cssselect
# $ chmod u+x preprocess.py


# TODO
# Handle "foo!!bar" in titles correctly.
# Introspect based on IDL parsing.

from __future__ import division
import re
from collections import defaultdict
import os
import sys
import json
import argparse
from urllib2 import urlopen
from datetime import date, datetime
import html5lib
import lxml
import lib.config as config
import lib.biblio as biblio
import lib.update as update
from lib.fuckunicode import u
from lib.ReferenceManager import ReferenceManager
from lib.htmlhelpers import *
from lib.messages import *

config.scriptPath = os.path.dirname(os.path.realpath(__file__))

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
    specParser.add_argument("infile", type=argparse.FileType('r'), nargs="?",
                            default="Overview.src.html",
                            help="Path to the source file. [default: %(default)s]")
    # Have to use string type for the outfile, so it doens't truncate the output on --dry-run
    specParser.add_argument("outfile", nargs="?",
                            default="Overview.html",
                            help="Path to the output file. [default: %(default)s]")
    specParser.add_argument("--para", dest="paragraphMode", default="markdown",
                            help="Pass 'markdown' for Markdown-style paragraph, or 'html' for normal HTML paragraphs. [default: %(default)s]")

    updateParser = subparsers.add_parser('update', help="Update supporting files (those in /spec-data).", epilog="If no options are specified, everything is downloaded.")
    updateParser.add_argument("--anchors", action="store_true", help="Download crossref anchor data.")
    updateParser.add_argument("--biblio", action="store_true", help="Download biblio data.")
    updateParser.add_argument("--link-defaults", dest="linkDefaults", action="store_true", help="Download link default data.")
    
    debugParser = subparsers.add_parser('debug', help="Run various debugging commands.")
    debugParser.add_argument("infile", type=argparse.FileType('r'), nargs="?",
                            default="Overview.src.html",
                            help="Path to the source file. [default: %(default)s]")
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

    if options.subparserName == "update":
        update.update(anchors=options.anchors, biblio=options.biblio, linkDefaults=options.linkDefaults)
    elif options.subparserName == "spec":
        config.doc = CSSSpec(inputFile=options.infile, paragraphMode=options.paragraphMode)
        config.doc.preprocess()
        config.doc.finish(outputFilename=options.outfile)
    elif options.subparserName == "debug":
        if options.printExports:
            config.doc = CSSSpec(inputFile=options.infile)
            config.doc.preprocess()
            config.doc.printTargets()
        elif options.jsonCode:
            config.doc = CSSSpec(inputFile=options.infile)
            config.doc.preprocess()
            exec("print json.dumps({0}, indent=2)".format(options.jsonCode))
        elif options.code:
            config.doc = CSSSpec(inputFile=options.infile)
            config.doc.preprocess()
            exec("print {0}".format(options.code))
        elif options.linkText:
            config.debug = True
            config.quiet = True
            config.doc = CSSSpec(inputFile=options.infile)
            config.doc.preprocess()
            refs = config.doc.refs.refs[options.linkText]
            config.quiet = options.quiet
            if not config.quiet:
                print "Refs for '{0}':".format(options.linkText)
            print json.dumps(refs, indent=2)


def replaceTextMacros(text):
    # Replace the [FOO] things.
    for tag, replacement in config.textMacros.items():
        text = u(text).replace(u"[{0}]".format(u(tag.upper())), u(replacement))
    # Replace <<<token>>> shortcuts.  (It's annoying to type the actual token syntax.)
    text = re.sub(ur"<<<([^>]+)>>>", ur"<a data-link-type='token'>〈\1〉</a>", text)
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
    text = re.sub(r"''(.+?)''", r'<span data-link-type="maybe" class="css">\1</span>', text)
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
            continue
        if inDataBlock and re.match("\s*</({0})".format(opaqueBlocks), line):
            inDataBlock = False
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


def transformPropdef(lines, doc, **kwargs):
    ret = ["<table class='propdef'>"]
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        key = match.group(1)
        val = match.group(2)
        ret.append("<tr><th>" + key + ":<td>" + val)
    ret.append("</table>")
    return ret


def transformDescdef(lines, doc, **kwargs):
    name = None
    descFor = None
    ret = []
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        key = match.group(1).strip()
        val = match.group(2).strip()
        if key == "Name":
            name = val
        elif key == "For":
            descFor = val
            val = "<a at-rule>{0}</a>".format(val)
        ret.append("<tr><th>" + key + ":<td>" + val)
    ret.append("</table>")
    if descFor is None:
        die("The descdef for '{0}' is missing a 'For' line.", name)
    ret.insert(0, "<table class='descdef' data-dfn-for='{0}'>".format(descFor))
    return ret


def transformMetadata(lines, doc, **kwargs):
    def boolFromString(str):
        return str.lower() in ('true', 't', 'yes', 'y', '1')

    doc.hasMetadata = True

    def parseDate(val, field):
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except:
            die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", field, val)

    for line in lines:
        match = re.match(u"\s*([^:]+):\s*(.*)", u(line))
        if(match is None):
            die(u"Incorrectly formatted metadata line:\n{0}", u(line))
        key = match.group(1)
        val = u(match.group(2)).strip()
        if key == "Status":
            doc.status = val
            doc.refs.setStatus(val)
        elif key == "Title":
            doc.title = val
        elif key == "TR":
            doc.TR = val
        elif key == "ED":
            doc.ED = val
        elif key == "Group":
            doc.group = val.lower()
        elif key == "Date":
            doc.date = parseDate(val, "Date")
        elif key == "Deadline":
            doc.deadline = parseDate(val, "Deadline")
        elif key == "Abstract":
            doc.abstract = val
        elif key == "Shortname":
            doc.shortname = val
        elif key == "Level":
            doc.level = int(val)
        elif key == "Warning":
            if val.lower() in (u'obsolete', u'not ready'):
                doc.warning = val.lower().replace(' ', '-')
            else:
                die('Unknown value for "Warning" metadata.')
        elif key == "Previous Version":
            doc.previousVersions.append(val)
        elif key == "Editor":
            match = re.match(u"([^,]+) ,\s* ([^,]+) ,?\s* (.*)", val, re.X)
            if match:
                doc.editors.append(
                    {
                        'name': match.group(1),
                        'org': match.group(2),
                        'link': match.group(3)})
            else:
                die("'Editor' format is '<name>, <company>, <email-or-contact-page>. Got:\n{0}", val)
        elif key == "At Risk":
            doc.atRisk.append(val)
        elif key == "Test Suite":
            doc.testSuite = val
        elif key == "Ignored Terms":
            doc.ignoredTerms.extend(term.strip() for term in val.split(u','))
        elif key == "Link Defaults":
            for default in val.split(","):
                match = re.match(u"^\s* ([\w-]+)  (?:\s+\( ({0}) (?:\s+(TR|ED))? \) )  \s+(.*) \s*$".format("|".join(config.dfnTypes)), default, re.X)
                if match:
                    spec = match.group(1)
                    type = match.group(2)
                    status = match.group(3)
                    terms = match.group(4).split('/')
                    dfnFor = None
                    for term in terms:
                        config.doc.refs.defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
                else:
                    die("'Link Defaults' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{0}", default)
        else:
            doc.otherMetadata[key].append(val)

    # Remove the metadata block from the generated document.
    return []

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
    if doc.title:
        config.textMacros["title"] = doc.title
    config.textMacros["shortname"] = doc.shortname
    config.textMacros["vshortname"] = u"{0}-{1}".format(doc.shortname, doc.level)
    if doc.status in longstatuses:
        config.textMacros["longstatus"] = longstatuses[doc.status]
    else:
        die(u"Unknown status '{0}' used.",doc.status)
    if doc.status == "LCWD":
        config.textMacros["status"] = u"WD"
    else:
        config.textMacros["status"] = doc.status
    config.textMacros["latest"] = doc.TR or u"???"
    config.textMacros["abstract"] = doc.abstract or u"???"
    config.textMacros["abstractattr"] = escapeAttr(doc.abstract.replace(u"<<",u"<").replace(u">>",u">")) or u"???"
    config.textMacros["year"] = u(doc.date.year)
    config.textMacros["date"] = doc.date.strftime(u"{0} %B %Y".format(doc.date.day))
    config.textMacros["cdate"] = doc.date.strftime(u"%Y%m%d")
    config.textMacros["isodate"] = doc.date.strftime(u"%Y-%m-%d")
    if doc.deadline:
        config.textMacros["deadline"] = doc.deadline.strftime(u"{0} %B %Y".format(doc.deadline.day))
    if doc.status == "ED":
        config.textMacros["version"] = doc.ED
    else:
        config.textMacros["version"] = u"http://www.w3.org/TR/{3}/{0}-{1}-{2}/".format(config.textMacros["status"],
                                                                                       config.textMacros["vshortname"],
                                                                                       config.textMacros["cdate"],
                                                                                       config.textMacros["year"])


def verifyRequiredMetadata(doc):
    if not doc.hasMetadata:
        die("The document requires at least one metadata block.")

    requiredSingularKeys = [
        ('status', 'Status'),
        ('ED', 'ED'),
        ('abstract', 'Abstract'),
        ('shortname', 'Shortname'),
        ('level', 'Level')
    ]
    requiredMultiKeys = [
        ('editors', 'Editor')
    ]
    errors = []
    for attr, name in requiredSingularKeys:
        if getattr(doc, attr) is None:
            errors.append(u"    Missing a '{0}' entry.".format(u(name)))
    for attr, name in requiredMultiKeys:
        if len(getattr(doc, attr)) == 0:
            errors.append(u"    Must provide at least one '{0}' entry.".format(u(name)))
    if errors:
        die(u"Not all required metadata was provided:\n{0}", u"\n".join(errors))


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
        while re.search(ur"\[\[(!?)([\w-]+)\]\]", text):
            match = re.search(ur"\[\[(!?)([\w-]+)\]\]", text)

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
            die(u"Unknown data-biblio-type value '{0}' on {1}. \
Only 'normative' and 'informative' allowed.", u(el.get('data-biblio-type')), outerHTML(el))


def processHeadings(doc):
    resetHeadings(doc)
    determineHeadingLevels(doc)
    addHeadingIds(doc)
    dedupIds(doc, findAll("h2, h3, h4, h5, h6"))
    addHeadingBonuses(doc)

def resetHeadings(doc):
    for header in findAll('h2, h3, h4, h5, h6'):
        # Reset to base, if this is a re-run
        if find(".content", header) is not None:
            content = find(".content", header)
            moveContents(header, content)

        # Insert current header contents into a <span class='content'>
        content = lxml.etree.Element('span', {"class":"content"})
        moveContents(content, header)
        appendChild(header, content)

def addHeadingIds(doc):
    for header in findAll("h2, h3, h4, h5, h6"):
        if header.get('id') is not None:
            continue
        header.set('id', simplifyText(textContent(find(".content", header))))

def determineHeadingLevels(doc):
    headerLevel = [0,0,0,0,0]
    def incrementLevel(level):
        headerLevel[level-2] += 1
        for i in range(level-1, 5):
            headerLevel[i] = 0
    def printLevel():
        return u'.'.join(u(x) for x in headerLevel if x > 0)

    skipLevel = float('inf')
    for header in findAll('h2, h3, h4, h5, h6'):
        # Add the heading number.
        level = int(header.tag[-1])

        # Reset, if this is a re-run.
        if(header.get('data-level')):
            del header.attrib['data-level']

        # If we encounter a no-num, don't number it or any in the same section.
        if re.search("no-num", header.get('class') or ''):
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue
        else:
            skipLevel = float('inf')

        incrementLevel(level)
        header.set('data-level', printLevel())

def addHeadingBonuses(doc):
    foundFirstSection = False
    for header in findAll('h2, h3, h4, h5, h6'):
        if header.get("data-level") is not None:
            foundFirstSection = True
            secno = lxml.etree.Element('span', {"class":"secno"})
            secno.text = header.get('data-level') + u' '
            header.insert(0, secno)

        if foundFirstSection:
            # Add a self-link, to help with sharing links.
            selflink = lxml.etree.Element('a', {"href": "#" + header.get('id'), "class":"section-link"});
            selflink.text = u"§"
            appendChild(header, selflink)


def formatPropertyNames(doc):
    propertyCells = findAll("table.propdef tr:first-child > td")
    descriptorCells = findAll("table.descdef tr:first-child > td")
    for cell in propertyCells:
        props = [u(x.strip()) for x in textContent(cell).split(u',')]
        html = u', '.join(u"<dfn property>{0}</dfn>".format(name, simplifyText(name)) for name in props)
        replaceContents(cell, parseHTML(html))
    for cell in descriptorCells:
        props = [u(x.strip()) for x in textContent(cell).split(u',')]
        html = u', '.join(u"<dfn descriptor>{0}</dfn>".format(name, simplifyText(name)) for name in props)
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
        "link-type":"data-link-type"
    }
    for el in findAll(",".join("[{0}]".format(attr) for attr in attrFixup.keys())):
        for attr, fixedAttr in attrFixup.items():
            if el.get(attr) is not None:
                el.set(fixedAttr, el.get(attr))
                del el.attrib[attr]

    for el in findAll("dfn"):
        for dfnType in config.dfnTypes.union(["dfn"]):
            if el.get(dfnType) is not None:
                del el.attrib[dfnType]
                el.set("data-dfn-type", dfnType)
    for el in findAll("a"):
        for linkType in (config.dfnTypes | set("dfn")):
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
    classifyDfns(doc)
    dedupIds(doc, findAll("dfn"))
    doc.refs.addLocalDfns(findAll("dfn"))


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
            if type in classList:
                return type
            if "idl" in classList and "extract" not in classList:
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
    elif text[-2:] == "()" and not (dfn.get('id') or '').startswith("dom-"):
        return "function"
    else:
        return "dfn"

def determineLinkType(el):
    # 1. Look at data-link-type
    linkType = treeAttr(el, 'data-link-type')
    text = textContent(el)
    # ''foo: bar'' is a propdef for 'foo'
    if linkType == "maybe" and re.match("^[\w-]+\s*:\s*\S", text):
        el.set('title', re.match("^\s*([\w-]+)\s*:\s*\S", text).group(1))
        return "property"
    if linkType:
        if linkType in config.linkTypes:
            return linkType
        die("Unknown link type '{0}' on:\n{1}", linkType, outerHTML(el))
    # 2. Introspect on the text
    if text[0:1] == "@":
        return "at-rule"
    elif re.match("^<[\w-]+>$", text):
        return "type"
    elif text[:1] == u"〈" and text[-1:] == u"〉":
        return "token"
    elif text[0:1] == ":":
        return "selector"
    elif text[-2:] == "()":
        return "functionish"
    else:
        return "dfn"

def classifyDfns(doc):
    dfnTypeToPrefix = {v:k for k,v in config.dfnClassToType.items()}
    for el in findAll("dfn"):
        dfnType = determineDfnType(el)
        # Push the dfn type down to the <dfn> itself.
        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', dfnType)
        if dfnType in config.typesUsingFor:
            if el.get('data-dfn-for'):
                pass
            else:
                dfnFor = treeAttr(el, "data-dfn-for")
                if dfnFor:
                    el.set('data-dfn-for', dfnFor)
                else:
                    die("'{0}' definitions need to specify what they're for.\nAdd a 'for' attribute to {1}, or add 'dfn-for' to an ancestor.", dfnType, outerHTML(el))
        if el.get('id') is None:
            id = simplifyText(textContent(el))
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                id = "dom-" + id
            elif dfnType in ("attribute", "method", "const", "dictmember"):
                id = "dom-{0}-{1}".format(el.get("data-dfn-for"), id)
            else:
                id = "{0}-{1}".format(dfnTypeToPrefix[dfnType], id)
            el.set('id', id)
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

        linkType = determineLinkType(el)
        text = u(el.get('title')) or textContent(el).lower()
        text = re.sub(u"\s+", u" ", text)
        if len(text) == 0:
            die(u"Autolink {0} has no linktext.", outerHTML(el))

        if linkType == u"biblio":
            # Move biblio management into ReferenceManager later
            el.set('href', '#'+simplifyText(text))
            continue

        url = doc.refs.getRef(linkType, text,
                              spec=treeAttr(el, 'data-link-spec'),
                              status=treeAttr(el, 'data-link-status'),
                              linkFor=treeAttr(el, 'data-link-for'),
                              el=el,
                              error=(text not in doc.ignoredTerms))
        if url is not None:
            el.set('href', url)
            el.tag = "a"


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
    # required metadata
    hasMetadata = False
    status = None
    ED = None
    abstract = None
    shortname = None
    level = None

    # optional metadata
    TR = None
    title = "???"
    date = datetime.utcnow().date()
    deadline = None
    group = "csswg"
    editors = []
    previousVersions = []
    warning = None
    atRisk = []
    ignoredTerms = []
    testSuite = None
    otherMetadata = defaultdict(list)

    # internal state
    normativeRefs = set()
    informativeRefs = set()
    refs = ReferenceManager()
    biblios = {}
    paragraphMode = "markdown"

    def __init__(self, inputFile, paragraphMode="markdown"):
        try:
            self.lines = inputFile.readlines()
            self.date = datetime.fromtimestamp(os.path.getmtime(inputFile.name))
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", inputFilename)

        bibliofh = retrieveCachedFile(cacheLocation=config.scriptPath + "/biblio.refer",
                                      fallbackurl="https://www.w3.org/Style/Group/css3-src/biblio.ref",
                                      type="bibliography")
        self.biblios = biblio.processReferBiblioFile(bibliofh)

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

        self.paragraphMode = paragraphMode

    def preprocess(self):
        # Textual hacks
        transformDataBlocks(self)
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

        # Handle all the links
        processDfns(self)
        buildBibliolinkDatabase(self)
        processAutolinks(self)

        addPropertyIndex(self)
        addReferencesSection(self)
        addIndexSection(self)
        processHeadings(self) # again
        addTOCSection(self)

        # Any final HTML cleanups
        cleanupHTML(self)

        return self

    def finish(self, outputFilename):
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

    def getInclusion(self, name, group=None, status=None):
        # First looks for a file specialized on the group and status.
        # If that fails, specializes only on the group.
        # If that fails, specializes only on the status.
        # If that fails, grabs the most general file.
        # Filenames must be of the format NAME-GROUP-STATUS.include
        if group is None:
            group = self.group
        if status is None:
            status = self.status

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
            die("Couldn't find an appropriate include file for the {0} inclusion, given group='{1}' and status='{2}'.", name, group, status)
            filename = "/dev/null"

        try:
            with open(filename, 'r') as fh:
                return fh.read()
        except IOError:
            die("The include file for {0} disappeared underneath me.", name)
















def fillInBoilerplate(doc):
    # Arbitrarily-chosen signal for whether there's already boilerplate.
    if doc.html.startswith("<!DOCTYPE html>"):
        return

    # Otherwise, if you start your spec with an <h1>, I'll take it as the spec's title and remove it.
    # (It gets added back in the header file.)
    match = re.match("^<h1>([^<]+)</h1>", doc.html)
    if match:
        doc.title = match.group(1)
        config.textMacros['title'] = doc.title
        doc.html = doc.html[len(match.group(0)):]

    if not doc.title:
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
    if doc.warning:
        html = doc.getInclusion(doc.warning)
        html = replaceTextMacros(html)
        fillWith('warning', parseHTML(html))

def addAtRisk(doc):
    if len(doc.atRisk) == 0:
        return
    html = "<p>The following features are at-risk, and may be dropped during the CR period:\n<ul>"
    for feature in doc.atRisk:
        html += "<li>"+replaceTextMacros(feature)
    fillWith('at-risk', parseHTML(html))

def addIndexSection(doc):
    from lib.ReferenceManager import linkTextsFromElement
    indexElements = findAll("dfn")
    indexEntries = []
    for el in indexElements:
        if el.get('data-dfn-type') in ("property", "descriptor"):
            # These get their own index section.
            continue
        linkTexts = linkTextsFromElement(el, preserveCasing=True)
        if el.get('data-dfn-type') == "value":
            linkTexts = map(u"{0} (value)".format, linkTexts)
        headingLevel = headingLevelOfElement(el) or u"Unnumbered section"
        id = el.get('id')
        for linkText in linkTexts:
            indexEntries.append((linkText, id, headingLevel))
    html = u"<ul class='indexlist'>\n"
    for text, id, level in sorted(indexEntries, key=lambda x:re.sub(r'[^a-z0-9]', '', x[0].lower())):
        html += u"<li>{0}, <a href='#{1}' title='section {2}'>{2}</a>\n".format(escapeHTML(u(text)), u(id), u(level))
    html += u"</ul>"
    fillWith("index", parseHTML(html))



def addPropertyIndex(doc):
    # Extract all the data from the propdef and descdef tables
    props = []
    for table in findAll('table.propdef'):
        prop = {}
        names = []
        rows = findAll('tr', table)
        for row in rows:
            # Extract the key, minus the trailing :
            key = re.match(u'(.*):', textContent(row[0])).group(1).strip()
            # Extract the value from the second cell
            if key == "Name":
                names = [textContent(x) for x in findAll('dfn', row[1])]
            else:
                prop[key] = innerHTML(row[1])
        for name in names:
            tempProp = prop.copy()
            tempProp['Name'] = name
            props.append(tempProp)
    atRules = defaultdict(list)
    for table in findAll('table.descdef'):
        desc = {}
        names = []
        atRule = ""
        rows = findAll('tr', table)
        for row in rows:
            # Extract the key, minus the trailing :
            key = re.match(u'(.*):', textContent(row[0])).group(1).strip()
            # Extract the value from the second cell
            if key == "Name":
                names = [textContent(x) for x in findAll('dfn', row[1])]
            elif key == "For":
                atRule = textContent(row[1])
            else:
                desc[key] = innerHTML(row[1])
        for name in names:
            tempDesc = desc.copy()
            tempDesc['Name'] = name
            atRules[atRule].append(tempDesc)

    html = u""

    if len(props):
        # Set up the initial table columns for properties
        columns = ["Name", "Value", "Initial", "Applies To", "Inherited", "Percentages", "Media"]
        # Add any additional keys used in the document.
        allKeys = set()
        for prop in props:
            allKeys |= set(prop.keys())
        columns.extend(sorted(allKeys - set(columns)))
        # Create the table
        html += u"<table class=proptable><thead><tr>"
        for column in columns:
            if column == "Inherited":
                html += u"<th scope=col>Inh."
            elif column == "Percentages":
                html += u"<th scope=col>%ages"
            else:
                html += u"<th scope=col>"+u(column)
        html += u"<tbody>"
        for prop in props:
            html += u"\n<tr><th scope=row><a data-property>{0}</a>".format(u(prop['Name']))
            for column in columns[1:]:
                html += u"<td>" + u(prop.get(column, ""))
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
            columns.extend(sorted(allKeys - set(columns) - set("For")))
            html += u"<h3 class='no-num'>{0} Descriptors</h3>".format(u(atRuleName))
            html += u"<table class=proptable><thead><tr>"
            for column in columns:
                html += u"<th scope=col>{0}".format(u(column))
            html += u"<tbody>"
            for desc in descs:
                html += u"\n<tr><th scope-row><a data-property>{0}</a>".format(u(desc['Name']))
                for column in columns[1:]:
                    html += u"<td>" + u(desc.get(column, ""))
            html += u"</table>"

    fillWith("property-index", parseHTML(html))


def addTOCSection(doc):
    def removeBadToCElements(html):
        # Several elements which can occur in headings shouldn't be copied over into the ToC.

        # ToC text is wrapped in an <a>, but the HTML parser doesn't like nested <a>s.
        html = html.replace(u'<a', u'<span').replace(u'</a', u'</span')

        # Remove any <dfn>s, so they don't get duplicated in the ToC.
        html = re.sub(u'(<dfn[^>]*>)|(</dfn>)', '', html)

        return html

    skipLevel = float('inf')
    previousLevel = 0
    html = u''
    for header in findAll('h2, h3, h4, h5, h6'):
        level = int(header.tag[-1])

        # Same deal - hit a no-toc, suppress the entire section.
        if re.search("no-toc", header.get('class') or ''):
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
    header = u"<dl>"
    header += u"<dt>This version:<dd><a href='[VERSION]' class='u-url'>[VERSION]</a>"
    if doc.TR:
        header += u"<dt>Latest version:<dd><a href='{0}'>{0}</a>".format(doc.TR)
    if doc.ED:
        header += u"<dt>Editor's Draft:<dd><a href='{0}'>{0}</a>".format(doc.ED)
    if len(doc.previousVersions):
        header += u"<dt>Previous Versions:" + u''.join(map(u"<dd><a href='{0}' rel='previous'>{0}</a>".format, doc.previousVersions))
    header += u"""
<dt>Feedback:</dt>
    <dd><a href="mailto:www-style@w3.org?subject=%5B[SHORTNAME]%5D%20feedback">www-style@w3.org</a>
        with subject line
        &ldquo;<kbd>[[SHORTNAME]] <var>&hellip; message topic &hellip;</var></kbd>&rdquo;
        (<a rel="discussion" href="http://lists.w3.org/Archives/Public/www-style/">archives</a>)"""
    if doc.testSuite is not None:
        header += u"<dt>Test Suite:<dd><a href='{0}'>{0}</a>".format(doc.testSuite)
    else:
        header += u"<dt>Test Suite:<dd>None Yet"
    if len(doc.editors):
        header += u"<dt>Editors:\n"
        for editor in doc.editors:
            header += u"<dd class='p-author h-card vcard'>"
            if(editor['link'][0:4] == "http"):
                header += u"<a class='p-name fn u-url url' href='{0}'>{1}</a> \
(<span class='p-org org'>{2}</span>)".format(editor['link'],
                                             editor['name'],
                                             editor['org'])
            else:
                # Link is assumed to be an email address
                header += u"<a class='p-name fn u-email email' href='mailto:{2}'>{0}</a> \
(<span class='p-org org'>{1}</span>)".format(editor['name'],
                                             editor['org'],
                                             editor['link'])
    else:
        header += u"<dt>Editors:<dd>???"
    if len(doc.otherMetadata):
        for key, vals in doc.otherMetadata.items():
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





if __name__ == "__main__":
    main()
