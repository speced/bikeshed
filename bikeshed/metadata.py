# pylint: disable=unused-argument

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
from collections import OrderedDict, defaultdict, Counter
from datetime import date, datetime, timedelta
from functools import partial

from isodate import Duration, parse_duration

from . import config, constants, datablocks, markdown, h, messages as m, repository, t
from .translate import _

if t.TYPE_CHECKING:
    from .line import Line

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
        self.status: str | None = None
        self.rawStatus: str | None = None

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
        self.complainAbout: config.BoolSet = config.BoolSet(["mixed-indents"])
        self.customTextMacros: list[tuple[str, str]] = []
        self.customWarningText: list[str] = []
        self.customWarningTitle: str | None = None
        self.date: date = datetime.utcnow().date()
        self.deadline: date | None = None
        self.defaultHighlight: str | None = None
        self.defaultBiblioDisplay: str = "index"
        self.defaultRefStatus: str | None = None
        self.editors: list[dict[str, str | None]] = []
        self.editorTerm: dict[str, str] = {"singular": _("Editor"), "plural": _("Editors")}
        self.expires: date | None = None
        self.externalInfotrees: config.BoolSet = config.BoolSet(default=False)
        self.favicon: str | None = None
        self.forceCrossorigin: bool = False
        self.group: str | None = None
        self.h1: str | None = None
        self.ignoreCanIUseUrlFailure: list[str] = []
        self.ignoredTerms: list[str] = []
        self.ignoredVars: list[str] = []
        self.implementationReport: str | None = None
        self.includeCanIUsePanels: bool = False
        self.includeMdnPanels: bool = False
        self.indent: int = 4
        self.inferCSSDfns: bool = False
        self.informativeClasses: list[str] = []
        self.inlineGithubIssues: bool = False
        self.inlineTagCommands: dict[str, str] = {}
        self.issueClass: str = "issue"
        self.issues: list[tuple[str, str]] = []
        self.issueTrackerTemplate: str | None = None
        self.lineNumbers: bool = False
        self.linkDefaults: t.LinkDefaultsT = defaultdict(list)
        self.localBoilerplate: config.BoolSet = config.BoolSet(default=False)
        self.logo: str | None = None
        self.mailingList: str | None = None
        self.mailingListArchives: str | None = None
        self.markupShorthands: config.BoolSet = config.BoolSet(
            ["css", "dfn", "biblio", "markup", "http", "idl", "algorithm"]
        )
        self.maxToCDepth: int | float | None = float("inf")
        self.metadataInclude: config.BoolSet = config.BoolSet(default=True)
        self.metadataOrder: list[str] = ["*", "!*"]
        self.noAbstract: bool = False
        self.noEditor: bool = False
        self.noteClass: str = "note"
        self.opaqueElements: list[str] = ["pre", "xmp", "script", "style"]
        self.prepTR: bool = False
        self.previousEditors: list[dict[str, str | None]] = []
        self.previousVersions: list[dict[str, str]] = []
        self.removeMultipleLinks: bool = False
        self.repository: repository.Repository | None = None
        self.requiredIDs: list[str] = []
        self.slimBuildArtifact: bool = False
        self.statusText: list[str] = []
        self.testSuite: str | None = None
        self.title: str | None = None
        self.toggleDiffs: bool = False
        self.TR: str | None = None
        self.trackingVectorAltText: str = _("(This is a tracking vector.)")
        self.trackingVectorClass: str = "tracking-vector"
        self.trackingVectorImage: str | None = None
        self.trackingVectorImageHeight: str = "64"
        self.trackingVectorImageWidth: str = "46"
        self.trackingVectorTitle: str = _("There is a tracking vector here.")
        self.translateIDs: dict[str, str] = {}
        self.translations: list[dict[str, str]] = []
        self.useDfnPanels: bool = True
        self.useIAutolinks: bool = False
        self.versionHistory: list[str] = []
        self.warning: str | None = None
        self.workStatus: str | None = None
        self.wptDisplay: str = "none"
        self.wptPathPrefix: str | None = None
        self.imgAutoSize: bool = True

        self.otherMetadata: OrderedDict[str, list[t.NodesT]] = OrderedDict()

        self.manuallySetKeys: set[str] = set()

    def addData(self, key: str, val: str, lineNum: str | int | None = None) -> MetadataManager:
        key = key.strip()
        if key in ["Abstract"]:
            val = val.strip("\n")
        else:
            val = val.strip()

        if key.startswith("!"):
            self.allData[key].append(val)
            key = key[1:]
            self.otherMetadata.setdefault(key, []).append(val)
            return self

        if key not in ("ED", "TR", "URL"):
            key = key.title()
        self.allData[key].append(val)

        if key not in knownKeys:
            m.die(f'Unknown metadata key "{key}". Prefix custom keys with "!".', lineNum=lineNum)
            return self
        md = knownKeys[key]

        val = md.parse(key, val, lineNum=lineNum)

        self.addParsedData(key, val)
        return self

    def addParsedData(self, key: str, val: t.Any) -> MetadataManager:
        md = knownKeys[key]
        result = md.join(getattr(self, md.attrName), val)
        setattr(self, md.attrName, result)
        self.manuallySetKeys.add(key)
        return self

    def computeImplicitMetadata(self, doc: t.SpecT) -> None:
        # Do some "computed metadata", based on the value of other metadata.
        # Only call this when you're sure all metadata sources are parsed.
        if self.group == "byos":
            self.boilerplate.default = False
        if not self.repository and doc:
            self.repository = getSpecRepository(doc)
        if (
            isinstance(self.repository, repository.GithubRepository)
            and "feedback-header" in self.boilerplate
            and "repository-issue-tracking" in self.boilerplate
        ):
            self.issues.append(("GitHub", self.repository.formatIssueUrl()))
        self.status = config.canonicalizeStatus(self.rawStatus, self.group)

        self.expires = canonicalizeExpiryDate(self.date, self.expires)

        # for TR document, defaults to TR
        # fallbacks to ED
        if (self.canonicalURL is None or self.canonicalURL == "TR") and self.TR:
            self.canonicalURL = self.TR
        elif (self.canonicalURL is None or self.canonicalURL == "ED") and self.ED:
            self.canonicalURL = self.ED

        if self.displayShortname:
            self.shortname = self.displayShortname.lower()

    def validate(self) -> bool:
        if self.group == "byos":
            return True

        if not self.hasMetadata:
            m.die("The document requires at least one <pre class=metadata> block.")
            return False

        if self.status in ("w3c/IG-NOTE", "w3c/WG-NOTE"):
            m.die(
                f"Under Process2021, {self.status} is no longer a valid status. Use NOTE (or one of its variants NOTE-ED, NOTE-FPWD, NOTE-WD) instead."
            )

        # { MetadataManager attr : metadata name (for printing) }
        requiredSingularKeys = {
            "status": "Status",
            "shortname": "Shortname",
            "title": "Title",
        }
        recommendedSingularKeys = {}
        requiredMultiKeys = {}

        if self.status not in config.noEDStatuses:
            requiredSingularKeys["ED"] = "ED"
        if self.status in config.deadlineStatuses:
            requiredSingularKeys["deadline"] = "Deadline"
        if self.status in config.datedStatuses:
            recommendedSingularKeys["date"] = "Date"
        if self.status in config.snapshotStatuses:
            requiredSingularKeys["TR"] = "TR"
            requiredMultiKeys["issues"] = "Issue Tracking"
        if self.status in config.implementationStatuses:
            requiredSingularKeys["implementationReport"] = "Implementation Report"
        if self.status not in config.unlevelledStatuses:
            requiredSingularKeys["level"] = "Level"
        if self.status not in config.shortToLongStatus:
            m.die(f"Unknown Status '{self.status}' used.")
        if not self.noEditor:
            requiredMultiKeys["editors"] = "Editor"
        if not self.noAbstract:
            requiredMultiKeys["abstract"] = "Abstract"
        if self.group and self.group.lower() == "csswg":
            requiredSingularKeys["workStatus"] = "Work Status"
        if self.group and self.group.lower() == "wg21":
            requiredSingularKeys["audience"] = "Audience"

        errors = []
        warnings = []
        for attrName, name in requiredSingularKeys.items():
            if getattr(self, attrName) is None:
                errors.append(f"    Missing a '{name}' entry.")
        for attrName, name in recommendedSingularKeys.items():
            if getattr(self, attrName) is None:
                warnings.append(f"    You probably want to provide a '{name}' entry.")
        for attrName, name in requiredMultiKeys.items():
            if len(getattr(self, attrName)) == 0:
                errors.append(f"    Must provide at least one '{name}' entry.")
        if warnings:
            m.warn("Some recommended metadata is missing:\n" + "\n".join(warnings))
        if errors:
            m.die("Not all required metadata was provided:\n" + "\n".join(errors))
            return False
        return True

    def fillTextMacros(self, macros: t.DefaultDict[str, str], doc: t.SpecT) -> None:
        # Fills up a set of text macros based on metadata.
        if self.title:
            macros["title"] = self.title
            macros["spectitle"] = self.title
        if self.h1:
            macros["spectitle"] = self.h1
        if self.displayShortname:
            macros["shortname"] = self.displayShortname
        if self.statusText:
            macros["statustext"] = "\n".join(markdown.parse(self.statusText, self.indent))
        else:
            macros["statustext"] = ""
        macros["level"] = str(self.level)
        if self.displayVshortname:
            macros["vshortname"] = self.displayVshortname
        if self.status == "FINDING" and self.group:
            macros["longstatus"] = f"Finding of the {self.group}"
        elif self.status in config.shortToLongStatus:
            macros["longstatus"] = config.shortToLongStatus[self.status]
        else:
            macros["longstatus"] = ""
        if self.status in ("w3c/LCWD", "w3c/FPWD"):
            macros["status"] = "WD"
        elif self.status in ("w3c/NOTE-FPWD", "w3c/NOTE-WD"):
            macros["status"] = "DNOTE"
        elif self.status in ("w3c/WG-NOTE", "w3c/IG-NOTE"):
            macros["status"] = "NOTE"
        elif self.status == "w3c/NOTE-ED":
            macros["status"] = "ED"
        elif self.rawStatus:
            macros["status"] = self.rawStatus
        if self.workStatus:
            macros["workstatus"] = self.workStatus
        if self.TR:
            macros["latest"] = self.TR
        if self.abstract:
            abstractLines = datablocks.transformDataBlocks(doc, self.abstract)
            macros["abstract"] = "\n".join(markdown.parse(abstractLines, self.indent))
            macros["abstractattr"] = h.escapeAttr("  ".join(abstractLines).replace("<<", "<").replace(">>", ">"))
        elif self.noAbstract:
            macros["abstract"] = ""
            macros["abstractattr"] = ""
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
        if self.status in config.snapshotStatuses:
            macros["version"] = "https://www.w3.org/TR/{year}/{status}-{vshortname}-{cdate}/".format(**macros)
            macros["history"] = f"https://www.w3.org/standards/history/{self.displayVshortname}"
        elif self.ED:
            macros["version"] = self.ED
        macros["annotations"] = constants.testAnnotationURL
        if doc and self.vshortname in doc.testSuites:
            macros["testsuite"] = doc.testSuites[self.vshortname].vshortname
        if self.warning and len(self.warning) >= 2:
            macros["replacedby"] = self.warning[1]
        if self.warning and len(self.warning) >= 3:
            macros["snapshotid"] = self.warning[2]
        if self.warning and len(self.warning) >= 4:
            macros["snapshoturl"] = self.warning[3]
        if self.logo:
            macros["logo"] = self.logo
        if self.repository:
            macros["repository"] = self.repository.name or _("Unnamed Repo")
            macros["repositoryurl"] = self.repository.url
        if self.mailingList:
            macros["mailinglist"] = self.mailingList
        if self.mailingListArchives:
            macros["mailinglistarchives"] = self.mailingListArchives
        if self.status == "w3c/FPWD":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-WD"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#FPWD"
        elif self.status in ("w3c/NOTE-FPWD", "w3c/NOTE-WD"):
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-DNOTE"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#DNOTE"
        elif self.status == "FINDING":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-NOTE"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#FINDING"
        elif self.status == "w3c/CG-DRAFT":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/cg-draft"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#CG-DRAFT"
        elif self.status == "w3c/CG-FINAL":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/cg-final"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#CG-FINAL"
        elif self.status == "w3c/NOTE-ED":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2021/W3C-ED"
            macros["w3c-status-url"] = "https://www.w3.org/standards/types#ED"
        else:
            shortStatus = (
                self.rawStatus.partition("/")[2] if (self.rawStatus and "/" in str(self.rawStatus)) else self.rawStatus
            )
            macros["w3c-stylesheet-url"] = f"https://www.w3.org/StyleSheets/TR/2021/W3C-{shortStatus}"
            macros["w3c-status-url"] = f"https://www.w3.org/standards/types#{shortStatus}"
        if self.customWarningText is not None:
            macros["customwarningtext"] = "\n".join(markdown.parse(self.customWarningText, self.indent))
        if self.customWarningTitle is not None:
            macros["customwarningtitle"] = self.customWarningTitle
        # Custom macros
        for name, text in self.customTextMacros:
            macros[name.lower()] = text


