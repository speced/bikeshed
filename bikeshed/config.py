# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import os.path
import re
from collections import defaultdict
from functools import total_ordering
from .messages import *

debug = True
quiet = True
dryRun = False
minify = True
scriptPath = unicode(os.path.dirname(os.path.realpath(__file__)), encoding="utf-8")
doc = None
textMacros = {}

TRStatuses = ["WD", "FPWD", "LCWD", "CR", "PR", "REC", "PER", "NOTE", "MO"]
unlevelledStatuses = ["LS", "DREAM", "UD", "LS-COMMIT", "LS-BRANCH"]
deadlineStatuses = ["LCWD", "PR"]
noEDStatuses = ["LS", "LS-COMMIT", "LS-BRANCH"]
shortToLongStatus = {
    "ED": "Editor's Draft",
    "WD": "W3C Working Draft",
    "FPWD": "W3C First Public Working Draft",
    "LCWD": "W3C Last Call Working Draft",
    "CR": "W3C Candidate Recommendation",
    "PR": "W3C Proposed Recommendation",
    "REC": "W3C Recommendation",
    "PER": "W3C Proposed Edited Recommendation",
    "NOTE": "W3C Working Group Note",
    "MO": "W3C Member-only Draft",
    "UD": "Unofficial Proposal Draft",
    "DREAM": "A Collection of Interesting Ideas",
    "LS": "Living Standard",
    "LS-COMMIT": "Commit Snapshot",
    "LS-BRANCH": "Branch Snapshot"
}

dfnClassToType = {
    "propdef"            : "property",
    "valdef"             : "value",
    "at-ruledef"         : "at-rule",
    "descdef"            : "descriptor",
    "typedef"            : "type",
    "funcdef"            : "function",
    "selectordef"        : "selector",
    "elementdef"         : "element",
    "element-attrdef"    : "element-attr",
    "eventdef"           : "event",
    "interfacedef"       : "interface",
    "constructordef"     : "constructor",
    "methoddef"          : "method",
    "argdef"             : "argument",
    "attrdef"            : "attribute",
    "callbackdef"        : "callback",
    "dictdef"            : "dictionary",
    "dict-memberdef"     : "dict-member",
    "exceptdef"          : "exception",
    "except-fielddef"    : "except-field",
    "exception-codedef"  : "exception-code",
    "enumdef"            : "enum",
    "constdef"           : "const",
    "typedefdef"         : "typedef",
    "stringdef"          : "stringifier",
    "serialdef"          : "serializer",
    "iterdef"            : "iterator",
    "grammardef"         : "grammar" }

dfnTypes = frozenset(dfnClassToType.values())
maybeTypes = frozenset(["value", "type", "at-rule", "function", "selector"])
cssTypes = frozenset(["property", "value", "at-rule", "descriptor", "type", "function", "selector"])
markupTypes = frozenset(["element", "element-attr"])
idlTypes = frozenset(["event", "interface", "constructor", "method", "argument", "attribute", "callback", "dictionary", "dict-member", "exception", "except-field", "exception-code", "enum", "const", "typedef", "stringifier", "serializer", "iterator"])
idlNameTypes = frozenset(["interface", "dictionary", "enum", "exception", "typedef", "callback"])
functionishTypes = frozenset(["function", "method", "constructor", "stringifier"])
idlMethodTypes = frozenset(["method", "constructor", "stringifier", "idl", "idl-name"])
linkTypes = dfnTypes | frozenset(["propdesc", "functionish", "idl", "idl-name", "maybe", "biblio"])
typesUsingFor = frozenset(["descriptor", "value", "element-attr", "method", "constructor", "argument", "attribute", "const", "dict-member", "event", "except-field", "stringifier", "serializer", "iterator"])
lowercaseTypes = cssTypes | markupTypes | frozenset(["propdesc", "maybe", "dfn"])

linkTypeToDfnType = {
    "propdesc": frozenset(["property", "descriptor"]),
    "functionish": functionishTypes,
    "idl": idlTypes,
    "idl-name": idlNameTypes,
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"])
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])

