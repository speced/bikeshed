#!/usr/bin/python
# -*- coding: utf-8 -*-

# Dependencies:
# * python 2.6 or 2.7
# * python-dev, libxml2-dev, libxslt1-dev
# * html5lib - "pip install html5lib"
# * lxml - "pip install lxml"
# * cssselect "pip install cssselect"

import re
from collections import defaultdict
import subprocess
import os
import sys
import html5lib
from lxml import html
from lxml import etree
from lxml.cssselect import CSSSelector
from optparse import OptionParser
from urllib import urlopen
from datetime import date, datetime

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
    optparser.add_option("-q", "--quiet", dest="quiet", default=False, action="store_true",
                         help="Suppresses everything but fatal errors from printing.")
    optparser.add_option("--debug", dest="debug", default=False, action="store_true",
                         help="Turns on some debug features.")
    (options, posargs) = optparser.parse_args()

    global debugQuiet
    debugQuiet = options.quiet
    global debug
    debug = options.debug

    global doc
    doc = CSSSpec(inputFilename=options.inputFile,
                  biblioFilename=options.biblioFile)    
    doc.preprocess()
    doc.finish(outputFilename=options.outputFile)


def die(msg):
    global debug
    print "FATAL ERROR: "+msg
    if not debug:
        sys.exit(1)


def warn(msg):
    global debugQuiet
    if not debugQuiet:
        print "WARNING: "+msg


def textContent(el):
    return html.tostring(el, method='text', with_tail=False)


def innerHTML(el):
    return (el.text or '') + ''.join(html.tostring(x) for x in el)


def outerHTML(el):
    return html.tostring(el, with_tail=False)


def parseHTML(str):
    doc = html5lib.parse(
        str,
        treebuilder='lxml',
        encoding='utf-8',
        namespaceHTMLElements=False)
    return find('body', doc)[0]


def escapeHTML(str):
    # Escape HTML
    return str.replace('&', '&amp;').replace('<', '&lt;')


def escapeAttr(str):
    return str.replace('&', '&amp;').replace("'", '&apos;').replace('"', '&quot;')


def findAll(sel, context=None):
    if context is None:
        global doc
        context = doc.document
    return CSSSelector(sel)(context)


def find(sel, context=None):
    if context is None:
        global doc
        context = doc.document
    result = findAll(sel, context)
    if result:
        return result[0]
    else:
        return None


def clearContents(el):
    for child in el.iterchildren():
        el.remove(child)
    el.text = ''
    return el


def replaceContents(el, new):
    clearContents(el).append(new)
    return el


def fillWith(tag, new):
    for el in findAll("[data-fill-with='{0}']".format(tag)):
        replaceContents(el, new)


def replaceTextMacros(text):
    global textMacros
    for tag, replacement in textMacros.items():
        text = text.replace("[{0}]".format(tag.upper()), replacement)
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
    for (i, line) in enumerate(doc.lines):
        if not inDataBlock and re.match("\s*<(pre|xmp)", line):
            inDataBlock = True
            continue
        if inDataBlock and re.match("\s*</(pre|xmp)", line):
            inDataBlock = False
            continue
        if (re.match("\s*[^<\s]", line) or re.match("\s*<(em|strong|i|b|u|dfn|a|code|var)", line)) and previousLineBlank and not inDataBlock:
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
            if re.match("^\s*$", match.group(1)):
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
                    'end': i,
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


def transformMetadata(lines, doc, **kwargs):
    for line in lines:
        match = re.match("\s*([^:]+):\s*(.*)", line)
        key = match.group(1)
        val = match.group(2)
        if key == "Status":
            doc.status = val
        elif key == "TR":
            doc.TR = val
        elif key == "ED":
            doc.ED = val
        elif key == "Date":
            doc.date = datetime.strptime(val, "%Y-%m-%d").date()
        elif key == "Abstract":
            doc.abstract = val
        elif key == "Shortname":
            doc.shortname = val
        elif key == "Previous Version":
            doc.previousVersions.append(val)
        elif key == "Editor":
            match = re.match("([^,]+) ,\s* ([^,]+) ,?\s* (.*)", val, re.X)
            if match:
                doc.editors.append(
                    {
                        'name': match.group(1),
                        'org': match.group(2),
                        'link': match.group(3)})
            else:
                die("Error: one of the editors didn't match the format \
'<name>, <company>, <email-or-contact-page>")
        else:
            doc.otherMetadata[key].append(val)

    # Fill in text macros. 
    global textMacros
    longstatuses = {
        "ED": "Editor's Draft",
        "WD": "W3C Working Draft",
        "CR": "W3C Candidate Recommendation",
        "PR": "W3C Proposed Recommendation",
        "REC": "W3C Recommendation",
        "PER": "W3C Proposed Edited Recommendation",
        "NOTE": "W3C Working Group Note",
        "MO": "W3C Member-only Draft",
        "UD": "Unofficial Proposal Draft"
    }
    textMacros["shortname"] = doc.shortname
    textMacros["longstatus"] = longstatuses[doc.status]
    textMacros["status"] = doc.status
    textMacros["latest"] = doc.TR
    textMacros["year"] = str(doc.date.year)
    textMacros["date"] = doc.date.strftime("{0} %B %Y".format(doc.date.day))
    textMacros["cdate"] = doc.date.strftime("%Y%m%d")
    textMacros["isodate"] = doc.date.strftime("%Y-%m-%d")
    if doc.status == "ED":
        textMacros["version"] = doc.ED
    else:
        textMacros["version"] = "http://www.w3.org/TR/{3}/{0}-{1}-{2}".format(doc.status, 
                                                                              doc.shortname, 
                                                                              textMacros["cdate"], 
                                                                              textMacros["year"])
    return []


