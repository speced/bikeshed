# -*- coding: utf-8 -*-


import collections
import copy
import json
import os
import re
import subprocess
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta, date
from functools import partial

import attr
from isodate import parse_duration, Duration

from . import config
from . import constants
from . import datablocks
from . import markdown
from .DefaultOrderedDict import DefaultOrderedDict
from .h import *
from .messages import *
from .repository import *


class MetadataManager:
    @property
    def vshortname(self):
        if self.level:
            return "{0}-{1}".format(self.shortname, self.level)
        return self.shortname

    @property
    def displayVshortname(self):
        if self.level:
            return "{0}-{1}".format(self.displayShortname, self.level)
        return self.displayShortname

    def __init__(self):
        self.hasMetadata = False

        # required metadata
        self.abstract = []
        self.ED = None
        self.level = None
        self.shortname = None
        self.status = None
        self.rawStatus = None

        # optional metadata
        self.advisementClass = "advisement"
        self.assertionClass = "assertion"
        self.assumeExplicitFor = False
        self.atRisk = []
        self.audience = []
        self.blockElements = []
        self.boilerplate = config.BoolSet(default=True)
        self.canIUseURLs = []
        self.canonicalURL = None
        self.complainAbout = config.BoolSet()
        self.customTextMacros = []
        self.customWarningText = []
        self.customWarningTitle = None
        self.date = datetime.utcnow().date()
        self.deadline = None
        self.defaultHighlight = None
        self.defaultRefStatus = None
        self.displayShortname = None
        self.editors = []
        self.editorTerm = {"singular": "Editor", "plural": "Editors"}
        self.expires = None
        self.externalInfotrees = config.BoolSet(default=False)
        self.favicon = None
        self.forceCrossorigin = False
        self.group = None
        self.h1 = None
        self.ignoreCanIUseUrlFailure = []
        self.ignoredTerms = []
        self.ignoredVars = []
        self.implementationReport = None
        self.includeCanIUsePanels = False
        self.includeMdnPanels = False
        self.indent = 4
        self.inferCSSDfns = False
        self.informativeClasses = []
        self.inlineGithubIssues = False
        self.inlineTagCommands = {}
        self.issueClass = "issue"
        self.issues = []
        self.issueTrackerTemplate = None
        self.lineNumbers = False
        self.linkDefaults = defaultdict(list)
        self.localBoilerplate = config.BoolSet(default=False)
        self.logo = ""
        self.mailingList = None
        self.mailingListArchives = None
        self.markupShorthands = config.BoolSet(["css", "dfn", "biblio", "markup", "idl", "algorithm"])
        self.maxToCDepth = float('inf')
        self.metadataInclude = config.BoolSet(default=True)
        self.metadataOrder = ["*", "!*"]
        self.noAbstract = False
        self.noEditor = False
        self.noteClass = "note"
        self.opaqueElements = ["pre", "xmp", "script", "style"]
        self.prepTR = False
        self.previousEditors = []
        self.previousVersions = []
        self.removeMultipleLinks = False
        self.repository = config.Nil()
        self.requiredIDs = []
        self.slimBuildArtifact = False
        self.statusText = []
        self.testSuite = None
        self.title = None
        self.toggleDiffs = False
        self.TR = None
        self.trackingVectorAltText = "(This is a tracking vector.)"
        self.trackingVectorClass = "tracking-vector"
        self.trackingVectorImage = None
        self.trackingVectorImageHeight = "64"
        self.trackingVectorImageWidth = "46"
        self.trackingVectorTitle = "There is a tracking vector here."
        self.translateIDs = defaultdict(list)
        self.translations = []
        self.useDfnPanels = True
        self.useIAutolinks = False
        self.versionHistory = []
        self.warning = None
        self.workStatus = None
        self.wptDisplay = "none"
        self.wptPathPrefix = None

        self.otherMetadata = DefaultOrderedDict(list)

        self.manuallySetKeys = set()

    def addData(self, key, val, lineNum=None):
        key = key.strip()
        if isinstance(val, str):
            if key in ["Abstract"]:
                val = val.strip("\n")
            else:
                val = val.strip()

        if key.startswith("!"):
            key = key[1:]
            self.otherMetadata[key].append(val)
            return

        if key not in ("ED", "TR", "URL"):
            key = key.title()

        if key not in knownKeys:
            die('Unknown metadata key "{0}". Prefix custom keys with "!".', key, lineNum=lineNum)
            return
        md = knownKeys[key]

        val = md.parse(key=key, val=val, lineNum=lineNum)

        self.addParsedData(key, val)

    def addParsedData(self, key, val):
        md = knownKeys[key]
        result = md.join(getattr(self, md.attrName), val)
        setattr(self, md.attrName, result)
        self.manuallySetKeys.add(key)

    def computeImplicitMetadata(self, doc):
        # Do some "computed metadata", based on the value of other metadata.
        # Only call this when you're sure all metadata sources are parsed.
        if self.group == "byos":
            self.boilerplate.default = False
        if not self.repository and doc:
            self.repository = getSpecRepository(doc)
        if self.repository.type == "github" and "feedback-header" in self.boilerplate and "repository-issue-tracking" in self.boilerplate:
            self.issues.append(("GitHub", self.repository.formatIssueUrl()))
        self.status = config.canonicalizeStatus(self.rawStatus, self.group)

        self.expires = canonicalizeExpiryDate(self.date, self.expires)

        # for TR document, defaults to TR
        # fallbacks to ED
        if (self.canonicalURL == None or self.canonicalURL == "TR") and self.TR:
            self.canonicalURL = self.TR
        elif (self.canonicalURL == None or self.canonicalURL == "ED") and self.ED:
            self.canonicalURL = self.ED

        if self.displayShortname:
            self.shortname = self.displayShortname.lower()

        # Temporary fix until W3C publishes a better version of the image
        if self.status in ["w3c/CG-DRAFT", "w3c/UD"] and not self.prepTR:
            doc.extraStyles['darkmode'] += '''
            @media (prefers-color-scheme: dark) {
                html { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cg fill='%23100808' transform='translate(200 200) rotate(-45) translate(-200 -200)' stroke='%23100808' stroke-width='3'%3E%3Ctext x='50%25' y='220' style='font: bold 70px sans-serif; text-anchor: middle; letter-spacing: 6px;'%3EUNOFFICIAL%3C/text%3E%3Ctext x='50%25' y='305' style='font: bold 70px sans-serif; text-anchor: middle; letter-spacing: 6px;'%3EDRAFT%3C/text%3E%3C/g%3E%3C/svg%3E") !important; }
            }
            '''

    def validate(self):
        if self.group == "byos":
            return True

        if not self.hasMetadata:
            die("The document requires at least one <pre class=metadata> block.")
            return

        # { MetadataManager attr : metadata name (for printing) }
        requiredSingularKeys = {
            'status': 'Status',
            'shortname': 'Shortname',
            'title': 'Title'
        }
        recommendedSingularKeys = {}
        requiredMultiKeys = {}

        if self.status not in config.noEDStatuses:
            requiredSingularKeys['ED'] = 'ED'
        if self.status in config.deadlineStatuses:
            requiredSingularKeys['deadline'] = 'Deadline'
        if self.status in config.datedStatuses:
            recommendedSingularKeys['date'] = 'Date'
        if self.status in config.snapshotStatuses:
            requiredSingularKeys['TR'] = "TR"
            requiredMultiKeys['issues'] = "Issue Tracking"
        if self.status in config.implementationStatuses:
            requiredSingularKeys['implementationReport'] = "Implementation Report"
        if self.status not in config.unlevelledStatuses:
            requiredSingularKeys['level'] = 'Level'
        if self.status not in config.shortToLongStatus:
            die("Unknown Status '{0}' used.", self.status)
        if not self.noEditor:
            requiredMultiKeys['editors'] = "Editor"
        if not self.noAbstract:
            requiredMultiKeys['abstract'] = "Abstract"
        if self.group and self.group.lower() == "csswg":
            requiredSingularKeys['workStatus'] = "Work Status"
        if self.group and self.group.lower() == "wg21":
            requiredSingularKeys['audience'] = "Audience"

        errors = []
        warnings = []
        for attr, name in requiredSingularKeys.items():
            if getattr(self, attr) is None:
                errors.append("    Missing a '{0}' entry.".format(name))
        for attr, name in recommendedSingularKeys.items():
            if getattr(self, attr) is None:
                warnings.append("    You probably want to provide a '{0}' entry.".format(name))
        for attr, name in requiredMultiKeys.items():
            if len(getattr(self, attr)) == 0:
                errors.append("    Must provide at least one '{0}' entry.".format(name))
        if warnings:
            warn("Some recommended metadata is missing:\n{0}", "\n".join(warnings))
        if errors:
            die("Not all required metadata was provided:\n{0}", "\n".join(errors))
            return

    def fillTextMacros(self, macros, doc):
        # Fills up a set of text macros based on metadata.
        if self.title:
            macros["title"] = self.title
            macros["spectitle"] = self.title
        if self.h1:
            macros["spectitle"] = self.h1
        macros["shortname"] = self.displayShortname
        if self.statusText:
            macros["statustext"] = "\n".join(markdown.parse(self.statusText, self.indent))
        else:
            macros["statustext"] = ""
        macros["level"] = str(self.level)
        macros["vshortname"] = self.displayVshortname
        if self.status == "FINDING" and self.group:
            macros["longstatus"] = "Finding of the {0}".format(self.group)
        elif self.status in config.shortToLongStatus:
            macros["longstatus"] = config.shortToLongStatus[self.status]
        else:
            macros["longstatus"] = ""
        if self.status in ("w3c/LCWD", "w3c/FPWD"):
            macros["status"] = "WD"
        elif self.status in ("w3c/WG-NOTE", "w3c/IG-NOTE"):
            macros["status"] = "NOTE"
        else:
            macros["status"] = self.rawStatus
        if self.workStatus:
            macros["workstatus"] = self.workStatus
        if self.TR:
            macros["latest"] = self.TR
        if self.abstract:
            abstractLines = datablocks.transformDataBlocks(doc, self.abstract)
            macros["abstract"] = "\n".join(markdown.parse(abstractLines, self.indent))
            macros["abstractattr"] = escapeAttr("  ".join(abstractLines).replace("<<","<").replace(">>",">"))
        elif self.noAbstract:
            macros["abstract"] = ""
            macros["abstractattr"] = ""
        macros["year"] = self.date.year
        macros["date"] = self.date.strftime("{0} %B %Y".format(self.date.day))
        macros["date-dmmy"] = self.date.strftime("{0} %B %Y".format(self.date.day)) #same as plain 'date'
        macros["cdate"] = self.date.strftime("%Y%m%d")
        macros["isodate"] = self.date.strftime("%Y-%m-%d")
        macros["date-my"] = self.date.strftime("%b %Y")
        macros["date-mmy"] = self.date.strftime("%B %Y")
        if isinstance(self.expires, date):
            macros["expires"] = self.expires.strftime("{0} %B %Y".format(self.expires.day))
            macros["expires-dmmy"] = self.expires.strftime("{0} %B %Y".format(self.expires.day)) #same as plain 'expires'
            macros["cexpires"] = self.expires.strftime("%Y%m%d")
            macros["isoexpires"] = self.expires.strftime("%Y-%m-%d")
            macros["expires-my"] = self.expires.strftime("%b %Y")
            macros["expires-mmy"] = self.expires.strftime("%B %Y")
        if self.deadline:
            macros["deadline"] = self.deadline.strftime("{0} %B %Y".format(self.deadline.day))
            macros["isodeadline"] = self.deadline.strftime("%Y-%m-%d")
        if self.status in config.snapshotStatuses:
            macros["version"] = "https://www.w3.org/TR/{year}/{status}-{vshortname}-{cdate}/".format(**macros)
        elif self.ED:
            macros["version"] = self.ED
        macros["annotations"] = constants.testAnnotationURL
        if doc and self.vshortname in doc.testSuites:
            macros["testsuite"] = doc.testSuites[self.vshortname]['vshortname']
        if self.warning and len(self.warning) >= 2:
            macros["replacedby"] = self.warning[1]
        if self.warning and len(self.warning) >= 3:
            macros["snapshotid"] = self.warning[2]
        if self.warning and len(self.warning) >= 4:
            macros["snapshoturl"] = self.warning[3]
        macros["logo"] = self.logo
        if self.repository:
            macros["repository"] = self.repository.name
            macros["repositoryurl"] = self.repository.url
        if self.mailingList:
            macros["mailinglist"] = self.mailingList
        if self.mailingListArchives:
            macros["mailinglistarchives"] = self.mailingListArchives
        if self.status == "w3c/FPWD":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-WD"
        elif self.status == "FINDING":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-NOTE"
        elif self.status == "w3c/CG-DRAFT":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/cg-draft"
        elif self.status == "w3c/CG-FINAL":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/cg-final"
        else:
            shortStatus = self.rawStatus.partition("/")[2] if (self.rawStatus and "/" in self.rawStatus) else self.rawStatus
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/2016/W3C-{0}".format(shortStatus)
        if self.customWarningText is not None:
            macros["customwarningtext"] = "\n".join(markdown.parse(self.customWarningText, self.indent))
        if self.customWarningTitle is not None:
            macros["customwarningtitle"] = self.customWarningTitle
        # Custom macros
        for name, text in self.customTextMacros:
            macros[name.lower()] = text