# Some of the more significant types and their patterns
trivialPattern = re.compile(".+")
typeRe = defaultdict(lambda:trivialPattern)
typeRe["property"] = re.compile("^[\w-]+$")
typeRe["at-rule"] = re.compile("^@[\w-]+$")
typeRe["descriptor"] = typeRe["property"]
typeRe["type"] = re.compile("^<[\w-]+>$")
typeRe["function"] = re.compile("^[\w-]+\(.*\)$")
typeRe["selector"] = re.compile("^::?[\w-]+(\(|$)")
typeRe["constructor"] = typeRe["function"]
typeRe["method"] = typeRe["function"]
typeRe["interface"] = re.compile("^\w+$")

anchorDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]
testSuiteDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]

testAnnotationURL = "//test.csswg.org/harness/annotate.js"

@total_ordering
class HierarchicalNumber(object):
    def __init__(self, valString):
        self.nums = re.split(r"\D+", valString)
        self.originalVal = valString

    def __lt__(self, other):
        try:
            return self.nums < other.nums
        except AttributeError:
            return self.nums[0] < other

    def __eq__(self, other):
        try:
            return self.nums == other.nums
        except AttributeError:
            return self.nums[0] == other

    def __str__(self):
        return self.originalVal

    def __json__(self):
        return self.originalVal

    def __repr__(self):
        return "HierarchicalNumber("+repr(self.originalVal)+")"

def intersperse(iterable, delimiter):
    it = iter(iterable)
    yield next(it)
    for x in it:
        yield delimiter
        yield x







def retrieveCachedFile(filename, quiet=False, str=False):
    cacheLocation = scriptPath + "/spec-data/" + filename
    fallbackLocation = scriptPath + "/spec-data/readonly/" + filename
    try:
        fh = open(cacheLocation, 'r')
    except IOError:
        try:
            fh = open(fallbackLocation, 'r')
        except IOError:
            die("Couldn't retrieve the file '{0}' from cache. Something's wrong, please report this.", filename)
            return
        import shutil
        try:
            if not quiet:
                say("Attempting to save the {0} file to cache...", type)
            if not dryRun:
                shutil.copy(fallbackLocation, cacheLocation)
            if not quiet:
                say("Successfully saved the {0} file to cache.", type)
        except:
            if not quiet:
                warn("Couldn't save the {0} file to cache. Proceeding...", type)
    if str:
        return unicode(fh.read(), encoding="utf-8")
    else:
        return fh

def printjson(obj):
    import json
    return json.dumps(obj, indent=2, default=lambda x:x.__json__())


def processTextNodes(nodes, regex, replacer):
    '''
    Takes an array of alternating text/objects,
    and runs reSubObject on the text parts,
    splicing them into the passed-in array.
    Mutates!
    '''
    for i, node in enumerate(nodes):
        # Node list always alternates between text and elements
        if i%2 == 0:
            nodes[i:i+1] = reSubObject(regex, node, replacer)
    return nodes

def reSubObject(pattern, string, repl=None):
    '''
    like re.sub, but replacements don't have to be text;
    returns an array of alternating unmatched text and match objects instead.
    If repl is specified, it's called with each match object,
    and the result then shows up in the array instead.
    '''
    lastEnd = 0
    pieces = []
    for match in pattern.finditer(string):
        pieces.append(string[lastEnd:match.start()])
        if repl:
            pieces.append(repl(match))
        else:
            pieces.append(match)
        lastEnd = match.end()
    pieces.append(string[lastEnd:])
    return pieces

def simplifyText(text, convertDashes=False):
    # Remove anything that's not a name character.
    # If convertDashes is True, turn dashes into underscores,
    # so two terms that differ only by dashes generate different text.
    if convertDashes:
        text = text.replace("-", "_")
    text = text.strip().lower()
    text = re.sub(r"[\s/]+", "-", text)
    text = re.sub(r"[^a-z0-9_-]", "", text)
    return text
