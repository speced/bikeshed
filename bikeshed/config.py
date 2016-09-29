# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import os.path
import io
import re
import collections
from collections import defaultdict
from functools import total_ordering
from .messages import *

force = True
quiet = True
dryRun = False
printMode = "console"
scriptPath = os.path.dirname(os.path.realpath(__file__))
doc = None
textMacros = {}

shortToLongStatus = {
    "DREAM": "A Collection of Interesting Ideas",
    "LS": "Living Standard",
    "LS-COMMIT": "Commit Snapshot",
    "LS-BRANCH": "Branch Snapshot",
    "FINDING": "Finding",
    "w3c/ED": "Editor's Draft",
    "w3c/WD": "W3C Working Draft",
    "w3c/FPWD": "W3C First Public Working Draft",
    "w3c/LCWD": "W3C Last Call Working Draft",
    "w3c/CR": "W3C Candidate Recommendation",
    "w3c/PR": "W3C Proposed Recommendation",
    "w3c/REC": "W3C Recommendation",
    "w3c/PER": "W3C Proposed Edited Recommendation",
    "w3c/NOTE": "W3C Working Group Note",
    "w3c/MO": "W3C Member-only Draft",
    "w3c/UD": "Unofficial Proposal Draft",
    "w3c/CG-DRAFT": "Draft Community Group Report",
    "w3c/CG-FINAL": "Final Community Group Report",
    "iso/I": "Issue",
    "iso/DR": "Defect Report",
    "iso/D": "Draft Proposal",
    "iso/P": "Published Proposal",
    "iso/MEET": "Meeting Announcements",
    "iso/RESP": "Records of Response",
    "iso/MIN": "Minutes",
    "iso/ER": "Editor's Report",
    "iso/SD": "Standing Document",
    "iso/PWI": "Preliminary Work Item",
    "iso/NP": "New Proposal",
    "iso/NWIP": "New Work Item Proposal",
    "iso/WD": "Working Draft",
    "iso/CD": "Committee Draft",
    "iso/FCD": "Final Committee Draft",
    "iso/DIS": "Draft International Standard",
    "iso/FDIS": "Final Draft International Standard",
    "iso/PRF": "Proof of a new International Standard",
    "iso/IS": "International Standard",
    "iso/TR": "Technical Report",
    "iso/DTR": "Draft Technical Report",
    "iso/TS": "Technical Specification",
    "iso/DTS": "Draft Technical Specification",
    "iso/PAS": "Publicly Available Specification",
    "iso/TTA": "Technology Trends Assessment",
    "iso/IWA": "International Workshop Agreement",
    "iso/COR": "Technical Corrigendum",
    "iso/GUIDE": "Guidance to Technical Committees",
    "iso/NP-AMD": "New Proposal Amendment",
    "iso/AWI-AMD": "Approved new Work Item Amendment",
    "iso/WD-AMD": "Working Draft Amendment",
    "iso/CD-AMD": "Committe Draft Amendment",
    "iso/PD-AMD": "Proposed Draft Amendment",
    "iso/FPD-AMD": "Final Proposed Draft Amendment",
    "iso/D-AMD": "Draft Amendment",
    "iso/FD-AMD": "Final Draft Amendment",
    "iso/PRF-AMD": "Proof Amendment",
    "iso/AMD": "Amendment"
}
TRStatuses = ["w3c/WD", "w3c/FPWD", "w3c/LCWD", "w3c/CR", "w3c/PR", "w3c/REC", "w3c/PER", "w3c/NOTE", "w3c/MO"]
unlevelledStatuses = ["LS", "DREAM", "w3c/UD", "LS-COMMIT", "LS-BRANCH", "FINDING"]
deadlineStatuses = ["w3c/LCWD", "w3c/PR"]
noEDStatuses = ["LS", "LS-COMMIT", "LS-BRANCH", "FINDING", "DREAM"]

megaGroups = {
    "w3c": frozenset(["csswg", "dap", "fxtf", "geolocation", "houdini", "html", "ricg", "svg", "texttracks", "uievents", "web-bluetooth-cg", "webappsec", "webauthn", "webperf", "webplatform", "webspecs", "webvr", "wicg"]),
    "iso": frozenset(["wg21"]),
    "priv-sec": frozenset(["csswg", "dap", "fxtf", "geolocation", "houdini", "html", "ricg", "svg", "texttracks", "uievents", "web-bluetooth-cg", "webappsec", "webplatform", "webspecs", "whatwg"])
}


