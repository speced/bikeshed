from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta

from isodate import Duration

from .. import config, h, markdown, repository, t
from .. import messages as m
from ..translate import _t
from . import keys, parsers

if t.TYPE_CHECKING:
    from ..line import Line

    class DurationT:
        pass


class MetadataManager:
    @property
    def vshortname(self) -> str | None:
        if self.level:
            return f"{self.shortname}-{self.level}"
        return self.shortname

    @property
    def displayVshortname(self) -> str | None:
        if self.level:
            return f"{self.displayShortname}-{self.level}"
        return self.displayShortname

    def __init__(self) -> None:
        self.hasMetadata: bool = False

        # All metadata ever passed to .addData()
        self.allData: t.DefaultDict[str, list[str]] = defaultdict(list)

        # required metadata
        self.abstract: list[str] = []
        self.ED: str | None = None
        self.level: str | None = None
        self.displayShortname: str | None = None
        self.shortname: str | None = None

        # optional metadata
        self.advisementClass: str = "advisement"
        self.assertionClass: str = "assertion"
        self.assumeExplicitFor: bool = False
        self.atRisk: list[str] = []
        self.audience: list[str] = []
        self.blockElements: list[str] = []
        self.boilerplate: config.BoolSet = config.BoolSet(default=True)
        self.canIUseURLs: list[str] = []
        self.canonicalURL: str | None = None
        self.cgMaturity: str | None = None
        self.cgTransferredTo: str | None = None
        self.complainAbout: config.BoolSet = config.BoolSet(["mixed-indents"])
        self.customTextMacros: list[tuple[str, str]] = []
        self.customWarningText: list[str] = []
        self.customWarningTitle: str | None = None
        self.darkMode: bool = True
        self.date: date = datetime.utcnow().date()
        self.deadline: date | None = None
        self.defaultHighlight: str | None = None
        self.defaultBiblioDisplay: str = "index"
        self.defaultRefStatus: str | None = None
        self.dieOn: str | None = None
        self.dieWhen: str | None = None
        self.editors: list[dict[str, str | None]] = []
        self.editorTerm: dict[str, str] = {"singular": _t("Editor"), "plural": _t("Editors")}
        self.expires: date | None = None
        self.externalInfotrees: config.BoolSet = config.BoolSet(default=False)
        self.favicon: str | None = None
        self.forceCrossorigin: bool = False
        self.h1: str | None = None
        self.ignoreCanIUseUrlFailure: list[str] = []
        self.ignoreMDNFailure: list[str] = []
        self.ignoredTerms: list[str] = []
        self.ignoredVars: list[str] = []
        self.implementationReport: str | None = None
        self.includeCanIUsePanels: bool = False
        self.includeMdnPanels: bool = False
        self.indent: int = 4
        self.indentInfo: IndentInfo | None = None
        self.inferCSSDfns: bool = False
        self.informativeClasses: list[str] = []
        self.inlineGithubIssues: bool = False
        self.inlineTagCommands: dict[str, str] = {}
        self.issueClass: str = "issue"
        self.issues: list[tuple[str, str]] = []
        self.issueTrackerTemplate: str | None = None
        self.lineNumbers: bool = False
        self.linkCheckerTimeout: parsers.LinkCheckerTimeout = parsers.LinkCheckerTimeout()
        self.linkDefaults: t.LinkDefaultsT = defaultdict(list)
        self.localBoilerplate: config.BoolSet = config.BoolSet(default=False)
        self.logo: str | None = None
        self.mailingList: str | None = None
        self.mailingListArchives: str | None = None
        self.markupShorthands: config.BoolSet = config.BoolSet(
            [
                "css",
                "dfn",
                "biblio",
                "markdown-block",
                "markup",
                "http",
                "idl",
                "cddl",
                "algorithm",
                "repository-links",
            ],
        )
        self.maxToCDepth: int | float | None = float("inf")
        self.metadataInclude: config.BoolSet = config.BoolSet(default=True)
        self.metadataOrder: list[str] = ["*", "!*"]
        self.noAbstract: bool = False
        self.noEditor: bool = False
        self.noteClass: str = "note"
        self.opaqueElements: list[str] = []
        self.prepTR: bool = False
        self.previousEditors: list[dict[str, str | None]] = []
        self.previousVersions: list[dict[str, str]] = []
        self.rawGroup: str | None = None
        self.rawOrg: str | None = None
        self.rawStatus: str | None = None
        self.removeMultipleLinks: bool = False
        self.repository: repository.Repository | None = None
        self.requiredIDs: list[str] = []
        self.slimBuildArtifact: bool = False
        self.statusText: list[str] = []
        self.testSuite: str | None = None
        self.title: str | None = None
        self.toggleDiffs: bool = False
        self.TR: str | None = None
        self.trackingVectorAltText: str = _t("(This is a tracking vector.)")
        self.trackingVectorClass: str = "tracking-vector"
        self.trackingVectorImage: str | None = None
        self.trackingVectorImageHeight: str = "64"
        self.trackingVectorImageWidth: str = "46"
        self.trackingVectorTitle: str = _t("There is a tracking vector here.")
        self.translateIDs: dict[str, str] = {}
        self.translations: list[dict[str, str]] = []
        self.useDfnPanels: bool = True
        self.useIAutolinks: bool = False
        self.versionHistory: list[str] = []
        self.warning: str | None = None
        self.workStatus: str | None = None
        self.wptDisplay: str = "none"
        self.wptErrors: str = "minimal"
        self.wptPathPrefix: str | None = None
        self.imgAutoSize: bool = True

        self.otherMetadata: OrderedDict[str, list[t.NodeT]] = OrderedDict()

        self.manuallySetKeys: set[str] = set()

    def addData(self, key: str, val: str, lineNum: str | int | None = None) -> MetadataManager:
        key = key.strip()
        val = val.strip()

        if key.startswith("!"):
            self.allData[key].append(val)
            key = key[1:]
            self.otherMetadata.setdefault(key, []).append(val)
            return self

        if key not in ("ED", "TR", "URL"):
            key = key.title()

        if key not in keys.KNOWN_KEYS:
            m.die(f'Unknown metadata key "{key}". Prefix custom keys with "!".', lineNum=lineNum)
            return self

        md = keys.KNOWN_KEYS[key]
        try:
            parsedVal = md.parse(key, val, lineNum=lineNum)
        except Exception as e:
            m.die(f"Error while parsing '{key}' metadata value:\n  {val}\n{e}")
            return self

        self.allData[key].append(val)
        self.addParsedData(key, parsedVal)
        return self

    def addParsedData(self, key: str, val: t.Any) -> MetadataManager:
        md = keys.KNOWN_KEYS[key]
        result = md.join(getattr(self, md.attrName), val)
        setattr(self, md.attrName, result)
        self.manuallySetKeys.add(key)
        return self

    def computeImplicitMetadata(self, doc: t.SpecT) -> None:
        # Do some "computed metadata", based on the value of other metadata.
        # Only call this when you're sure all metadata sources are parsed.

        if doc.doctype.group.name == "BYOS":
            self.boilerplate.default = False
        if not self.repository and doc:
            self.repository = getSpecRepository(doc)
        if (
            isinstance(self.repository, repository.GithubRepository)
            and "feedback-header" in self.boilerplate
            and "repository-issue-tracking" in self.boilerplate
        ):
            self.issues.append(("GitHub", self.repository.formatIssueUrl()))

        self.expires = canonicalizeExpiryDate(self.date, self.expires)

        # for TR document, defaults to TR
        # fallbacks to ED
        if (self.canonicalURL is None or self.canonicalURL == "TR") and self.TR:
            self.canonicalURL = self.TR
        elif (self.canonicalURL is None or self.canonicalURL == "ED") and self.ED:
            self.canonicalURL = self.ED

        if self.displayShortname:
            self.shortname = self.displayShortname.lower()

        if self.dieOn:
            m.state.dieOn = self.dieOn

    def validate(self, doc: t.SpecT) -> bool:
        if doc.doctype.group.name == "BYOS":
            return True

        if not self.hasMetadata:
            m.die("The document requires at least one <pre class=metadata> block.")
            return False

        requiredMd = [
            keys.KNOWN_KEYS["Status"],
            keys.KNOWN_KEYS["Shortname"],
            keys.KNOWN_KEYS["Title"],
        ]

        if doc.doctype.status:
            for mdName in doc.doctype.status.requires:
                if mdName in keys.KNOWN_KEYS:
                    requiredMd.append(keys.KNOWN_KEYS[mdName])
                else:
                    m.warn(
                        f"Programming error: your Status '{doc.doctype.status.fullName()}' claims to require the unknown metadata '{mdName}'. Please report this to the maintainer.",
                    )
        if doc.doctype.group:
            for mdName in doc.doctype.group.requires:
                if mdName in keys.KNOWN_KEYS:
                    requiredMd.append(keys.KNOWN_KEYS[mdName])
                else:
                    m.warn(
                        f"Programming error: your Group '{doc.doctype.group.fullName()}' claims to require the unknown metadata '{mdName}'. Please report this to the maintainer.",
                    )

        if not self.noEditor:
            requiredMd.append(keys.KNOWN_KEYS["Editor"])
        if not self.noAbstract:
            requiredMd.append(keys.KNOWN_KEYS["Abstract"])

        errors = []
        for md in requiredMd:
            if getattr(self, md.attrName) is None:
                errors.append(f"    Missing '{md.humanName}'")
        if errors:
            m.die("Not all required metadata was provided:\n" + "\n".join(errors))
            return False
        return True

    def fillTextMacros(self, macros: t.DefaultDict[str, str], doc: t.SpecT) -> None:
        # Fills up a set of text macros based on metadata.
        if self.title:
            macros["title"] = h.parseTitle(
                self.title,
                h.ParseConfig.fromSpec(doc, context="Title metadata"),
                context="Title metadata",
            )
        if self.h1:
            macros["spectitle"] = h.parseText(
                self.h1,
                h.ParseConfig.fromSpec(doc, context="H1 metadata"),
                context="H1 metadata",
            )
        elif self.title:
            macros["spectitle"] = h.parseText(
                self.title,
                h.ParseConfig.fromSpec(doc, context="Title metadata"),
                context="Title metadata",
            )
        if self.displayShortname:
            macros["shortname"] = self.displayShortname
        if self.statusText:
            macros["statustext"] = parsedTextFromRawLines(
                self.statusText,
                doc=doc,
                context="Status Text metadata",
            )
        else:
            macros["statustext"] = ""
        macros["level"] = str(self.level)
        if self.displayVshortname:
            macros["vshortname"] = self.displayVshortname
        if doc.doctype.status.name == "FINDING" and doc.doctype.group:
            macros["longstatus"] = f"Finding of the {doc.doctype.group.name}"
        elif doc.doctype.status.name == "DRAFT-FINDING" and doc.doctype.group:
            macros["longstatus"] = f"Draft Finding of the {doc.doctype.group.name}"
        elif doc.doctype.status:
            macros["longstatus"] = doc.doctype.status.longName
        else:
            macros["longstatus"] = ""
        if doc.doctype.group.name == "W3C":
            if doc.doctype.status.name in ("LCWD", "FPWD"):
                macros["status"] = "WD"
            elif doc.doctype.status.name in ("NOTE-FPWD", "NOTE-WD"):
                macros["status"] = "DNOTE"
            elif doc.doctype.status.name in ("WG-NOTE", "IG-NOTE"):
                macros["status"] = "NOTE"
            elif doc.doctype.status.name == "NOTE-ED":
                macros["status"] = "ED"
            elif doc.doctype.status:
                macros["status"] = doc.doctype.status.name
        elif doc.doctype.status:
            macros["status"] = doc.doctype.status.name
        if self.workStatus:
            macros["workstatus"] = self.workStatus
        if doc.doctype.status.name in ("CG-LIVING", "CG-SNAPSHOT"):
            maturity = self.cgMaturity or "draft"
            macros["cg-maturity"] = maturity
            macros["cg-maturity-label"] = maturity.capitalize()
            if maturity == "transferred" and not self.cgTransferredTo:
                m.warn(
                    "CG Maturity is 'transferred' but CG Transferred To is not set; the notice will not name an organization.",
                )
            macros["cg-transferred-to"] = self.cgTransferredTo or "Another organization"
            shortname = self.displayShortname or ""
            group = doc.doctype.group.name.lower()
            macros["cg-snapshots-index"] = f"https://incubation.w3.org/groups/{group}/specs/#{shortname}"
            macros["cg-snapshot-address"] = (
                f"https://incubation.w3.org/specs/{shortname}-{self.date.strftime('%Y%m%d')}/"
            )
        if self.TR:
            macros["latest"] = self.TR
        if self.abstract:
            macros["abstract"] = parsedTextFromRawLines(
                self.abstract,
                doc=doc,
                context="Abstract metadata",
            )
        elif self.noAbstract:
            macros["abstract"] = ""
        macros["year"] = str(self.date.year)
        macros["date"] = self.date.strftime(f"{self.date.day} %B %Y")
        macros["date-dmmy"] = self.date.strftime(f"{self.date.day} %B %Y")  # same as plain 'date'
        macros["cdate"] = self.date.strftime("%Y%m%d")
        macros["isodate"] = self.date.strftime("%Y-%m-%d")
        macros["date-my"] = self.date.strftime("%b %Y")
        macros["date-mmy"] = self.date.strftime("%B %Y")
        if isinstance(self.expires, date):
            macros["expires"] = self.expires.strftime(f"{self.expires.day} %B %Y")
            macros["expires-dmmy"] = self.expires.strftime(f"{self.expires.day} %B %Y")  # same as plain 'expires'
            macros["cexpires"] = self.expires.strftime("%Y%m%d")
            macros["isoexpires"] = self.expires.strftime("%Y-%m-%d")
            macros["expires-my"] = self.expires.strftime("%b %Y")
            macros["expires-mmy"] = self.expires.strftime("%B %Y")
        if self.deadline:
            macros["deadline"] = self.deadline.strftime(f"{self.deadline.day} %B %Y")
            macros["isodeadline"] = self.deadline.strftime("%Y-%m-%d")
        if doc.doctype.org.name == "W3C" and "Date" in doc.doctype.status.requires:
            status_name = doc.doctype.status.name
            if status_name == "NOTE-WD":
                status_name = "DNOTE"
            macros["version"] = (
                f"https://www.w3.org/TR/{macros['year']}/{status_name}-{macros['vshortname']}-{macros['cdate']}/"
            )
            macros["history"] = f"https://www.w3.org/standards/history/{self.displayVshortname}/"
        elif self.ED:
            macros["version"] = self.ED
        if self.warning and len(self.warning) >= 2:
            macros["replacedby"] = self.warning[1]
        if self.warning and len(self.warning) >= 3:
            macros["snapshotid"] = self.warning[2]
        if self.warning and len(self.warning) >= 4:
            macros["snapshoturl"] = self.warning[3]
        if self.logo:
            macros["logo"] = self.logo
        if self.repository:
            macros["repository"] = self.repository.name or _t("Unnamed Repo")
            macros["repositoryurl"] = self.repository.url
        if self.mailingList:
            macros["mailinglist"] = self.mailingList
        if self.mailingListArchives:
            macros["mailinglistarchives"] = self.mailingListArchives
        if doc.doctype.org.name == "W3C":
            statusName = doc.doctype.status.name
            if statusName == "FPWD":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-WD"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#FPWD"
            elif statusName in ("NOTE-FPWD", "NOTE-WD"):
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-DNOTE"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#DNOTE"
            elif statusName == "FINDING":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/base.css"
                macros["w3c-status-url"] = "https://tag.w3.org/findings/"
            elif statusName == "DRAFT-FINDING":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/base.css"
                macros["w3c-status-url"] = "https://tag.w3.org/findings/"
            elif statusName == "CG-DRAFT":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/cg-draft"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#CG-DRAFT"
            elif statusName == "CG-FINAL":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/cg-final"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#CG-FINAL"
            elif statusName == "NOTE-ED":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-ED"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#ED"
            elif statusName == "STATEMENT":
                macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-STMT"
                macros["w3c-status-url"] = "https://www.w3.org/standards/types/#STMT"
            else:
                macros["w3c-stylesheet-url"] = f"https://www.w3.org/StyleSheets/TR/2021/W3C-{statusName}"
                macros["w3c-status-url"] = f"https://www.w3.org/standards/types/#{statusName}"
        if self.customWarningText is not None:
            macros["customwarningtext"] = parsedTextFromRawLines(
                self.customWarningText,
                doc=doc,
                context="Custom Warning Text metadata",
            )
        if self.customWarningTitle is not None:
            macros["customwarningtitle"] = h.parseText(
                self.customWarningTitle,
                h.ParseConfig.fromSpec(doc, context="Custom Warning Title metadata"),
                context="Custom Warning Title metadata",
            )
        # Custom macros
        for name, text in self.customTextMacros:
            macros[name.lower()] = text


