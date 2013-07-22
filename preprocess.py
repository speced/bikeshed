#!/usr/bin/python
# -*- coding: utf-8 -*-

# Dependencies:
# * python 2.6 or 2.7
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

from __future__ import division
import re
from collections import defaultdict
import subprocess
import os
import sys
import html5lib
from html5lib import treewalkers
from html5lib.serializer import htmlserializer
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
from optparse import OptionParser
from urllib import urlopen
from datetime import date, datetime
import json
from lib import biblio
from lib.fuckunicode import u
from lib.ReferenceManager import ReferenceManager
from lib.htmlhelpers import *

debugQuiet = False
debug = False
doc = None
textMacros = {}

def main():
    optparser = OptionParser()
    optparser.add_option("-i", "--in", dest="inputFile",
                         default="Overview.src.html",
                         help="Path to the source file. [default: %default]")
    optparser.add_option("-o", "--out", dest="outputFile",
                         default="Overview.html",
                         help="Path to the output file. [default: %default]")
    optparser.add_option("-b", "--biblio", dest="biblioFile",
                         help="Path to a local bibliography file. By default,\
the processor uses the remote file at \
<https://www.w3.org/Style/Group/css3-src/biblio.ref>.")
    optparser.add_option("--para", dest="paragraphMode", default="markdown",
                         help="Pass 'markdown' for Markdown-style paragraph, or 'html' for normal HTML paragraphs. [default: %default]")
    optparser.add_option("-q", "--quiet", dest="quiet", default=False, action="store_true",
                         help="Suppresses everything but fatal errors from printing.")
    optparser.add_option("--debug", dest="debug", default=False, action="store_true",
                         help="Makes the processor continue after hitting a fatal error.")
    optparser.add_option("--print-exports", dest="printExports", default=False, action="store_true",
                         help="Prints those terms that will be exported for cross-ref purposes.")
    optparser.add_option("--update-cross-refs", dest="updateCrossRefs", default=False, action="store_true",
                         help="Forces a fresh download of all the cross-ref data.")
    (options, posargs) = optparser.parse_args()

    global debugQuiet
    debugQuiet = options.quiet
    global debug
    debug = options.debug

    global doc
    doc = CSSSpec(inputFilename=options.inputFile,
                  biblioFilename=options.biblioFile,
                  paragraphMode=options.paragraphMode)
    doc.preprocess()

    if options.printExports:
        doc.printTargets()
    elif options.updateCrossRefs:
        updateCrossRefs()
    else:
        doc.finish(outputFilename=options.outputFile)


def die(msg, *formatArgs):
    global debug
    print u"FATAL ERROR: "+u(msg).format(*map(u, formatArgs))
    if not debug:
        sys.exit(1)

def warn(msg, *formatArgs):
    global debugQuiet
    if not debugQuiet:
        print u"WARNING: "+u(msg).format(*map(u, formatArgs))

def say(msg, *formatArgs):
    global debugQuiet
    if not debugQuiet:
        print u(msg).format(*map(u, formatArgs))

def progress(msg, val, total):
    global debugQuiet
    if debugQuiet:
        return
    barSize = 20
    fractionDone = val / total
    hashes = "#" * int(fractionDone*barSize)
    spaces = " " * (barSize - int(fractionDone*barSize))
    print "\r{0} [{1}{2}] {3}%".format(msg, hashes, spaces, int(fractionDone*100)),
    if val == total:
        print
    sys.stdout.flush()


def findAll(sel, context=None):
    if context is None:
        global doc
        context = doc.document
    return CSSSelector(sel)(context)


def find(sel, context=None):
    result = findAll(sel, context)
    if result:
        return result[0]
    else:
        return None


def replaceTextMacros(text):
    global textMacros
    for tag, replacement in textMacros.items():
        text = u(text).replace(u"[{0}]".format(u(tag.upper())), u(replacement))
    # Also replace the <<production>> shortcuts, because they won't survive the HTML parser.
    text = re.sub(r"<<([\w-]+)>>", r'<a data-autolink="link" class="production"><var>&lt;\1></var></a>', text)
    # Also replace the ''maybe link'' shortcuts.
    # They'll survive the HTML parser, but they don't match if they contain an element.
    # (The other shortcuts are "atomic" and can't contain elements.)
    text = re.sub(r"''(.+?)''", r'<span data-autolink="maybe" class="css">\1</span>', text)
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
    ret = ["<table class='descdef'>"]
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        key = match.group(1)
        val = match.group(2)
        ret.append("<tr><th>" + key + ":<td>" + val)
    ret.append("</table>")
    return ret