if t.TYPE_CHECKING:

    class ParseFunc(t.Protocol):
        def __call__(self, key: str, val: str, lineNum: str | int | None) -> t.Any:
            ...


def parseDate(key: str, val: str, lineNum: str | int | None) -> date | None:
    if val == "now":
        return datetime.utcnow().date()
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        m.die(f'The {key} field must be in the format YYYY-MM-DD - got "{val}" instead.', lineNum=lineNum)
        return None


def parseDateOrDuration(key: str, val: str, lineNum: str | int | None) -> date | timedelta | None:
    if val == "now":
        return datetime.utcnow().date()
    if val == "never" or boolish(val) is False:
        return None
    try:
        if val.startswith("P"):
            return t.cast(timedelta, parse_duration(val))
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        m.die(
            f"The {key} field must be an ISO 8601 duration, a date in the format YYYY-MM-DD, now, never, false, no, n, or off. Got '{val}' instead.",
            lineNum=lineNum,
        )
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


def parseLevel(key: str, val: str, lineNum: str | int | None) -> str:
    val = val.lower().strip()
    if val == "none":
        return ""
    return val.strip()


def parseInteger(key: str, val: str, lineNum: str | int | None) -> int:
    return int(val)


def parseBoolean(key: str, val: str, lineNum: str | int | None) -> bool | None:
    b = boolish(val)
    if b is None:
        m.die(f"The {key} field must be true/false, yes/no, y/n, or on/off. Got '{val}' instead.", lineNum=lineNum)
    return b