def parsedTextFromRawLines(lines: list[str], doc: t.SpecT, context: str) -> str:
    if len(lines) == 0:
        return ""
    lines = [line.rstrip() + "\n" for line in lines]
    lines = t.cast("list[str]", h.parseLines(lines, h.ParseConfig.fromSpec(doc, context=context), context=context))
    lines = markdown.parse(lines, markdown.MarkdownConfig.fromSpec(doc))
    return "".join(lines)


def parse(lines: t.Sequence[Line]) -> tuple[list[Line], MetadataManager]:
    # Given HTML document text, in the form of an array of text lines,
    # extracts all <pre class=metadata> lines and parses their contents.
    # Returns the text lines, with the metadata-related lines removed,
    # and a filled MetadataManager object

    newlines = []
    inMetadata = False
    lastKey = None
    multilineVal = False
    endTag = None
    md = MetadataManager()
    for line in lines:
        if not inMetadata and ("<pre" in line.text or "<xmp" in line.text) and "metadata" in line.text:
            match = re.match(r"<(pre|xmp) [^>]*class=[^>]*metadata[^>]*>", line.text)
            if match:
                inMetadata = True
                md.hasMetadata = True
                if line.text.startswith("<pre"):
                    endTag = r"</pre>\s*"
                else:
                    endTag = r"</xmp>\s*"
                continue
        if inMetadata and re.match(t.cast(str, endTag), line.text):
            inMetadata = False
            continue
        if inMetadata:
            # Skip newlines except for multiline blocks
            if line.text.strip() == "" and not multilineVal:
                continue
            if lastKey and (line.text.strip() == "" or re.match(r"\s+", line.text)):
                # empty lines, or lines that start with 1+ spaces, continue previous key
                md.addData(lastKey, line.text, lineNum=line.i)
            else:
                match = re.match(r"([^:]+):(.*)", line.text)
                if match:
                    key = match[1].strip()
                    val = match[2].strip()
                    if key in keys.KNOWN_KEYS and keys.KNOWN_KEYS[key].multiline:
                        multilineVal = True
                    elif key[0] == "!":
                        multilineVal = True
                    else:
                        multilineVal = False
                    md.addData(key, val, lineNum=line.i)
                    lastKey = match[1]
                else:
                    m.die(
                        f"Incorrectly formatted metadata line:\n{line.text}",
                        lineNum=line.i,
                    )
                    continue
        elif "<h1" in line.text and md.title is None:
            match = re.match(r"\s*<h1[^>]*>(.*?)</h1>", line.text)
            if match:
                title = match[1]
                md.addData("Title", title, lineNum=line.i)
            newlines.append(line)
        else:
            newlines.append(line)
    indentInfo = inferIndent(newlines)
    md.addParsedData("Indent Info", indentInfo)
    if "Indent" not in md.manuallySetKeys and indentInfo.size:
        md.indent = indentInfo.size
    return newlines, md