def parseDate(key, val, lineNum):
    if val == "now":
        return datetime.utcnow().date()
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", key, val, lineNum=lineNum)
        return None


def parseDateOrDuration(key, val, lineNum):
    if val == "now":
        return datetime.utcnow().date()
    if val == "never" or boolish(val) is False:
        return None
    try:
        if val.startswith("P"):
            return parse_duration(val)
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be an ISO 8601 duration, a date in the format YYYY-MM-DD, now, never, false, no, n, or off. Got '{1}' instead.", key, val, lineNum=lineNum)
        return None

def canonicalizeExpiryDate(base, expires):
    if expires is None:
        return None
    if isinstance(expires, timedelta):
        return base + expires
    if isinstance(expires, Duration):
        return base + expires
    if isinstance(expires, datetime):
        return expires.date()
    if isinstance(expires, date):
        return expires
    die("Unexpected expiry type: canonicalizeExpiryDate({0}, {1})", base, expires)
    return None


def parseLevel(key, val, lineNum):
    val = val.lower().strip()
    if val == "none":
        return ""
    return val.strip()


def parseInteger(key, val, lineNum):
    return int(val)


def parseBoolean(key, val, lineNum):
    b = boolish(val)
    if b is None:
        die("The {0} field must be true/false, yes/no, y/n, or on/off. Got '{1}' instead.", key, val, lineNum=lineNum)
    return b


