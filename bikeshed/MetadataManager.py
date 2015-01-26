# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import os
from subprocess import check_output
from collections import defaultdict
from datetime import date, datetime
from . import config
from . import markdown
from .messages import *
from .htmlhelpers import *

class MetadataManager:
    @property
    def hasMetadata(self):
        return len(self.manuallySetKeys) > 0

    @property
    def vshortname(self):
        if self.level is not None:
            return "{0}-{1}".format(self.shortname, self.level)
        return self.shortname

    def __init__(self, doc):
        self.doc = doc

        # required metadata
        self.status = None
        self.ED = None
        self.abstract = []
        self.shortname = None
        self.level = None

        # optional metadata
        self.TR = None
        self.title = None
        self.h1 = None
        self.statusText = ""
        self.date = datetime.utcnow().date()
        self.deadline = None
        self.group = None
        self.editors = []
        self.previousEditors = []
        self.previousVersions = []
        self.warning = None
        self.atRisk = []
        self.ignoredTerms = []
        self.testSuite = None
        self.mailingList = None
        self.mailingListArchives = None
        self.boilerplate = {'omitSections':set()}
        self.versionHistory = None
        self.logo = ""
        self.indent = 4
        self.linkDefaults = defaultdict(list)
        self.useIAutolinks = False
        self.noEditor = False
        self.defaultBiblioStatus = "dated"
        self.issues = []

        self.otherMetadata = defaultdict(list)

        self.overrides = set()

        # Some keys are single-value:
        # the result of parsing is simply assigned to them.
        self.singleValueKeys = {
            "Title": "title",
            "H1": "h1",
            "Status": "status",
            "Status Text": "statusText",
            "ED": "ED",
            "URL": "ED", # URL is a synonym for ED
            "Shortname": "shortname",
            "Level": "level",
            "TR": "TR",
            "Warning": "warning",
            "Group": "group",
            "Date": "date",
            "Deadline": "deadline",
            "Test Suite": "testSuite",
            "Mailing List": "mailingList",
            "Mailing List Archives": "mailingListArchives",
            "Boilerplate": "boilerplate",
            "Version History": "versionHistory",
            "Logo": "logo",
            "Indent": "indent",
            "Use <I> Autolinks": "useIAutolinks",
            "No Editor": "noEditor",
            "Default Biblio Status": "defaultBiblioStatus"
        }

        # Some keys are multi-value:
        # they *must* already be established as lists or dicts in __init__.
        # If a list, result of parsing can be a single value (appended) or a list (extended).
        # If a dict, result of parsing must be a dict of either single values or lists.
        # (Note that a multi-valued key might only allow a single value *per key instance*, like Editor,
        #  or multiple values per key, like Ignored Terms, which are agglomerated across keys.)
        self.multiValueKeys = {
            "Editor": "editors",
            "Former Editor": "previousEditors",
            "Abstract": "abstract",
            "Previous Version": "previousVersions",
            "At Risk": "atRisk",
            "Ignored Terms": "ignoredTerms",
            "Link Defaults": "linkDefaults",
            "Issue Tracking": "issues"
        }

        self.knownKeys = self.singleValueKeys.viewkeys() | self.multiValueKeys.viewkeys()

        self.manuallySetKeys = set()

        # Input transformers, passed the key and string value.
        # The "default" input is a no-op that just returns the input string.
        self.customInput = {
            "Group": convertGroup,
            "Date": parseDate,
            "Deadline": parseDate,
            "Level": parseLevel,
            "Warning": convertWarning,
            "Editor": parseEditor,
            "Former Editor": parseEditor,
            "Ignored Terms": parseIgnoredTerms,
            "Link Defaults": parseLinkDefaults,
            "Boilerplate": parseBoilerplate,
            "Indent": parseInteger,
            "Use <I> Autolinks": parseBoolean,
            "No Editor": parseBoolean,
            "Default Biblio Status": parseBiblioStatus,
            "Issue Tracking": parseIssues
        }

        # Alternate output handlers, passed key/value/doc.
        # The "default" output assigns the value to self.key.
        self.customOutput = {
        }

    def addData(self, key, val, default=False):
        key = key.strip()
        val = val.strip()

        if key in self.overrides:
            return

        if key.startswith("!"):
            key = key[1:]
            self.otherMetadata[key].append(val)
            return

        if key not in ("ED", "TR", "URL"):
            key = key.title()

        if not (key in self.knownKeys or key.startswith("!")):
            die('Unknown metadata key "{0}". Prefix custom keys with "!".', key)
            return

        if key in self.knownKeys and not default:
            self.manuallySetKeys.add(key)

        if default and key in self.manuallySetKeys:
            return

        if key in self.customInput:
            val = self.customInput[key](key, val)

        if key in self.customOutput:
            self.customOutput[key](key, val, doc=self.doc)
            return

        if key in self.singleValueKeys:
            setattr(self, self.singleValueKeys[key], val)
        elif key in self.multiValueKeys:
            attr = getattr(self, self.multiValueKeys[key])
            smooshValues(attr, val)


    def addDefault(self, key, val):
        self.addData(key, val, default=True)

    def addOverrides(self, overrides):
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
            self.addData(key, val)
            self.overrides.add(key)

    def finish(self):
        self.validate()

    def validate(self):
        if not self.hasMetadata:
            die("The document requires at least one metadata block.")
            return

        # { MetadataManager attr : metadata name (for printing) }
        requiredSingularKeys = {
            'status': 'Status',
            'shortname': 'Shortname'
        }
        recommendedSingularKeys = {}
        requiredMultiKeys = {
            'abstract': 'Abstract'
        }

        if self.status not in config.noEDStatuses:
            requiredSingularKeys['ED'] = 'ED'
        if self.status in config.deadlineStatuses:
            requiredSingularKeys['deadline'] = 'Deadline'
        if self.status in config.TRStatuses:
            recommendedSingularKeys['date'] = 'Date'
        if self.status not in config.unlevelledStatuses:
            requiredSingularKeys['level'] = 'Level'
        if not self.noEditor:
            requiredMultiKeys['editors'] = "Editor"

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

    def fillTextMacros(self, macros, doc=None):
        # Fills up a set of text macros based on metadata.
        if self.title:
            macros["title"] = self.title
            macros["spectitle"] = self.title
        if self.h1:
            macros["spectitle"] = self.h1
        macros["shortname"] = self.shortname
        if self.status:
            macros["statusText"] = self.statusText
        macros["vshortname"] = self.vshortname
        if self.status in config.shortToLongStatus:
            macros["longstatus"] = config.shortToLongStatus[self.status]
        else:
            die("Unknown status '{0}' used.", self.status)
        if self.status in ("LCWD", "FPWD"):
            macros["status"] = "WD"
        else:
            macros["status"] = self.status
        if self.TR:
            macros["latest"] = self.TR
        if self.abstract:
            macros["abstract"] = "\n".join(markdown.parse(self.abstract, self.indent))
            macros["abstractattr"] = escapeAttr("  ".join(self.abstract).replace("<<","<").replace(">>",">"))
        macros["year"] = unicode(self.date.year)
        macros["date"] = unicode(self.date.strftime("{0} %B %Y".format(self.date.day)), encoding="utf-8")
        macros["cdate"] = unicode(self.date.strftime("%Y%m%d"), encoding="utf-8")
        macros["isodate"] = unicode(self.date.strftime("%Y-%m-%d"), encoding="utf-8")
        if self.deadline:
            macros["deadline"] = unicode(self.deadline.strftime("{0} %B %Y".format(self.deadline.day)), encoding="utf-8")
        if self.status in config.TRStatuses:
            macros["version"] = "http://www.w3.org/TR/{year}/{status}-{vshortname}-{cdate}/".format(**macros)
        elif self.ED:
            macros["version"] = self.ED
        macros["annotations"] = config.testAnnotationURL
        if doc and self.vshortname in doc.testSuites:
            macros["testsuite"] = doc.testSuites[self.vshortname]['vshortname']
        if self.warning and len(self.warning) >= 2:
            macros["replacedby"] = self.warning[1]
        if self.warning and len(self.warning) >= 3:
            macros["snapshotid"] = self.warning[2]
        if self.warning and len(self.warning) >= 4:
            macros["snapshoturl"] = self.warning[3]
        macros["logo"] = self.logo
        # get GH repo from remote
        macros["repository"] = getSpecRepository(doc)
        # W3C stylesheets are *mostly* of the form W3C-[status], except for *one*. Ugh.
        if self.status == "UD":
            macros["w3c-stylesheet-url"] = "http://www.w3.org/StyleSheets/TR/w3c-unofficial"
        else:
            macros["w3c-stylesheet-url"] = "http://www.w3.org/StyleSheets/TR/W3C-{0}".format(self.status)