def canonicalizeStatus(rawStatus, group):
    if rawStatus is None:
        return None

    def megaGroupsForStatus(status):
        # Returns a list of megagroups that recognize the given status
        megaGroups = []
        for key in shortToLongStatus.keys():
            mg,_,s = key.partition("/")
            if s == status:
                megaGroups.append(mg)
        return megaGroups

    def printList(items):
        # Format a list of strings into an English list.
        items = list(items)
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return "{0} or {1}".format(*items)
        return "{0}, or {1}".format(", ".join(items[:-1]), items[-1])

    # Canonicalize the rawStatus that was passed in, into a known form.
    # Might be foo/BAR, or just BAR.
    megaGroup,_,status = rawStatus.partition("/")
    if status == "":
        status = megaGroup
        megaGroup = ""
    megaGroup = megaGroup.lower()
    status = status.upper()
    if megaGroup:
        canonStatus = megaGroup + "/" + status
    else:
        canonStatus = status

    if group is not None:
        group = group.lower()

    # Using a directly-recognized status is A-OK.
    # (Either one of the unrestricted statuses,
    # or one of the restricted statuses with the correct standards-org prefix.)
    if canonStatus in shortToLongStatus:
        return canonStatus

    possibleMgs = megaGroupsForStatus(status)

    # If they specified a standards-org prefix and it wasn't found,
    # that's an error.
    if megaGroup:
        # Was the error because the megagroup doesn't exist?
        if possibleMgs:
            if megaGroup not in megaGroups:
                msg = "Status metadata specified an unrecognized '{0}' organization.".format(megaGroup)
            else:
                msg = "Status '{0}' can't be used with the org '{1}'.".format(status, megaGroup)
            if "" in possibleMgs:
                if len(possibleMgs) == 1:
                    msg += " That status must be used without an org at all, like `Status: {0}`".format(status)
                else:
                    msg += " That status can only be used with the org{0} {1}, or without an org at all.".format(
                        "s" if len(possibleMgs)>1 else "",
                        printList("'{0}'".format(x) for x in possibleMgs if x != ""))
            else:
                if len(possibleMgs) == 1:
                    msg += " That status can only be used with the org '{0}', like `Status: {0}/{1}`".format(possibleMgs[0], status)
                else:
                    msg += " That status can only be used with the orgs {0}.".format(printList("'{0}'".format(x) for x in possibleMgs))

        else:
            if megaGroup not in megaGroups:
                msg = "Unknown Status metadata '{0}'. Check the docs for valid Status values.".format(canonStatus)
            else:
                msg = "Status '{0}' can't be used with the org '{1}'. Check the docs for valid Status values.".format(status, megaGroup)
        die("{0}", msg)
        return canonStatus

    # Otherwise, they provided a bare status.
    # See if their group is compatible with any of the prefixed statuses matching the bare status.
    assert "" not in possibleMgs # if it was here, the literal "in" test would have caught this bare status
    for mg in possibleMgs:
        if group in megaGroups[mg]:
            return mg + "/" + status
    # Group isn't in any compatible org, so suggest prefixing.
    if possibleMgs:
        msg = "You used Status: {0}, but that's limited to the {1} org{2}".format(
            rawStatus,
            printList("'{0}'".format(mg) for mg in possibleMgs),
            "s" if len(possibleMgs)>1 else "")
        if group:
            msg += ", and your group '{0}' isn't recognized as being in {1}.".format(group, "any of those orgs" if len(possibleMgs)>1 else "that org")
            msg += " If this is wrong, please file a Bikeshed issue to categorize your group properly, and/or try:\n"
            msg += "\n".join("Status: {0}/{1}".format(mg, status) for mg in possibleMgs)
        else:
            msg += ", and you don't have a Group metadata. Please declare your Group, or check the docs for statuses that can be used by anyone."
    else:
        msg = "Unknown Status metadata '{0}'. Check the docs for valid Status values.".format(canonStatus)
    die("{0}", msg)
    return canonStatus


