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
    optparser.add_option("--login", dest="loginInfo",
                         help="W3C username/password combo, separated by a \
colon, like 'un:pw'.")
    optparser.add_option("--no-bert", dest="noBert", default=False, action="store_true",
                         help="Use this preprocessor only; \
don't run it through Bert's preprocessor afterwards.")
    (options, posargs) = optparser.parse_args()

    doc = CSSSpec(inputFilename=options.inputFile,
                  biblioFilename=options.biblioFile,
                  loginInfo=options.loginInfo)
    doc.preprocess()
    doc.finish(outputFilename=options.outputFile, noBert=options.noBert)


def die(msg):
    print "FATAL ERROR: "+msg
    sys.exit(1)


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
def processDataBlocks(doc):
    inBlock = False
    blockTypes = {
        'propdef': processPropdef,
        'metadata': processMetadata,
        'pre': processPre
    }
    blockType = ""
    tagName = ""
    startLine = 0
    replacements = []
    for (i, line) in enumerate(doc.lines):
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
        match = re.match("(.*)</"+tagName+">", line, re.I)
        if match and inBlock:
            inBlock = False
            if re.match("^\s*$", match.group(1)):
                # End tag was on a line by itself
                replacements.append({
                    'start': startLine,
                    'end': i+1,
                    'value': blockTypes[blockType](
                        lines=doc.lines[startLine+1:i],
                        tagName=tagName,
                        firstLine=doc.lines[startLine],
                        doc=doc)})
            else:
                # End tag was at the end of line of useful content.
                doc.lines[i] = match.group(1)
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


def processPre(lines, tagName, firstLine, **kwargs):
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


def processPropdef(lines, doc, **kwargs):
    ret = ["<table class='propdef'>"]
    for (i, line) in enumerate(lines):
        match = re.match("\s*([^:]+):\s*(.*)", line)
        key = match.group(1)
        val = match.group(2)
        if key == "Name":
            val = ', '.join("<dfn>"+x.strip()+"</dfn>" for x in val.split(","))
        if key == "Values":
            val = re.sub("<([^>]+)>", r"<a>&lt;\1></a>", val)
        ret.append("<tr><th>" + key + ":<td>" + val)
    ret.append("</table>")
    return ret


def processMetadata(lines, doc, **kwargs):
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
        elif key == "Abstract":
            doc.abstract = val
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
    return []


def fillInBoilerplate(doc):
    # I need some signal for whether or not to insert boilerplate,
    # to preserve the quality that you can run the processor over
    # an already-processed document as a no-op.
    # Arbitrarily, I choose to use whether the first line in the doc
    # is an <h1> with the document's title.

    if re.match("<h1>[^<]+</h1>", doc.lines[0]):
        doc.title = re.match("<h1>([^<]+)</h1>", doc.lines[0]).group(1)
        doc.lines = doc.lines[1:]

    header = """
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html lang="en">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">"""
    header += "<title>"+doc.title+"</title>"
    header += """   <link href="../default.css" rel=stylesheet type="text/css">
    <link href="../csslogo.ico" rel="shortcut icon" type="image/x-icon">"""
    header += '<link href="https://www.w3.org/StyleSheets/TR/W3C-'+doc.status+'.css" rel=stylesheet type="text/css">'
    header += """
</head>
<body>
<div class="head">
<!--logo-->
"""
    header += '<h1 id="title" class="no-ref">'+doc.title+'</h1>'
    header += '<h2 id="subtitle" class="no-num no-toc no-ref">[LONGSTATUS] [DATE]</h2>'
    header += generateHeaderDL(doc)
    header += """<!--copyright-->

<hr title="Separator for header">
</div>
<h2 class='no-num no-toc no-ref' id='abstract'>Abstract</h2>
<p>
"""
    header += doc.abstract
    header += """<h2 class='no-num no-toc no-ref' id='status'>Status of this document</h2>
    <!--status-->"""
    if doc.atRisk:
        header += "<p>The following features are at risk:\n<ul>"
        for feature in doc.atRisk:
            header += "<li>"+feature
        header += "</ul>"
    header += """<h2 class="no-num no-toc no-ref" id="contents">
Table of contents</h2>

<!--toc-->
"""
    footer = """

<h2 id="conformance" class="no-ref">
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
<div></div>

<h3 class="no-num no-ref" id="informative">
Informative References</h3>
<div></div>

<h2 class="no-num no-ref" id="index">
Index</h2>
<div></div>

<h2 class="no-num no-ref" id="property-index">
Property index</h2>
<div></div>

</body>
</html>
"""
    doc.lines.insert(0, header)
    doc.lines.append(footer)