def transformBibliolinks(doc):
    while re.search(r"\[\[(!?)([^\]]+)\]\]", doc.html):
        match = re.search(r"\[\[(!?)([^\]]+)\]\]", doc.html)

        if match.group(1) == "!":
            biblioType = "normative"
        else:
            biblioType = "informative"
        
        doc.html = doc.html.replace(
            match.group(0),
            "<a title='{0}' data-autolink='biblio' data-biblio-type='{1}'>[{0}]</a>".format(
                match.group(2), 
                biblioType))


def transformCSSText(doc):
    doc.html = re.sub(r"''([^']+)''", r"<a data-autolink='maybe' class='css'>\1</a>", doc.html)


def transformPropertyNames(doc):
    doc.html = re.sub(r"'([a-z0-9_*-]+)'", r"<a data-autolink='property' class='property' title='\1'>\1</a>", doc.html)


def transformProductions(doc):
    doc.html = re.sub(r"<<([^ ]+)>>", r"<a data-autolink='internal' class='production'>&lt;\1></a>", doc.html)


def addSpecMetadataSection(doc):
    header = "<dl>"
    header += "<dt>This version:<dd><a href='{0}' class='u-url'>{0}</a>".format("[VERSION]")
    if doc.TR:
        header += "<dt>Latest version:<dd><a href='{0}'>{0}</a>".format(doc.TR)
    if doc.ED:
        header += "<dt>Editor's Draft:<dd><a href='{0}'>{0}</a>".format(doc.ED)
    if len(doc.previousVersions):
        header += "<dt>Previous Versions:" + ''.join(map("<dd><a href='{0}' rel='previous'>{0}</a>".format, doc.previousVersions))
    if len(doc.editors):
        header += "<dt>Editors:\n"
        for editor in doc.editors:
            header += "<dd class='p-author h-card vcard'>"
            if(editor['link'][0:4] == "http"):
                header += "<a class='p-name fn u-url url' href='{0}'>{1}</a> \
(<span class='p-org org'>{2}</span>)".format(editor['link'],
                                             editor['name'],
                                             editor['org'])
            else:
                # Link is assumed to be an email address
                header += "<span class='p-name fn'>{0}</span> \
(<span class='p-org org'>{1}</span>), \
<a class='u-email email' href='mailto:{2}'>{2}</a>".format(editor['name'],
                                                           editor['org'],
                                                           editor['link'])
    else:
        header += "<dt>Editors:<dd>???"
    if len(doc.otherMetadata):
        for key, vals in doc.otherMetadata.items():
            header += "<dt>{0}:".format(key)
            for val in vals:
                header += "<dd>"+val
    header += "</dl>"
    header = replaceTextMacros(header)
    fillWith('spec-metadata', parseHTML(header))


def buildBibliolinkDatabase(doc):
    biblioLinks = findAll("a[data-autolink='biblio']")
    for el in biblioLinks:

        if el.get('title'):
            linkText = el.get('title')
        else:
            # Assume the text is of the form "[NAME]"
            linkText = textContent(el)[1:-1]
            el.set('title', linkText)
        if linkText not in doc.biblios:
            die("Couldn't find '{0}' in bibliography data.".format(linkText))
        biblioEntry = doc.biblios[linkText]
        if el.get('data-biblio-type') == "normative":
            doc.normativeRefs.add(biblioEntry)
        elif el.get('data-biblio-type') == "informative":
            doc.informativeRefs.add(biblioEntry)
        else:
            die("Unknown data-biblio-type value '{0}' on {1}. \
Only 'normative' and 'informative' allowed.".format(el.get('data-biblio-type'), outerHTML(el)))