def parseSoftBoolean(key, val, lineNum):
    b = boolish(val)
    if b is not None:
        return b
    if val.lower() in ["maybe", "if possible", "if needed"]:
        return "maybe"
    die(f"The {key} field must be boolish, or 'maybe'. Got '{val}' instead.", lineNum=lineNum)


def boolish(val):
    if val.lower() in ("true", "yes", "y", "on"):
        return True
    if val.lower() in ("false", "no", "n", "off"):
        return False
    return None


def parseWarning(key, val, lineNum):
    if val.lower() == "obsolete":
        return "warning-obsolete",
    if val.lower() == "not ready":
        return "warning-not-ready",
    if val.lower() == "custom":
        return "warning-custom",
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
    die('''Unknown value "{1}" for "{0}" metadata. Expected one of:
  obsolete
  not ready
  replaced by [new url]
  new version [new url]
  commit [snapshot id] [snapshot url] replaced by [master url]
  branch [branch name] [branch url] replaced by [master url]
  custom''', key, val, lineNum=lineNum)
    return None


def parseEditor(key, val, lineNum):
    pieces = [unescape(piece.strip()) for piece in val.split(',')]

    def looksLinkish(string):
        return re.match(r"\w+:", string) or looksEmailish(string)

    def looksEmailish(string):
        return re.match(r".+@.+\..+", string)
    data = {
        'name'   : pieces[0],
        'w3cid'  : None,
        'org'    : None,
        'orglink': None,
        'link'   : None,
        'email'  : None,
        'w3cid'  : None
    }
    # Handle well-known pieces, split off the ambiguous ones
    ambiguousPieces = []
    for piece in pieces[1:]:
        if re.match(r"w3cid \d+$", piece) and data['w3cid'] is None:
            data['w3cid'] = piece[6:]
        else:
            ambiguousPieces.append(piece)
    if len(ambiguousPieces) == 3 and looksLinkish(ambiguousPieces[1]) and looksLinkish(ambiguousPieces[2]):
        # [org, email, url] or [org, url, email]
        data['org'] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data['email'] = ambiguousPieces[1]
            data['link'] = ambiguousPieces[2]
        else:
            data['link'] = ambiguousPieces[1]
            data['email'] = ambiguousPieces[2]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[0]) and looksLinkish(ambiguousPieces[1]):
        # [email, url] or [url, email]
        if looksEmailish(ambiguousPieces[0]):
            data['email'] = ambiguousPieces[0]
            data['link'] = ambiguousPieces[1]
        else:
            data['link'] = ambiguousPieces[0]
            data['email'] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 2 and looksLinkish(ambiguousPieces[1]):
        # [org, email] or [org, url]
        data['org'] = ambiguousPieces[0]
        if looksEmailish(ambiguousPieces[1]):
            data['email'] = ambiguousPieces[1]
        else:
            data['link'] = ambiguousPieces[1]
    elif len(ambiguousPieces) == 1:
        # [org], [email], or [url]
        if looksLinkish(ambiguousPieces[0]):
            if looksEmailish(ambiguousPieces[0]):
                data['email'] = ambiguousPieces[0]
            else:
                data['link'] = ambiguousPieces[0]
        else:
            data['org'] = ambiguousPieces[0]
    elif len(ambiguousPieces) == 0:
        pass
    else:
        die("'{0}' format is '<name>, <company>?, <email-or-contact-page>?'. Got:\n{1}", key, val, lineNum=lineNum)
        return []
    # Check if the org ends with a link
    if data['org'] is not None and " " in data['org'] and looksLinkish(data['org'].split()[-1]):
        pieces = data['org'].split()
        data['orglink'] = pieces[-1]
        data['org'] = ' '.join(pieces[:-1])
    # Check if the name ends with an ID.
    # TODO: remove this, it's redundant with the "w3cid ####" piece
    if data['name'] and re.search(r"\s\d+$", data['name']):
        pieces = data['name'].split()
        data['w3cid'] = pieces[-1]
        data['name'] = ' '.join(pieces[:-1])
    return [data]


