# pylint: disable=attribute-defined-outside-init
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict, OrderedDict
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
    language,
    line,
    lint,
    markdown,
    mdn,
    messages as m,
    metadata,
    refs,
    retrieve,
    shorthands,
    t,
    testsuite,
    unsortedJunk as u,
    wpt,
)

if t.TYPE_CHECKING:
    import widlparser


class Spec:
    def __init__(
        self,
        inputFilename: str,
        debug: bool = False,
        token: str | None = None,
        lineNumbers: bool = False,
        fileRequester: retrieve.DataFileRequester | None = None,
        testing: bool = False,
    ):
        catchArgparseBug(inputFilename)
        self.valid: bool = False
        self.lineNumbers: bool = lineNumbers
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
        self.inputSource: InputSource.InputSource = InputSource.inputFromName(inputFilename, chroot=constants.chroot)
        self.transitiveDependencies: set[InputSource.InputSource] = set()
        self.debug: bool = debug
        self.token: str | None = token
        self.testing: bool = testing
        self.dataFile: retrieve.DataFileRequester
        if fileRequester is None:
            self.dataFile = retrieve.defaultRequester
        else:
            self.dataFile = fileRequester

        self.lines: list[line.Line] = []
        self.valid = self.initializeState()

    def initializeState(self) -> bool:
        self.normativeRefs: dict[str, biblio.BiblioEntry] = {}
        self.informativeRefs: dict[str, biblio.BiblioEntry] = {}
        self.refs: refs.ReferenceManager = refs.ReferenceManager(fileRequester=self.dataFile, testing=self.testing)
        self.externalRefsUsed: refs.ExternalRefsManager = refs.ExternalRefsManager()

        self.md: metadata.MetadataManager
        self.mdBaseline: metadata.MetadataManager | None = metadata.MetadataManager()
        self.mdDocument: metadata.MetadataManager | None = None
        self.mdCommandLine: metadata.MetadataManager | None = metadata.MetadataManager()
        self.mdDefaults: metadata.MetadataManager | None = None
        self.mdOverridingDefaults: metadata.MetadataManager | None = None

        self.typeExpansions: dict[str, str] = {}

        self.cachedLinksFromHref: OrderedDict[str, list[t.ElementT]] = OrderedDict()
        self.cachedClassTests: dict[tuple[str, str], bool] = {}
        self.cachedNormativeEls: dict[t.ElementT, bool] = {}

        defaultMacro: t.Callable[[], str] = lambda: "???"
        self.macros: t.DefaultDict[str, str] = defaultdict(defaultMacro)

        self.widl: widlparser.Parser = idl.getParser()

        self.testSuites: dict[str, testsuite.TestSuite] = fetchTestSuites(self.dataFile)
        self.languages: dict[str, language.Language] = fetchLanguages(self.dataFile)

        self.extraStyles: t.DefaultDict[str, str] = defaultdict(str)
        self.extraStyles["style-colors"] = getModuleFile("Spec-colors.css")
        self.extraStyles["style-darkmode"] = getModuleFile("Spec-darkmode.css")
        self.extraStyles["style-md-lists"] = getModuleFile("Spec-mdlists.css")
        self.extraStyles["style-autolinks"] = getModuleFile("Spec-autolinks.css")
        self.extraStyles["style-selflinks"] = getModuleFile("Spec-selflinks.css")
        self.extraStyles["style-counters"] = getModuleFile("Spec-counters.css")
        self.extraStyles["style-issues"] = getModuleFile("Spec-issues.css")
        self.extraScripts: t.DefaultDict[str, str] = defaultdict(str)

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

    def recordDependencies(self, *inputSources: InputSource.InputSource) -> None:
        self.transitiveDependencies.update(inputSources)

    def preprocess(self) -> Spec:
        self.transitiveDependencies.clear()
        self.assembleDocument()
        self.processDocument()
        return self

    def assembleDocument(self) -> Spec:
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
        self.refs.initializeRefs(doc=self, datablocks=datablocks)
        self.refs.initializeBiblio()

        # Deal with further <pre> blocks, and markdown
        self.lines = datablocks.transformDataBlocks(self, self.lines)

        markdownFeatures: set[str] = {"headings"}
        self.lines = markdown.parse(
            self.lines,
            self.md.indent,
            opaqueElements=self.md.opaqueElements,
            blockElements=self.md.blockElements,
            features=markdownFeatures,
        )

        self.refs.setSpecData(self.md)

        # Convert to a single string of html now, for convenience.
        self.html = "".join(x.text for x in self.lines)
        boilerplate.addHeaderFooter(self)
        self.html = self.fixText(self.html)

        # Build the document
        self.document = h.parseDocument(self.html)
        headEl = h.find("head", self)
        bodyEl = h.find("body", self)
        assert headEl is not None
        assert bodyEl is not None
        self.head = headEl
        self.body = bodyEl
        u.correctFrontMatter(self)
        includes.processInclusions(self)
        metadata.parseDoc(self)
        return self

    def processDocument(self) -> Spec:
        # Fill in and clean up a bunch of data
        conditional.processConditionals(self)
        self.fillContainers: t.FillContainersT = u.locateFillContainers(self)
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
        u.fixInterDocumentReferences(self)
        biblio.dedupBiblioReferences(self)
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
        boilerplate.removeUnwantedBoilerplate(self)
        # Add MDN panels after all IDs/anchors have been added
        mdnPanels = mdn.addMdnPanels(self)
        ciuPanels = caniuse.addCanIUsePanels(self)
        if mdnPanels or ciuPanels:
            self.extraScripts["position-annos"] = getModuleFile("Spec-position-annos.js")
        highlight.addSyntaxHighlighting(self)
        boilerplate.addBikeshedBoilerplate(self)
        fingerprinting.addTrackingVector(self)
        u.fixIntraDocumentReferences(self)
        u.fixInterDocumentReferences(self)
        u.verifyUsageOfAllLocalBiblios(self)
        u.removeMultipleLinks(self)
        u.forceCrossorigin(self)
        addDomintroStyles(self)
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
                if el.get("href", "").startswith("https://www.w3.org/StyleSheets/TR"):
                    h.appendChild(self.head, el)
            # Ensure that all W3C links are https.
            for el in h.findAll("a", self):
                href = el.get("href", "")
                if href.startswith("http://www.w3.org") or href.startswith("http://lists.w3.org"):
                    el.set("href", "https" + href[4:])
                text = el.text or ""
                if text.startswith("http://www.w3.org") or text.startswith("http://lists.w3.org"):
                    el.text = "https" + text[4:]
            # Loaded from .include files
            extensions.BSPrepTR(self)  # type: ignore # pylint: disable=no-member

        return self

    def serialize(self) -> str | None:
        try:
            rendered = h.Serializer(self.md.opaqueElements, self.md.blockElements).serialize(self.document)
        except Exception as e:
            m.die(str(e))
            return None
        rendered = u.finalHackyCleanup(rendered)
        return rendered

    def fixMissingOutputFilename(self, outputFilename: str | None) -> str:
        if outputFilename is None:
            # More sensible defaults!
            if isinstance(self.inputSource, InputSource.TarInputSource):
                outputFilename = os.path.splitext(self.inputSource.sourceName)[0] + ".html"
            elif not isinstance(self.inputSource, InputSource.FileInputSource):
                outputFilename = "-"
            elif self.inputSource.sourceName.endswith(".bs"):
                outputFilename = self.inputSource.sourceName[0:-3] + ".html"
            elif self.inputSource.sourceName.endswith(".src.html"):
                outputFilename = self.inputSource.sourceName[0:-9] + ".html"
            else:
                outputFilename = "-"
        return outputFilename

    def finish(self, outputFilename: str | None = None, newline: str | None = None) -> None:
        catchArgparseBug(outputFilename)
        self.printResultMessage()
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        rendered = self.serialize()
        if rendered and not constants.dryRun:
            try:
                if outputFilename == "-":
                    sys.stdout.write(rendered)
                else:
                    with open(outputFilename, "w", encoding="utf-8", newline=newline) as f:
                        f.write(rendered)
            except Exception as e:
                m.die(f"Something prevented me from saving the output document to {outputFilename}:\n{e}")

    def printResultMessage(self) -> None:
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

    def watch(self, outputFilename: str | None, port: int | None = None, localhost: bool = False) -> None:
        import time

        outputFilename = self.fixMissingOutputFilename(outputFilename)
        if self.inputSource.mtime() is None:
            m.die(f"Watch mode doesn't support {self.inputSource}")
            return
        if outputFilename == "-":
            m.die("Watch mode doesn't support streaming to STDOUT.")
            return

        if port:
            # Serve the folder on an HTTP server
            import http.server
            import socketserver
            import threading

            class SilentServer(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: t.Any, *args: t.Any) -> None:
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

    def fixText(self, text: str, moreMacros: dict[str, str] | None = None) -> str:
        # Do several textual replacements that need to happen *before* the document is parsed as h.

        # If markdown shorthands are on, remove all `foo`s while processing,
        # so their contents don't accidentally trigger other stuff.
        # Also handle markdown escapes.
        if moreMacros is None:
            moreMacros = {}
        textFunctor: func.Functor
        if "markdown" in self.md.markupShorthands:
            textFunctor = u.MarkdownCodeSpans(text)
        else:
            textFunctor = func.Functor(text)

        macros = dict(self.macros, **moreMacros)
        textFunctor = textFunctor.map(curry(h.replaceMacros, macros=macros))
        textFunctor = textFunctor.map(h.fixTypography)
        if "css" in self.md.markupShorthands:
            textFunctor = textFunctor.map(h.replaceAwkwardCSSShorthands)

        return t.cast(str, textFunctor.extract())

    def printTargets(self) -> None:
        m.p("Exported terms:")
        for el in h.findAll("[data-export]", self):
            for term in config.linkTextsFromElement(el):
                m.p("  " + term)
        m.p("Unexported terms:")
        for el in h.findAll("[data-noexport]", self):
            for term in config.linkTextsFromElement(el):
                m.p("  " + term)

    def isOpaqueElement(self, el: t.ElementT) -> bool:
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("data-opaque") is not None:
            return True
        return False