def transformMetadata(lines, doc, **kwargs):
    def boolFromString(str):
        return str.lower() in ('true', 't', 'yes', 'y', '1')

    doc.hasMetadata = True

    for line in lines:
        match = re.match(u"\s*([^:]+):\s*(.*)", u(line))
        if(match is None):
            die(u"Incorrectly formatted metadata line:\n{0}", u(line))
        key = match.group(1)
        val = u(match.group(2))
        if key == "Status":
            doc.status = val
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
                die("Error: one of the editors didn't match the format \
'<name>, <company>, <email-or-contact-page>")
        elif key == "At Risk":
            doc.atRisk.append(val)
        elif key == "Test Suite":
            doc.testSuite = val
        elif key == "Ignored Properties":
            doc.ignoredProperties.extend(prop.strip() for prop in val.split(u','))
        elif key == "Ignored Terms":
            doc.ignoredTerms.extend(term.strip() for term in val.split(u','))
        else:
            doc.otherMetadata[key].append(val)

    # Fill in text macros.
    global textMacros
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
    textMacros["shortname"] = doc.shortname
    textMacros["vshortname"] = u"{0}-{1}".format(doc.shortname, doc.level)
    if doc.status in longstatuses:
        textMacros["longstatus"] = longstatuses[doc.status]
    else:
        die(u"Unknown status '{0}' used.",doc.status)
    if doc.status == "LCWD":
        textMacros["status"] = u"WD"
    else:
        textMacros["status"] = doc.status
    textMacros["latest"] = doc.TR or u"???"
    textMacros["abstract"] = doc.abstract or u"???"
    textMacros["abstractattr"] = escapeAttr(doc.abstract.replace(u"<<",u"<").replace(u">>",u">")) or u"???"
    textMacros["year"] = u(doc.date.year)
    textMacros["date"] = doc.date.strftime(u"{0} %B %Y".format(doc.date.day))
    textMacros["cdate"] = doc.date.strftime(u"%Y%m%d")
    textMacros["isodate"] = doc.date.strftime(u"%Y-%m-%d")
    if doc.deadline:
        textMacros["deadline"] = doc.deadline.strftime(u"{0} %B %Y".format(doc.deadline.day))
    if doc.status == "ED":
        textMacros["version"] = doc.ED
    else:
        textMacros["version"] = u"http://www.w3.org/TR/{3}/{0}-{1}-{2}/".format(textMacros["status"],
                                                                              textMacros["vshortname"],
                                                                              textMacros["cdate"],
                                                                              textMacros["year"])
    return []


def parseDate(val, field):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", field, val)


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
            errors.append(u"Metadata block must contain a '{0}' entry.".format(u(name)))
    for attr, name in requiredMultiKeys:
        if len(getattr(doc, attr)) == 0:
            errors.append(u"Metadata block must contain at least one '{0}' entry.".format(u(name)))
    if errors:
        die(u"\n".join(errors))


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
                        u'<a title="{0}" data-autolink="biblio" data-biblio-type="{1}">[{0}]</a>'.format(
                            u(match.group(2)),
                            biblioType)))
        text = re.sub(ur"'([*-]*[a-zA-Z][a-zA-Z0-9_*/-]*)'", ur'<a data-autolink="property" class="property" title="\1">\1</a>', text)
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
    biblioLinks = findAll("a[data-autolink='biblio']")
    for el in biblioLinks:

        if el.get('title'):
            linkText = u(el.get('title'))
        else:
            # Assume the text is of the form "[NAME]"
            linkText = textContent(el)[1:-1]
            el.set('title', linkText)
        if linkText not in doc.biblios:
            die(u"Couldn't find '{0}' in bibliography data.", linkText)
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
    dedupIds(doc, findAll("h1, h2, h3, h4, h5, h6"))
    addHeadingBonuses(doc)