def parseCommaSeparated(key, val, lineNum):
    return [term.strip().lower() for term in val.split(',')]


def parseIdList(key, val, lineNum):
    return [term.strip() for term in val.split(',')]


def parseLinkDefaults(key, val, lineNum):
    defaultSpecs = defaultdict(list)
    for default in val.split(","):
        match = re.match(r"^([\w\d-]+)  (?:\s+\( ({0}) (?:\s+(snapshot|current))? \) )  \s+(.*)$".format("|".join(config.dfnTypes.union(["dfn"]))), default.strip(), re.X)
        if match:
            spec = match.group(1)
            type = match.group(2)
            status = match.group(3)
            terms = match.group(4).split('/')
            dfnFor = None
            for term in terms:
                defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
        else:
            die("'{0}' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{1}", key, default, lineNum=lineNum)
            continue
    return defaultSpecs


def parseBoilerplate(key, val, lineNum):
    boilerplate = config.BoolSet(default=True)
    for command in val.split(","):
        pieces = command.lower().strip().split()
        if len(pieces) != 2:
            die("Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{0}", command, lineNum=lineNum)
            continue
        if pieces[0] == "omit":
            # legacy syntax; allows "omit foo" in addition to the normal "foo off"/etc
            boilerplate[pieces[1]] = False
        else:
            onoff = boolish(pieces[1])
            if onoff is None:
                die("Boilerplate metadata pieces are a boilerplate label and a boolean. Got:\n{0}", command, lineNum=lineNum)
                continue
            boilerplate[pieces[0]] = onoff
    return boilerplate