def convertGroup(key, val):
    return val.lower()

def parseDate(key, val):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", key, val)

def parseLevel(key, val):
    return config.HierarchicalNumber(val)

def parseInteger(key, val):
    return int(val)

def parseBoolean(key, val):
    if val.lower() in ("true", "yes", "y", "on"):
        return True
    if val.lower() in ("false", "no", "n", "off"):
        return False
    die("The {0} field must be true/false, yes/no, y/n, or on/off. Got '{1}' instead.", key, val);

def convertWarning(key, val):
    if val.lower() == "obsolete":
        return "warning-obsolete",
    if val.lower() == "not ready":
        return "warning-not-ready",
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
    die('Unknown value for "{0}" metadata.', key)

def parseEditor(key, val):
    match = re.match(r"([^,]+) ,\s* ([^,]*) ,?\s* ([^,]*) ,?\s* ([^,]*)", val, re.X)
    pieces = [unescape(piece.strip()) for piece in val.split(',')]
    def looksLinkish(string):
        return re.match(r"\w+:", string) or looksEmailish(string)
    def looksEmailish(string):
        return re.match(r".+@.+\..+", string)
    data = {
        'name'   : pieces[0],
        'org'    : None,
        'orglink': None,
        'link'   : None,
        'email'  : None
    }
    if len(pieces) == 4 and looksLinkish(pieces[2]) and looksLinkish(pieces[3]):
        data['org'] = pieces[1]
        if looksEmailish(pieces[2]):
            data['email'] = pieces[2]
            data['link'] = pieces[3]
        else:
            data['link'] = pieces[2]
            data['email'] = pieces[3]
    elif len(pieces) == 3 and looksLinkish(pieces[1]) and looksLinkish(pieces[2]):
        if looksEmailish(pieces[1]):
            data['email'] = pieces[1]
            data['link'] = pieces[2]
        else:
            data['link'] = pieces[1]
            data['email'] = pieces[2]
    elif len(pieces) == 3 and looksLinkish(pieces[2]):
        data['org'] = pieces[1]
        if looksEmailish(pieces[2]):
            data['email'] = pieces[2]
        else:
            data['link'] = pieces[2]
    elif len(pieces) == 2:
        # See if the piece looks like a link/email
        if looksLinkish(pieces[1]):
            if looksEmailish(pieces[1]):
                data['email'] = pieces[1]
            else:
                data['link'] = pieces[1]
        else:
            data['org'] = pieces[1]
    elif len(pieces) == 1:
        pass
    else:
        die("'{0}' format is '<name>, <company>?, <email-or-contact-page>?. Got:\n{1}", key, val)
    # Check if the org ends with a link
    if data['org'] is not None and " " in data['org'] and looksLinkish(data['org'].split()[-1]):
        pieces = data['org'].split()
        data['orglink'] = pieces[-1]
        data['org'] = ' '.join(pieces[:-1])
    return data