def addReferencesSection(doc):
    text = "<dl>"
    for ref in doc.normativeRefs:
        text += "<dt id='{1}' title='{0}'>[{0}]</dt>".format(ref.linkText, idFromText(ref.linkText))
        text += "<dd>"+str(ref)+"</dd>"
    text += "</dl>"
    fillWith("normative-references", parseHTML(text))

    text = "<dl>"
    # If the same doc is referenced as both normative and informative, normative wins.
    for ref in doc.informativeRefs - doc.normativeRefs:
        text += "<dt id='{1}' title='{0}'>[{0}]</dt>".format(ref.linkText, idFromText(ref.linkText))
        text += "<dd>"+str(ref)+"</dd>"
    text += "</dl>"
    fillWith("informative-references", parseHTML(text))


def addHeadingNumbers(doc):
    headerLevel = [0,0,0,0,0]
    def incrementLevel(level):
        headerLevel[level-2] += 1
        for i in range(level-1, 5):
            headerLevel[i] = 0
    def printLevel():
        return '.'.join(str(x) for x in headerLevel if x > 0)

    skipLevel = float('inf')
    for header in findAll('h2, h3, h4, h5, h6'):
        level = int(header.tag[-1])

        # Reset, if this is a re-run.
        if(header.get('level')):
            del header.attrib['level']
        if(len(header) > 0 and header[0].tag == 'span' and header[0].get('class') == "secno"):
            header.text = header[0].tail
            del header[0]

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
        secno = etree.Element('span', {"class":"secno"})
        secno.text = printLevel() + ' '
        header.insert(0, secno)
        secno.tail = header.text
        header.text = ''


def addTOCSection(doc):
    skipLevel = float('inf')
    previousLevel = 0
    html = ''
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
            html += "<ul class='toc'>"
        elif level < previousLevel:
            html += "</ul>"
        html += "<li><a href='#{0}'>{1}</a>".format(header.get('id'),
                                                   innerHTML(header))
        previousLevel = level
    fillWith("table-of-contents", parseHTML(html))


def formatPropertyNames(doc):
    propertyCells = findAll("table.propdef tr:first-child > td")
    for cell in propertyCells:
        props = [x.strip() for x in textContent(cell).split(',')]
        html = ', '.join("<dfn id='{1}'>{0}</dfn>".format(name, idFromText(name)) for name in props)
        replaceContents(cell, parseHTML(html))


def buildPropertyDatabase(doc):
    propdefTables = findAll('table.propdef')
    for propdefTable in propdefTables:
        propdef = {}
        names = []
        rows = findAll('tr', propdefTable)
        for row in rows:
            # Extract the key, minus the trailing :
            key = re.match('(.*):', textContent(row[0])).group(1).strip()
            # Extract the value from the second cell
            if key == "Name":
                names = [textContent(x) for x in findAll('dfn', row[1])]
            else:
                propdef[key] = innerHTML(row[1])
        for name in names:
            doc.propdefs[name] = propdef


def addPropertyIndex(doc):
    # Set up the initial table columns
    columns = ["Values", "Initial", "Applies To", "Inherited", "Percentages", "Media"]
    # Add any additional keys used in the document.
    allKeys = set()
    for propdef in doc.propdefs.values():
        allKeys |= set(propdef.keys())
    columns.extend(allKeys - set(columns))
    # Create the table
    html = "<table class=proptable><thead><tr><th scope=col>Name"
    for column in columns:
        if column == "Inherited":
            html += "<th scope=col>Inh."
        elif column == "Percentages":
            html += "<th scope=col>%ages"
        else:
            html += "<th scope=col>"+column
    for name, propdef in doc.propdefs.items():
        html += "<tr><th scope=row><a data-property>{0}</a>".format(name)
        for column in columns:
            html += "<td>" + propdef.get(column, "")
    html += "</table>"
    fillWith("property-index", parseHTML(html))


def genIdsForAutolinkTargets(doc):
    ids = set()
    linkTargets = findAll("dfn, h1, h2, h3, h4, h5, h6")
    for el in linkTargets:
        if el.get('id') is not None:
            id = el.get('id')
            if id in ids:
                die("Found a duplicate explicitly-specified id '{0}' in {1}".format(id, outerHTML(el)))
        else:
            id = idFromText(textContent(el))
            if id in ids:
                # Try to de-dup the id by appending an integer after it.
                for x in range(10):
                    if (id+str(x)) not in ids:
                        id = id + str(x)
                        break
                else:
                    die("More than 10 link-targets with the same id '{0}'.".format(id))
            el.set('id', id)
        ids.add(id)
    doc.ids = ids


def idFromText(id):
    if id[-2:] == "()":
        id = id[:-2]
        suffix = "-function"
    elif id[0] == "<" and id[-1] == ">":
        id = id[1:-1]
        suffix = "-production"
    else:
        suffix = ""
    return re.sub("[^a-z0-9_-]", "", id.replace(" ", "-").lower()) + suffix


def linkTextsFromElement(el, preserveCasing=False):
    if el.get('title') == '':
        return []
    elif el.get('title'):
        return [x.strip() for x in el.get('title').split('|')]
    elif preserveCasing:
        return [textContent(el).strip()]
    else:
        return [textContent(el).strip().lower()]       