def parseRefStatus(key, val, lineNum):
    val = val.strip().lower()
    if val == "dated":
        # Legacy term that used to be allowed
        val == "snapshot"
    if val in constants.refStatus:
        return val
    else:
        die("'{0}' must be either 'current' or 'snapshot'. Got '{1}'", key, val, lineNum=lineNum)
        return constants.refStatus.current


def parseComplainAbout(key, val, lineNum):
    validLabels = frozenset(["missing-example-ids", "broken-links", "accidental-2119", "missing-exposed"])
    ret = parseBoolishList(key, val.lower(), default=False, validLabels=validLabels, lineNum=lineNum)
    return ret


def parseExternalInfotrees(key, val, lineNum):
    return parseBoolishList(key, val.lower(), default=False,
                            validLabels=frozenset(["anchors.bsdata", "link-defaults.infotree"]),
                            lineNum=lineNum)


def parseBoolishList(key, val, default=None, validLabels=None, extraValues=None, lineNum=None):
    # Parses anything defined as "label <boolish>, label <boolish>" into a passed BoolSet
    # Supply a list of valid labels if you want to have them checked,
    # and a dict of {value=>bool} pairs you want in addition to the standard boolish values
    if default is None:
        boolset = {}
    elif default in (True, False):
        boolset = config.BoolSet(default=default)
    else:
        die("Programming error - parseBoolishList() got a non-bool default value: '{0}'", default)
    if extraValues is None:
        extraValues = {}
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        name,_, boolstring = v.strip().rpartition(" ")
        if not name or not boolstring:
            die("{0} metadata pieces are a label and a boolean. Got:\n{1}", key, v, lineNum=lineNum)
            continue
        if validLabels and name not in validLabels:
            die("Unknown {0} label '{1}'.", key, name, lineNum=lineNum)
            continue
        if boolstring in extraValues:
            boolset[name] = extraValues[boolstring]
        else:
            onoff = boolish(boolstring)
            if isinstance(onoff, bool):
                boolset[name] = onoff
            else:
                die("{0} metadata pieces are a shorthand category and a boolean. Got:\n{1}", key, v, lineNum=lineNum)
                continue
    return boolset


def parseLinkedText(key, val, lineNum):
    # Parses anything defined as "text url, text url, text url" into a list of 2-tuples.
    entries = []
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        entries.append(v.rsplit(" ", 1))
    return entries


def parseMarkupShorthands(key, val, lineNum):
    # Format is comma-separated list of shorthand category followed by boolean.
    # Output is a dict of the shorthand categories with boolean values.
    vals = [v.strip() for v in val.lower().split(",")]
    ret = config.BoolSet(default=False)
    validCategories = frozenset(["css", "markup", "dfn", "biblio", "idl", "markdown", "algorithm"])
    for v in vals:
        pieces = v.split()
        if len(pieces) != 2:
            die("Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{0}", v, lineNum=lineNum)
            continue
        name, boolstring = pieces
        if name not in validCategories:
            die("Unknown Markup Shorthand category '{0}'.", name, lineNum=lineNum)
            continue
        onoff = boolish(boolstring)
        if onoff is None:
            die("Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{0}", v, lineNum=lineNum)
            continue
        ret[name] = onoff
    return ret