def parseIgnoredTerms(key, val):
    return [term.strip().lower() for term in val.split(',')]

def parseLinkDefaults(key, val):
    defaultSpecs = defaultdict(list)
    for default in val.split(","):
        match = re.match(r"^([\w\d-]+)  (?:\s+\( ({0}) (?:\s+(TR|ED))? \) )  \s+(.*)$".format("|".join(config.dfnTypes.union(["dfn"]))), default.strip(), re.X)
        if match:
            spec = match.group(1)
            type = match.group(2)
            status = match.group(3)
            terms = match.group(4).split('/')
            dfnFor = None
            for term in terms:
                defaultSpecs[term.strip()].append((spec, type, status, dfnFor))
        else:
            die("'{0}' is a comma-separated list of '<spec> (<dfn-type>) <terms>'. Got:\n{1}", key, default)
            continue
    return defaultSpecs

def parseBoilerplate(key, val):
    boilerplate = {'omitSections':set()}
    for command in val.split(","):
        command = command.strip()
        if re.match(r"omit [\w-]+$", command):
            boilerplate['omitSections'].add(command[5:])
    return boilerplate

def parseBiblioStatus(key, val):
    val = val.strip().lower()
    if val in ("current", "dated"):
        return val
    else:
        die("'{0}' must be either 'current' or 'dated'. Got '{1}'", key, val)
        return "dated"

