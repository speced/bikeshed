# -*- coding: utf-8 -*-
import re
from collections import defaultdict
from datetime import date, datetime
from lib.fuckunicode import u
from lib.messages import *
from lib.htmlhelpers import *

class MetadataManager:
    # required metadata
    status = None
    ED = None
    abstracts = []
    shortname = None
    level = None

    # optional metadata
    TR = None
    title = "???"
    date = datetime.utcnow().date()
    deadline = None
    group = "csswg"
    editors = []
    previousEditors = []
    previousVersions = []
    warning = None
    atRisk = []
    ignoredTerms = []
    testSuite = None
    mailingList = None
    mailingListArchives = None

    otherMetadata = defaultdict(list)

    @property
    def hasMetadata(self):
        return len(self.manuallySetKeys) > 0

    def __init__(self):
        self.singleValueKeys = {
            "Title": "title",
            "Status": "status",
            "ED": "ED",
            "Shortname": "shortname",
            "Level": "level",
            "TR": "TR",
            "Warning": "warning",
            "Group": "group",
            "Date": "date",
            "Deadline": "deadline",
            "Test Suite": "testSuite",
            "Mailing List": "mailingList",
            "Mailing List Archives": "mailingListArchives"
        }

        self.multiValueKeys = {
            "Editor": "editors",
            "Former Editor": "previousEditors",
            "Abstract": "abstracts",
            "Previous Version": "previousVersions",
            "At Risk": "atRisk",
            "Ignored Terms": "ignoredTerms",
            "Link Defaults": ""
        }

        self.knownKeys = self.singleValueKeys.viewkeys() | self.multiValueKeys.viewkeys()

        self.manuallySetKeys = set()

        # Input transformers
        self.customInput = {
            "Status": setStatus,
            "Group": convertGroup,
            "Date": parseDate,
            "Deadline": parseDate,
            "Level": lambda a,b: int(b),
            "Warning": convertWarning,
            "Editor": parseEditor,
            "Former Editor": parseEditor,
            "Ignored Terms": parseIgnoredTerms,
            "Link Defaults": parseLinkDefaults
        }

        # Alternate output handlers
        self.customOutput = {
            "Link Defaults": saveLinkDefaults
        }

    def addData(self, key, val, default=False):
        key = key.strip()
        if key not in ("ED", "TR"):
            key = key.title()
        val = val.strip()

        # This'll be a fatal error later, but for now it's just a warning.
        if not (key in self.knownKeys or key.startswith("!")):
            die('Unknown metadata key "{0}". Prefix custom keys with "!".', key)
            return

        if key.startswith("!"):
            key = key.lstrip("!")
            self.otherMetadata[key].append(val)
            return

        if key in self.knownKeys and not default:
            self.manuallySetKeys.add(key)

        if default and key in self.manuallySetKeys:
            return

        if key in self.customInput:
            val = self.customInput[key](key, val)

        if key in self.customOutput:
            self.customOutput[key](key, val)
            return

        if key in self.singleValueKeys:
            setattr(self, self.singleValueKeys[key], val)
        else:
            if isinstance(val, list):
                getattr(self, self.multiValueKeys[key]).extend(val)
            else:
                getattr(self, self.multiValueKeys[key]).append(val)

    def addDefault(self, key, val):
        self.addData(key, val, default=True)


def setStatus(key, val):
    config.doc.refs.setStatus(val)
    return val

def convertGroup(key, val):
    return val.lower()

def parseDate(key, val):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except:
        die("The {0} field must be in the format YYYY-MM-DD - got \"{1}\" instead.", key, val)

def convertWarning(key, val):
    if val.lower() in (u'obsolete', u'not ready'):
        return val.lower().replace(' ', '-')
    die('Unknown value for "{0}" metadata.', key)

def parseEditor(key, val):
    match = re.match(u"([^,]+) ,\s* ([^,]+) ,?\s* (.*)", val, re.X)
    if match:
        return {
            'name': match.group(1),
            'org': match.group(2),
            'link': match.group(3)
        }
    die("'{0}' format is '<name>, <company>, <email-or-contact-page>. Got:\n{1}", key, val)

def parseIgnoredTerms(key, val):
    return [term.strip().lower() for term in val.split(u',')]

def parseLinkDefaults(key, val):
    defaultSpecs = defaultdict(list)
    for default in val.split(","):
        match = re.match(u"^([\w-]+)  (?:\s+\( ({0}) (?:\s+(TR|ED))? \) )  \s+(.*)$".format("|".join(config.dfnTypes.union(["dfn"]))), default.strip(), re.X)
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

def saveLinkDefaults(key, val):
    for term, defaults in val.items():
        for default in defaults:
            config.doc.refs.defaultSpecs[term].append(default)