def generateHeaderDL(doc):
    header = "<dl>"
    if doc.status != "ED" and doc.TR:
        header += "<dt>This version:\n<dd><a href='"+doc.TR+"'>"+doc.TR+"</a>\n"
    elif doc.status == "ED" and doc.ED:
        header += "<dt>This version:\n<dd><a href='"+doc.ED+"'>"+doc.ED+"</a>\n"
    else:
        header += "<dt>This version:\n<dd>???\n"
    if doc.TR:
        header += "<dt>Latest version:\n<dd><a href='"+doc.TR+"'>"+doc.TR+"</a>\n"
    if doc.ED:
        header += "<dt>Editor's Draft\n<dd><a href='"+doc.ED+"'>"+doc.ED+"</a>\n"
    if len(doc.previousVersions):
        header += "<dt>Previous Versions:" + ''.join(map("<dd><a href='{0}'>{0}</a>".format, doc.previousVersions))
    if len(doc.editors):
        header += "<dt>Editors:\n"
        for editor in doc.editors:
            header += "<dd class='hcard'>"
            if(editor['link'][0:4] == "http"):
                header += "<a class='fn url' href='{0}'>{1}</a> \
(<span class='org'>{2}</span>".format(
                    editor['link'],
                    editor['name'],
                    editor['org'])
            else:
                # Link is assumed to be an email address
                header += "<span class='fn'>{0}</span> \
(<span class='org'>{1}</span>), \
<a class='email' href='mailto:{2}'>{2}</a>".format(
                    editor['name'],
                    editor['org'],
                    editor['link'])
    else:
        header += "<dt>Editors:\n<dd>???\n"
    if len(doc.otherMetadata):
        for (key, vals) in doc.otherMetadata.items():
            header += "<dt>"+key+":\n"
            for val in vals:
                header += "<dd>"+val+"\n"
    header += "</dl>"
    return header


def transformBiblioLinks(doc):
    for i in range(len(doc.lines)):
        while re.search(r"\[\[(!?)([^\]]+)\]\]", doc.lines[i]):
            match = re.search(r"\[\[(!?)([^\]]+)\]\]", doc.lines[i])
            
            if match.group(2) not in doc.biblios:
                die("Couldn't find '{0}' in biblio database.".format(match.group(2)))
            biblioEntry = doc.biblios[match.group(2)]

            if match.group(1) == "!":
                biblioType = "normative"
                doc.normativeRefs.add(biblioEntry)
            else:
                biblioType = "informative"
                doc.informativeRefs.add(biblioEntry)
            
            doc.lines[i] = doc.lines[i].replace(
                match.group(0),
                "<a title='{0}' data-biblio-type='{1}'>[{0}]</a>".format(
                    match.group(2), 
                    biblioType,))


def addReferencesSection(doc):
    text = "<dl>"
    for ref in doc.normativeRefs:
        text += "<dt id='{0}' title='{0}'>[{0}]</dt>".format(ref.linkText)
        text += "<dd>"+str(ref)+"</dd>"
    text += "</dl>"
    CSSSelector("#normative + div")(doc.document)[0].append(etree.fromstring(text))
    text = "<dl>"
    for ref in doc.informativeRefs:
        text += "<dt id='{0}' title='{0}'>[{0}]</dt>".format(ref.linkText)
        text += "<dd>"+str(ref)+"</dd>"
    text += "</dl>"
    CSSSelector("#informative + div")(doc.document)[0].append(etree.fromstring(text))


def textContent(el):
    return etree.tostring(el, method='text', with_tail=False)


def genIdsForAutolinkTargets(doc):
    ids = set()
    linkTargets = CSSSelector("dfn, h1, h2, h3, h4, h5, h6")(doc.document)
    for el in linkTargets:
        if el.get('id') is not None:
            id = el.get('id')
            if id in ids:
                die("Found a duplicate explicitly-specified id:" + id)
        else:
            id = idFromText(textContent(el))
            if id in ids:
                # Try to de-dup the id by appending an integer after it.
                for x in range(10):
                    if (id+str(x)) not in ids:
                        id = id + str(x)
                        break
                else:
                    die("More than 10 link-targets with the same id, giving up: " + id)
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