def parseSoftBoolean(key: str, val: str, lineNum: str | int | None) -> bool | t.Literal["maybe"] | None:
    b = boolish(val)
    if b is not None:
        return b
    if val.lower() in ["maybe", "if possible", "if needed"]:
        return "maybe"
    m.die(f"The {key} field must be boolish, or 'maybe'. Got '{val}' instead.", lineNum=lineNum)
    return None


def boolish(val: str) -> bool | None:
    if val.lower() in ("true", "yes", "y", "on"):
        return True
    if val.lower() in ("false", "no", "n", "off"):
        return False
    return None


def parseWarning(key: str, val: str, lineNum: str | int | None) -> tuple[str, ...] | None:
    if val.lower() == "obsolete":
        return ("warning-obsolete",)
    if val.lower() == "not ready":
        return ("warning-not-ready",)
    if val.lower() == "custom":
        return ("warning-custom",)
    match = re.match(r"Commit +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-commit", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Branch +([^ ]+) +(.+) +replaced by +(.+)", val, re.I)
    if match:
        return "warning-branch", match.group(3), match.group(1), match.group(2)
    match = re.match(r"Replaced By +(.+)", val, re.I)
    if match:
        return "warning-replaced-by", match.group(1)
    match = re.match(r"New Version +(.+)", val, re.I)
    if match:
        return "warning-new-version", match.group(1)
    m.die(
        f"""Unknown value "{val}" for "{key}" metadata. Expected one of:
  obsolete
  not ready
  replaced by [new url]
  new version [new url]
  commit [snapshot id] [snapshot url] replaced by [master url]
  branch [branch name] [branch url] replaced by [master url]
  custom""",
        lineNum=lineNum,
    )
    return None


def parseEditor(key: str, val: str, lineNum: None | str | int) -> list[dict[str, str | None]]:
    pieces = [h.unescape(piece.strip()) for piece in val.split(",")]

    def looksLinkish(string: str) -> bool:
        return bool(re.match(r"\w+:", string)) or looksEmailish(string)

    def looksEmailish(string: str) -> bool:
        return bool(re.match(r".+@.+\..+", string))

    data = {
        "name": pieces[0],
        "w3cid": None,
        "org": None,
        "orglink": None,
        "link": None,
        "email": None,
    }
    # Handle well-known pieces, split off the ambiguous ones
    ambiguousPieces = []
    for piece in pieces[1:]:
        if re.match(r"w3cid \d+$", piece) and data["w3cid"] is None:
            data["w3cid"] = piece[6:]
        else:
            ambiguousPieces.append(piece)
    if len(ambiguousPieces) == 3 and looksLinkish(ambiguousPieces[1]) and looksLinkish(ambiguousPieces[2]):
        # [org, email, url] or [org, url, email]
        data["org"] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data["email"] = ambiguousPieces[1]
            data["link"] = ambiguousPieces[2]
        else:
            data["link"] = ambiguousPieces[1]
            data["email"] = ambiguousPieces[2]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[0]) and looksLinkish(ambiguousPieces[1]):
        # [email, url] or [url, email]
        if looksEmailish(ambiguousPieces[0]):
            data["email"] = ambiguousPieces[0]
            data["link"] = ambiguousPieces[1]
        else:
            data["link"] = ambiguousPieces[0]
            data["email"] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[1]):
        # [org, email] or [org, url]
        data["org"] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data["email"] = ambiguousPieces[1]
        else:
            data["link"] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 1:
        # [org], [email], or [url]
        if looksLinkish(ambiguousPieces[0]):
            if looksEmailish(ambiguousPieces[0]):
                data["email"] = ambiguousPieces[0]
            else:
                data["link"] = ambiguousPieces[0]
        else:
            data["org"] = ambiguousPieces[0]
    elif len(ambiguousPieces) == 0:
        pass
    else:
        m.die(
            f"'{key}' format is '<name>, <company>?, <email-or-contact-page>?'. Got:\n{val}",
            lineNum=lineNum,
        )
        return []
    # Check if the org ends with a link
    if data["org"] is not None and " " in str(data["org"]) and looksLinkish(data["org"].split()[-1]):
        pieces = data["org"].split()
        data["orglink"] = pieces[-1]
        data["org"] = " ".join(pieces[:-1])
    # Check if the name ends with an ID.
    # TODO: remove this, it's redundant with the "w3cid ####" piece
    if data["name"] and re.search(r"\s\d+$", data["name"]):
        pieces = data["name"].split()
        data["w3cid"] = pieces[-1]
        data["name"] = " ".join(pieces[:-1])
    return [data]