def parseInlineGithubIssues(key, val, lineNum):
    val = val.lower()
    if val in ["title", "full"]:
        return val
    b = boolish(val)
    if b is None:
        die("Inline Github Issues must be 'title', 'full' or a boolish value. Got: '{0}'", val, lineNum=lineNum)
        return False
    elif b is True:
        return "full"
    else:
        return False

def parseTextMacro(key, val, lineNum):
    # Each Text Macro line is just a macro name (must be uppercase)
    # followed by the text it expands to.
    try:
        name, text = val.lstrip().split(None, 1)
    except:
        die("Text Macro lines must contain a macro name followed by the macro text. Got:\n{0}", val, lineNum=lineNum)
        return []
    if not re.match(r"[A-Z0-9-]+$", name):
        die("Text Macro names must be all-caps and alphanumeric. Got '{0}'", name, lineNum=lineNum)
        return []
    return [(name, text)]


def parseWorkStatus(key, val, lineNum):
    # The Work Status is one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned).
    val = val.strip().lower()
    if val not in ('completed', 'stable', 'testing', 'refining', 'revising', 'exploring', 'rewriting', 'abandoned'):
        die("Work Status must be one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned). Got '{0}'. See http://fantasai.inkedblade.net/weblog/2011/inside-csswg/process for details.", val, lineNum=lineNum)
        return None
    return val


def parseRepository(key, val, lineNum):
    # Shortname followed by url, or just url.
    # If just url, I'll try to recognize the shortname from it; otherwise it's the url again.
    val = val.strip()
    pieces = val.split(None, 1)
    if len(pieces) == 2:
        return Repository(url=pieces[0], name=pieces[1])
    elif len(pieces) == 1:
        # Try to recognize a GitHub url
        match = re.match("https://github\.([\w.-]+)/([\w-]+)/([\w-]+)/?$", val)
        if match:
            return GithubRepository(*match.groups())
        # If you just provide a user/repo pair, assume it's a github.com repo.
        # Will provide ways to opt into other repos when people care.
        match = re.match("([\w-]+)/([\w-]+)$", val)
        if match:
            return GithubRepository("com", *match.groups())
        # Otherwise just use the url as the shortname
        return Repository(url=val)
    else:
        die("Repository must be a url, optionally followed by a shortname. Got '{0}'", val, lineNum=lineNum)
        return config.Nil()


def parseTranslateIDs(key, val, lineNum):
    translations = {}
    for v in val.split(","):
        pieces = v.strip().split()
        if len(pieces) != 2:
            die("‘Translate IDs’ values must be an old ID followed by a new ID. Got '{0}'", v, lineNum=lineNum)
            continue
        old,new = pieces
        translations[old] = new
    return translations


def parseTranslation(key, val, lineNum):
    # Format is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?
    pieces = val.split(",")
    if not(1 <= len(pieces) <= 3):
        die("Format of a Translation line is <lang-code> <url> [ [ , name <name-in-spec-lang> ] || [ , native-name <name-in-the-lang> ] ]?. Got:\n{0}", val, lineNum=lineNum)
        return
    firstParts = pieces[0].split()
    if len(firstParts) != 2:
        die("First part of a Translation line must be a lang-code followed by a url. Got:\n{0}", pieces[0], lineNum=lineNum)
        return
    langCode, url = firstParts
    name = None
    nativeName = None
    for piece in pieces[1:]:
        k,v = piece.split(None, 1)
        if k.lower() == "name":
            name = v
        elif k.lower() == "native-name":
            nativeName = v
        else:
            die("Later parts of a Translation line must start with 'name' or 'native-name'. Got:\n{0}", piece, lineNum=lineNum)
    return [{"lang-code": langCode, "url": url, "name": name, "native-name": nativeName}]


def parseAudience(key, val, lineNum):
    # WG21 value
    values = [x.strip().upper() for x in val.strip().split(",")]
    if not values:
        die("Audience metadata must have at least one value if specified.")
        return []
    elif len(values) == 1 and values[0] == "ALL":
        return ["all"]
    elif len(values) >= 1:
        ret = []
        namedAudiences = {"CWG", "LWG", "EWG", "LEWG", "DIRECTION"}
        pseudonymAudiences = {"Concurrency":"SG1", "Modules":"SG2", "Networking":"SG4", "TM":"SG5", "Numerics":"SG6", "Reflection":"SG7", "FeatureTesting":"SG10", "UB":"SG12", "HMI":"SG13", "LowLatency":"SG14", "Tooling":"SG15", "Unicode":"SG16", "EWGI":"SG17", "LEWGI":"SG18", "MachineLearning":"SG19", "Education":"SG20", "Contracts":"SG21"}
        for v in values:
            if v in namedAudiences:
                ret.append(v)
            elif v in pseudonymAudiences:
                ret.append(pseudonymAudiences[v])
            elif re.match(r"WG\d+|SG\d+", v):
                ret.append(v)
            else:
                die("Unknown 'Audience' value '{0}'.", v, lineNum=lineNum)
                continue
        return ret