def buildAutolinkDatabase(doc):
    links = {}
    linkTargets = findAll("dfn, h2, h3, h4, h5, h6")
    for el in linkTargets:
        if not re.search("no-ref", el.get('class') or ""):
            linkTexts = linkTextsFromElement(el)
            for linkText in linkTexts:
                if linkText in links:
                    die("Two link-targets have the same linking text: " + linkText)
                else:
                    links[linkText] = el.get('id')
    doc.links = links


def processAutolinks(doc):
    autolinks = findAll("a:not([href]), a[data-autolink], i")
    for el in autolinks:
        # Empty title means this shouldn't be an autolink.
        if el.get('title') == '':
            break
        # Using an <i> is a legacy autolinking form.
        if el.tag == "i":
            el.tag = "a"
        # If it's not yet classified, it's a plain "internal" link.
        if not el.get('data-autolink'):
            el.set('data-autolink', 'internal')
        linkText = el.get('title') or textContent(el).lower()

        if len(linkText) == 0:
            die("Autolink {0} has no linktext.".format(outerHTML(el)))

        type = el.get('data-autolink')
        if type == "biblio":
            # All the biblio links have already been verified.
            el.set('href', '#'+idFromText(linkText))
        elif type == "property":
            if linkText in doc.propdefs:
                el.set('href', '#'+idFromText(linkText))
            else:
                pass
                # Until I get the cross-spec references, don't die here.
                # die("Autolink '{0}'' pointed to unknown property.".format(linkText))
        elif type in ["internal", "maybe"]:
            for variation in linkTextVariations(linkText):
                if variation in doc.links:
                    el.set('href', '#'+doc.links[variation])
                    break
            else:
                if type == "internal":
                    # "maybe"-type links don't care if they don't link up.
                    die("Couldn't find an autolink target matching '{0}' for {1}".format(linkText, outerHTML(el)))
        else:
            die("Unknown type of autolink '{0}'".format(type))


def linkTextVariations(str):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding a title attr isn't usually necessary.
    yield str

    if str[-3:] == "ies":
        yield str[:-3]+"y"
    if str[-2:] == "es":
        yield str[:-2]
    if str[-2:] == "'s":
        yield str[:-2]
    if str[-1:] == "s":
        yield str[:-1]
    if str[-1:] == "'":
        yield str[:-1]


def headingLevelOfElement(el):
    while el.getparent().tag != "body":
        el = el.getparent()
    while not re.match(r"h\d", el.tag):
        el = el.getprevious()
    return el.get('data-level') or '??'


def addIndexSection(doc):
    indexElements = findAll("dfn:not([data-autolink='property'])")
    indexEntries = {}
    for el in indexElements:
        linkTexts = linkTextsFromElement(el, preserveCasing=True)
        headingLevel = headingLevelOfElement(el)
        id = el.get('id')
        for linkText in linkTexts:
            if linkText in indexEntries:
                die("Multiple declarations with the same linktext '{0}'".format(linkText))
            indexEntries[linkText] = (linkText, id, headingLevel)
    sortedEntries = sorted(indexEntries.values(), key=lambda x:re.sub(r'[^a-z0-9]', '', x[0].lower()))
    html = "<ul class='indexlist'>"
    for text, id, level in sortedEntries:
        html += "<li>{0}, <a href='#{1}' title='section {2}'>{2}</a>".format(escapeHTML(text), id, level)
    html += "</ul>"
    fillWith("index", parseHTML(html))


def retrieveCachedFile(cacheLocation, type, fallbackurl=None):
    try:
        fh = open(cacheLocation, 'r')
    except IOError:
        if fallbackurl is None:
            die("Couldn't find the {0} cache file at the specified location '{1}'.".format(type, cacheLocation))
        else:
            warn("Couldn't find the {0} cache file at the specified location '{1}'.".format(type, cacheLocation))
            warn("Attempting to download it from '{0}'...".format(url))
            try:
                fh = urlopen(url)
            except:
                die("Couldn't retrieve the {0} file from '{1}'.".format(type, url))
            try:
                warn("Attempting to save the {0} file to cache...".format(type))
                outfh = open(cacheLocation, 'w')
                outfh.write(fh.read())
                fh.close()
                fh = open(cacheLocation, 'r')
                warn("Successfully saved the {0} file to cache.".format(type))
            except:
                warn("Couldn't save the {0} file to cache. Proceeding...".format(type))
    return fh