def parseCommaSeparated(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [term.strip().lower() for term in val.split(",")]


def parseIdList(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [term.strip() for term in val.split(",")]


def parseLinkDefaults(key: str, val: str, lineNum: str | int | None) -> t.LinkDefaultsT:
    defaultSpecs: t.LinkDefaultsT = defaultdict(list)
    for default in val.split(","):
        match = re.match(
            r"^([\w\d-]+)  (?:\s+\( ({}) (?:\s+(snapshot|current))? \) )  \s+(.*)$".format(
                "|".join(config.dfnTypes.union(["dfn"]))
            ),
            default.strip(),
            re.X,
        )
        if match:
            spec = match.group(1)
            type = match.group(2)
            status = match.group(3)
            terms = match.group(4).split("/")
            dfnFor = None
            for term in terms:
                defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
        else:
            m.die(
                f"'{key}' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{default}",
                lineNum=lineNum,
            )
            continue
    return defaultSpecs


def parseBoilerplate(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    boilerplate = config.BoolSet(default=True)
    for command in val.split(","):
        pieces = command.lower().strip().split()
        if len(pieces) != 2:
            m.die(
                f"Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{command}",
                lineNum=lineNum,
            )
            continue
        if pieces[0] == "omit":
            # legacy syntax; allows "omit foo" in addition to the normal "foo off"/etc
            boilerplate[pieces[1]] = False
        else:
            onoff = boolish(pieces[1])
            if onoff is None:
                m.die(
                    f"Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{command}",
                    lineNum=lineNum,
                )
                continue
            boilerplate[pieces[0]] = onoff
    return boilerplate


def parseBiblioDisplay(key: str, val: str, lineNum: str | int | None) -> str:
    val = val.strip().lower()
    if val in constants.biblioDisplay:
        return val
    m.die(f"'{key}' must be either 'inline', 'index', or 'direct'. Got '{val}'", lineNum=lineNum)
    return constants.biblioDisplay.index


def parseRefStatus(key: str, val: str, lineNum: str | int | None) -> str:
    val = val.strip().lower()
    if val == "dated":
        # Legacy term that used to be allowed
        val = "snapshot"
    if val in constants.refStatus:
        return val
    m.die(f"'{key}' must be either 'current' or 'snapshot'. Got '{val}'", lineNum=lineNum)
    return constants.refStatus.current


def parseComplainAbout(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    validLabels = frozenset(
        ["missing-example-ids", "broken-links", "accidental-2119", "missing-exposed", "mixed-indents"]
    )
    ret = parseBoolishList(key, val.lower(), default=False, validLabels=validLabels, lineNum=lineNum)
    return ret


def parseExternalInfotrees(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    return parseBoolishList(
        key,
        val.lower(),
        default=False,
        validLabels=frozenset(["anchors.bsdata", "link-defaults.infotree"]),
        lineNum=lineNum,
    )


def parseBoolishList(
    key: str,
    val: str,
    default: bool,
    validLabels: t.AbstractSet[str] | None = None,
    extraValues: dict[str, bool] | None = None,
    lineNum: str | int | None = None,
) -> config.BoolSet:
    # Parses anything defined as "label <boolish>, label <boolish>" into a BoolSet
    # Supply a list of valid labels if you want to have them checked,
    # and a dict of {value=>bool} pairs you want in addition to the standard boolish values
    boolset = config.BoolSet(default=default)

    if extraValues is None:
        extraValues = {}
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        name, _, boolstring = v.strip().rpartition(" ")
        if not name or not boolstring:
            m.die(f"{key} metadata pieces are a label and a boolean. Got:\n{v}", lineNum=lineNum)
            continue
        if validLabels and name not in validLabels:
            m.die(f"Unknown {key} label '{name}'.", lineNum=lineNum)
            continue
        if boolstring in extraValues:
            boolset[name] = extraValues[boolstring]
        else:
            onoff = boolish(boolstring)
            if isinstance(onoff, bool):
                boolset[name] = onoff
            else:
                m.die(f"{key} metadata pieces are a shorthand category and a boolean. Got:\n{v}", lineNum=lineNum)
                continue
    return boolset


def parseLinkedText(key: str, val: str, lineNum: str | int | None) -> list[tuple[str, str]]:
    # Parses anything defined as "text url, text url, text url" into a list of 2-tuples.
    entries = []
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        pieces = v.rsplit(" ", 1)
        entries.append((pieces[0], pieces[1]))
    return entries


def parseMarkupShorthands(key: str, val: str, lineNum: str | int | None) -> config.BoolSet:
    # Format is comma-separated list of shorthand category followed by boolean.
    # Output is a boolset of the shorthand categories.
    # TODO: Just call parseBoolistList instead
    vals = [v.strip() for v in val.lower().split(",")]
    ret = config.BoolSet(default=False)
    validCategories = frozenset(["css", "markup", "dfn", "biblio", "http", "idl", "markdown", "algorithm"])
    for v in vals:
        pieces = v.split()
        if len(pieces) != 2:
            m.die(
                f"Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{v}", lineNum=lineNum
            )
            continue
        name, boolstring = pieces
        if name not in validCategories:
            m.die(f"Unknown Markup Shorthand category '{name}'.", lineNum=lineNum)
            continue
        onoff = boolish(boolstring)
        if onoff is None:
            m.die(
                f"Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{v}",
                lineNum=lineNum,
            )
            continue
        ret[name] = onoff
    return ret


def parseInlineGithubIssues(key: str, val: str, lineNum: str | int | None) -> t.Literal[False] | str:
    val = val.lower()
    if val in ["title", "full"]:
        return val
    b = boolish(val)
    if b is None:
        m.die(f"Inline Github Issues must be 'title', 'full' or a boolish value. Got: '{val}'", lineNum=lineNum)
        return False
    if b is True:
        return "full"
    return False


def parseTextMacro(key: str, val: str, lineNum: str | int | None) -> list[tuple[str, str]]:
    # Each Text Macro line is just a macro name (must be uppercase)
    # followed by the text it expands to.
    try:
        name, text = val.lstrip().split(None, 1)
    except ValueError:
        m.die(f"Text Macro lines must contain a macro name followed by the macro text. Got:\n{val}", lineNum=lineNum)
        return []
    if not re.match(r"[A-Z0-9-]+$", name):
        m.die(f"Text Macro names must be all-caps and alphanumeric. Got '{name}'", lineNum=lineNum)
        return []
    return [(name, text)]


def parseWorkStatus(key: str, val: str, lineNum: str | int | None) -> str | None:
    # The Work Status is one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned).
    val = val.strip().lower()
    if val not in (
        "completed",
        "stable",
        "testing",
        "refining",
        "revising",
        "exploring",
        "rewriting",
        "abandoned",
    ):
        m.die(
            f"Work Status must be one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned). Got '{val}'. See http://fantasai.inkedblade.net/weblog/2011/inside-csswg/process for details.",
            lineNum=lineNum,
        )
        return None
    return val


def parseRepository(key: str, val: str, lineNum: str | int | None) -> repository.Repository | None:
    # Shortname followed by url, or just url.
    # If just url, I'll try to recognize the shortname from it; otherwise it's the url again.
    val = val.strip()
    pieces = val.split(None, 1)
    if len(pieces) == 2:
        return repository.Repository(url=pieces[0], name=pieces[1])
    if len(pieces) == 1:
        # Try to recognize a GitHub url
        match = re.match(r"https://github\.([\w.-]+)/([\w-]+)/([\w-]+)/?$", val)
        if match:
            return repository.GithubRepository(*match.groups())
        # If you just provide a user/repo pair, assume it's a github.com repo.
        # Will provide ways to opt into other repos when people care.
        match = re.match(r"([\w-]+)/([\w-]+)$", val)
        if match:
            return repository.GithubRepository("com", *match.groups())
        # Otherwise just use the url as the shortname
        return repository.Repository(url=val)
    m.die(f"Repository must be a url, optionally followed by a shortname. Got '{val}'", lineNum=lineNum)
    return None


def parseTranslateIDs(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    translations = {}
    for v in val.split(","):
        pieces = v.strip().split()
        if len(pieces) != 2:
            m.die(f"‘Translate IDs’ values must be an old ID followed by a new ID. Got '{v}'", lineNum=lineNum)
            continue
        old, new = pieces
        translations[old] = new
    return translations


def parseTranslation(key: str, val: str, lineNum: str | int | None) -> list[dict[str, str | None]]:
    # Format is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?
    pieces = val.split(",")
    if not (1 <= len(pieces) <= 3):
        m.die(
            f"Format of a Translation line is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?. Got:\n{val}",
            lineNum=lineNum,
        )
        return []
    firstParts = pieces[0].split()
    if len(firstParts) != 2:
        m.die(
            f"First part of a Translation line must be a lang-code followed by a url. Got:\n{pieces[0]}",
            lineNum=lineNum,
        )
        return []
    langCode, url = firstParts
    name = None
    nativeName = None
    for piece in pieces[1:]:
        k, v = piece.split(None, 1)
        if k.lower() == "name":
            name = v
        elif k.lower() == "native-name":
            nativeName = v
        else:
            m.die(
                f"Later parts of a Translation line must start with 'name' or 'native-name'. Got:\n{piece}",
                lineNum=lineNum,
            )
    return [{"lang-code": langCode, "url": url, "name": name, "native-name": nativeName}]


def parseAudience(key: str, val: str, lineNum: str | int | None) -> list[str]:
    # WG21 value
    values = [x.strip().upper() for x in val.strip().split(",")]
    if len(values) == 1 and values[0] == "ALL":
        return ["all"]
    elif len(values) >= 1:
        ret = []
        namedAudiences = {"CWG", "LWG", "EWG", "LEWG", "DIRECTION"}
        pseudonymAudiences = {
            "Concurrency": "SG1",
            "Modules": "SG2",
            "Networking": "SG4",
            "TM": "SG5",
            "Numerics": "SG6",
            "Reflection": "SG7",
            "FeatureTesting": "SG10",
            "UB": "SG12",
            "HMI": "SG13",
            "LowLatency": "SG14",
            "Tooling": "SG15",
            "Unicode": "SG16",
            "EWGI": "SG17",
            "LEWGI": "SG18",
            "MachineLearning": "SG19",
            "Education": "SG20",
            "Contracts": "SG21",
        }
        for v in values:
            if v in namedAudiences:
                ret.append(v)
            elif v in pseudonymAudiences:
                ret.append(pseudonymAudiences[v])
            elif re.match(r"WG\d+|SG\d+", v):
                ret.append(v)
            else:
                m.die(f"Unknown 'Audience' value '{v}'.", lineNum=lineNum)
                continue
        return ret
    else:
        m.die("Audience metadata must have at least one value if specified.")
        return []


def parseEditorTerm(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    values = [x.strip() for x in val.strip().split(",")]
    if len(values) == 2:
        return {"singular": values[0], "plural": values[1]}
    m.die(
        f"Editor Term metadata must be two comma-separated terms, giving the singular and plural term for editors. Got '{val}'.",
        lineNum=lineNum,
    )
    return {"singular": "Editor", "plural": "Editors"}


def parseMaxToCDepth(key: str, val: str, lineNum: str | int | None) -> int | float:
    if val.lower() == "none":
        return float("inf")
    try:
        v = int(val)
    except ValueError:
        m.die(
            f"Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{val}'.",
            lineNum=lineNum,
        )
        return float("inf")
    if not (1 <= v <= 5):
        m.die(
            f"Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{val}'.",
            lineNum=lineNum,
        )
        return float("inf")
    return v


def parseMetadataOrder(key: str, val: str, lineNum: str | int | None) -> list[str]:
    pieces = [x.strip() for x in val.split(",")]
    return pieces


def parseWptDisplay(key: str, val: str, lineNum: str | int | None) -> str:
    val = val.lower()
    if val in ("none", "inline", "open", "closed"):
        return val
    m.die(
        f"WPT Display metadata only accepts the values 'none', 'closed', 'open', or 'inline'. Got '{val}'.",
        lineNum=lineNum,
    )
    return "none"


def parsePreviousVersion(key: str, val: str, lineNum: str | int | None) -> list[dict[str, str]]:
    biblioMatch = re.match(r"from biblio(\s+\S+)?", val.lower())
    if biblioMatch:
        if biblioMatch.group(1):
            return [{"type": "from-biblio", "value": biblioMatch.group(1).strip()}]
        return [{"type": "from-biblio-implicit"}]
    return [{"type": "url", "value": val}]


def parseInlineTagCommand(key: str, val: str, lineNum: str | int | None) -> dict[str, str]:
    tag, _, command = val.strip().partition(" ")
    command = command.strip()
    return {tag: command}


def parse(lines: t.Sequence[Line]) -> tuple[list[Line], MetadataManager]:
    # Given HTML document text, in the form of an array of text lines,
    # extracts all <pre class=metadata> lines and parses their contents.
    # Returns the text lines, with the metadata-related lines removed,
    # and a filled MetadataManager object

    newlines = []
    inMetadata = False
    lastKey = None
    endTag = None
    md = MetadataManager()
    for line in lines:
        if not inMetadata and re.match(r"<(pre|xmp) [^>]*class=[^>]*metadata[^>]*>", line.text):
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
            if line.text.strip() == "" and lastKey not in ("Abstract", "Status Text"):
                continue
            if lastKey and (line.text.strip() == "" or re.match(r"\s+", line.text)):
                # empty lines, or lines that start with 1+ spaces, continue previous key
                md.addData(lastKey, line.text, lineNum=line.i)
            elif re.match(r"([^:]+):\s*(.*)", line.text):
                match = re.match(r"([^:]+):\s*(.*)", line.text)
                assert match is not None
                md.addData(match.group(1), match.group(2), lineNum=line.i)
                lastKey = match.group(1)
            else:
                m.die(
                    f"Incorrectly formatted metadata line:\n{line.text}",
                    lineNum=line.i,
                )
                continue
        elif re.match(r"\s*<h1[^>]*>.*?</h1>", line.text):
            if md.title is None:
                match = re.match(r"\s*<h1[^>]*>(.*?)</h1>", line.text)
                assert match is not None
                title = match.group(1)
                md.addData("Title", title, lineNum=line.i)
            newlines.append(line)
        else:
            newlines.append(line)
    indentInfo = inferIndent(newlines)
    if "Indent" not in md.manuallySetKeys and indentInfo.size:
        md.indent = indentInfo.size
    if "mixed-indents" in md.complainAbout and indentInfo.char:
        checkForMixedIndents(newlines, indentInfo)
    return newlines, md


@dataclasses.dataclass
class IndentInfo:
    size: int | None = None
    char: str | None = None
    spaceLines: int = 0
    tabLines: int = 0
    totalLines: int = 0


def inferIndent(lines: t.Sequence[Line]) -> IndentInfo:
    # If the document uses space indentation,
    # infer what the indent size is by seeing what % of indents
    # are divisible by various values.
    # (If it uses tabs, or no indents at all, returns None.)
    indentSizes: Counter[int] = Counter()
    info = IndentInfo()
    for line in lines:
        match = re.match("( +)", line.text)
        if match:
            indentSizes[len(match.group(1))] += 1
            info.spaceLines += 1
        elif line.text[0:1] == "\t":
            info.tabLines += 1
        info.totalLines += 1
    # If very few lines are indented at all, just bail
    if (info.spaceLines + info.tabLines) < info.totalLines / 20:
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
        info.size = evenDivisions.most_common(1)[0][0]
    return info


def checkForMixedIndents(lines: t.Sequence[Line], info: IndentInfo) -> None:
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
                r"origin\tgit@github\.([\w.-]+):([\w-]+)/([\w-]+)\.git \(\w+\)",
                r"origin\thttps://github\.([\w.-]+)/([\w-]+)/([\w-]+)\.git \(\w+\)",
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
            mdentry = knownKeys[k]
            md.addParsedData(k, getattr(mdsource, mdentry.attrName))
        for k, v in mdsource.otherMetadata.items():
            md.otherMetadata.setdefault(k, []).extend(v)
    return md


@dataclasses.dataclass
class Metadata:
    humanName: str
    attrName: str
    join: t.Callable[[t.Any, t.Any], t.Any]
    parse: ParseFunc


if t.TYPE_CHECKING:
    JoinA = t.TypeVar("JoinA")
    JoinB = t.TypeVar("JoinB")


def joinValue(a: JoinA, b: JoinB) -> JoinB:
    return b


def joinList(a: t.Sequence[JoinA], b: t.Sequence[JoinB]) -> t.Sequence[JoinA | JoinB]:
    return a + b  # type: ignore[operator, no-any-return]


def joinDict(a: t.Mapping[str, JoinA], b: t.Mapping[str, JoinB]) -> dict[str, JoinA | JoinB]:
    x: dict[str, JoinA | JoinB] = {}
    x.update(a)
    x.update(b)
    return x


def joinBoolSet(a: config.BoolSet, b: config.BoolSet) -> config.BoolSet:
    x = config.BoolSet()
    x.update(a)
    x.update(b)
    return x


def joinDdList(
    a: defaultdict[str, list[JoinA]], b: defaultdict[str, list[JoinB]]
) -> defaultdict[str, list[JoinA | JoinB]]:
    x: defaultdict[str, list[JoinA | JoinB]] = defaultdict(list)
    x.update(a)  # type: ignore[arg-type]
    x.update(b)  # type: ignore[arg-type]
    return x


def parseLiteral(key: str, val: str, lineNum: str | int | None) -> str:
    return val


def parseLiteralOrNone(key: str, val: str, lineNum: str | int | None) -> str | None:
    if val.lower() == "none":
        return None
    return val


def parseLiteralCaseless(key: str, val: str, lineNum: str | int | None) -> str:
    return val.lower()


def parseLiteralList(key: str, val: str, lineNum: str | int | None) -> list[str]:
    return [val]


knownKeys = {
    "Abstract": Metadata("Abstract", "abstract", joinList, parseLiteralList),
    "Advisement Class": Metadata("Advisement Class", "advisementClass", joinValue, parseLiteral),
    "Assertion Class": Metadata("Assertion Class", "assertionClass", joinValue, parseLiteral),
    "Assume Explicit For": Metadata("Assume Explicit For", "assumeExplicitFor", joinValue, parseBoolean),
    "At Risk": Metadata("At Risk", "atRisk", joinList, parseLiteralList),
    "Audience": Metadata("Audience", "audience", joinList, parseAudience),
    "Block Elements": Metadata("Block Elements", "blockElements", joinList, parseCommaSeparated),
    "Boilerplate": Metadata("Boilerplate", "boilerplate", joinBoolSet, parseBoilerplate),
    "Can I Use Url": Metadata("Can I Use URL", "canIUseURLs", joinList, parseLiteralList),
    "Canonical Url": Metadata("Canonical URL", "canonicalURL", joinValue, parseLiteral),
    "Complain About": Metadata("Complain About", "complainAbout", joinBoolSet, parseComplainAbout),
    "Custom Warning Text": Metadata("Custom Warning Text", "customWarningText", joinList, parseLiteralList),
    "Custom Warning Title": Metadata("Custom Warning Title", "customWarningTitle", joinValue, parseLiteral),
    "Date": Metadata("Date", "date", joinValue, parseDate),
    "Deadline": Metadata("Deadline", "deadline", joinValue, parseDate),
    "Default Biblio Display": Metadata("Default Biblio Display", "defaultBiblioDisplay", joinValue, parseBiblioDisplay),
    "Default Biblio Status": Metadata(
        "Default Biblio Status", "defaultRefStatus", joinValue, parseRefStatus
    ),  # synonym of "Default Ref Status"
    "Default Highlight": Metadata("Default Highlight", "defaultHighlight", joinValue, parseLiteral),
    "Default Ref Status": Metadata("Default Ref Status", "defaultRefStatus", joinValue, parseRefStatus),
    "ED": Metadata("ED", "ED", joinValue, parseLiteral),
    "Editor": Metadata("Editor", "editors", joinList, parseEditor),
    "Editor Term": Metadata("Editor Term", "editorTerm", joinValue, parseEditorTerm),
    "Expires": Metadata("Expires", "expires", joinValue, parseDateOrDuration),
    "External Infotrees": Metadata("External Infotrees", "externalInfotrees", joinBoolSet, parseExternalInfotrees),
    "Favicon": Metadata("Favicon", "favicon", joinValue, parseLiteral),
    "Force Crossorigin": Metadata("Force Crossorigin", "forceCrossorigin", joinValue, parseBoolean),
    "Former Editor": Metadata("Former Editor", "previousEditors", joinList, parseEditor),
    "Group": Metadata("Group", "group", joinValue, parseLiteral),
    "H1": Metadata("H1", "h1", joinValue, parseLiteral),
    "Ignore Can I Use Url Failure": Metadata(
        "Ignore Can I Use Url Failure", "ignoreCanIUseUrlFailure", joinList, parseLiteralList
    ),
    "Ignored Terms": Metadata("Ignored Terms", "ignoredTerms", joinList, parseCommaSeparated),
    "Ignored Vars": Metadata("Ignored Vars", "ignoredVars", joinList, parseCommaSeparated),
    "Image Auto Size": Metadata("Image Auto Size", "imgAutoSize", joinValue, parseBoolean),
    "Implementation Report": Metadata("Implementation Report", "implementationReport", joinValue, parseLiteral),
    "Include Can I Use Panels": Metadata("Include Can I Use Panels", "includeCanIUsePanels", joinValue, parseBoolean),
    "Include Mdn Panels": Metadata("Include Mdn Panels", "includeMdnPanels", joinValue, parseSoftBoolean),
    "Indent": Metadata("Indent", "indent", joinValue, parseInteger),
    "Infer Css Dfns": Metadata("Infer Css Dfns", "inferCSSDfns", joinValue, parseBoolean),
    "Informative Classes": Metadata("Informative Classes", "informativeClasses", joinList, parseCommaSeparated),
    "Inline Github Issues": Metadata("Inline Github Issues", "inlineGithubIssues", joinValue, parseInlineGithubIssues),
    "Inline Tag Command": Metadata("Inline Tag Command", "inlineTagCommands", joinDict, parseInlineTagCommand),
    "Issue Class": Metadata("Issue Class", "issueClass", joinValue, parseLiteral),
    "Issue Tracker Template": Metadata("Issue Tracker Template", "issueTrackerTemplate", joinValue, parseLiteral),
    "Issue Tracking": Metadata("Issue Tracking", "issues", joinList, parseLinkedText),
    "Level": Metadata("Level", "level", joinValue, parseLevel),
    "Line Numbers": Metadata("Line Numbers", "lineNumbers", joinValue, parseBoolean),
    "Link Defaults": Metadata("Link Defaults", "linkDefaults", joinDdList, parseLinkDefaults),
    "Local Boilerplate": Metadata(
        "Local Boilerplate", "localBoilerplate", joinBoolSet, partial(parseBoolishList, default=False)
    ),
    "Logo": Metadata("Logo", "logo", joinValue, parseLiteral),
    "Mailing List Archives": Metadata("Mailing List Archives", "mailingListArchives", joinValue, parseLiteral),
    "Mailing List": Metadata("Mailing List", "mailingList", joinValue, parseLiteral),
    "Markup Shorthands": Metadata("Markup Shorthands", "markupShorthands", joinBoolSet, parseMarkupShorthands),
    "Max Toc Depth": Metadata("Max ToC Depth", "maxToCDepth", joinValue, parseMaxToCDepth),
    "Metadata Include": Metadata(
        "Metadata Include", "metadataInclude", joinBoolSet, partial(parseBoolishList, default=True)
    ),
    "Metadata Order": Metadata("Metadata Order", "metadataOrder", joinValue, parseMetadataOrder),
    "No Abstract": Metadata("No Abstract", "noAbstract", joinValue, parseBoolean),
    "No Editor": Metadata("No Editor", "noEditor", joinValue, parseBoolean),
    "Note Class": Metadata("Note Class", "noteClass", joinValue, parseLiteral),
    "Opaque Elements": Metadata("Opaque Elements", "opaqueElements", joinList, parseCommaSeparated),
    "Prepare For Tr": Metadata("Prepare For Tr", "prepTR", joinValue, parseBoolean),
    "Previous Version": Metadata("Previous Version", "previousVersions", joinList, parsePreviousVersion),
    "Remove Multiple Links": Metadata("Remove Multiple Links", "removeMultipleLinks", joinValue, parseBoolean),
    "Repository": Metadata("Repository", "repository", joinValue, parseRepository),
    "Required Ids": Metadata("Required Ids", "requiredIDs", joinList, parseIdList),
    "Revision": Metadata("Revision", "level", joinValue, parseLevel),
    "Shortname": Metadata("Shortname", "displayShortname", joinValue, parseLiteral),
    "Slim Build Artifact": Metadata("Slim Build Artifact", "slimBuildArtifact", joinValue, parseBoolean),
    "Status Text": Metadata("Status Text", "statusText", joinList, parseLiteralList),
    "Status": Metadata("Status", "rawStatus", joinValue, parseLiteral),
    "Test Suite": Metadata("Test Suite", "testSuite", joinValue, parseLiteral),
    "Text Macro": Metadata("Text Macro", "customTextMacros", joinList, parseTextMacro),
    "Title": Metadata("Title", "title", joinValue, parseLiteral),
    "Toggle Diffs": Metadata("Toggle Diffs", "toggleDiffs", joinValue, parseBoolean),
    "TR": Metadata("TR", "TR", joinValue, parseLiteral),
    "Tracking Vector Class": Metadata("Tracking Vector Class", "trackingVectorClass", joinValue, parseLiteralOrNone),
    "Tracking Vector Image": Metadata("Tracking Vector Image", "trackingVectorImage", joinValue, parseLiteralOrNone),
    "Tracking Vector Image Width": Metadata(
        "Tracking Vector Image Width", "trackingVectorImageWidth", joinValue, parseLiteral
    ),
    "Tracking Vector Image Height": Metadata(
        "Tracking Vector Image Height", "trackingVectorImageHeight", joinValue, parseLiteral
    ),
    "Tracking Vector Alt Text": Metadata("Tracking Vector Alt Text", "trackingVectorAltText", joinValue, parseLiteral),
    "Tracking Vector Title": Metadata("Tracking Vector Title", "trackingVectorTitle", joinValue, parseLiteral),
    "Translate Ids": Metadata("Translate Ids", "translateIDs", joinDdList, parseTranslateIDs),
    "Translation": Metadata("Translation", "translations", joinList, parseTranslation),
    "URL": Metadata("URL", "ED", joinValue, parseLiteral),  # URL is a synonym for ED
    "Use <I> Autolinks": Metadata("Use <I> Autolinks", "useIAutolinks", joinValue, parseBoolean),
    "Use Dfn Panels": Metadata("Use Dfn Panels", "useDfnPanels", joinValue, parseBoolean),
    "Version History": Metadata("Version History", "versionHistory", joinList, parseLiteralList),
    "Warning": Metadata("Warning", "warning", joinValue, parseWarning),
    "Work Status": Metadata("Work Status", "workStatus", joinValue, parseWorkStatus),
    "Wpt Display": Metadata("Wpt Display", "wptDisplay", joinValue, parseWptDisplay),
    "Wpt Path Prefix": Metadata("Wpt Path Prefix", "wptPathPrefix", joinValue, parseLiteral),
}