@dataclasses.dataclass
class IndentInfo:
    size: int | None = None
    char: str | None = None
    spaceLines: int = 0
    tabLines: int = 0
    neitherLines: int = 0

    def tooShort(self) -> bool:
        return (self.spaceLines + self.tabLines) < 20


def inferIndent(lines: t.Sequence[Line]) -> IndentInfo:
    # Infer what indent character the document is using.
    # If the document uses space indentation,
    # infer what the indent size is by seeing what % of indents
    # are divisible by various values.
    # A sufficiently short document, or one with too few indented lines,
    # will fail to infer anything.
    indentSizes: Counter[int] = Counter()
    info = IndentInfo()
    for line in lines:
        # Purposely require at least two spaces; I don't
        # auto-detect single-space indents. Get help.

        spaceCount = spaceIndentFromLine(line.text)
        if spaceCount >= 2:
            indentSizes[spaceCount] += 1
            info.spaceLines += 1
        elif line.text[0:1] == "\t":
            info.tabLines += 1
        else:
            info.neitherLines += 1
    # If very few lines are indented at all, just bail
    if info.tooShort():
        return info
    # If tab indents predominate, assume tab-indent.
    if info.spaceLines < info.tabLines:
        info.char = "\t"
    else:
        info.char = " "
    # If we have more than a handful of indented lines,
    # do a pretend Fourier analysis
    # (see how many lines' indents are evenly divided).
    # This allows *some* lines to be indented incorrectly
    # (or space indent + space alignment on code samples).
    # Add some extra weight for being *exactly* the desired indent,
    # to counterbalance the fact that every 4-indent line
    # looks like a 2-indent line as well, etc.
    if info.spaceLines >= 50:
        evenDivisions: Counter[int] = Counter()
        for candidateIndent in range(8, 1, -1):
            for spaceCount, lineCount in indentSizes.items():
                if spaceCount % candidateIndent == 0:
                    evenDivisions[candidateIndent] += lineCount
                if spaceCount == candidateIndent:
                    evenDivisions[candidateIndent] += lineCount
        if evenDivisions:
            info.size = evenDivisions.most_common(1)[0][0]
    return info