class CSSSpec(object):
    title = "???"
    date = date.today()
    status = "???"
    TR = "???"
    ED = "???"
    editors = []
    previousVersions = []
    abstract = "???"
    shortname = "???"
    atRisk = []
    otherMetadata = defaultdict(list)
    ids = set()
    links = {}
    normativeRefs = set()
    informativeRefs = set()
    propdefs = {}
    biblios = {}
    loginInfo = None

    def __init__(self, inputFilename, biblioFilename=None):
        try:
            self.lines = open(inputFilename, 'r').readlines()
        except OSError:
            die("Couldn't find the input file at the specified location \""+inputFilename+"\".")

        bibliofh = retrieveCachedFile(cacheLocation=(biblioFilename or os.path.dirname(os.path.realpath(__file__)) + "/biblio.refer"),
                                      fallbackurl="https://www.w3.org/Style/Group/css3-src/biblio.ref",
                                      type="bibliography")

        self.biblios = processReferBiblioFile(bibliofh)

    def preprocess(self):
        # Textual hacks
        transformDataBlocks(self)
        transformMarkdownParagraphs(self)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(self.lines)
        fillInBoilerplate(self)
        self.html = replaceTextMacros(self.html)
        transformCSSText(self)
        transformPropertyNames(self)
        transformProductions(self)
        transformBibliolinks(self)

        # Build the document
        self.document = html5lib.parse(
            self.html,
            treebuilder='lxml',
            encoding='utf-8',
            namespaceHTMLElements=False)

        # Fill in and clean up a bunch of data
        addStatusSection(self)
        addLogo(self)
        addCopyright(self)
        addSpecMetadataSection(self)
        addAbstract(self)
        formatPropertyNames(self)
        buildPropertyDatabase(self)

        # Normative/informative references
        buildBibliolinkDatabase(self)
        addReferencesSection(self)

        # Autolinks
        genIdsForAutolinkTargets(self)
        buildAutolinkDatabase(self)
        
        # ToC
        addHeadingNumbers(self)
        addTOCSection(self)

        # Property index
        addPropertyIndex(self)

        # Finish Autolinks
        processAutolinks(self)

        # Index
        addIndexSection(self)

        return self

    def finish(self, outputFilename):
        try:
            open(outputFilename, mode='w').write(html.tostring(self.document))
        except:
            die("Something prevented me from saving the output document to {0}.".format(outputFilename))


class BiblioEntry(object):
    linkText = None
    title = None
    authors = None
    foreignAuthors = None
    status = None
    date = None
    url = None
    other = None
    bookName = None
    city = None
    issuer = None
    journal = None
    volumeNumber = None
    numberInVolume = None
    pageNumber = None
    reportNumber = None
    abstract = None

    def __init__(self, **kwargs):
        self.authors = []
        self.foreignAuthors = []
        for key, val in kwargs.items():
            setattr(self, key, val)

    def __str__(self):
        str = ""
        authors = self.authors + self.foreignAuthors

        if len(authors) == 0:
            str += "???. "
        elif len(authors) == 1:
            str += authors[0] + ". "
        elif len(authors) < 4:
            str += "; ".join(authors) + ". "
        else:
            str += authors[0] + "; et al. "

        str += "<a href='{0}'>{1}</a>. ".format(self.url, self.title)

        if self.date:
            str += self.date + ". "

        if self.status:
            str += self.status + ". "

        if self.other:
            str += self.other + " "

        str += "URL: <a href='{0}'>{0}</a>".format(self.url)
        return str


