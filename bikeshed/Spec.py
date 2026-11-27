# pylint: disable=attribute-defined-outside-init
from __future__ import annotations

import contextlib
import dataclasses
import glob
import json
import os
import sys
import time
import urllib.parse
from collections import OrderedDict, defaultdict
from datetime import datetime

from . import (
    InputSource,
    admonitions,
    algorithms,
    biblio,
    boilerplate,
    caniuse,
    cddl,
    cleanup,
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
    language,
    links,
    lint,
    mdn,
    metadata,
    refs,
    retrieve,
    stylescript,
    t,
    wpt,
)
from . import messages as m

if t.TYPE_CHECKING:
    import widlparser


@dataclasses.dataclass
class PhaseRecord:
    name: str
    elapsed: float
    group: str = ""


class PhaseTimer:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.phases: list[PhaseRecord] = []

    @contextlib.contextmanager
    def phase(self, name: str, group: str = "") -> t.Generator[None, None, None]:
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.phases.append(PhaseRecord(name=name, elapsed=elapsed, group=group))

    def total_time(self) -> float:
        return sum(p.elapsed for p in self.phases)


class Spec:
    def __init__(
        self,
        inputFilename: str | None = None,
        *,
        inputSource: InputSource.InputSource | None = None,
        debug: bool = False,
        debugPrint: str | None = None,
        token: str | None = None,
        lineNumbers: bool = False,
        fileRequester: retrieve.DataFileRequester | None = None,
        testing: bool = False,
        timer: PhaseTimer | None = None,
    ) -> None:
        self.timer: PhaseTimer = timer or PhaseTimer(enabled=False)
        self.valid: bool = False
        self.lineNumbers: bool = lineNumbers
        if lineNumbers:
            # line-numbers are too hacky, so force this to be a dry run
            constants.dryRun = True
        self.inputSource: InputSource.InputSource
        if inputSource is not None:
            self.inputSource = inputSource
        else:
            catchArgparseBug(inputFilename)
            if inputFilename is None:
                inputFilename = findImplicitInputFile()
            if inputFilename is None:  # still
                m.die(
                    "No input file specified, and no *.bs or *.src.html files found in current directory.\nPlease specify an input file, or use - to pipe from STDIN.",
                )
                return
            self.inputSource = InputSource.inputFromName(inputFilename, chroot=constants.chroot)
        self.transitiveDependencies: set[InputSource.InputSource] = set()
        self.debug: bool = debug
        self.debugPrint: str | None = debugPrint
        self.token: str | None = token
        self.testing: bool = testing
        self.dataFile: retrieve.DataFileRequester
        if fileRequester is None:
            self.dataFile = retrieve.defaultRequester
        else:
            self.dataFile = fileRequester

        self.nodes: list[h.ParserNode] = []
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
        self.metadataSpans: dict[int, int] | None = None
        self.indentInfo: metadata.IndentInfo | None = None

        self.typeExpansions: dict[str, str | None] = {}

        self.cachedLinksFromHref: OrderedDict[str, list[t.ElementT]] = OrderedDict()
        self.cachedClassTests: dict[tuple[str, str], bool] = {}
        self.cachedNormativeEls: dict[t.ElementT, bool] = {}

        defaultMacro: t.Callable[[], str] = lambda: "???"
        self.macros: t.DefaultDict[str, str] = defaultdict(defaultMacro)

        self.widl: widlparser.Parser = idl.getParser()

        self.languages: dict[str, language.Language] = fetchLanguages(self.dataFile)
        self.doctypes: doctypes.DoctypeManager = fetchDoctypes(self.dataFile)

        self.highlightGrammars: highlight.HighlightGrammarManager = highlight.HighlightGrammarManager(self)

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

        # Extract and parse metadata blocks near the start of the document.
        extracted = h.extractMetadata(inputContent.content)
        self.metadataSpans = extracted.spans
        self.indentInfo = metadata.inferIndent(inputContent.content, excludeSpans=extracted.spans)
        self.mdDocument = metadata.parse(inputContent.content, extracted=extracted)
        if (
            self.testing
            and (self.mdCommandLine is None or "Date" not in self.mdCommandLine.manuallySetKeys)
            and self.mdDocument.allData.get("Date")
            and self.mdDocument.allData["Date"][-1] == "now"
        ):
            self.mdDocument.addData("Date", "1970-01-01")

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
        with self.timer.phase("assembleDocument: initMetadata & recordDependencies"):
            self.initMetadata(self.inputContent)
            self.recordDependencies(self.inputSource)

        indentChecker: h.IndentChecker | None = None
        if "mixed-indents" in self.md.complainAbout and self.indentInfo and self.indentInfo.char:
            indentChecker = h.IndentChecker(
                indentChar=self.indentInfo.char,
                opaqueTags=h.DEFAULT_OPAQUE_ELEMENTS | frozenset(self.md.opaqueElements),
            )

        with self.timer.phase("assembleDocument: initialDocumentParse"):
            self.nodes = h.initialDocumentParse(
                self.inputContent.content,
                h.ParseConfig.fromSpec(self),
                indentChecker=indentChecker,
                metadataSpans=self.metadataSpans,
            )
        if self.debugPrint == "parse-nodes":
            h.debugNodes(self.nodes)
        elif self.debugPrint == "parsed-html":
            print(h.strFromNodes(self.nodes))  # noqa: T201

        if indentChecker is not None:
            indentChecker.emit()

        with self.timer.phase("assembleDocument: loadExtensions"):
            extensions.load(self)

        # Initialize things
        with self.timer.phase("assembleDocument: initializeRefs"):
            self.refs.initializeRefs(doc=self, datablocks=datablocks)
        with self.timer.phase("assembleDocument: initializeBiblio"):
            self.refs.initializeBiblio(doc=self)

        with self.timer.phase("assembleDocument: addHeaderFooter"):
            boilerplate.addHeaderFooter(self)

        # Build the document
        with self.timer.phase("assembleDocument: buildDocument"):
            self.document, self.head, self.body = h.buildDocument(self.nodes)
        if self.debugPrint == "boilerplate":
            print(h.printNodeTree(self.document))  # noqa: T201
        with self.timer.phase("assembleDocument: transformDataBlocks"):
            datablocks.transformDataBlocks(self, self.document)
        if self.debugPrint == "datablocks":
            print(h.printNodeTree(self.document))  # noqa: T201
        with self.timer.phase("assembleDocument: setSpecData"):
            self.refs.setSpecData(self)
        with self.timer.phase("assembleDocument: correctFrontMatter"):
            boilerplate.correctFrontMatter(self)
        with self.timer.phase("assembleDocument: processInclusions"):
            includes.processInclusions(self)
        with self.timer.phase("assembleDocument: metadata.parseDoc"):
            metadata.parseDoc(self)
        return self

    def processDocument(self) -> Spec:
        # Fill in and clean up a bunch of data
        with self.timer.phase("processDocument: boilerplate setup"):
            conditional.processConditionals(self)
            self.fillContainers: t.FillContainersT = boilerplate.locateFillContainers(self)
            lint.exampleIDs(self)
            wpt.processWptElements(self)

            boilerplate.addBikeshedVersion(self)
            boilerplate.addCanonicalURL(self)
            boilerplate.addFavicon(self)
            boilerplate.addSpecVersion(self)
            boilerplate.addStatusSection(self)
            boilerplate.addCGHeader(self)
            if boilerplate.isCGRedesign(self):
                self.fillContainers = boilerplate.locateFillContainers(self)
                boilerplate.addCGStatusBlocks(self)
                boilerplate.addCGFoot(self)
            boilerplate.addLogo(self)
            boilerplate.addCopyright(self)
            boilerplate.addSpecMetadataSection(self)
            boilerplate.addAbstract(self)
            boilerplate.addExpiryNotice(self)
            boilerplate.addObsoletionNotice(self)
            boilerplate.addAtRisk(self)
            admonitions.addNoteHeaders(self)
            boilerplate.removeUnwantedBoilerplate(self)

        with self.timer.phase("processDocument: algorithms"):
            algorithms.addImplicitAlgorithms(self)
            datablocks.fixManualDefTables(self)
        with self.timer.phase("processDocument: headings (pass 1)"):
            headings.processHeadings(self)
            algorithms.checkVarHygiene(self)
        with self.timer.phase("processDocument: admonitions"):
            admonitions.processIssuesAndExamples(self)
        with self.timer.phase("processDocument: IDL & CDDL markup"):
            idl.markupIDL(self)
            cddl.markupCDDL(self)
            admonitions.inlineRemoteIssues(self)
            cleanup.addImageSize(self)

        # Handle all the links
        with self.timer.phase("processDocument: biblio links"):
            biblio.processBiblioLinks(self)
        with self.timer.phase("processDocument: dfns"):
            dfns.processDfns(self)
            idl.processIDL(self)
            cddl.processCDDL(self)
            dfns.annotateDfns(self)
        with self.timer.phase("processDocument: def tables"):
            datablocks.formatArgumentdefTables(self)
            datablocks.formatElementdefTables(self)
        with self.timer.phase("processDocument: links.processAutolinks (pass 1)"):
            links.processAutolinks(self)
        with self.timer.phase("processDocument: references & indexes"):
            links.fixInterDocumentReferences(self)
            biblio.dedupBiblioReferences(self)
            boilerplate.addIndexSection(self)
            boilerplate.addExplicitIndexes(self)
            boilerplate.addStyles(self)
            boilerplate.addReferencesSection(self)
            boilerplate.addPropertyIndex(self)
            boilerplate.addIDLSection(self)
            boilerplate.addCDDLSection(self)
            boilerplate.addIssuesSection(self)
            boilerplate.addCustomBoilerplate(self)
        with self.timer.phase("processDocument: headings (pass 2)"):
            headings.processHeadings(self, "all")  # again
            boilerplate.removeUnwantedBoilerplate(self)
            boilerplate.addTOCSection(self)
            links.addSelfLinks(self)
        with self.timer.phase("processDocument: links.processAutolinks (pass 2)"):
            links.processAutolinks(self)
            boilerplate.removeUnwantedBoilerplate(self)
        # Add MDN panels after all IDs/anchors have been added
        with self.timer.phase("processDocument: MDN & CanIUse panels"):
            mdn.addMdnPanels(self)
            caniuse.addCanIUsePanels(self)
        with self.timer.phase("processDocument: syntax highlighting"):
            highlight.addSyntaxHighlighting(self)
        with self.timer.phase("processDocument: boilerplate & references"):
            boilerplate.addBikeshedBoilerplate(self)
            boilerplate.addDarkmodeIndicators(self)
            fingerprinting.addTrackingVector(self)
            links.fixIntraDocumentReferences(self)
            links.fixInterDocumentReferences(self)
            biblio.verifyUsageOfAllLocalBiblios(self)
            links.removeMultipleLinks(self)
            cleanup.forceCrossorigin(self)
            addDomintroStyles(self)
        with self.timer.phase("processDocument: lint"):
            lint.brokenLinks(self)
            lint.accidental2119(self)
            lint.missingExposed(self)
            lint.requiredIDs(self)
            lint.unusedInternalDfns(self)

        if self.debugPrint == "final":
            print(h.printNodeTree(self.document))  # noqa: T201

        # Any final HTML cleanups
        with self.timer.phase("processDocument: cleanup HTML"):
            cleanup.cleanupHTML(self)
            boilerplate.addCGAssets(self)
            if self.md.prepTR:
                prepTR(self)

        return self

    def serialize(self) -> str | None:
        with self.timer.phase("serialize (HTML)"):
            try:
                rendered = h.Serializer(self.md.opaqueElements, self.md.blockElements).serialize(self.document)
            except Exception as e:
                m.die(str(e))
                return None
            return rendered

    def fixMissingOutputFilename(self, outputFilename: str | None) -> str:
        if outputFilename is None:
            # More sensible defaults!
            if isinstance(self.inputSource, InputSource.TarInputSource):
                outputFilename = os.path.splitext(self.inputSource.sourceName)[0] + ".html"
            elif not isinstance(self.inputSource, InputSource.FileInputSource):
                outputFilename = "-"
            else:
                outputFilename = defaultOutputFilename(self.inputSource.sourceName)
        return outputFilename

    def finish(self, outputFilename: str | None = None, newline: str | None = None) -> None:
        # Check the errors one more time.
        m.retroactivelyCheckErrorLevel(timing="late")
        catchArgparseBug(outputFilename)
        self.printResultMessage()
        outputFilename = self.fixMissingOutputFilename(outputFilename)
        rendered = self.serialize()
        if rendered and not constants.dryRun:
            with self.timer.phase("write output file"):
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
        linkErrors = m.state.categoryCounts["link-error"]
        warnings = m.state.categoryCounts["warning"]
        if self.lineNumbers:
            m.warn("Because --line-numbers was used, no output was saved.")
        if fatals:
            m.success("Successfully generated, but fatal errors were suppressed")
            return
        if linkErrors:
            m.success(f"Successfully generated, with {linkErrors} linking errors")
            return
        if warnings:
            m.success("Successfully generated, with warnings")
            return

    def watch(self, outputFilename: str | None, port: int | None = None, localhost: bool = False) -> None:
        if m.wrappedOutput():
            m.die(f"Watch mode only supports console output; you've set --print={m.state.printMode}")
            return

        outputFilename = self.fixMissingOutputFilename(outputFilename)
        if self.inputSource.mtime() is None:
            m.die(f"Watch mode doesn't support {self.inputSource}")
            return
        if outputFilename == "-":
            m.die("Watch mode doesn't support streaming to STDOUT.")
            return

        if port:
            # Serve the folder on an HTTP server
            import http.server  # noqa: PLC0415
            import socketserver  # noqa: PLC0415
            import threading  # noqa: PLC0415

            class SilentServer(http.server.SimpleHTTPRequestHandler):
                def log_message(self, format: t.Any, *args: t.Any) -> None:
                    pass

            socketserver.TCPServer.allow_reuse_address = True
            server = socketserver.TCPServer(("localhost" if localhost else "", port), SilentServer)

            print(f"Serving at http://localhost:{port}/")  # noqa: T201
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
                        m.say("Source file modified. Rebuilding...")
                        self.initializeState()
                        self.mdCommandLine = mdCommandLine
                        self.preprocess()
                        self.finish(outputFilename)
                        lastInputModified = {dep: dep.mtime() for dep in self.transitiveDependencies}
                        printDone()
                    time.sleep(1)
            except KeyboardInterrupt:
                m.say("Exiting~")
                if server:
                    server.shutdown()
                    thread.join()
                m.printCloser()
                sys.exit(0)
        except Exception as e:
            m.die(f"Something went wrong while watching the file:\n{e}")

    def printTargets(self) -> None:
        exportMsg = "Exported terms:\n"
        for el in h.findAll("[data-export]", self):
            for term in h.linkTextsFromElement(el):
                exportMsg += "  " + term + "\n"
        m.say(exportMsg)
        unexportMsg = "Unexported terms:\n"
        for el in h.findAll("[data-noexport]", self):
            for term in h.linkTextsFromElement(el):
                unexportMsg += "  " + term + "\n"
        m.say(unexportMsg)

    def isOpaqueElement(self, el: t.ElementT) -> bool:
        if el.tag in h.DEFAULT_OPAQUE_ELEMENTS:
            return True
        if el.tag in self.md.opaqueElements:
            return True
        if el.get("bs-opaque") is not None:
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


def defaultOutputFilename(inputFilename: str) -> str:
    if inputFilename.endswith(".bs"):
        return inputFilename[0:-3] + ".html"
    elif inputFilename.endswith(".src.html"):
        return inputFilename[0:-9] + ".html"
    else:
        return "-"


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


def prepTR(doc: t.SpecT) -> None:
    # Don't try and override the W3C's icon.
    for el in h.findAll("[rel ~= 'icon']", doc):
        h.removeNode(el)
    # Make sure the W3C stylesheet is after all other styles.
    for el in h.findAll("link", doc):
        if el.get("href", "").startswith("https://www.w3.org/StyleSheets/TR"):
            h.appendChild(doc.head, el)
    # Ensure that all W3C links are https.
    for el in h.findAll("a", doc):
        upgradeToHttpsDomain(el)
    # Loaded from .include files
    extensions.BSPrepTR(doc)  # type: ignore # pylint: disable=no-member


def upgradeToHttpsDomain(el: t.ElementT) -> None:
    href = el.get("href")
    if not href:
        return
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme == "http":
        hostname = parsed.hostname
        assert hostname is not None
        if hostname == "w3.org" or hostname.endswith("w3.org"):
            el.set("href", parsed._replace(scheme="https").geturl())
