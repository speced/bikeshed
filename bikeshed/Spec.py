# pylint: disable=attribute-defined-outside-init
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime

from . import (
    InputSource,
    biblio,
    boilerplate,
    caniuse,
    conditional,
    constants,
    datablocks,
    dfns,
    doctypes,
    extensions,
    fingerprinting,
    h,
    headings,
    highlight,
    idl,
    includes,
    inlineTags,
    language,
    lint,
    markdown,
    mdn,
    metadata,
    refs,
    retrieve,
    shorthands,
    stylescript,
    t,
    wpt,
)
from . import line as l
from . import messages as m
from . import unsortedJunk as u

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
    ) -> None:
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
                "No input file specified, and no *.bs or *.src.html files found in current directory.\nPlease specify an input file, or use - to pipe from STDIN.",
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

        self.lines: list[l.Line] = []
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

        self.languages: dict[str, language.Language] = fetchLanguages(self.dataFile)
        self.doctypes: doctypes.DoctypeManager = fetchDoctypes(self.dataFile)

        self.extraJC = stylescript.JCManager()
        self.extraJC.addColors()
        self.extraJC.addMdLists()
        self.extraJC.addAutolinks()
        self.extraJC.addSelflinks()
        self.extraJC.addCounters()
        self.extraJC.addIssues()

        try:
            self.inputContent = self.inputSource.read()
            if self.inputContent.date is not None:
                self.mdBaseline.addParsedData("Date", self.inputContent.date)
        except FileNotFoundError:
            m.die(f"Couldn't find the input file at the specified location '{self.inputSource}'.")
            return False
        except OSError:
            m.die(f"Couldn't open the input file '{self.inputSource}'.")
            return False

        return True

    def initMetadata(self, inputContent: InputSource.InputContent) -> None:
        # mdDefault is already set up
        # and cli() inited the mdCommandLine

        # Get the md from the doc itself
        # TODO: currently I just leave the node in,
        #       I should do something about that
        # TODO: Pure textual hack, no way to, say, put a block
        #       in a markdown code span or an <xmp> to show off.
        _, self.mdDocument = metadata.parse(lines=inputContent.lines)

        # Combine the data so far, and compute the doctype
        # (the other md sources need the doctype in order to be found)
        self.md = metadata.join(self.mdBaseline, self.mdDocument, self.mdCommandLine)
        rawDoctype = (self.md.rawOrg, self.md.rawGroup, self.md.rawStatus)
        self.doctype = self.doctypes.getDoctype(self.md.rawOrg, self.md.rawGroup, self.md.rawStatus)

        self.mdDefaults = metadata.fromJson(
            data=retrieve.retrieveBoilerplateFile(self, "defaults"),
            source="defaults",
        )
        self.md = metadata.join(self.mdBaseline, self.mdDefaults, self.mdDocument, self.mdCommandLine)
        if rawDoctype != (self.md.rawOrg, self.md.rawGroup, self.md.rawStatus):
            # recompute doctype
            self.doctype = self.doctypes.getDoctype(self.md.rawOrg, self.md.rawGroup, self.md.rawStatus)

        # Using all of that, load up the text macros so I can sub them into the computed-metadata file.
        self.md.fillTextMacros(self.macros, doc=self)
        jsonEscapedMacros = {k: json.dumps(v)[1:-1] for k, v in self.macros.items()}

        computedMdText = h.replaceMacrosTextly(
            retrieve.retrieveBoilerplateFile(self, "computed-metadata"),
            macros=jsonEscapedMacros,
            context="? of computed-metadata.include",
        )
        self.mdOverridingDefaults = metadata.fromJson(data=computedMdText, source="computed-metadata")
        # And create the final, complete md combo
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

        self.md.validate(doc=self)
        m.retroactivelyCheckErrorLevel()

    def earlyParse(self, inputContent: InputSource.InputContent) -> list[l.Line]:
        text = h.strFromNodes(h.initialDocumentParse(inputContent.content, h.ParseConfig.fromSpec(self)), withIlcc=True)
        inputContent.rawLines = [x + "\n" for x in text.split("\n")]
        return inputContent.lines

    def checkValidity(self) -> bool:
        return True

    def recordDependencies(self, *inputSources: InputSource.InputSource) -> None:
        self.transitiveDependencies.update(inputSources)

    def preprocess(self) -> Spec:
        self.transitiveDependencies.clear()
        self.assembleDocument()
        self.processDocument()
        return self

    def assembleDocument(self) -> Spec:
        self.initMetadata(self.inputContent)
        self.recordDependencies(self.inputSource)
        self.lines = self.earlyParse(self.inputContent)

        # Remove the metadata
        # FIXME: This should be done the first time I parse metadata.
        self.lines, _ = metadata.parse(lines=self.lines)
        extensions.load(self)

        # Initialize things
        self.refs.initializeRefs(doc=self, datablocks=datablocks)
        self.refs.initializeBiblio()

        if "mixed-indents" in self.md.complainAbout:
            if self.md.indentInfo and self.md.indentInfo.char:
                checkForMixedIndents(self.lines, self.md.indentInfo)
            elif len(self.lines) > 50:
                # Only complain about a failed inference if it's long
                # enough that I could reasonably infer something.
                m.warn(
                    "`Complain About: mixed-indents yes` is active, but I couldn't infer the document's indentation. Be more consistent, or turn this lint off.",
                )
            else:
                pass

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

        self.refs.setSpecData(self)

        # Convert to a single string of html now, for convenience.
        self.html = "".join(x.text for x in self.lines)
        boilerplate.addHeaderFooter(self)

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
        mdn.addMdnPanels(self)
        caniuse.addCanIUsePanels(self)
        highlight.addSyntaxHighlighting(self)
        boilerplate.addBikeshedBoilerplate(self)
        boilerplate.addDarkmodeIndicators(self)
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
        # Check the errors one more time.
        m.retroactivelyCheckErrorLevel(timing="late")
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
        fatals = m.state.categoryCounts["fatal"]
        links = m.state.categoryCounts["link-error"]
        warnings = m.state.categoryCounts["warning"]
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

            print(f"Serving at port {port}")  # noqa: T201
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
                        m.state = m.state.replace()
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

    def printTargets(self) -> None:
        m.p("Exported terms:")
        for el in h.findAll("[data-export]", self):
            for term in h.linkTextsFromElement(el):
                m.p("  " + term)
        m.p("Unexported terms:")
        for el in h.findAll("[data-noexport]", self):
            for term in h.linkTextsFromElement(el):
                m.p("  " + term)

    def isOpaqueElement(self, el: t.ElementT) -> bool:
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("data-opaque") is not None or el.get("bs-opaque") is not None:  # noqa: SIM103
            return True
        return False