def spaceIndentFromLine(line: str) -> int:
    # Returns just the whitespace prefix of a line
    if line[0] != " ":
        return 0
    for i, ch in enumerate(line):
        if ch == " ":
            continue
        return i
    return len(line)


def fromCommandLine(overrides: list[str]) -> MetadataManager:
    # Given a list of strings representing command-line arguments,
    # finds the args that correspond to metadata keys
    # and fills a MetadataManager accordingly.
    md = MetadataManager()
    for o in overrides:
        match = re.match(r"--md-([^ =]+)=(.+)", o)
        if not match:
            # Not a metadata key
            continue
        # Convert the key into a metadata name
        key = match.group(1).replace("-", " ")
        if key not in ("ED", "TR"):
            key = key.title()
        val = match.group(2).strip()
        md.addData(key, val)
    return md


def fromJson(data: str, source: str) -> MetadataManager:
    md = MetadataManager()
    try:
        defaults = json.loads(data, object_pairs_hook=OrderedDict)
    except Exception as e:
        if data != "":
            if source == "computed-metadata":
                m.die(
                    f"Error loading computed-metadata JSON.\nCheck if you need to JSON-escape some characters in a text macro?\n{e}",
                )
            else:
                m.die(f"Error loading {source} JSON:\n{e}")
        return md
    for key, val in defaults.items():
        if isinstance(val, str):
            md.addData(key, val)
        elif isinstance(val, list):
            for indivVal in val:
                md.addData(key, indivVal)
        else:
            m.die(f"JSON metadata values must be strings or arrays of strings. '{key}' is something else.")
            return md
    return md