def processReferBiblioFile(file):
    biblios = {}
    biblio = None
    singularReferCodes = {
        "B": "bookName",
        "C": "city",
        "D": "date",
        "I": "issuer",
        "J": "journal",
        "L": "linkText",
        "N": "numberInVolume",
        "O": "other",
        "P": "pageNumber",
        "R": "reportNumber",
        "S": "status",
        "T": "title",
        "U": "url",
        "V": "volumeNumber",
        "X": "abstract"
    }
    pluralReferCodes = {
        "A": "authors",
        "Q": "foreignAuthors",
    }
    for line in file:
        if re.match("\s*#", line) or re.match("\s*$", line):
            # Comment or empty line
            if biblio is not None:
                biblios[biblio.linkText] = biblio
            biblio = BiblioEntry()
        else:
            if biblio is None:
                biblio = BiblioEntry()

        for (letter, name) in singularReferCodes.items():
            if re.match("\s*%"+letter+"\s+[^\s]", line):
                setattr(biblio, name, re.match("\s*%"+letter+"\s+(.*)", line).group(1))
        for (letter, name) in pluralReferCodes.items():
            if re.match("\s*%"+letter+"\s+[^\s]", line):
                getattr(biblio, name).append(re.match("\s*%"+letter+"\s+(.*)", line).group(1))
    return biblios


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

    header = """
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <title>[TITLE]</title>
  <link href="../default.css" rel=stylesheet type="text/css">
  <link href="../csslogo.ico" rel="shortcut icon" type="image/x-icon">
  <link href="https://www.w3.org/StyleSheets/TR/W3C-[STATUS].css" rel=stylesheet type="text/css">
</head>
<body class="h-entry">
<div class="head">
  <p data-fill-with="logo"></p>
  <h1 id="title" class="p-name no-ref">[TITLE]</h1>
  <h2 id="subtitle" class="no-num no-toc no-ref">[LONGSTATUS],
    <span class="dt-updated"><span class="value-title" title="[CDATE]">[DATE]</span></h2>
  <div data-fill-with="spec-metadata"></div>
  <p class='copyright' data-fill-with='copyright'></p>
  <hr title="Separator for header">
</div>

<h2 class='no-num no-toc no-ref' id='abstract'>Abstract</h2>
<p class="p-summary" data-fill-with="abstract"></p>

<h2 class='no-num no-toc no-ref' id='status'>Status of this document</h2>
<div data-fill-with="status"></div>

<h2 class="no-num no-toc no-ref" id="contents">Table of contents</h2>
<div data-fill-with="table-of-contents"></div>
"""
    footer = """

<h2 id="conformance" class="no-ref no-num">
Conformance</h2>

<h3 id="conventions" class="no-ref">
Document conventions</h3>

    <p>Conformance requirements are expressed with a combination of
    descriptive assertions and RFC 2119 terminology. The key words "MUST",
    "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT",
    "RECOMMENDED", "MAY", and "OPTIONAL" in the normative parts of this
    document are to be interpreted as described in RFC 2119.
    However, for readability, these words do not appear in all uppercase
    letters in this specification.

    <p>All of the text of this specification is normative except sections
    explicitly marked as non-normative, examples, and notes. [[!RFC2119]]</p>

    <p>Examples in this specification are introduced with the words "for example"
    or are set apart from the normative text with <code>class="example"</code>,
    like this:

    <div class="example">
        <p>This is an example of an informative example.</p>
    </div>

    <p>Informative notes begin with the word "Note" and are set apart from the
    normative text with <code>class="note"</code>, like this:

    <p class="note">Note, this is an informative note.</p>

<h3 id="conformance-classes" class="no-ref">
Conformance classes</h3>

    <p>Conformance to this specification
    is defined for three conformance classes:
    <dl>
        <dt><dfn title="style sheet!!as conformance class">style sheet</dfn>
            <dd>A <a href="http://www.w3.org/TR/CSS21/conform.html#style-sheet">CSS
            style sheet</a>.
        <dt><dfn>renderer</dfn></dt>
            <dd>A <a href="http://www.w3.org/TR/CSS21/conform.html#user-agent">UA</a>
            that interprets the semantics of a style sheet and renders
            documents that use them.
        <dt><dfn id="authoring-tool">authoring tool</dfn></dt>
            <dd>A <a href="http://www.w3.org/TR/CSS21/conform.html#user-agent">UA</a>
            that writes a style sheet.
    </dl>

    <p>A style sheet is conformant to this specification
    if all of its statements that use syntax defined in this module are valid
    according to the generic CSS grammar and the individual grammars of each
    feature defined in this module.

    <p>A renderer is conformant to this specification
    if, in addition to interpreting the style sheet as defined by the
    appropriate specifications, it supports all the features defined
    by this specification by parsing them correctly
    and rendering the document accordingly. However, the inability of a
    UA to correctly render a document due to limitations of the device
    does not make the UA non-conformant. (For example, a UA is not
    required to render color on a monochrome monitor.)

    <p>An authoring tool is conformant to this specification
    if it writes style sheets that are syntactically correct according to the
    generic CSS grammar and the individual grammars of each feature in
    this module, and meet all other conformance requirements of style sheets
    as described in this module.

<h3 id="partial" class="no-ref">
Partial implementations</h3>

    <p>So that authors can exploit the forward-compatible parsing rules to
    assign fallback values, CSS renderers <strong>must</strong>
    treat as invalid (and <a href="http://www.w3.org/TR/CSS21/conform.html#ignore">ignore
    as appropriate</a>) any at-rules, properties, property values, keywords,
    and other syntactic constructs for which they have no usable level of
    support. In particular, user agents <strong>must not</strong> selectively
    ignore unsupported component values and honor supported values in a single
    multi-value property declaration: if any value is considered invalid
    (as unsupported values must be), CSS requires that the entire declaration
    be ignored.</p>

<h3 id="experimental" class="no-ref">
Experimental implementations</h3>

    <p>To avoid clashes with future CSS features, the CSS2.1 specification
    reserves a <a href="http://www.w3.org/TR/CSS21/syndata.html#vendor-keywords">prefixed
    syntax</a> for proprietary and experimental extensions to CSS.

    <p>Prior to a specification reaching the Candidate Recommendation stage
    in the W3C process, all implementations of a CSS feature are considered
    experimental. The CSS Working Group recommends that implementations
    use a vendor-prefixed syntax for such features, including those in
    W3C Working Drafts. This avoids incompatibilities with future changes
    in the draft.
    </p>

<h3 id="testing" class="no-ref">
Non-experimental implementations</h3>

    <p>Once a specification reaches the Candidate Recommendation stage,
    non-experimental implementations are possible, and implementors should
    release an unprefixed implementation of any CR-level feature they
    can demonstrate to be correctly implemented according to spec.

    <p>To establish and maintain the interoperability of CSS across
    implementations, the CSS Working Group requests that non-experimental
    CSS renderers submit an implementation report (and, if necessary, the
    testcases used for that implementation report) to the W3C before
    releasing an unprefixed implementation of any CSS features. Testcases
    submitted to W3C are subject to review and correction by the CSS
    Working Group.

    <p>Further information on submitting testcases and implementation reports
    can be found from on the CSS Working Group's website at
    <a href="http://www.w3.org/Style/CSS/Test/">http://www.w3.org/Style/CSS/Test/</a>.
    Questions should be directed to the
    <a href="http://lists.w3.org/Archives/Public/public-css-testsuite">public-css-testsuite@w3.org</a>
    mailing list."""

    if doc.status == "CR":
        footer += """
<h3 id="cr-exit-criteria" class="no-ref">
CR exit criteria</h3>

    <p>
    For this specification to be advanced to Proposed Recommendation,
    there must be at least two independent, interoperable implementations
    of each feature. Each feature may be implemented by a different set of
    products, there is no requirement that all features be implemented by
    a single product. For the purposes of this criterion, we define the
    following terms:

    <dl>
        <dt>independent <dd>each implementation must be developed by a
        different party and cannot share, reuse, or derive from code
        used by another qualifying implementation. Sections of code that
        have no bearing on the implementation of this specification are
        exempt from this requirement.

        <dt>interoperable <dd>passing the respective test case(s) in the
        official CSS test suite, or, if the implementation is not a Web
        browser, an equivalent test. Every relevant test in the test
        suite should have an equivalent test created if such a user
        agent (UA) is to be used to claim interoperability. In addition
        if such a UA is to be used to claim interoperability, then there
        must one or more additional UAs which can also pass those
        equivalent tests in the same way for the purpose of
        interoperability. The equivalent tests must be made publicly
        available for the purposes of peer review.

        <dt>implementation <dd>a user agent which:

        <ol class=inline>
            <li>implements the specification.

            <li>is available to the general public. The implementation may
            be a shipping product or other publicly available version
            (i.e., beta version, preview release, or "nightly build").
            Non-shipping product releases must have implemented the
            feature(s) for a period of at least one month in order to
            demonstrate stability.

            <li>is not experimental (i.e., a version specifically designed
            to pass the test suite and is not intended for normal usage
            going forward).
        </ol>
    </dl>

    <p>The specification will remain Candidate Recommendation for at least
    six months.
"""

    footer += """
<h2 class="no-num no-ref" id="references">
References</h2>

<h3 class="no-num no-ref" id="normative">
Normative References</h3>
<div data-fill-with="normative-references"></div>

<h3 class="no-num no-ref" id="informative">
Informative References</h3>
<div data-fill-with="informative-references"></div>

<h2 class="no-num no-ref" id="index">
Index</h2>
<div data-fill-with="index"></div>

<h2 class="no-num no-ref" id="property-index">
Property index</h2>
<div data-fill-with="property-index"></div>

</body>
</html>
"""
    doc.html = '\n'.join([header, doc.html, footer])