def printDone() -> None:
    contents = f"Finished at {datetime.now().strftime('%H:%M:%S %b-%d-%Y')}"
    contentLen = len(contents) + 2
    if not m.state.asciiOnly:
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
            "You're hitting a bug with Python's argparse library. Please specify both the input and output filenames manually, and move all command-line flags with spaces in their values to after those arguments.\nSee <https://speced.github.io/bikeshed/#md-issues> for details.",
        )
        return False
    return True


def fetchLanguages(dataFile: retrieve.DataFileRequester) -> dict[str, language.Language]:
    return {
        k: language.Language(v["name"], v["native-name"])
        for k, v in json.loads(dataFile.fetch("languages.json", str=True)).items()
    }


def fetchDoctypes(dataFile: retrieve.DataFileRequester) -> doctypes.DoctypeManager:
    return doctypes.DoctypeManager.fromKdlStr(dataFile.fetch("boilerplate", "doctypes.kdl", str=True))


def addDomintroStyles(doc: Spec) -> None:
    # Adds common WHATWG styles for domintro blocks.

    if h.find(".domintro", doc) is None:
        return

    doc.extraJC.addDomintro()


def checkForMixedIndents(lines: t.Sequence[l.Line], info: metadata.IndentInfo) -> None:
    badIndentChar = " " if info.char == "\t" else "\t"
    for line in lines:
        if not line.text:
            continue
        if line.text.startswith(badIndentChar):
            if info.char == " ":
                m.lint(f"Your document appears to use spaces to indent, but line {line.i} starts with tabs.")
            else:
                m.lint(f"Your document appears to use tabs to indent, but line {line.i} starts with spaces.")
        if re.match(r"(\t+ +\t)|( +\t)", line.text):
            m.lint(f"Line {line.i}'s indent contains tabs after spaces.")