dfnClassToType = {
    "abstract-opdef"     : "abstract-op",
    "propdef"            : "property",
    "valdef"             : "value",
    "at-ruledef"         : "at-rule",
    "descdef"            : "descriptor",
    "typedef"            : "type",
    "funcdef"            : "function",
    "selectordef"        : "selector",
    "elementdef"         : "element",
    "element-attrdef"    : "element-attr",
    "attr-valuedef"      : "attr-value",
    "element-statedef"   : "element-state",
    "eventdef"           : "event",
    "interfacedef"       : "interface",
    "namespacedef"       : "namespace",
    "extendedattrdef"    : "extended-attribute",
    "constructordef"     : "constructor",
    "methoddef"          : "method",
    "argdef"             : "argument",
    "attrdef"            : "attribute",
    "callbackdef"        : "callback",
    "dictdef"            : "dictionary",
    "dict-memberdef"     : "dict-member",
    "enumdef"            : "enum",
    "enum-valuedef"      : "enum-value",
    "exceptiondef"       : "exception",
    "constdef"           : "const",
    "typedefdef"         : "typedef",
    "stringdef"          : "stringifier",
    "serialdef"          : "serializer",
    "iterdef"            : "iterator",
    "mapdef"             : "maplike",
    "setdef"             : "setlike",
    "grammardef"         : "grammar",
    "schemedef"          : "scheme",
    "statedef"           : "state",
    "modedef"            : "mode",
    "contextdef"         : "context",
    "facetdef"           : "facet",
    "http-headerdef"     : "http-header"}

dfnTypes = frozenset(dfnClassToType.values() + ["dfn"])
maybeTypes = frozenset(["value", "type", "at-rule", "function", "selector"])
cssTypes = frozenset(["property", "value", "at-rule", "descriptor", "type", "function", "selector"])
markupTypes = frozenset(["element", "element-attr", "element-state", "attr-value"])
idlTypes = frozenset(["event", "interface", "namespace", "extended-attribute", "constructor", "method", "argument", "attribute", "callback", "dictionary", "dict-member", "enum", "enum-value", "exception", "const", "typedef", "stringifier", "serializer", "iterator", "maplike", "setlike"])
idlNameTypes = frozenset(["interface", "namespace", "dictionary", "enum", "typedef", "callback"])
functionishTypes = frozenset(["function", "method", "constructor", "stringifier"])
idlMethodTypes = frozenset(["method", "constructor", "stringifier", "idl", "idl-name"])
linkTypes = dfnTypes | frozenset(["propdesc", "functionish", "idl", "idl-name", "element-sub", "maybe", "biblio"])
typesUsingFor = frozenset(["descriptor", "value", "element-attr", "attr-value", "element-state", "method", "constructor", "argument", "attribute", "const", "dict-member", "event", "enum-value", "stringifier", "serializer", "iterator", "maplike", "setlike", "state", "mode", "context", "facet"])
lowercaseTypes = cssTypes | markupTypes | frozenset(["propdesc", "element-sub", "maybe", "dfn", "grammar", "http-header"])

linkTypeToDfnType = {
    "propdesc": frozenset(["property", "descriptor"]),
    "functionish": functionishTypes,
    "idl": idlTypes,
    "idl-name": idlNameTypes,
    "element-sub": frozenset(["element-attr", "element-state"]),
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"]),
    "all": linkTypes
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])


def linkTypeIn(linkTypes, targetTypes="all"):
    # Tests if a link type (which might be a shorthand type like "idl")
    # matches against a given set of types.
    if isinstance(linkTypes, basestring):
        linkTypes = linkTypeToDfnType[linkTypes]
    else:
        linkTypes = set(linkTypes)
    if isinstance(targetTypes, basestring):
        targetTypes = linkTypeToDfnType[targetTypes]
    else:
        targetTypes = set(targetTypes)
    return bool(linkTypes & targetTypes)

# Elements that are allowed to provide definitions to Shepherd
dfnElements = frozenset(["dfn", "h2", "h3", "h4", "h5", "h6"])
anchorishElements = dfnElements.union(["a"])
dfnElementsSelector = "dfn, h2[data-dfn-type], h3[data-dfn-type], h4[data-dfn-type], h5[data-dfn-type], h6[data-dfn-type]"

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

testAnnotationURL = "https://test.csswg.org/harness/annotate.js"


@total_ordering
class HierarchicalNumber(object):
    def __init__(self, valString):
        if valString.strip().lower() == "none":
            self.nums = None
        else:
            self.nums = [int(x) for x in re.split(r"\D+", valString) if x != ""]
        self.originalVal = valString

    def __nonzero__(self):
        return bool(self.nums)

    def __lt__(self, other):
        # Unlevelled numbers are falsey, and greater than all numbers.
        if not self and other:
            return False
        elif self and not other:
            return True
        elif not self and not other:
            return False

        try:
            return self.nums < other.nums
        except AttributeError:
            return self.nums[0] < other

    def __eq__(self, other):
        if (not self and other) or (self and not other):
            return False
        if not self and not other:
            return True
        try:
            return self.nums == other.nums
        except AttributeError:
            return self.nums[0] == other

    def __str__(self):
        return self.originalVal

    def __json__(self):
        return self.originalVal

    def __repr__(self):
        return "HierarchicalNumber(" + repr(self.originalVal) + ")"


