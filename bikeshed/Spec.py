import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from functools import partial as curry

from . import (
    biblio,
    boilerplate,
    caniuse,
    conditional,
    config,
    constants,
    datablocks,
    dfns,
    extensions,
    fingerprinting,
    func,
    h,
    headings,
    highlight,
    idl,
    includes,
    inlineTags,
    InputSource,
    lint,
    markdown,
    mdnspeclinks,
    messages as m,
    metadata,
    refs,
    retrieve,
    shorthands,
    unsortedJunk as u,
    wpt,
)


class Spec:
    def __init__(
        self,
        inputFilename,
        debug=False,
        token=None,
        lineNumbers=False,
        fileRequester=None,
        testing=False,
    ):
        catchArgparseBug(inputFilename)
        self.valid = False
        self.lineNumbers = lineNumbers
        if lineNumbers:
            # line-numbers are too hacky, so force this to be a dry run
            constants.dryRun = True
        if inputFilename is None:
            inputFilename = findImplicitInputFile()
        if inputFilename is None:  # still
            m.die(
                "No input file specified, and no *.bs or *.src.html files found in current directory.\nPlease specify an input file, or use - to pipe from STDIN."
            )
            return
        self.inputSource = InputSource.InputSource(inputFilename, chroot=constants.chroot)
        self.transitiveDependencies = set()
        self.debug = debug
        self.token = token
        self.testing = testing
        if fileRequester is None:
            self.dataFile = retrieve.defaultRequester
        else:
            self.dataFile = fileRequester

        self.md = None
        self.mdBaseline = None
        self.mdDocument = None
        self.mdCommandLine = None
        self.mdDefaults = None
        self.mdOverridingDefaults = None
        self.lines = []
        self.document = None
        self.html = None
        self.head = None
        self.body = None
        self.fillContainers = None
        self.valid = self.initializeState()

    def initializeState(self):
        self.normativeRefs = {}
        self.informativeRefs = {}
        self.refs = refs.ReferenceManager(fileRequester=self.dataFile, testing=self.testing)
        self.externalRefsUsed = defaultdict(lambda: defaultdict(dict))
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
        self.mdnSpecLinks = {}
        self.widl = idl.getParser()
        self.testSuites = json.loads(self.dataFile.fetch("test-suites.json", str=True))
        self.languages = json.loads(self.dataFile.fetch("languages.json", str=True))
        self.extraStyles = defaultdict(str)
        self.extraStyles["style-colors"] = styleColors
        self.extraStyles["style-darkmode"] = styleDarkMode
        self.extraStyles["style-md-lists"] = styleMdLists
        self.extraStyles["style-autolinks"] = styleAutolinks
        self.extraStyles["style-selflinks"] = styleSelflinks
        self.extraStyles["style-counters"] = styleCounters
        self.extraStyles["style-issues"] = styleIssues
        self.extraScripts = defaultdict(str)

        try:
            inputContent = self.inputSource.read()
            self.lines = inputContent.lines
            if inputContent.date is not None:
                self.mdBaseline.addParsedData("Date", inputContent.date)
        except FileNotFoundError:
            m.die(f"Couldn't find the input file at the specified location '{self.inputSource}'.")
            return False
        except OSError:
            m.die(f"Couldn't open the input file '{self.inputSource}'.")
            return False

        return True

    def recordDependencies(self, *inputSources):
        self.transitiveDependencies.update(inputSources)

    def preprocess(self):
        self.transitiveDependencies.clear()
        self.assembleDocument()
        self.processDocument()

    def assembleDocument(self):
        # Textual hacks
        u.stripBOM(self)
        if self.lineNumbers:
            self.lines = u.hackyLineNumbers(self.lines)
        self.lines = markdown.stripComments(self.lines)
        self.recordDependencies(self.inputSource)
        # Extract and process metadata
        self.lines, self.mdDocument = metadata.parse(lines=self.lines)
        # First load the metadata sources from 'local' data
        self.md = metadata.join(self.mdBaseline, self.mdDocument, self.mdCommandLine)
        # Using that to determine the Group and Status, load the correct defaults.include boilerplate
        self.mdDefaults = metadata.fromJson(
            data=retrieve.retrieveBoilerplateFile(self, "defaults", error=True),
            source="defaults",
        )
        self.md = metadata.join(self.mdBaseline, self.mdDefaults, self.mdDocument, self.mdCommandLine)
        # Using all of that, load up the text macros so I can sub them into the computed-metadata file.
        self.md.fillTextMacros(self.macros, doc=self)
        jsonEscapedMacros = {k: json.dumps(v)[1:-1] for k, v in self.macros.items()}
        computedMdText = h.replaceMacros(
            retrieve.retrieveBoilerplateFile(self, "computed-metadata", error=True),
            macros=jsonEscapedMacros,
        )
        self.mdOverridingDefaults = metadata.fromJson(data=computedMdText, source="computed-metadata")
        self.md = metadata.join(
            self.mdBaseline,
            self.mdDefaults,
            self.mdOverridingDefaults,
            self.mdDocument,
            self.mdCommandLine,
        )
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
        self.lines = markdown.parse(
            self.lines,
            self.md.indent,
            opaqueElements=self.md.opaqueElements,
            blockElements=self.md.blockElements,
        )

        self.refs.setSpecData(self.md)

        # Convert to a single string of html now, for convenience.
        self.html = "".join(line.text for line in self.lines)
        boilerplate.addHeaderFooter(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = h.parseDocument(self.html)
        self.head = h.find("head", self)
        self.body = h.find("body", self)
        u.correctFrontMatter(self)
        includes.processInclusions(self)
        metadata.parseDoc(self)

    def processDocument(self):
        # Fill in and clean up a bunch of data
        conditional.processConditionals(self)
        self.fillContainers = u.locateFillContainers(self)
        lint.exampleIDs(self)
        wpt.processWptElements(self)

        boilerplate.addBikeshedVersion(self)
        boilerplate.addCanonicalURL(self)
        boilerplate.addFavicon(self)
        boilerplate.addSpecVersion(self)
        boilerplate.addStatusSection(self)
        boilerplate.addLogo(self)
        boilerplate.addCopyright(self)
        boilerplate.addSpecMetadataSection(self)
        boilerplate.addAbstract(self)
        boilerplate.addExpiryNotice(self)
        boilerplate.addObsoletionNotice(self)
        boilerplate.addAtRisk(self)
        u.addNoteHeaders(self)
        boilerplate.removeUnwantedBoilerplate(self)
        shorthands.run(self)
        inlineTags.processTags(self)
        u.canonicalizeShortcuts(self)
        u.addImplicitAlgorithms(self)
        u.fixManualDefTables(self)
        headings.processHeadings(self)
        u.checkVarHygiene(self)
        u.processIssuesAndExamples(self)
        idl.markupIDL(self)
        u.inlineRemoteIssues(self)
        u.addImageSize(self)

        # Handle all the links
        u.processBiblioLinks(self)
        u.processDfns(self)
        u.processIDL(self)
        dfns.annotateDfns(self)
        u.formatArgumentdefTables(self)
        u.formatElementdefTables(self)
        u.processAutolinks(self)
        biblio.dedupBiblioReferences(self)
        u.verifyUsageOfAllLocalBiblios(self)
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
        u.addSelfLinks(self)
        u.processAutolinks(self)
        boilerplate.addAnnotations(self)
        boilerplate.removeUnwantedBoilerplate(self)
        # Add MDN panels after all IDs/anchors have been added
        mdnspeclinks.addMdnPanels(self)
        highlight.addSyntaxHighlighting(self)
        boilerplate.addBikeshedBoilerplate(self)
        fingerprinting.addTrackingVector(self)
        u.fixIntraDocumentReferences(self)
        u.fixInterDocumentReferences(self)
        u.removeMultipleLinks(self)
        u.forceCrossorigin(self)
        lint.brokenLinks(self)
        lint.accidental2119(self)
        lint.missingExposed(self)
        lint.requiredIDs(self)
        lint.unusedInternalDfns(self)

        # Any final HTML cleanups
        u.cleanupHTML(self)
        if self.md.prepTR:
            # Don't try and override the W3C's icon.
            for el in h.findAll("[rel ~= 'icon']", self):
                h.removeNode(el)
            # Make sure the W3C stylesheet is after all other styles.
            for el in h.findAll("link", self):
                if el.get("href").startswith("https://www.w3.org/StyleSheets/TR"):
                    h.appendChild(h.find("head", self), el)
            # Ensure that all W3C links are https.
            for el in h.findAll("a", self):
                href = el.get("href", "")
                if href.startswith("http://www.w3.org") or href.startswith("http://lists.w3.org"):
                    el.set("href", "https" + href[4:])
                text = el.text or ""
                if text.startswith("http://www.w3.org") or text.startswith("http://lists.w3.org"):
                    el.text = "https" + text[4:]
            # Loaded from .include files
            extensions.BSPrepTR(self)  # pylint: disable=no-member

        return self

    def serialize(self):
        try:
            rendered = h.Serializer(self.md.opaqueElements, self.md.blockElements).serialize(self.document)
        except Exception as e:
            m.die(str(e))
            return
        rendered = u.finalHackyCleanup(rendered)
        return rendered

    def fixMissingOutputFilename(self, outputFilename):
        if outputFilename is None:
            # More sensible defaults!
            if not isinstance(self.inputSource, InputSource.FileInputSource):
                outputFilename = "-"
            elif self.inputSource.sourceName.endswith(".bs"):
                outputFilename = self.inputSource.sourceName[0:-3] + ".html"
            elif self.inputSource.sourceName.endswith(".src.html"):
                outputFilename = self.inputSource.sourceName[0:-9] + ".html"
            else:
                outputFilename = "-"
        return outputFilename

    def finish(self, outputFilename=None, newline=None):
        catchArgparseBug(outputFilename)
        self.printResultMessage()
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        rendered = self.serialize()
        if not constants.dryRun:
            try:
                if outputFilename == "-":
                    sys.stdout.write(rendered)
                else:
                    with open(outputFilename, "w", encoding="utf-8", newline=newline) as f:
                        f.write(rendered)
            except Exception as e:
                m.die(f"Something prevented me from saving the output document to {outputFilename}:\n{e}")

    def printResultMessage(self):
        # If I reach this point, I've succeeded, but maybe with reservations.
        fatals = m.messageCounts["fatal"]
        links = m.messageCounts["linkerror"]
        warnings = m.messageCounts["warning"]
        if self.lineNumbers:
            m.warn("Because --line-numbers was used, no output was saved.")
        if fatals:
            m.success("Successfully generated, but fatal errors were suppressed")
            return
        if links:
            m.success(f"Successfully generated, with {links} linking errors")
            return
        if warnings:
            m.success("Successfully generated, with warnings")
            return

    def watch(self, outputFilename, port=None, localhost=False):
        import time

        outputFilename = self.fixMissingOutputFilename(outputFilename)
        if self.inputSource.mtime() is None:
            m.die(f"Watch mode doesn't support {self.inputSource}")
        if outputFilename == "-":
            m.die("Watch mode doesn't support streaming to STDOUT.")
            return

        if port:
            # Serve the folder on an HTTP server
            import http.server
            import socketserver
            import threading

            class SilentServer(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format, *args):
                    pass

            socketserver.TCPServer.allow_reuse_address = True
            server = socketserver.TCPServer(("localhost" if localhost else "", port), SilentServer)

            print(f"Serving at port {port}")
            thread = threading.Thread(target=server.serve_forever)
            thread.daemon = True
            thread.start()
        else:
            server = None

        mdCommandLine = self.mdCommandLine

        try:
            self.preprocess()
            self.finish(outputFilename)
            lastInputModified = {dep: dep.mtime() for dep in self.transitiveDependencies}
            printDone()
            try:
                while True:
                    # Comparing mtimes with "!=" handles when a file starts or
                    # stops existing, and it's fine to rebuild if an mtime
                    # somehow gets older.
                    if any(input.mtime() != lastModified for input, lastModified in lastInputModified.items()):
                        m.resetSeenMessages()
                        m.p("\nSource file modified. Rebuilding...")
                        self.initializeState()
                        self.mdCommandLine = mdCommandLine
                        self.preprocess()
                        self.finish(outputFilename)
                        lastInputModified = {dep: dep.mtime() for dep in self.transitiveDependencies}
                        printDone()
                    time.sleep(1)
            except KeyboardInterrupt:
                m.p("Exiting~")
                if server:
                    server.shutdown()
                    thread.join()
                sys.exit(0)
        except Exception as e:
            m.die(f"Something went wrong while watching the file:\n{e}")

    def fixText(self, text, moreMacros=None):
        # Do several textual replacements that need to happen *before* the document is parsed as h.

        # If markdown shorthands are on, remove all `foo`s while processing,
        # so their contents don't accidentally trigger other stuff.
        # Also handle markdown escapes.
        if moreMacros is None:
            moreMacros = {}
        if "markdown" in self.md.markupShorthands:
            textFunctor = u.MarkdownCodeSpans(text)
        else:
            textFunctor = func.Functor(text)

        macros = dict(self.macros, **moreMacros)
        textFunctor = textFunctor.map(curry(h.replaceMacros, macros=macros))
        textFunctor = textFunctor.map(h.fixTypography)
        if "css" in self.md.markupShorthands:
            textFunctor = textFunctor.map(h.replaceAwkwardCSSShorthands)

        return textFunctor.extract()

    def printTargets(self):
        m.p("Exported terms:")
        for el in h.findAll("[data-export]", self):
            for term in config.linkTextsFromElement(el):
                m.p("  " + term)
        m.p("Unexported terms:")
        for el in h.findAll("[data-noexport]", self):
            for term in config.linkTextsFromElement(el):
                m.p("  " + term)

    def isOpaqueElement(self, el):
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("data-opaque") is not None:
            return True
        return False


def printDone():
    contents = f"Finished at {datetime.now().strftime('%H:%M:%S %b-%d-%Y')}"
    contentLen = len(contents) + 2
    if not constants.asciiOnly:
        m.p(f"╭{'─'*contentLen}╮")
        m.p(f"│ {contents} │")
        m.p(f"╰{'─'*contentLen}╯")
        m.p("")
    else:
        m.p(f"/{'-'*contentLen}\\")
        m.p(f"| {contents} |")
        m.p(f"\\{'-'*contentLen}/")
        m.p("")


def findImplicitInputFile():
    """
    Find what input file the user *probably* wants to use,
    by scanning the current folder.
    In preference order:
    1. index.bs
    2. Overview.bs
    3. the first file with a .bs extension
    4. the first file with a .src.html extension
    """

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


def catchArgparseBug(string):
    # Argparse has had a long-standing bug
    # https://bugs.python.org/issue22433
    # about spaces in the values of unknown optional arguments
    # (even when the space is in a quoted string!).
    # I can't fix this without doing a lot of work myself,
    # but I *can* discover when it has been tripped,
    # as the input or output filename will look like
    # a command-line flag, very unlikely on its own.

    if isinstance(string, str) and string.startswith("--") and "=" in string:
        m.die(
            "You're hitting a bug with Python's argparse library. Please specify both the input and output filenames manually, and move all command-line flags with spaces in their values to after those arguments.\nSee <https://tabatkins.github.io/bikeshed/#md-issues> for details."
        )
        return False
    return True


styleColors = """
/* Any --*-text not paired with a --*-bg is assumed to have a transparent bg */
:root {
    color-scheme: light dark;

    --text: black;
    --bg: white;

    --unofficial-watermark: url(https://www.w3.org/StyleSheets/TR/2016/logos/UD-watermark);

    --logo-bg: #1a5e9a;
    --logo-active-bg: #c00;
    --logo-text: white;

    --tocnav-normal-text: #707070;
    --tocnav-normal-bg: var(--bg);
    --tocnav-hover-text: var(--tocnav-normal-text);
    --tocnav-hover-bg: #f8f8f8;
    --tocnav-active-text: #c00;
    --tocnav-active-bg: var(--tocnav-normal-bg);

    --tocsidebar-text: var(--text);
    --tocsidebar-bg: #f7f8f9;
    --tocsidebar-shadow: rgba(0,0,0,.1);
    --tocsidebar-heading-text: hsla(203,20%,40%,.7);

    --toclink-text: var(--text);
    --toclink-underline: #3980b5;
    --toclink-visited-text: var(--toclink-text);
    --toclink-visited-underline: #054572;

    --heading-text: #005a9c;

    --hr-text: var(--text);

    --algo-border: #def;

    --del-text: red;
    --del-bg: transparent;
    --ins-text: #080;
    --ins-bg: transparent;

    --a-normal-text: #034575;
    --a-normal-underline: #bbb;
    --a-visited-text: var(--a-normal-text);
    --a-visited-underline: #707070;
    --a-hover-bg: rgba(75%, 75%, 75%, .25);
    --a-active-text: #c00;
    --a-active-underline: #c00;

    --blockquote-border: silver;
    --blockquote-bg: transparent;
    --blockquote-text: currentcolor;

    --issue-border: #e05252;
    --issue-bg: #fbe9e9;
    --issue-text: var(--text);
    --issueheading-text: #831616;

    --example-border: #e0cb52;
    --example-bg: #fcfaee;
    --example-text: var(--text);
    --exampleheading-text: #574b0f;

    --note-border: #52e052;
    --note-bg: #e9fbe9;
    --note-text: var(--text);
    --noteheading-text: hsl(120, 70%, 30%);
    --notesummary-underline: silver;

    --assertion-border: #aaa;
    --assertion-bg: #eee;
    --assertion-text: black;

    --advisement-border: orange;
    --advisement-bg: #fec;
    --advisement-text: var(--text);
    --advisementheading-text: #b35f00;

    --warning-border: red;
    --warning-bg: hsla(40,100%,50%,0.95);
    --warning-text: var(--text);

    --amendment-border: #330099;
    --amendment-bg: #F5F0FF;
    --amendment-text: var(--text);
    --amendmentheading-text: #220066;

    --def-border: #8ccbf2;
    --def-bg: #def;
    --def-text: var(--text);
    --defrow-border: #bbd7e9;

    --datacell-border: silver;

    --indexinfo-text: #707070;

    --indextable-hover-text: black;
    --indextable-hover-bg: #f7f8f9;

    --outdatedspec-bg: rgba(0, 0, 0, .5);
    --outdatedspec-text: black;
    --outdated-bg: maroon;
    --outdated-text: white;
    --outdated-shadow: red;

    --editedrec-bg: darkorange;
}"""

styleDarkMode = """
@media (prefers-color-scheme: dark) {
    :root {
        --text: #ddd;
        --bg: black;

        --unofficial-watermark: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cg fill='%23100808' transform='translate(200 200) rotate(-45) translate(-200 -200)' stroke='%23100808' stroke-width='3'%3E%3Ctext x='50%25' y='220' style='font: bold 70px sans-serif; text-anchor: middle; letter-spacing: 6px;'%3EUNOFFICIAL%3C/text%3E%3Ctext x='50%25' y='305' style='font: bold 70px sans-serif; text-anchor: middle; letter-spacing: 6px;'%3EDRAFT%3C/text%3E%3C/g%3E%3C/svg%3E");

        --logo-bg: #1a5e9a;
        --logo-active-bg: #c00;
        --logo-text: white;

        --tocnav-normal-text: #999;
        --tocnav-normal-bg: var(--bg);
        --tocnav-hover-text: var(--tocnav-normal-text);
        --tocnav-hover-bg: #080808;
        --tocnav-active-text: #f44;
        --tocnav-active-bg: var(--tocnav-normal-bg);

        --tocsidebar-text: var(--text);
        --tocsidebar-bg: #080808;
        --tocsidebar-shadow: rgba(255,255,255,.1);
        --tocsidebar-heading-text: hsla(203,20%,40%,.7);

        --toclink-text: var(--text);
        --toclink-underline: #6af;
        --toclink-visited-text: var(--toclink-text);
        --toclink-visited-underline: #054572;

        --heading-text: #8af;

        --hr-text: var(--text);

        --algo-border: #456;

        --del-text: #f44;
        --del-bg: transparent;
        --ins-text: #4a4;
        --ins-bg: transparent;

        --a-normal-text: #6af;
        --a-normal-underline: #555;
        --a-visited-text: var(--a-normal-text);
        --a-visited-underline: var(--a-normal-underline);
        --a-hover-bg: rgba(25%, 25%, 25%, .2);
        --a-active-text: #f44;
        --a-active-underline: var(--a-active-text);

        --borderedblock-bg: rgba(255, 255, 255, .05);

        --blockquote-border: silver;
        --blockquote-bg: var(--borderedblock-bg);
        --blockquote-text: currentcolor;

        --issue-border: #e05252;
        --issue-bg: var(--borderedblock-bg);
        --issue-text: var(--text);
        --issueheading-text: hsl(0deg, 70%, 70%);

        --example-border: hsl(50deg, 90%, 60%);
        --example-bg: var(--borderedblock-bg);
        --example-text: var(--text);
        --exampleheading-text: hsl(50deg, 70%, 70%);

        --note-border: hsl(120deg, 100%, 35%);
        --note-bg: var(--borderedblock-bg);
        --note-text: var(--text);
        --noteheading-text: hsl(120, 70%, 70%);
        --notesummary-underline: silver;

        --assertion-border: #444;
        --assertion-bg: var(--borderedblock-bg);
        --assertion-text: var(--text);

        --advisement-border: orange;
        --advisement-bg: #222218;
        --advisement-text: var(--text);
        --advisementheading-text: #f84;

        --warning-border: red;
        --warning-bg: hsla(40,100%,20%,0.95);
        --warning-text: var(--text);

        --amendment-border: #330099;
        --amendment-bg: #080010;
        --amendment-text: var(--text);
        --amendmentheading-text: #cc00ff;

        --def-border: #8ccbf2;
        --def-bg: #080818;
        --def-text: var(--text);
        --defrow-border: #136;

        --datacell-border: silver;

        --indexinfo-text: #aaa;

        --indextable-hover-text: var(--text);
        --indextable-hover-bg: #181818;

        --outdatedspec-bg: rgba(255, 255, 255, .5);
        --outdatedspec-text: black;
        --outdated-bg: maroon;
        --outdated-text: white;
        --outdated-shadow: red;

        --editedrec-bg: darkorange;
    }
    /* In case a transparent-bg image doesn't expect to be on a dark bg,
       which is quite common in practice... */
    img { background: white; }
}"""

styleMdLists = """
/* This is a weird hack for me not yet following the commonmark spec
   regarding paragraph and lists. */
[data-md] > :first-child {
    margin-top: 0;
}
[data-md] > :last-child {
    margin-bottom: 0;
}"""

styleAutolinks = """
.css.css, .property.property, .descriptor.descriptor {
    color: var(--a-normal-text);
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
}"""

styleSelflinks = """
:root {
    --selflink-text: white;
    --selflink-bg: gray;
    --selflink-hover-text: black;
}
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
    background: var(--selflink-bg);
    color: var(--selflink-text);
    font-style: normal;
    transition: opacity .2s, background-color .2s, color .2s;
}
dfn:hover > a.self-link {
    opacity: 1;
}
dfn > a.self-link:hover {
    color: var(--selflink-hover-text);
}

a.self-link::before            { content: "¶"; }
.heading > a.self-link::before { content: "§"; }
dfn > a.self-link::before      { content: "#"; }
"""
styleDarkMode += """
@media (prefers-color-scheme: dark) {
    :root {
        --selflink-text: black;
        --selflink-bg: silver;
        --selflink-hover-text: white;
    }
}
"""


styleCounters = """
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
}"""

styleIssues = """
a[href].issue-return {
    float: right;
    float: inline-end;
    color: var(--issueheading-text);
    font-weight: bold;
    text-decoration: none;
}
"""
