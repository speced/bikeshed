# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import os
from DefaultOrderedDict import DefaultOrderedDict
from subprocess import check_output
from collections import defaultdict
from datetime import date, datetime
from . import config
from . import markdown
from .messages import *
from .htmlhelpers import *
from .repository import *

class MetadataManager:
    @property
    def vshortname(self):
        if self.level is not None:
            return "{0}-{1}".format(self.shortname, self.level)
        return self.shortname

    def __init__(self, doc):
        self.doc = doc
        self.hasMetadata = False

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
        self.versionHistory = []
        self.logo = ""
        self.indent = 4
        self.linkDefaults = defaultdict(list)
        self.useIAutolinks = False
        self.noEditor = False
        self.defaultBiblioStatus = "dated"
        self.markupShorthands = set(["css", "biblio", "markup", "idl"])
        self.customTextMacros = []
        self.issues = []
        self.issueTrackerTemplate = None
        self.workStatus = None
        self.inlineGithubIssues = False
        self.repository = config.Nil()
        self.opaqueElements = ["pre", "xmp", "script", "style"]
        self.issueClass = "issue"
        self.noteClass = "note"
        self.advisementClass = "advisement"

        self.otherMetadata = DefaultOrderedDict(list)

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
            "Logo": "logo",
            "Indent": "indent",
            "Use <I> Autolinks": "useIAutolinks",
            "No Editor": "noEditor",
            "Default Biblio Status": "defaultBiblioStatus",
            "Issue Tracker Template": "issueTrackerTemplate",
            "Work Status": "workStatus",
            "Inline Github Issues": "inlineGithubIssues",
            "Repository": "repository",
            "Issue Class": "issueClass",
            "Note Class": "noteClass",
            "Advisement Class": "advisementClass"
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
            "Issue Tracking": "issues",
            "Markup Shorthands": "markupShorthands",
            "Version History": "versionHistory",
            "Text Macro": "customTextMacros",
            "Opaque Elements": "opaqueElements"
        }

        self.knownKeys = self.singleValueKeys.viewkeys() | self.multiValueKeys.viewkeys()

        self.manuallySetKeys = set()

        # Input transformers, passed the key and string value.
        # The "default" input is a no-op that just returns the input string.
        self.customInput = {
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
            "Issue Tracking": parseIssues,
            "Markup Shorthands": parseMarkupShorthands,
            "Text Macro": parseTextMacro,
            "Work Status": parseWorkStatus,
            "Inline Github Issues": parseBoolean,
            "Repository": parseRepository,
            "Opaque Elements": parseOpaqueElements
        }

        # Alternate output handlers, passed key/value/doc.
        # The "default" output assigns the value to self.key.
        self.customOutput = {
            "Markup Shorthands": glomMarkupShorthands
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
        if not self.repository:
            self.repository = getSpecRepository(self.doc)
        if self.repository and "feedback-header" not in self.doc.md.boilerplate['omitSections']:
            self.issues.append(("GitHub", self.repository.formatIssueUrl()))
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
        if self.group and self.group.lower() == "csswg":
            requiredSingularKeys['workStatus'] = "Work Status"

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
        if self.statusText:
            macros["statustext"] = self.statusText
        else:
            macros["statustext"] = ""
        macros["vshortname"] = self.vshortname
        if self.status == "FINDING" and self.group:
            macros["longstatus"] = "Finding of the {0}".format(self.group)
        elif self.status in config.shortToLongStatus:
            macros["longstatus"] = config.shortToLongStatus[self.status]
        else:
            die("Unknown status '{0}' used.", self.status)
        if self.status in ("LCWD", "FPWD"):
            macros["status"] = "WD"
        else:
            macros["status"] = self.status
        if self.workStatus:
            macros["workstatus"] = self.workStatus
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
            macros["isodeadline"] = unicode(self.deadline.strftime("%Y-%m-%d"), encoding="utf-8")
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
        if self.repository:
            macros["repository"] = self.repository.name
            macros["repositoryurl"] = self.repository.url
        if self.status == "UD":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/w3c-unofficial"
        elif self.status == "FPWD":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/W3C-WD"
        elif self.status == "FINDING":
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/W3C-NOTE"
        else:
            macros["w3c-stylesheet-url"] = "https://www.w3.org/StyleSheets/TR/W3C-{0}".format(self.status)
        # Custom macros
        for name, text in self.customTextMacros:
            macros[name.lower()] = text

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
    die('''Unknown value "{1}" for "{0}" metadata. Expected one of:
  obsolete
  not ready
  replaced by [new url]
  new version [new url]
  commit [snapshot id] [snapshot url] replaced by [master url]
  branch [branch name] [branch url] replaced by [master url]''', key, val)

def parseEditor(key, val):
    match = re.match(r"([^,]+) ,\s* ([^,]*) ,?\s* ([^,]*) ,?\s* ([^,]*)", val, re.X)
    pieces = [unescape(piece.strip()) for piece in val.split(',')]
    def looksLinkish(string):
        return re.match(r"\w+:", string) or looksEmailish(string)
    def looksEmailish(string):
        return re.match(r".+@.+\..+", string)
    data = {
        'name'   : pieces[0],
        'id'     : None,
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
    # Check if the name ends with an ID.
    if data['name'] and re.search(r"\s\d+$", data['name']):
        pieces = data['name'].split()
        data['id'] = pieces[-1]
        data['name'] = ' '.join(pieces[:-1])
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

def parseMarkupShorthands(key, val):
    # Format is comma-separated list of shorthand category followed by boolean.
    # Output is a dict of the shorthand categories with boolean values.
    vals = [v.strip() for v in val.lower().split(",")]
    ret = {}
    validCategories = frozenset(["css", "markup", "biblio", "idl"])
    for v in vals:
        pieces = v.split()
        if len(pieces) != 2:
            die("Markup Shorthand metadata pieces are a shorthand category and a boolean. Got:\n{0}", v)
            return {}
        name, boolstring = pieces
        if name not in validCategories:
            die("Unknown Markup Shorthand category '{0}'.", name)
            return {}
        onoff = parseBoolean(key, boolstring)
        if onoff is None:
            # parsing failed
            return {}
        ret[name] = onoff
    return ret

def glomMarkupShorthands(key, val, doc):
    ms = doc.md.markupShorthands
    for name, onoff in val.items():
        if onoff:
            ms.add(name)
        else:
            ms.discard(name)

def parseTextMacro(key, val):
    # Each Text Macro line is just a macro name (must be uppercase)
    # followed by the text it expands to.
    try:
        name, text = val.lstrip().split(None, 1)
    except:
        die("Text Macro lines must contain a macro name followed by the macro text. Got:\n{0}", val)
        return None
    if not re.match(r"[A-Z0-9-]+$", name):
        die("Text Macro names must be all-caps and alphanumeric. Got '{0}'", name)
        return None
    return (name, text)

def parseWorkStatus(key, val):
    # The Work Status is one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned).
    val = val.strip().lower()
    if val not in ('completed', 'stable', 'testing', 'refining', 'revising', 'exploring', 'rewriting', 'abandoned'):
        die("Work Status must be one of (completed, stable, testing, refining, revising, exploring, rewriting, abandoned). Got '{0}'. See http://fantasai.inkedblade.net/weblog/2011/inside-csswg/process for details.", val)
        return None
    return val

def parseRepository(key, val):
    # Shortname followed by url, or just url.
    # If just url, I'll try to recognize the shortname from it; otherwise it's the url again.
    val = val.strip()
    pieces = val.split(None, 1)
    if len(pieces) == 2:
        return Repository(url=pieces[0], name=pieces[1])
    elif len(pieces) == 1:
        # Try to recognize a GitHub url
        match = re.match("https://github.com/([\w-]+)/([\w-]+)/?$", val)
        if match:
            return GithubRepository(*match.groups())
        # If you just provide a user/repo pair, assume it's a github repo.
        # Will provide ways to opt into other repos when people care.
        match = re.match("([\w-]+)/([\w-]+)$", val)
        if match:
            return GithubRepository(*match.groups())
        # Otherwise just use the url as the shortname
        return Repository(url=val)
    else:
        die("Repository must be a url, optionally followed by a shortname. Got '{0}'", val)
        return config.Nil()

def parseOpaqueElements(key, val):
    return [x.strip() for x in val.split(",")]

def parse(md, lines):
    # Given a MetadataManager and HTML document text, in the form of an array of text lines,
    # extracts all <pre class=metadata> lines and parses their contents.
    # Returns the text lines, with the metadata-related lines removed.

    newlines = []
    inMetadata = False
    lastKey = None
    blockSize = 0
    for line in lines:
        if not inMetadata and re.match(r"<pre .*class=.*metadata.*>", line):
            blockSize = 1
            inMetadata = True
            md.hasMetadata = True
            continue
        elif inMetadata and re.match(r"</pre>\s*", line):
            newlines.append("<!--line count correction {0}-->".format(blockSize+1))
            blockSize = 0
            inMetadata = False
            continue
        elif inMetadata:
            blockSize += 1
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
        if val is None:
            return
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
    Returns a "shortname" of the repo, and the full url.
    '''
    if doc and doc.inputSource and doc.inputSource != "-":
        source_dir = os.path.dirname(os.path.abspath(doc.inputSource))
        old_dir = os.getcwd()
        try:
            os.chdir(source_dir)
            with open(os.devnull, "wb") as fnull:
                remotes = check_output(["git", "remote", "-v"], stderr=fnull)
            os.chdir(old_dir)
            search = re.search(r"origin\tgit@github\.com:([\w-]+)/([\w-]+)\.git \(\w+\)", remotes)
            if search:
                return GithubRepository(*search.groups())
            else:
                return config.Nil()
        except:
            # check_output will throw CalledProcessError when not in a git repo
            os.chdir(old_dir)
            return config.Nil()

def parseDoc(doc):
    # Look through the doc for any additional metadata information that might be needed.
    if "feedback-header" not in doc.md.boilerplate['omitSections']:
        if "issues-index" not in doc.md.boilerplate['omitSections'] and find(".issue", doc) is not None:
            # There's at least one inline issue.
            doc.md.issues.append(("Inline In Spec", "#issues-index"))

    for el in findAll(".replace-with-note-class", doc):
        removeClass(el, "replace-with-note-class")
        addClass(el, doc.md.noteClass)
    for el in findAll(".replace-with-issue-class", doc):
        removeClass(el, "replace-with-issue-class")
        addClass(el, doc.md.issueClass)
    for el in findAll(".replace-with-advisement-class", doc):
        removeClass(el, "replace-with-advisement-class")
        addClass(el, doc.md.advisementClass)