def resetHeadings(doc):
    for header in findAll('h2, h3, h4, h5, h6'):
        # Reset to base, if this is a re-run
        if find(".content", header) is not None:
            content = find(".content", header)
            moveContents(header, content)

        # Insert current header contents into a <span class='content'>
        content = etree.Element('span', {"class":"content"})
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
            secno = etree.Element('span', {"class":"secno"})
            secno.text = header.get('data-level') + u' '
            header.insert(0, secno)

        if foundFirstSection:
            # Add a self-link, to help with sharing links.
            selflink = etree.Element('a', {"href": "#" + header.get('id'), "class":"section-link"});
            selflink.text = u"§"
            appendChild(header, selflink)


def formatPropertyNames(doc):
    propertyCells = findAll("table.propdef tr:first-child > td")
    descriptorCells = findAll("table.descdef tr:first-child > td")
    for cell in propertyCells:
        props = [u(x.strip()) for x in textContent(cell).split(u',')]
        html = u', '.join(u"<dfn id='{1}' data-dfn-type='property'>{0}</dfn>".format(name, simplifyText(name)) for name in props)
        replaceContents(cell, parseHTML(html))
    for cell in descriptorCells:
        props = [u(x.strip()) for x in textContent(cell).split(u',')]
        html = u', '.join(u"<dfn id='{1}' data-dfn-type='descriptor'>{0}</dfn>".format(name, simplifyText(name)) for name in props)
        replaceContents(cell, parseHTML(html))


def processDfns(doc):
    classifyDfns(doc)
    dedupIds(doc, findAll("dfn"))
    doc.refs.processDfns(findAll("dfn"))


def classifyDfns(doc):
    for el in findAll("dfn"):
        text = textContent(el)
        prefix = u""
        suffix = u""
        if text[-2:] == "()":
            text = text[:-2]
            suffix = u"-function"
            type = "function"
        elif text[0:1] == "<" and text[-1:] == ">":
            text = text[1:-1]
            suffix = u"-production"
            type = "production"
        elif text[0:1] == "@":
            prefix = u"at-"
            type = "at-rule"
        elif el.tag == "dfn" and len(el) == 1 and el[0].get('data-autolink') == "maybe":
            suffix = u"-value"
            type = "value"
        else:
            type = "link"

        if el.get('data-dfn-type') is None:
            el.set('data-dfn-type', type)
        if el.get('id') is None:
            el.set('id', text)


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
    # For re-run, if you have a [data-autolink] property, we'll regen your href anyway.
    # <i> is a legacy syntax for term autolinks. If it links up, we change it into an <a>.
    # Maybe autolinks can be any element.  If it links up, we change it into an <a>.
    autolinks = findAll("a:not([href]), a[data-autolink], i, [data-autolink='maybe']")
    badProperties = set()
    badLinks = set()
    for el in autolinks:
        # Explicitly empty title indicates this shouldn't be an autolink.
        if el.get('title') == '':
            break

        type = el.get('data-autolink') or "link"
        text = u(el.get('title')) or textContent(el).lower()
        if len(text) == 0:
            die(u"Autolink {0} has no linktext.", outerHTML(el))

        if type == u"biblio":
            # Move biblio management into ReferenceManager later
            el.set('href', '#'+simplifyText(text))
            continue

        id = doc.refs.getRef(type, text)
        if id is None:
            if type == "property":
                if text not in doc.ignoredProperties:
                    badProperties.add(text)
            elif type != "maybe":
                if text not in doc.ignoredTerms:
                    badLinks.add(text)
        else:
            el.set('href', '#'+id)
            el.tag = "a"

    if badProperties:
        die(u"Couldn't find definitions for the properties: {0}\nDefine them, or add them to the 'Ignored Properties' metadata entry.", u', '.join(map(u"'{0}'".format, badProperties)))
    if badLinks:
        die(u"Couldn't find definitions for the terms: {0}\nDefine them, or add them to the 'Ignored Terms' metadata entry.", u', '.join(map(u'"{0}"'.format, badLinks)))