def intersperse(iterable, delimiter):
    it = iter(iterable)
    yield next(it)
    for x in it:
        yield delimiter
        yield x

# Super-None, falsey and returns itself from every method/attribute/etc


class Nil(object):
    def __repr__(self):
        return "Nil()"

    def __str__(self):
        return "Nil"

    def __nonzero__(self):
        return False

    def __call__(self, *args, **kwargs):
        return self

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, val):
        return self

    def __delitem__(self, key, val):
        return self

    def __getattr__(self, name):
        return self

    def __setattr__(self, name, value):
        return self

    def __delattr__(self, name, value):
        return self

    def __eq__(self, other):
        if isinstance(other, Nil) or other is None:
            return True
        return False

    def __iter__(self):
        return iter([])


def retrieveDataFile(filename, quiet=False, str=False):
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


def retrieveBoilerplateFile(self, name, group=None, status=None, error=True):
    # Looks in three locations, in order:
    # the folder the spec source is in, the group's boilerplate folder, and the generic boilerplate folder.
    # In each location, it first looks for the file specialized on status, and then for the generic file.
    # Filenames must be of the format NAME.include or NAME-STATUS.include
    if group is None and self.md.group is not None:
        group = self.md.group.lower()
    if status is None:
        status = self.md.rawStatus

    localFolder = os.path.dirname(os.path.abspath(self.inputSource))
    includeFolder = os.path.join(config.scriptPath, "include")
    statusFile = "{0}-{1}.include".format(name, status)
    genericFile = "{0}.include".format(name)
    filenames = []
    filenames.append(os.path.join(localFolder, statusFile))
    filenames.append(os.path.join(localFolder, genericFile))
    if group:
        filenames.append(os.path.join(includeFolder, group, statusFile))
        filenames.append(os.path.join(includeFolder, group, genericFile))
    filenames.append(os.path.join(includeFolder, statusFile))
    filenames.append(os.path.join(includeFolder, genericFile))

    for filename in filenames:
        if os.path.isfile(filename):
            try:
                with io.open(filename, 'r', encoding="utf-8") as fh:
                    return fh.read()
            except IOError:
                if error:
                    die("The include file for {0} disappeared underneath me.", name)
                return ""
            break
    else:
        if error:
            die("Couldn't find an appropriate include file for the {0} inclusion, given group='{1}' and status='{2}'.", name, group, status)
        return ""


def printjson(x, indent=2, level=0):
    if isinstance(indent, int):
        # Convert into a number of spaces.
        indent = " " * indent
    x = getjson(x)
    if isinstance(x, dict):
        ret = printjsonobject(x, indent, level)
    elif isinstance(x, list):
        if len(x) > 0 and isinstance(getjson(x[0]), dict):
            ret = printjsonobjectarray(x, indent, level)
        else:
            ret = printjsonsimplearray(x, indent, level)
    else:
        ret = printjsonprimitive(x)
    if level == 0 and ret.startswith("\n"):
        ret = ret[1:]
    return ret
    #return json.dumps(obj, indent=2, default=lambda x:x.__json__())


def getjson(x):
    try:
        return x.__json__()
    except:
        return x


def printjsonobject(x, indent, level):
    x = getjson(x)
    ret = ""
    maxKeyLength = 0
    for k in x.keys():
        maxKeyLength = max(maxKeyLength, len(k))
    for k,v in x.items():
        ret += "\n" + (indent * level) + printColor((k + ": ").ljust(maxKeyLength + 2), "cyan") + printjson(v, indent, level + 1)
    return ret


def printjsonobjectarray(x, indent, level):
    # Prints an array of objects
    x = getjson(x)
    ret = ""
    for i,v in enumerate(x):
        if i != 0:
            ret += "\n" + (indent * level) + printColor("=" * 10, "blue")
        ret += printjsonobject(v, indent, level)
    return ret


def printjsonsimplearray(x, indent, level):
    x = getjson(x)
    ret = printColor("[", "blue")
    for i,v in enumerate(x):
        if i != 0:
            ret += ", "
        ret += printjsonprimitive(v)
    ret += printColor("]", "blue")
    return ret


