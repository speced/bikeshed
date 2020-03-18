# -*- coding: utf-8 -*-


import glob
import io
import sys
import os
from collections import defaultdict, OrderedDict
from datetime import datetime

from . import biblio
from . import boilerplate
from . import caniuse
from . import config
from . import constants
from . import datablocks
from . import extensions
from . import fingerprinting
from . import headings
from . import highlight
from . import HTMLSerializer
from . import idl
from . import includes
from . import inlineTags
from . import lint
from . import markdown
from . import metadata
from . import shorthands
from . import wpt

from .htmlhelpers import *
from .Line import Line
from .messages import *
from .refs import ReferenceManager
from .unsortedJunk import *

class Spec(object):

    def __init__(self, inputFilename, debug=False, token=None, lineNumbers=False, fileRequester=None, testing=False):
        self.valid = False
        self.lineNumbers = lineNumbers
        if lineNumbers:
            # line-numbers are too hacky, so force this to be a dry run
            constants.dryRun = True
        if inputFilename is None:
            inputFilename = findImplicitInputFile()
        if inputFilename is None: # still
            die("No input file specified, and no *.bs or *.src.html files found in current directory.\nPlease specify an input file, or use - to pipe from STDIN.")
            return
        self.inputSource = inputFilename
        self.debug = debug
        self.token = token
        self.testing = testing
        if fileRequester is None:
            self.dataFile = config.defaultRequester
        else:
            self.dataFile = fileRequester

        self.valid = self.initializeState()

    def initializeState(self):
        self.normativeRefs = {}
        self.informativeRefs = {}
        self.refs = ReferenceManager(fileRequester=self.dataFile, testing=self.testing)
        self.externalRefsUsed = defaultdict(lambda:defaultdict(dict))
        self.md = None
        self.mdBaseline = metadata.MetadataManager()
        self.mdDocument = None
        self.mdCommandLine = metadata.MetadataManager()
        self.mdDefaults = None
        self.mdOverridingDefaults = None
        self.biblios = {}
        self.typeExpansions = {}
        self.macros = defaultdict(lambda x: "???")
        self.canIUse = {}
        self.widl = idl.getParser()
        self.testSuites = json.loads(self.dataFile.fetch("test-suites.json", str=True))
        self.languages = json.loads(self.dataFile.fetch("languages.json", str=True))
        self.extraStyles = defaultdict(str)
        self.extraStyles['style-md-lists'] = styleMdLists
        self.extraStyles['style-autolinks'] = styleAutolinks
        self.extraStyles['style-selflinks'] = styleSelflinks
        self.extraStyles['style-counters'] = styleCounters
        self.extraScripts = defaultdict(str)

        try:
            if self.inputSource == "-":
                self.lines = [Line(i,line) for i,line in enumerate(sys.stdin.readlines(), 1)]
            else:
                self.lines = [Line(i,l) for i,l in enumerate(io.open(self.inputSource, 'r', encoding="utf-8").readlines(), 1)]
                # Initialize date to the last-modified date on the file,
                # so processing repeatedly over time doesn't cause spurious date-only changes.
                self.mdBaseline.addParsedData("Date", datetime.fromtimestamp(os.path.getmtime(self.inputSource)).date())
        except OSError:
            die("Couldn't find the input file at the specified location '{0}'.", self.inputSource)
            return False
        except IOError:
            die("Couldn't open the input file '{0}'.", self.inputSource)
            return False

        return True

    def preprocess(self):
        self.assembleDocument()
        self.processDocument()
        return self

    def assembleDocument(self):
        # Textual hacks
        stripBOM(self)
        if self.lineNumbers:
            self.lines = hackyLineNumbers(self.lines)
        self.lines = markdown.stripComments(self.lines)
        # Extract and process metadata
        self.lines, self.mdDocument = metadata.parse(lines=self.lines)
        # First load the metadata sources from 'local' data
        self.md = metadata.join(self.mdBaseline, self.mdDocument, self.mdCommandLine)
        # Using that to determine the Group and Status, load the correct defaults.include boilerplate
        self.mdDefaults = metadata.fromJson(data=config.retrieveBoilerplateFile(self, 'defaults', error=True), source="defaults")
        self.md = metadata.join(self.mdBaseline, self.mdDefaults, self.mdDocument, self.mdCommandLine)
        # Using all of that, load up the text macros so I can sub them into the computed-metadata file.
        self.md.fillTextMacros(self.macros, doc=self)
        jsonEscapedMacros = {k: json.dumps(v)[1:-1] for k,v in self.macros.items()}
        computedMdText = replaceMacros(config.retrieveBoilerplateFile(self, 'computed-metadata', error=True), macros=jsonEscapedMacros)
        self.mdOverridingDefaults = metadata.fromJson(data=computedMdText, source="computed-metadata")
        self.md = metadata.join(self.mdBaseline, self.mdDefaults, self.mdOverridingDefaults, self.mdDocument, self.mdCommandLine)
        # Finally, compute the "implicit" things.
        self.md.computeImplicitMetadata(doc=self)
        # And compute macros again, in case the preceding steps changed them.
        self.md.fillTextMacros(self.macros, doc=self)
        self.md.validate()
        extensions.load(self)

        # Initialize things
        self.refs.initializeRefs(self)
        self.refs.initializeBiblio()

        # Deal with further <pre> blocks, and markdown
        self.lines = datablocks.transformDataBlocks(self, self.lines)
        self.lines = markdown.parse(self.lines, self.md.indent, opaqueElements=self.md.opaqueElements, blockElements=self.md.blockElements)
        # Note that, currently, markdown.parse returns an array of strings, not of Line objects.

        self.refs.setSpecData(self.md)

        # Convert to a single string of html now, for convenience.
        self.html = ''.join(l.text for l in self.lines)
        boilerplate.addHeaderFooter(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = parseDocument(self.html)
        self.head = find("head", self)
        self.body = find("body", self)
        correctH1(self)
        includes.processInclusions(self)
        metadata.parseDoc(self)
        return self

    def processDocument(self):
        # Fill in and clean up a bunch of data
        self.fillContainers = locateFillContainers(self)
        lint.exampleIDs(self)
        boilerplate.addBikeshedVersion(self)
        boilerplate.addCanonicalURL(self)
        boilerplate.addFavicon(self)
        boilerplate.addSpecVersion(self)
        boilerplate.addStatusSection(self)
        boilerplate.addLogo(self)
        boilerplate.addCopyright(self)
        boilerplate.addSpecMetadataSection(self)
        boilerplate.addAbstract(self)
        boilerplate.addObsoletionNotice(self)
        boilerplate.addAtRisk(self)
        addNoteHeaders(self)
        boilerplate.removeUnwantedBoilerplate(self)
        shorthands.transformShorthandElements(self)
        shorthands.transformProductionPlaceholders(self)
        shorthands.transformMaybePlaceholders(self)
        shorthands.transformAutolinkShortcuts(self)
        shorthands.transformProductionGrammars(self)
        inlineTags.processTags(self)
        canonicalizeShortcuts(self)
        addImplicitAlgorithms(self)
        fixManualDefTables(self)
        headings.processHeadings(self)
        checkVarHygiene(self)
        processIssuesAndExamples(self)
        idl.markupIDL(self)
        inlineRemoteIssues(self)
        wpt.processWptElements(self)

        # Handle all the links
        processBiblioLinks(self)
        processDfns(self)
        idl.processIDL(self)
        fillAttributeInfoSpans(self)
        formatArgumentdefTables(self)
        formatElementdefTables(self)
        processAutolinks(self)
        biblio.dedupBiblioReferences(self)
        verifyUsageOfAllLocalBiblios(self)
        caniuse.addCanIUsePanels(self)
        boilerplate.addIndexSection(self)
        boilerplate.addExplicitIndexes(self)
        boilerplate.addStyles(self)
        boilerplate.addReferencesSection(self)
        boilerplate.addPropertyIndex(self)
        boilerplate.addIDLSection(self)
        boilerplate.addIssuesSection(self)
        boilerplate.addCustomBoilerplate(self)
        headings.processHeadings(self, "all")  # again
        boilerplate.removeUnwantedBoilerplate(self)
        boilerplate.addTOCSection(self)
        addSelfLinks(self)
        processAutolinks(self)
        boilerplate.addAnnotations(self)
        boilerplate.removeUnwantedBoilerplate(self)
        highlight.addSyntaxHighlighting(self)
        boilerplate.addBikeshedBoilerplate(self)
        fingerprinting.addTrackingVector(self)
        fixIntraDocumentReferences(self)
        fixInterDocumentReferences(self)
        removeMultipleLinks(self)
        forceCrossorigin(self)
        lint.brokenLinks(self)
        lint.accidental2119(self)
        lint.missingExposed(self)
        lint.requiredIDs(self)
        lint.unusedInternalDfns(self)

        # Any final HTML cleanups
        cleanupHTML(self)
        if self.md.prepTR:
            # Don't try and override the W3C's icon.
            for el in findAll("[rel ~= 'icon']", self):
                removeNode(el)
            # Make sure the W3C stylesheet is after all other styles.
            for el in findAll("link", self):
                if el.get("href").startswith("https://www.w3.org/StyleSheets/TR"):
                    appendChild(find("head", self), el)
            # Ensure that all W3C links are https.
            for el in findAll("a", self):
                href = el.get("href", "")
                if href.startswith("http://www.w3.org") or href.startswith("http://lists.w3.org"):
                    el.set("href", "https" + href[4:])
                text = el.text or ""
                if text.startswith("http://www.w3.org") or text.startswith("http://lists.w3.org"):
                    el.text = "https" + text[4:]
            extensions.BSPrepTR(self)

        return self

    def serialize(self):
        rendered = HTMLSerializer.HTMLSerializer(self.document, self.md.opaqueElements, self.md.blockElements).serialize()
        rendered = finalHackyCleanup(rendered)
        return rendered

    def fixMissingOutputFilename(self, outputFilename):
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
        return outputFilename

    def finish(self, outputFilename=None):
        self.printResultMessage()
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        rendered = self.serialize()
        if not constants.dryRun:
            try:
                if outputFilename == "-":
                    sys.stdout.write(rendered.encode("utf-8"))
                else:
                    with io.open(outputFilename, "w", encoding="utf-8") as f:
                        f.write(rendered)
            except Exception as e:
                die("Something prevented me from saving the output document to {0}:\n{1}", outputFilename, e)

    def printResultMessage(self):
        # If I reach this point, I've succeeded, but maybe with reservations.
        fatals = messageCounts['fatal']
        links = messageCounts['linkerror']
        warnings = messageCounts['warning']
        if self.lineNumbers:
            warn("Because --line-numbers was used, no output was saved.")
        if fatals:
            success("Successfully generated, but fatal errors were suppressed")
            return
        if links:
            success("Successfully generated, with {0} linking errors", links)
            return
        if warnings:
            success("Successfully generated, with warnings")
            return

    def watch(self, outputFilename, port=None, localhost=False):
        import time
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        if self.inputSource == "-" or outputFilename == "-":
            die("Watch mode doesn't support streaming from STDIN or to STDOUT.")
            return

        if port:
            # Serve the folder on an HTTP server
            import http.server
            import socketserver
            import threading

            class SilentServer(http.server.SimpleHTTPRequestHandler):
                def log_message(*args):
                    pass

            socketserver.TCPServer.allow_reuse_address = True
            server = socketserver.TCPServer(
              ("localhost" if localhost else "", port), SilentServer)

            print("Serving at port {0}".format(port))
            thread = threading.Thread(target = server.serve_forever)
            thread.daemon = True
            thread.start()
        else:
            server = None

        mdCommandLine = self.mdCommandLine

        try:
            lastInputModified = os.stat(self.inputSource).st_mtime
            self.preprocess()
            self.finish(outputFilename)
            p("==============DONE==============")
            try:
                while(True):
                    inputModified = os.stat(self.inputSource).st_mtime
                    if inputModified > lastInputModified:
                        resetSeenMessages()
                        lastInputModified = inputModified
                        formattedTime = datetime.fromtimestamp(inputModified).strftime("%H:%M:%S")
                        p("Source file modified at {0}. Rebuilding...".format(formattedTime))
                        self.initializeState()
                        self.mdCommandLine = mdCommandLine
                        self.preprocess()
                        self.finish(outputFilename)
                        p("==============DONE==============")
                    time.sleep(1)
            except KeyboardInterrupt:
                p("Exiting~")
                if server:
                    server.shutdown()
                    thread.join()
                sys.exit(0)
        except Exception as e:
            die("Something went wrong while watching the file:\n{0}", e)

    def fixText(self, text, moreMacros={}):
        # Do several textual replacements that need to happen *before* the document is parsed as HTML.

        # If markdown shorthands are on, remove all `foo`s while processing,
        # so their contents don't accidentally trigger other stuff.
        # Also handle markdown escapes.
        if "markdown" in self.md.markupShorthands:
            textFunctor = MarkdownCodeSpans(text)
        else:
            textFunctor = func.Functor(text)

        macros = dict(self.macros, **moreMacros)
        textFunctor = textFunctor.map(curry(replaceMacros, macros=macros))
        textFunctor = textFunctor.map(fixTypography)
        if "css" in self.md.markupShorthands:
            textFunctor = textFunctor.map(replaceAwkwardCSSShorthands)

        return textFunctor.extract()

    def printTargets(self):
        p("Exported terms:")
        for el in findAll("[data-export]", self):
            for term in config.linkTextsFromElement(el):
                p("  " + term)
        p("Unexported terms:")
        for el in findAll("[data-noexport]", self):
            for term in config.linkTextsFromElement(el):
                p("  " + term)

    def isOpaqueElement(self, el):
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("data-opaque") is not None:
            return True
        return False

def findImplicitInputFile():
    '''
    Find what input file the user *probably* wants to use,
    by scanning the current folder.
    In preference order:
    1. index.bs
    2. Overview.bs
    3. the first file with a .bs extension
    4. the first file with a .src.html extension
    '''
    import glob
    import os
    if os.path.isfile("index.bs"):
        return "index.bs"
    if os.path.isfile("Overview.bs"):
        return "Overview.bs"

    allBs = glob.glob("*.bs")
    if allBs:
        return allBs[0]

    allHtml = glob.glob("*.src.html")
    if allHtml:
        return allHtml[0]

    return None

constants.specClass = Spec

styleMdLists = '''
/* This is a weird hack for me not yet following the commonmark spec
   regarding paragraph and lists. */
[data-md] > :first-child {
    margin-top: 0;
}
[data-md] > :last-child {
    margin-bottom: 0;
}'''

styleAutolinks = '''
.css.css, .property.property, .descriptor.descriptor {
    color: #005a9c;
    font-size: inherit;
    font-family: inherit;
}
.css::before, .property::before, .descriptor::before {
    content: "‘";
}
.css::after, .property::after, .descriptor::after {
    content: "’";
}
.property, .descriptor {
    /* Don't wrap property and descriptor names */
    white-space: nowrap;
}
.type { /* CSS value <type> */
    font-style: italic;
}
pre .property::before, pre .property::after {
    content: "";
}
[data-link-type="property"]::before,
[data-link-type="propdesc"]::before,
[data-link-type="descriptor"]::before,
[data-link-type="value"]::before,
[data-link-type="function"]::before,
[data-link-type="at-rule"]::before,
[data-link-type="selector"]::before,
[data-link-type="maybe"]::before {
    content: "‘";
}
[data-link-type="property"]::after,
[data-link-type="propdesc"]::after,
[data-link-type="descriptor"]::after,
[data-link-type="value"]::after,
[data-link-type="function"]::after,
[data-link-type="at-rule"]::after,
[data-link-type="selector"]::after,
[data-link-type="maybe"]::after {
    content: "’";
}

[data-link-type].production::before,
[data-link-type].production::after,
.prod [data-link-type]::before,
.prod [data-link-type]::after {
    content: "";
}

[data-link-type=element],
[data-link-type=element-attr] {
    font-family: Menlo, Consolas, "DejaVu Sans Mono", monospace;
    font-size: .9em;
}
[data-link-type=element]::before { content: "<" }
[data-link-type=element]::after  { content: ">" }

[data-link-type=biblio] {
    white-space: pre;
}'''

styleSelflinks = '''
.heading, .issue, .note, .example, li, dt {
    position: relative;
}
a.self-link {
    position: absolute;
    top: 0;
    left: calc(-1 * (3.5rem - 26px));
    width: calc(3.5rem - 26px);
    height: 2em;
    text-align: center;
    border: none;
    transition: opacity .2s;
    opacity: .5;
}
a.self-link:hover {
    opacity: 1;
}
.heading > a.self-link {
    font-size: 83%;
}
li > a.self-link {
    left: calc(-1 * (3.5rem - 26px) - 2em);
}
dfn > a.self-link {
    top: auto;
    left: auto;
    opacity: 0;
    width: 1.5em;
    height: 1.5em;
    background: gray;
    color: white;
    font-style: normal;
    transition: opacity .2s, background-color .2s, color .2s;
}
dfn:hover > a.self-link {
    opacity: 1;
}
dfn > a.self-link:hover {
    color: black;
}

a.self-link::before            { content: "¶"; }
.heading > a.self-link::before { content: "§"; }
dfn > a.self-link::before      { content: "#"; }'''

styleCounters = '''
body {
    counter-reset: example figure issue;
}
.issue {
    counter-increment: issue;
}
.issue:not(.no-marker)::before {
    content: "Issue " counter(issue);
}

.example {
    counter-increment: example;
}
.example:not(.no-marker)::before {
    content: "Example " counter(example);
}
.invalid.example:not(.no-marker)::before,
.illegal.example:not(.no-marker)::before {
    content: "Invalid Example" counter(example);
}

figcaption {
    counter-increment: figure;
}
figcaption:not(.no-marker)::before {
    content: "Figure " counter(figure) " ";
}'''