def parseEditorTerm(key, val, lineNum):
    values = [x.strip() for x in val.strip().split(",")]
    if len(values) == 2:
        return {"singular": values[0], "plural": values[1]}
    else:
        die("Editor Term metadata must be two comma-separated terms, giving the singular and plural term for editors. Got '{0}'.", val)
        return {"singular": "Editor", "plural": "Editors"}


def parseMaxToCDepth(key, val, lineNum):
    if val.lower() == "none":
        return float('inf')
    try:
        v = int(val)
    except ValueError as e:
        die("Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{0}'.", val, lineNum=lineNum)
        return float('inf')
    if not (1 <= v <= 5):
        die("Max ToC Depth metadata must be 'none' or an integer 1-5. Got '{0}'.", val, lineNum=lineNum)
        return float('inf')
    return v


def parseMetadataOrder(key, val, lineNum):
    pieces = [x.strip() for x in val.split(",")]
    return pieces


def parseWptDisplay(key, val, lineNum):
    val = val.lower()
    if val in ("none", "inline"):
        return val
    die("WPT Display metadata only accepts the values 'none' or 'inline'. Got '{0}'.", val, lineNum=lineNum)
    return "none"


def parsePreviousVersion(key, val, lineNum):
    biblioMatch = re.match(r"from biblio(\s+\S+)?", val.lower())
    if biblioMatch:
        if biblioMatch.group(1):
            return [{"type":"from-biblio", "value":biblioMatch.group(1).strip()}]
        else:
            return [{"type":"from-biblio-implicit"}]
    else:
        return [{"type":"url", "value":val}]


def parseInlineTagCommand(key, val, lineNum):
    tag,_,command = val.strip().partition(" ")
    command = command.strip()
    return {tag: command}


def parse(lines):
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
        elif inMetadata and re.match(endTag, line.text):
            inMetadata = False
            continue
        elif inMetadata:
            if lastKey and (line.text.strip() == "" or re.match(r"\s+", line.text)):
                # empty lines, or lines that start with 1+ spaces, continue previous key
                md.addData(lastKey, line.text, lineNum=line.i)
            elif re.match(r"([^:]+):\s*(.*)", line.text):
                match = re.match(r"([^:]+):\s*(.*)", line.text)
                md.addData(match.group(1), match.group(2), lineNum=line.i)
                lastKey = match.group(1)
            else:
                die("Incorrectly formatted metadata line:\n{0}", line.text, lineNum=line.i)
                continue
        elif re.match(r"\s*<h1[^>]*>.*?</h1>", line.text):
            if md.title is None:
                title = re.match(r"\s*<h1[^>]*>(.*?)</h1>", line.text).group(1)
                md.addData("Title", title, lineNum=line.i)
            newlines.append(line)
        else:
            newlines.append(line)
    return newlines, md


def fromCommandLine(overrides):
    # Given a list of strings representing command-line arguments,
    # finds the args that correspond to metadata keys
    # and fills a MetadataManager accordingly.
    md = MetadataManager()
    for o in overrides:
        match = re.match("--md-([^ =]+)=(.+)", o)
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


def fromJson(data, source=""):
    md = MetadataManager()
    try:
        defaults = json.loads(data, object_pairs_hook=OrderedDict)
    except Exception as e:
        if data != "":
            if source == "computed-metadata":
                die("Error loading computed-metadata JSON.\nCheck if you need to JSON-escape some characters in a text macro?\n{0}", str(e))
            else:
                die("Error loading {1} JSON:\n{0}", str(e), source)
        return md
    for key,val in defaults.items():
        if isinstance(val, str):
            md.addData(key, val)
        elif isinstance(val, list):
            for indivVal in val:
                md.addData(key, indivVal)
        else:
            die("JSON metadata values must be strings or arrays of strings. '{0}' is something else.", key)
            return md
    return md