def parseIssues(key, val):
    issues = []
    vals = [v.strip() for v in val.split(",")]
    for v in vals:
        issues.append(v.rsplit(" ", 1))
    return issues


def parse(md, lines):
    # Given a MetadataManager and HTML document text, in the form of an array of text lines,
    # extracts all <pre class=metadata> lines and parses their contents.
    # Returns the text lines, with the metadata-related lines removed.

    newlines = []
    inMetadata = False
    lastKey = None
    for line in lines:
        if not inMetadata and re.match(r"<pre .*class=.*metadata.*>", line):
            inMetadata = True
            continue
        elif inMetadata and re.match(r"</pre>\s*", line):
            inMetadata = False
            continue
        elif inMetadata:
            if lastKey and (line.strip() == "" or re.match(r"\s+", line)):
                # empty lines, or lines that start with 1+ spaces, continue previous key
                md.addData(lastKey, line.lstrip())
            elif re.match(r"([^:]+):\s*(.*)", line):
                match = re.match(r"([^:]+):\s*(.*)", line)
                md.addData(match.group(1), match.group(2))
                lastKey = match.group(1)
            else:
                die("Incorrectly formatted metadata line:\n{0}", line)
                continue
        else:
            newlines.append(line)
    return newlines

def smooshValues(container, val):
    '''
    "Smooshes" the values into the container.
    If container is a list,
    val must be either a single item or a list;
    it's merged into the container.
    If container is a dict with list values,
    val must be a dict,
    which is merged in dict-wise same as lists.
    (container should be a defaultdict(list) in this case).
    '''
    if isinstance(container, list):
        if isinstance(val, list):
            container.extend(val)
        else:
            container.append(val)
    elif isinstance(container, dict):
        for k,v in val.items():
            if isinstance(v, list):
                container[k].extend(v)
            else:
                container[k].append(v)

def getSpecRepository(doc):
    '''
    Attempts to find the name of the repository the spec is a part of.
    Currently only searches for GitHub repos.
    '''
    if doc and doc.inputSource and doc.inputSource != "-":
        source_dir = os.path.dirname(os.path.abspath(doc.inputSource))
        old_dir = os.getcwd()
        try:
            os.chdir(source_dir)
            with open(os.devnull, "wb") as fnull:
                remotes = check_output(["git", "remote", "-v"], stderr=fnull)
            os.chdir(old_dir)
            search = re.search('origin\tgit@github\.com:(.*?)\.git \(\w+\)', remotes)
            if search:
                return search.group(1)
            else:
                return ""
        except:
            # check_output will throw CalledProcessError when not in a git repo
            os.chdir(old_dir)
            return ""

def parseDoc(doc):
    # Look through the doc for any additional metadata information that might be needed.

    if find(".issue", doc) is not None:
        # There's at least one inline issue.
        doc.md.issues.append(("Inline In Spec", "#issues-index"))