def cleanupHTML(doc):
    # Find <style> in body, add scoped='', move to be first child.
    for el in findAll("body style"):
        parent = el.getparent()
        parent.insert(0, el)
        el.set('scoped', '')


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
    ignoredProperties = []
    ignoredTerms = []
    testSuite = None
    otherMetadata = defaultdict(list)

    # internal state
    normativeRefs = set()
    informativeRefs = set()
    refs = ReferenceManager()
    biblios = {}
    paragraphMode = "markdown"

    def __init__(self, inputFilename, biblioFilename=None, paragraphMode="markdown"):
        try:
            self.lines = open(inputFilename, 'r').readlines()
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", inputFilename)

        bibliofh = retrieveCachedFile(cacheLocation=(biblioFilename or os.path.dirname(os.path.realpath(__file__)) + "/biblio.refer"),
                                      fallbackurl="https://www.w3.org/Style/Group/css3-src/biblio.ref",
                                      type="bibliography")

        self.biblios = biblio.processReferBiblioFile(bibliofh)

        self.paragraphMode = paragraphMode

    def preprocess(self):
        # Textual hacks
        transformDataBlocks(self)
        verifyRequiredMetadata(self)
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
        walker = treewalkers.getTreeWalker("lxml")
        s = htmlserializer.HTMLSerializer(alphabetical_attributes=True)
        rendered = s.render(walker(self.document), encoding='utf-8')
        try:
            open(outputFilename, mode='w').write(rendered)
        except:
            die("Something prevented me from saving the output document to {0}.", outputFilename)

    def printTargets(self):
        def targetText(el):
            return el.get('title') or textContent(el)
        allTerms = set(targetText(el) for el in findAll('dfn'))
        exportedTerms = set(targetText(el) for el in findAll('[data-export], .propdef dfn, .descdef dfn'))
        ignoredTerms = set(targetText(el) for el in findAll('[data-noexport]'))
        unexportedTerms = allTerms - exportedTerms - ignoredTerms
        print "Exported terms:"
        print exportedTerms
        print "Unexported terms:"
        print unexportedTerms

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

        pathprefix = os.path.dirname(os.path.realpath(__file__)) + "/include"
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
    # I need some signal for whether or not to insert boilerplate,
    # to preserve the quality that you can run the processor over
    # an already-processed document as a no-op.
    # Arbitrarily, I choose to use whether the first line in the doc
    # is an <h1> with the document's title.

    if not re.match("<h1>[^<]+</h1>", doc.html):
        return

    match = re.match("<h1>([^<]+)</h1>", doc.html)
    doc.title = match.group(1)
    global textMacros
    textMacros['title'] = doc.title
    doc.html = doc.html[len(match.group(0)):]

    header = doc.getInclusion('header')
    footer = doc.getInclusion('footer')

    doc.html = '\n'.join([header, doc.html, footer])


def fillWith(tag, newElements):
    global doc
    for el in findAll(u"[data-fill-with='{0}']".format(u(tag)), doc.document):
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
        header += u"<dt>Test Suite<dd><a href='{0}'>{0}</a>".format(doc.testSuite)
    else:
        header += u"<dt>Test Suite<dd>None Yet"
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


















def updateCrossRefs():
    def linearizeAnchorTree(multiTree, list):
        # Call with multiTree being a list of trees
        for item in multiTree:
            if item['type'] not in ("section", "other"):
                list.append(item)
            if item['children']:
                linearizeAnchorTree(item['children'], list)
            item['children'] = False
        return list

    specFile = retrieveCachedFile(cacheLocation=os.path.dirname(os.path.realpath(__file__))+"/speclist.json",
                                  fallbackurl="http://test.csswg.org/shepherd/api/spec",
                                  type="spec list",
                                  force=True)
    specData = json.load(specFile)
    specNames = [x['name'] for x in specData.values()]
    specs = []
    anchorTypes = set()
    anchorsByType = {
        'propdef':defaultdict(list),
        'descdef':defaultdict(list),
        'dfn':defaultdict(list),
    }
    allAnchors = defaultdict(list)
    for i,specName in enumerate(specNames):
        #progress("Fetching xref data", i+1, len(specNames))
        sys.stdout.flush()
        f = retrieveCachedFile(cacheLocation=os.path.dirname(os.path.realpath(__file__))+"/spec-data/{0}.json".format(specName),
                               fallbackurl="http://test.csswg.org/shepherd/api/spec?spec={0}&anchors=1".format(specName),
                               type="spec data", quiet=True)
        data = json.load(f)
        anchors = linearizeAnchorTree(data['anchors'], [])
        for anchor in anchors:
            type = anchor['type']
            if type in ("section", "other"):
                continue
            anchorData = {'spec':specName, 'url':anchor['uri']}
            if 'linking_text' in anchor:
                texts = anchor['linking_text']
            else:
                texts = [anchor['title']]
            for text in texts:
                anchorsByType[type][text].append(anchorData)
                allAnchors[text].append(anchorData)



if __name__ == "__main__":
    main()