def getSpecRepository(doc):
    '''
    Attempts to find the name of the repository the spec is a part of.
    Currently only searches for GitHub repos.
    Returns a "shortname" of the repo, and the full url.
    '''
    if doc and doc.inputSource and doc.inputSource.hasDirectory():
        source_dir = doc.inputSource.directory()
        try:
            with open(os.devnull, "wb") as fnull:
                remotes = str(subprocess.check_output(["git", "remote", "-v"], stderr=fnull, cwd=source_dir), encoding="utf-8")
            searches = [
              r"origin\tgit@github\.([\w.-]+):([\w-]+)/([\w-]+)\.git \(\w+\)",
              r"origin\thttps://github\.([\w.-]+)/([\w-]+)/([\w-]+)\.git \(\w+\)",
              r"origin\thttps://github\.([\w.-]+)/([\w-]+)/([\w-]+)/? \(\w+\)",
            ]
            for search_re in searches:
                search = re.search(search_re, remotes)
                if search:
                    return GithubRepository(*search.groups())
            return config.Nil()
        except subprocess.CalledProcessError:
            # check_output will throw CalledProcessError when not in a git repo
            return config.Nil()
    return config.Nil()


def parseDoc(doc):
    # Look through the doc for any additional metadata information that might be needed.

    for el in findAll(".replace-with-note-class", doc):
        removeClass(el, "replace-with-note-class")
        addClass(el, doc.md.noteClass)
    for el in findAll(".replace-with-issue-class", doc):
        removeClass(el, "replace-with-issue-class")
        addClass(el, doc.md.issueClass)
    for el in findAll(".replace-with-assertion-class", doc):
        removeClass(el, "replace-with-assertion-class")
        addClass(el, doc.md.assertionClass)
    for el in findAll(".replace-with-advisement-class", doc):
        removeClass(el, "replace-with-advisement-class")
        addClass(el, doc.md.advisementClass)

    if "feedback-header" in doc.md.boilerplate and "issues-index" in doc.md.boilerplate and find("." + doc.md.issueClass, doc) is not None:
            # There's at least one inline issue.
            doc.md.issues.append(("Inline In Spec", "#issues-index"))


def join(*sources):
    '''
    MetadataManager is a monoid
    '''
    md = MetadataManager()
    md.hasMetadata = any(x.hasMetadata for x in sources)
    for mdsource in sources:
        for k in mdsource.manuallySetKeys:
            mdentry = knownKeys[k]
            md.addParsedData(k, getattr(mdsource, mdentry.attrName))
        for k,v in mdsource.otherMetadata.items():
            md.otherMetadata[k].extend(v)
    return md

@attr.s(slots=True, frozen=True)
class Metadata(object):
    humanName = attr.ib()
    attrName = attr.ib()
    join = attr.ib()
    parse = attr.ib()


def joinValue(a, b):
    return b


def joinList(a, b):
    return a + b


def joinDict(a,b):
    x = {}
    x.update(a)
    x.update(b)
    return x


def joinBoolSet(a,b):
    x = copy.deepcopy(a)
    x.update(b)
    return x


def joinDdList(a,b):
    x = defaultdict(list)
    x.update(a)
    x.update(b)
    return x


def parseLiteral(key, val, lineNum):
    return val


def parseLiteralOrNone(key, val, lineNum):
    if val.lower() == "none":
        return None
    return val


def parseLiteralCaseless(key, val, lineNum):
    return val.lower()


def parseLiteralList(key, val, lineNum):
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
    "Default Biblio Status": Metadata("Default Biblio Status", "defaultRefStatus", joinValue, parseRefStatus), #synonym of "Default Ref Status"
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
    "Ignore Can I Use Url Failure": Metadata("Ignore Can I Use Url Failure", "ignoreCanIUseUrlFailure", joinList, parseLiteralList),
    "Ignored Terms": Metadata("Ignored Terms", "ignoredTerms", joinList, parseCommaSeparated),
    "Ignored Vars": Metadata("Ignored Vars", "ignoredVars", joinList, parseCommaSeparated),
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
    "Local Boilerplate": Metadata("Local Boilerplate", "localBoilerplate", joinBoolSet, partial(parseBoolishList, default=False)),
    "Logo": Metadata("Logo", "logo", joinValue, parseLiteral),
    "Mailing List Archives": Metadata("Mailing List Archives", "mailingListArchives", joinValue, parseLiteral),
    "Mailing List": Metadata("Mailing List", "mailingList", joinValue, parseLiteral),
    "Markup Shorthands": Metadata("Markup Shorthands", "markupShorthands", joinBoolSet, parseMarkupShorthands),
    "Max Toc Depth": Metadata("Max ToC Depth", "maxToCDepth", joinValue, parseMaxToCDepth),
    "Metadata Include": Metadata("Metadata Include", "metadataInclude", joinBoolSet, partial(parseBoolishList, default=True)),
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
    "Tracking Vector Image Width": Metadata("Tracking Vector Image Width", "trackingVectorImageWidth", joinValue, parseLiteral),
    "Tracking Vector Image Height": Metadata("Tracking Vector Image Height", "trackingVectorImageHeight", joinValue, parseLiteral),
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
    "Wpt Path Prefix": Metadata("Wpt Path Prefix", "wptPathPrefix", joinValue, parseLiteral)
}