def getSpecRepository(doc: t.SpecT) -> repository.Repository | None:
    """
    Attempts to find the name of the repository the spec is a part of.
    Currently only searches for GitHub repos.
    Returns a "shortname" of the repo, and the full url.
    """
    if doc and doc.inputSource and doc.inputSource.hasDirectory():
        source_dir = doc.inputSource.directory()
        try:
            with open(os.devnull, "wb") as fnull:
                remotes = str(
                    subprocess.check_output(["git", "remote", "-v"], stderr=fnull, cwd=source_dir),
                    encoding="utf-8",
                )
            searches = [
                r"origin\tgit@github\.([\w.-]+):([\w-]+)/([\w-]+)(?:\.git)? \(\w+\)",
                r"origin\thttps://github\.([\w.-]+)/([\w-]+)/([\w-]+)(?:\.git)? \(\w+\)",
                r"origin\thttps://github\.([\w.-]+)/([\w-]+)/([\w-]+)/? \(\w+\)",
            ]
            for search_re in searches:
                search = re.search(search_re, remotes)
                if search:
                    return repository.GithubRepository(*search.groups())
            return None
        except subprocess.CalledProcessError:
            # check_output will throw CalledProcessError when not in a git repo
            return None
    return None


def canonicalizeExpiryDate(base: date, expires: timedelta | datetime | date | None) -> date | None:
    if expires is None:
        return None
    if isinstance(expires, timedelta):
        return base + expires
    if isinstance(expires, Duration):
        return t.cast(date, base + expires)
    if isinstance(expires, datetime):
        return expires.date()
    if isinstance(expires, date):
        return expires
    m.die(f"Unexpected expiry type: canonicalizeExpiryDate({base}, {expires})")
    return None


