# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from collections import defaultdict
from datetime import date, datetime
from .messages import *
from .htmlhelpers import *

class MetadataManager:
    # required metadata
    status = None
    ED = None
    abstracts = []
    shortname = None
    level = None
    vshortname = None

    # optional metadata
    TR = None
    title = None
    statusText = ""
    date = datetime.utcnow().date()
    deadline = None
    group = None
    editors = []
    previousEditors = []
    previousVersions = []
    warning = None
    atRisk = []
    ignoredTerms = []
    testSuite = None
    mailingList = None
    mailingListArchives = None
    boilerplate = {'omitSections':set()}

    otherMetadata = defaultdict(list)

    @property
    def hasMetadata(self):
        return len(self.manuallySetKeys) > 0

    def __init__(self):
        self.singleValueKeys = {
            "Title": "title",
            "Status": "status",
            "Status Text": "statusText",
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
            "Mailing List Archives": "mailingListArchives",
            "Boilerplate": "boilerplate"
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
            "Link Defaults": parseLinkDefaults,
            "Boilerplate": parseBoilerplate
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
    if val.lower() in ('obsolete', 'not ready'):
        return val.lower().replace(' ', '-')
    match = re.match("Replaced By +(.+)", val, re.I)
    if match:
        config.textMacros['replacedby'] = match.group(1)
        return "replaced-by"
    die('Unknown value for "{0}" metadata.', key)

def parseEditor(key, val):
    match = re.match("([^,]+) ,\s* ([^,]*) ,?\s* (.*)", val, re.X)
    pieces = [piece.strip() for piece in val.split(',')]
    def looksLinkish(string):
        return re.match(ur"\w+:", string) or re.match(ur".+@.+\..+", string)
    data = {
        'name': pieces[0],
        'org' : '',
        'link': ''
    }
    if len(pieces) == 3 and looksLinkish(pieces[2]):
        data['org'] = pieces[1]
        data['link'] = pieces[2]
    elif len(pieces) == 2:
        # See if the piece looks like a link/email
        if looksLinkish(pieces[1]):
            data['link'] = pieces[1]
        else:
            data['org'] = pieces[1]
    elif len(pieces) == 1:
        pass
    else:
        die("'{0}' format is '<name>, <company>?, <email-or-contact-page>?. Got:\n{1}", key, val)
    return data


def parseIgnoredTerms(key, val):
    return [term.strip().lower() for term in val.split(',')]

def parseLinkDefaults(key, val):
    defaultSpecs = defaultdict(list)
    for default in val.split(","):
        match = re.match("^([\w\d-]+)  (?:\s+\( ({0}) (?:\s+(TR|ED))? \) )  \s+(.*)$".format("|".join(config.dfnTypes.union(["dfn"]))), default.strip(), re.X)
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

def parseBoilerplate(key, val):
    boilerplate = {'omitSections':set()}
    for command in val.split(","):
        command = command.strip()
        if re.match("omit [\w-]+$", command):
            boilerplate['omitSections'].add(command[5:])
    return boilerplate