def addLogo(doc):
    html = """
    <a href="http://www.w3.org/">
        <img alt="W3C" height="48" src="http://www.w3.org/Icons/w3c_home" width="72">
    </a>"""
    fillWith('logo', parseHTML(html))


def addCopyright(doc):
    html = """
<span><a href="http://www.w3.org/Consortium/Legal/ipr-notice#Copyright" rel="license">Copyright</a> © [YEAR] <a href="http://www.w3.org/"><abbr title="World Wide Web Consortium">W3C</abbr></a><sup>®</sup> (<a href="http://www.csail.mit.edu/"><abbr title="Massachusetts Institute of Technology">MIT</abbr></a>, <a href="http://www.ercim.eu/"><abbr title="European Research Consortium for Informatics and Mathematics">ERCIM</abbr></a>,
    <a href="http://www.keio.ac.jp/">Keio</a>, <a href="http://ev.buaa.edu.cn/">Beihang</a>), All Rights Reserved. W3C <a href="http://www.w3.org/Consortium/Legal/ipr-notice#Legal_Disclaimer">liability</a>,
    <a href="http://www.w3.org/Consortium/Legal/ipr-notice#W3C_Trademarks">trademark</a>
    and <a href="http://www.w3.org/Consortium/Legal/copyright-documents">document
    use</a> rules apply.</span>"""
    html = replaceTextMacros(html)
    fillWith('copyright', parseHTML(html))