def printDone() -> None:
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


def findImplicitInputFile() -> str | None:
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


def catchArgparseBug(string: str | None) -> bool:
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
            "You're hitting a bug with Python's argparse library. Please specify both the input and output filenames manually, and move all command-line flags with spaces in their values to after those arguments.\nSee <https://speced.github.io/bikeshed/#md-issues> for details."
        )
        return False
    return True


def fetchTestSuites(dataFile: retrieve.DataFileRequester) -> dict[str, testsuite.TestSuite]:
    return {k: testsuite.TestSuite(**v) for k, v in json.loads(dataFile.fetch("test-suites.json", str=True)).items()}


def fetchLanguages(dataFile: retrieve.DataFileRequester) -> dict[str, language.Language]:
    return {
        k: language.Language(v["name"], v["native-name"])
        for k, v in json.loads(dataFile.fetch("languages.json", str=True)).items()
    }


def addDomintroStyles(doc: Spec) -> None:
    # Adds common WHATWG styles for domintro blocks.

    if h.find(".domintro", doc) is None:
        return

    doc.extraStyles["styles-domintro"] = getModuleFile("Spec-domintro.css")


def getModuleFile(filename: str) -> str:
    with open(config.scriptPath(filename), "r", encoding="utf-8") as fh:
        return fh.read()