def initializeAutolinkTargets(doc):
    links = {}
    linkTargets = CSSSelector("dfn, h1, h2, h3, h4, h5, h6, \
                              #normative + div dt, #informative + div dt")(doc.document)
    for el in linkTargets:
        if not re.search("no-ref", el.get('class') or ""):
            if el.get("title") is not None:
                linkTexts = [x.strip() for x in el.get("title").split("|")]
            else:
                linkTexts = [autolinkTitleFromText(textContent(el))]
            for linkText in linkTexts:
                if linkText in links:
                    die("Two link-targets have the same linking text: " + linkText)
                else:
                    links[linkText] = el.get('id')
    doc.links = links


def autolinkTitleFromText(str):
    return str.strip().lower()


def processAutolinks(doc):
    autolinks = CSSSelector("a:not([href])")(doc.document)
    for el in autolinks:
        if el.get('title') is not None:
            if el.get('title') == '':
                break
            linkText = el.get('title')
        else:
            linkText = textContent(el).lower()

        for variation in linkTextVariations(linkText):
            if variation in doc.links:
                el.set('href', '#'+doc.links[variation])
                break
        else:
            die("Couldn't link up a ref: " + etree.tostring(el, with_tail=False))


def linkTextVariations(str):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding a title attr isn't usually necessary.
    yield str

    if str[-3:] == "ies":
        yield str[:-3]+"y"
    elif str[-2:] == "'s":
        yield str[:-2]
    elif str[-1] == "s":
        yield str[:-1]


class CSSSpec(object):
    title = "???"
    status = "???"
    TR = "???"
    ED = "???"
    editors = []
    previousVersions = []
    abstract = "???"
    atRisk = []
    otherMetadata = defaultdict(list)
    lines = []
    document = None
    ids = set()
    links = {}
    biblios = {}
    normativeRefs = set()
    informativeRefs = set()
    loginInfo = None

    def __init__(self, inputFilename, biblioFilename=None, loginInfo=None):
        self.loginInfo = loginInfo

        try:
            self.lines = open(inputFilename, 'r').readlines()
        except OSError:
            die("Couldn't find the input file at the specified location \""+inputFilename+"\".")

        if biblioFilename:
            try:
                biblioFile = open(biblioFilename, 'r')
            except OSError:
                die("Couldn't find the biblio file at the specified location \""+inputFilename+"\".")
        else:
            try:
                biblioFile = urlopen("https://www.w3.org/Style/Group/css3-src/biblio.ref")
            except:
                die("Something prevented me from retrieving the bibliography file.")
        self.biblios = processReferBiblioFile(biblioFile)

    def preprocess(self):
        # Textual hacks
        processDataBlocks(self)
        transformMarkdownParagraphs(self)
        fillInBoilerplate(self)
        transformBiblioLinks(self)

        # Build the document
        self.document = html5lib.parse(
            ''.join(self.lines),
            treebuilder='lxml',
            namespaceHTMLElements=False)
        addReferencesSection(self)

        # All the linking.
        genIdsForAutolinkTargets(self)
        initializeAutolinkTargets(self)
        processAutolinks(self)

        return self

    def finish(self, outputFilename, noBert=False):
        if noBert:
            try:
                open(outputFilename, mode='w').write(html.tostring(self.document))
            except:
                die("Something prevented me from saving the output document.")
        else:
            try:
                outputFile = open("~temp-generated-source.html", mode='w')
            except:
                die("Something prevented me from writing out a temp file in this directory.")
            else:
                outputFile.write(html.tostring(self.document))
                outputFile.close()

            try:
                if self.loginInfo:
                    credentials = "-u " + self.loginInfo
                else:
                    credentials = "-n"
                subprocess.call("curl -# " + credentials + " \
                    -F file=@~temp-generated-source.html \
                    -F group=CSS \
                    -F output=html \
                    -F method=file \
                    https://www.w3.org/Style/Group/process.cgi \
                    -o "+outputFilename,
                                shell=True)
            except subprocess.CalledProcessError as e:
                print "Some error occurred in the curl call."
                print "Error code ", e.returncode
                print "Error message:"
                print e.output
                sys.exit(1)
            else:
                os.remove("~temp-generated-source.html")


class BiblioEntry(object):
    linkText = None
    title = None
    authors = []
    foreignAuthors = []
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


if __name__ == "__main__":
    main()