def parseDoc(doc: t.SpecT) -> None:
    # Look through the doc for any additional metadata information that might be needed.

    for el in h.findAll(".replace-with-note-class", doc):
        h.removeClass(el, "replace-with-note-class")
        h.addClass(doc, el, doc.md.noteClass)
    for el in h.findAll(".replace-with-issue-class", doc):
        h.removeClass(el, "replace-with-issue-class")
        h.addClass(doc, el, doc.md.issueClass)
    for el in h.findAll(".replace-with-assertion-class", doc):
        h.removeClass(el, "replace-with-assertion-class")
        h.addClass(doc, el, doc.md.assertionClass)
    for el in h.findAll(".replace-with-advisement-class", doc):
        h.removeClass(el, "replace-with-advisement-class")
        h.addClass(doc, el, doc.md.advisementClass)

    if (
        "feedback-header" in doc.md.boilerplate
        and "issues-index" in doc.md.boilerplate
        and h.find("." + doc.md.issueClass, doc) is not None
    ):
        # There's at least one inline issue.
        doc.md.issues.append(("Inline In Spec", "#issues-index"))


def join(*sources: MetadataManager | None) -> MetadataManager:
    """
    MetadataManager is a monoid
    """
    md = MetadataManager()
    md.hasMetadata = any(x.hasMetadata for x in sources if x)
    for mdsource in sources:
        if mdsource is None:
            continue
        for k in mdsource.manuallySetKeys:
            mdentry = keys.KNOWN_KEYS[k]
            md.addParsedData(k, getattr(mdsource, mdentry.attrName))
        for k, v in mdsource.otherMetadata.items():
            md.otherMetadata.setdefault(k, []).extend(v)
    return md