def addAbstract(doc):
    html = "<span>" + doc.abstract
    html += " <a href='http://www.w3.org/TR/CSS/'>CSS</a> is a language for describing the rendering of structured documents (such as HTML and XML) on screen, on paper, in speech, etc.</span>"
    fillWith('abstract', parseHTML(html))


def addStatusSection(doc):
    if doc.status == "ED":
        html = """
<div>
  <p>This is a public copy of the editors' draft. It is provided for
   discussion only and may change at any moment. Its publication here does
   not imply endorsement of its contents by W3C. Don't cite this document
   other than as work in progress.

  <p>The (<a href="http://lists.w3.org/Archives/Public/www-style/">archived</a>) 
   public mailing list 
   <a href="mailto:www-style@w3.org?Subject=%5B[SHORTNAME]%5D%20PUT%20SUBJECT%20HERE">www-style@w3.org</a> 
   (see <a href="http://www.w3.org/Mail/Request">instructions</a>) 
   is preferred for discussion of this specification. 
   When sending e-mail, please put the text
   “[SHORTNAME]” in the subject, preferably like this:
   “[<!---->[SHORTNAME]<!---->] <em>…summary of comment…</em>”

  <p>This document was produced by the <a href="/Style/CSS/members">CSS
   Working Group</a> (part of the <a href="/Style/">Style Activity</a>).

  <p>This document was produced by a group operating under the 
   <a href="/Consortium/Patent-Policy-20040205/">5 February 2004 W3C Patent Policy</a>. 
   W3C maintains a 
   <a href="/2004/01/pp-impl/32061/status" rel=disclosure>public list of any patent disclosures</a> 
   made in connection with the deliverables of the group; that page also includes
   instructions for disclosing a patent. An individual who has actual
   knowledge of a patent which the individual believes contains 
   <a href="/Consortium/Patent-Policy-20040205/#def-essential">Essential Claim(s)</a> 
   must disclose the information in accordance with 
   <a href="/Consortium/Patent-Policy-20040205/#sec-Disclosure">section 6 of the W3C Patent Policy</a>.</p>
</div>"""
    elif doc.status == "CR":
        html = """
<div>
  <p><em>This section describes the status of this document at the time of
   its publication. Other documents may supersede this document. A list of
   current W3C publications and the latest revision of this technical report
   can be found in the <a href="http://www.w3.org/TR/">W3C technical reports
   index at http://www.w3.org/TR/.</a></em>

  <p>Publication as a Working Draft does not imply endorsement by the W3C
   Membership. This is a draft document and may be updated, replaced or
   obsoleted by other documents at any time. It is inappropriate to cite this
   document as other than work in progress.

  <p>The (<a href="http://lists.w3.org/Archives/Public/www-style/">archived</a>) 
   public mailing list 
   <a href="mailto:www-style@w3.org?Subject=%5B[SHORTNAME]%5D%20PUT%20SUBJECT%20HERE">www-style@w3.org</a> 
   (see <a href="http://www.w3.org/Mail/Request">instructions</a>) 
   is preferred for discussion of this specification. 
   When sending e-mail, please put the text
   “[SHORTNAME]” in the subject, preferably like this:
   “[<!---->[SHORTNAME]<!---->] <em>…summary of comment…</em>”

  <p>This document was produced by the <a
   href="http://www.w3.org/Style/CSS/members">CSS Working Group</a> (part of
   the <a href="http://www.w3.org/Style/">Style Activity</a>).

  <p>This document was produced by a group operating under the <a
   href="http://www.w3.org/Consortium/Patent-Policy-20040205/">5 February
   2004 W3C Patent Policy</a>. W3C maintains a <a
   href="http://www.w3.org/2004/01/pp-impl/32061/status"
   rel=disclosure>public list of any patent disclosures</a> made in
   connection with the deliverables of the group; that page also includes
   instructions for disclosing a patent. An individual who has actual
   knowledge of a patent which the individual believes contains <a
   href="http://www.w3.org/Consortium/Patent-Policy-20040205/#def-essential">Essential
   Claim(s)</a> must disclose the information in accordance with <a
   href="http://www.w3.org/Consortium/Patent-Policy-20040205/#sec-Disclosure">section
   6 of the W3C Patent Policy</a>.</p>
  <!--end-status-->

  <p>For changes since the last draft, see the <a href="#changes">Changes</a>
   section.
</div>"""
    else:
        die("Don't have a status section for {0} documents yet.".format(doc.status))
    if len(doc.atRisk):
        html += "<p>The following features are at risk:\n<ul>"
        for feature in doc.atRisk:
            html += "<li>"+feature
        html += "</ul>"
    html = replaceTextMacros(html)
    fillWith('status', parseHTML(html))



if __name__ == "__main__":
    main()