def printjsonprimitive(x):
    x = getjson(x)
    if isinstance(x, int):
        return unicode(x)
    if isinstance(x, basestring):
        return x
    if isinstance(x, bool):
        return unicode(x)
    if x is None:
        return "null"


def processTextNodes(nodes, regex, replacer):
    '''
    Takes an array of alternating text/objects,
    and runs reSubObject on the text parts,
    splicing them into the passed-in array.
    Mutates!
    '''
    for i, node in enumerate(nodes):
        # Node list always alternates between text and elements
        if i % 2 == 0:
            nodes[i:i + 1] = reSubObject(regex, node, replacer)
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


def simplifyText(text):
    # Remove anything that's not a name character.
    text = text.strip().lower()
    # I convert ( to - so foo(bar) becomes foo-bar,
    # but then I have to remove () because there's nothing to separate,
    # otherwise I get a double-dash in some cases.
    text = re.sub(r"\(\)", "", text)
    text = re.sub(r"[\s/(,]+", "-", text)
    text = re.sub(r"[^a-z0-9_-]", "", text)
    text = text.rstrip("-")
    return text


def linkTextsFromElement(el, preserveCasing=False):
    from .htmlhelpers import find, textContent
    if el.get('data-lt') == '':
        return []
    elif el.get('data-lt'):
        rawText = el.get('data-lt')
        if rawText in ["|", "||", "|||"]:
            texts = [rawText]
        else:
            texts = [x.strip() for x in rawText.split('|')]
    else:
        if el.tag in ("dfn", "a"):
            texts = [textContent(el).strip()]
        elif el.tag in ("h2", "h3", "h4", "h5", "h6"):
            texts = [textContent(find(".content", el)).strip()]
    if el.get('data-local-lt'):
        localTexts = [x.strip() for x in el.get('data-local-lt').split('|')]
        for text in localTexts:
            if text in texts:
                # lt and local-lt both specify the same thing
                raise DuplicatedLinkText(text, texts + localTexts, el)
        texts += localTexts

    texts = [re.sub(r"\s+", " ", x) for x in texts if x != '']
    return texts


class DuplicatedLinkText(Exception):
    def __init__(self, offendingText, allTexts, el):
        self.offendingText = offendingText
        self.allTexts = allTexts
        self.el = el

    def __unicode__(self):
        return "<Text '{0}' shows up in both lt and local-lt>".format(self.offendingText)


def firstLinkTextFromElement(el):
    try:
        texts = linkTextsFromElement(el)
    except DuplicatedLinkText as e:
        texts = e.allTexts
    return texts[0] if len(texts) else None


def splitForValues(forValues):
    '''
    Splits a string of 1+ "for" values into an array of individual value.
    Respects function args, etc.
    Currently, for values are separated by commas.
    '''
    if forValues is None:
        return None
    return [value.strip() for value in re.split(r',(?![^()]*\))', forValues) if value.strip()]


class BoolSet(collections.MutableMapping):
    '''
    Implements a "boolean set",
    where keys can be explicitly set to True or False,
    but interacted with like a normal set
    (similar to Counter, but with bools).
    Can also set whether the default should consider unset values to be True or False by default.
    '''

    def __init__(self, values=None, default=False):
        self._internal = {}
        if isinstance(values, collections.Mapping):
            for k,v in values.items():
                self._internal[k] = bool(v)
        elif isinstance(values, collections.Iterable):
            for k in values:
                self._internal[k] = True
        self.default = bool(default)

    def __missing__(self, key):
        return self.default

    def __contains__(self, key):
        if key in self._internal:
            return self._internal[key]
        else:
            return self.default

    def __getitem__(self, key):
        return key in self

    def __setitem__(self, key, val):
        self._internal[key] = bool(val)

    def __delitem__(self, key):
        del self._internal[key]

    def __iter__(self):
        return iter(self._internal)

    def __len__(self):
        return len(self._internal)

    def __repr__(self):
        if self.default is False:
            trueVals = [k for k,v in self._internal.items() if v is True]
            vrepr = "[" + ", ".join(repr(x) for x in trueVals) + "]"
        else:
            falseVals = [k for k,v in self._internal.items() if v is False]
            vrepr = "{" + ", ".join(repr(x) + ":False" for x in falseVals) + "}"
        return "BoolSet({0}, default={1})".format(vrepr, self.default)
