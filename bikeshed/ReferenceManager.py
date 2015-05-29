# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
import io
import collections
import copy
import collections
from collections import defaultdict
from operator import itemgetter
from . import config
from . import biblio
from . import enum
from . import datablocks
from .SortedList import SortedList
from .messages import *
from .htmlhelpers import *

class ReferenceManager(object):

    def __init__(self, specStatus=None):
        # Dict of {linking text => [anchor data]}
        self.refs = defaultdict(list)
        # Dict of {argless method signatures => [full method signatures]}
        self.methods = defaultdict(list)
        # Dict of {spec vshortname => spec data}
        self.specs = dict()
        # Dict of {linking text => link-defaults data}
        self.defaultSpecs = defaultdict(list)
        # Set of spec vshortnames to remove from consideration when there are other possible anchors
        self.ignoredSpecs = set()
        # Set of (obsolete spec vshortname, replacing spec vshortname), when both obsolete and replacing specs are possible anchors
        self.replacedSpecs = set()
        # Dict of {biblio term => biblio data}
        self.biblios = defaultdict(list)
        self.status = specStatus

    def initializeRefs(self, doc):
        # Load up the xref data
        self.specs.update(json.loads(config.retrieveCachedFile("specs.json", quiet=True, str=True)))
        with config.retrieveCachedFile("anchors.data", quiet=True) as lines:
            self.refs = decodeAnchors(lines)
        self.methods.update(json.loads(config.retrieveCachedFile("methods.json", quiet=True, str=True)))
        # Get local anchor data
        try:
            with io.open("anchors.bsdata", 'r', encoding="utf-8") as lines:
                datablocks.transformAnchors(lines, doc)
        except IOError:
            pass

        datablocks.transformInfo(config.retrieveCachedFile("link-defaults.infotree", quiet=True, str=True).split("\n"), doc)
        # local info
        try:
            with io.open("link-defaults.infotree", 'r', encoding="utf-8") as lines:
                datablocks.transformInfo(lines, doc)
        except IOError:
            pass

    def initializeBiblio(self):
        with config.retrieveCachedFile("biblio.data", quiet=True) as lines:
            try:
                while True:
                    key = lines.next()
                    b = {
                        "linkText": lines.next(),
                        "date": lines.next(),
                        "status": lines.next(),
                        "title": lines.next(),
                        "dated_url": lines.next(),
                        "current_url": lines.next(),
                        "other": lines.next(),
                        "etAl": lines.next() != "\n",
                        "order": 3,
                        "authors": []
                    }
                    while True:
                        line = lines.next()
                        if line == b"-\n":
                            break
                        b['authors'].append(line)
                    self.biblios[key].append(b)
            except StopIteration:
                pass


        # Get local bibliography data
        try:
            with io.open("biblio.json", 'r', encoding="utf-8") as fh:
                biblio.processSpecrefBiblioFile(fh.read(), self.biblios, order=2)
        except IOError:
            # Missing file is fine
            pass


    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, val):
        if val is None:
            self._status = None
        elif val in config.TRStatuses:
            self._status = "TR"
        elif val in config.shortToLongStatus:
            self._status = "ED"
        else:
            die("Unknown spec status '{0}'.", val)
            self._status = None
        return self._status

    def setSpecData(self, md):
        self.status = md.status
        self.specName = md.shortname
        self.specLevel = md.level
        self.specVName = md.vshortname

        for term, defaults in md.linkDefaults.items():
            for default in defaults:
                self.defaultSpecs[term].append(default)

        # Need to get a real versioned shortname,
        # with the possibility of overriding the "shortname-level" pattern.
        self.removeSameSpecRefs()

    def removeSameSpecRefs(self):
        # Kill all the non-local anchors with the same shortname as the current spec,
        # so you don't end up accidentally linking to something that's been removed from the local copy.
        for term, refs in self.refs.items():
            self.refs[term] = [ref for ref in refs if ref['shortname'].rstrip("\n")!=self.specName or ref['status']=="local"]
            # TODO: OMIGOD WHY AM I DOING THIS FOR EVERY SINGLE REF EVER AT LEAST SEARCH FIRST
            # Or maybe just move this functionality into addLocalDfns, ffs
            # This damned thing is a whole 1.25% of runtime

    def addLocalDfns(self, dfns):
        for el in dfns:
            if hasClass(el, "no-ref"):
                continue
            for linkText in linkTextsFromElement(el):
                linkText = unfixTypography(linkText)
                linkText = re.sub("\s+", " ", linkText)
                linkType = treeAttr(el, 'data-dfn-type')
                if linkType in config.lowercaseTypes:
                    linkText = linkText.lower()
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                    if self.getLocalRef(linkType, linkText):
                        die("Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, linkType)
                        continue
                else:
                    dfnFor = set(splitForValues(dfnFor))
                    encounteredError = False
                    for singleFor in dfnFor:
                        if self.getLocalRef(linkType, linkText, linkFor=singleFor):
                            encounteredError = True
                            die("Multiple local '{1}' <dfn>s for '{2}' have the same linking text '{0}'.", linkText, linkType, singleFor)
                            break
                    if encounteredError:
                        continue
                for term in dfnFor.copy():
                    # Saying a value is for a descriptor with @foo/bar
                    # should also make it for the bare descriptor bar.
                    match = re.match("@[a-zA-Z0-9-_]+/(.*)", term)
                    if match:
                        dfnFor.add(match.group(1).strip())
                # convert back into a list now, for easier JSONing
                dfnFor = list(dfnFor)
                if linkType in config.dfnTypes.union(["dfn"]):
                    existingAnchors = self.refs[linkText]
                    ref = {
                        "type":linkType,
                        "status":"local",
                        "spec":self.specVName,
                        "shortname":self.specName,
                        "level":self.specLevel,
                        "url":"#"+el.get('id'),
                        "export":True,
                        "for": dfnFor
                    }
                    self.refs[linkText].append(ref)

    def getLocalRef(self, linkType, text, linkFor=None, linkForHint=None, el=None):
        return self.queryRefs(text=text, linkType=linkType, status="local", linkFor=linkFor, linkForHint=linkForHint)[0]

    def getRef(self, linkType, text, spec=None, status=None, linkFor=None, linkForHint=None, error=True, el=None):
        # If error is False, this function just shuts up and returns a reference or None
        # Otherwise, it pops out debug messages for the user.

        # 'maybe' links might not link up, so it's fine for them to have no references.
        # The relevent errors are gated by this variable.
        zeroRefsError = error and linkType!="maybe"

        text = unfixTypography(text)
        if linkType in config.lowercaseTypes:
            text = text.lower()

        status = status or self.status
        if status not in ("ED", "TR", "local"):
            if error:
                die("Unknown spec status '{0}'. Status must be ED, TR, or local.", status)
            return None

        # Local refs always get precedence, no matter what.
        localRefs = self.getLocalRef(linkType, text, linkFor, linkForHint, el)
        if len(localRefs) == 1:
            return localRefs[0]
        elif len(localRefs) > 1:
            if error:
                warn("Multiple possible '{0}' local refs for '{1}'.\nArbitrarily chose the one with type '{2}' and for '{3}'.",
                     linkType,
                     text,
                     localRefs[0].type,
                     "' or '".join(localRefs[0].for_))
            return localRefs[0]

        # Take defaults into account
        if (not spec or not status):
            variedTexts = [v for v in linkTextVariations(text, linkType) if v in self.defaultSpecs]
            if variedTexts:
                for dfnSpec, dfnType, dfnStatus, dfnFor in reversed(self.defaultSpecs[variedTexts[0]]):
                    if dfnType in config.linkTypeToDfnType[linkType]:
                        spec = spec or dfnSpec
                        status = status or dfnStatus
                        linkFor = linkFor or dfnFor
                        break

        # Get the relevant refs
        if spec is None:
            export = True
        else:
            export = None
        refs, failure = self.queryRefs(text=text, linkType=linkType, spec=spec, status=status, linkFor=linkFor, linkForHint=linkForHint, export=export, ignoreObsoletes=True)

        if failure and linkType in config.idlMethodTypes and text.endswith("()"):
            # Allow foo(bar) to be linked to with just foo(), but only if it's completely unambiguous.
            def multipleEmptyArgMethodRefs(refs, text):
                # If there's a single ref, we're good.
                if len(refs) == 1:
                    return refs[0]
                # If there's none, we might find more elsewhere
                if len(refs) == 0:
                    return None
                # Otherwise, there's more than one ref.
                # Need to distinguish between multiple overloads for the same method
                # and multiple methods for different interfaces.
                forValue = refs[0].for_
                if all(ref.for_ == forValue for ref in refs):
                    die("'{0}' has multiple overloads, and it's not clear which to link to.\n  Please specify the names of the required args, like 'foo(bar, baz)'.", text)
                    return None
                die("Multiple interfaces have the method '{0}'. Please specify the interface this is for.", text)
                return None
            textPrefix = text[:-1]
            candidates, _ = self.queryRefs(linkType=linkType, status="local", linkFor=linkFor)
            candidateRefs = {c.url: c for c in candidates if c.text.startswith(textPrefix)}.values()
            candidateRef = multipleEmptyArgMethodRefs(candidateRefs, text)
            if candidateRef:
                return candidateRef
            # And repeat for non-locals
            candidates, _ = self.queryRefs(linkType=linkType, spec=spec, status=status, linkFor=linkFor, export=export, ignoreObsoletes=True)
            candidateRefs = {c.url: c for c in candidates if c.text.startswith(textPrefix)}.values()
            candidateRef = multipleEmptyArgMethodRefs(candidateRefs, text)
            if candidateRef:
                return candidateRef

        if failure and linkType in ("argument", "idl") and linkFor is not None and linkFor.endswith("()"):
            # Allow foo(bar) to be for'd to with just foo() if it's completely unambiguous.
            candidateFor, _, forPrefix = linkFor.partition("/") if "/" in linkFor else (None, None, '')
            forPrefix = forPrefix[:-1]
            candidates, _ = self.queryRefs(linkType="functionish", status="local", linkFor=candidateFor)
            localRefs = {c.url: c for c in candidates if c.text.startswith(forPrefix)}.values()
            if len(localRefs) == 1:
                return localRefs[0]
            # And repeat for non-locals
            candidates, _ = self.queryRefs(linkType="functionish", spec=spec, status=status, linkFor=candidateFor, export=export, ignoreObsoletes=True)
            remoteRefs = {c.url: c for c in candidates if c.text.startswith(forPrefix)}.values()
            if len(remoteRefs) == 1:
                return remoteRefs[0]
            if zeroRefsError and (len(localRefs) or len(remoteRefs)):
                die("Too many possible method targets to disambiguate '{0}/{1}'. Please specify the names of the required args, like 'foo(bar, baz)', in the 'for' attribute.", linkFor, text)

        if failure == "text" or failure == "type":
            if linkType in ("property", "propdesc", "descriptor") and text.startswith("--"):
                return None
            if zeroRefsError:
                die("No '{0}' refs found for '{1}'.", linkType, text)
            return None
        elif failure == "export":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' that are marked for export.", linkType, text)
            return None
        elif failure == "spec":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with spec '{2}'.", linkType, text, spec)
            return None
        elif failure == "for":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with for='{2}'.", linkType, text, linkFor)
            return None
        elif failure == "status":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' compatible with status '{2}'.", linkType, text, status)
            return None
        elif failure == "ignored-specs":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}':\n{2}", linkType, text, outerHTML(el))
            return None
        elif failure:
            die("Programming error - I'm not catching '{0}'-type link failures. Please report!", failure)
            return None

        if len(refs) == 1:
            # Success!
            return refs[0]

        # If all the refs are for the same shortname,
        # assume you want to link to the latest one (highest level).
        if all(ref.shortname == refs[0].shortname for ref in refs):
            maxLevel = config.HierarchicalNumber("-1")
            for ref in refs:
                if ref.level > maxLevel:
                    maxLevel = ref.level
            leveledRefs = [ref for ref in refs if ref.level == maxLevel]
            # Still potentially possible for a non-Bikeshed spec to have duplicate refs here,
            # so I have to check for singularity.
            if len(leveledRefs) == 1:
                return leveledRefs[0]

        # If we hit this point, there are >1 possible refs to choose from.
        # Default to linking to the first one.
        defaultRef = refs[0]
        if linkType == "propdesc":
            # If both props and descs are possible, default to prop.
            for ref in refs:
                if ref.type == "property":
                    defaultRef = ref
                    break
        if error:
            possibleRefs = []
            for ref in simplifyPossibleRefs(refs):
                if ref['for_']:
                    possibleRefs.append('spec:{spec}; type:{type}; for:{for_}; text:{text}'.format(**ref))
                else:
                    possibleRefs.append('spec:{spec}; type:{type}; text:{text}'.format(**ref))
            warn("Multiple possible '{0}' refs for '{1}'.\nArbitrarily chose the one in {2}.\nIf this is wrong, insert one of the following lines into a <pre class=link-defaults> block:\n{3}",
                 linkType,
                 text,
                 defaultRef.spec,
                 '\n'.join(possibleRefs))
        return defaultRef

    def getBiblioRef(self, text, status, generateFakeRef=False, el=None):
        key = text.lower()
        if key in self.biblios:
            candidates = self.biblios[key]
        elif key+"\n" in self.biblios:
            candidates = self.biblios[key+"\n"]
        elif key in self.specs and generateFakeRef:
            return biblio.SpecBasedBiblioEntry(self.specs[key], preferredURL=status)
        else:
            return None

        candidates = sorted(stripLineBreaks(candidates), key=itemgetter('order'))
        # TODO: When SpecRef definitely has all the CSS specs, turn on this code.
        # if candidates[0]['order'] > 3: # 3 is SpecRef level
        #    warn("Bibliography term '{0}' wasn't found in SpecRef.\n         Please find the equivalent key in SpecRef, or submit a PR to SpecRef.", text)
        return biblio.BiblioEntry(preferredURL=status, **candidates[0])

    def queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, linkForHint=None, status=None, export=None, ignoreObsoletes=False, **kwargs):
        results, error = self._queryRefs(text, spec, linkType, linkFor, linkForHint, status, export, ignoreObsoletes, exact=True)
        if error:
            return self._queryRefs(text, spec, linkType, linkFor, linkForHint, status, export, ignoreObsoletes)
        else:
            return results, error

    def _queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, linkForHint=None, status=None, export=None, ignoreObsoletes=False, exact=False, **kwargs):
        # Query the ref database.
        # If it fails to find a ref, also returns the stage at which it finally ran out of possibilities.
        def refsIterator(refs):
            # Turns a dict of arrays of refs into an iterator of refs
            for key, group in refs.items():
                for ref in group:
                    yield RefWrapper(key, ref)
        def textRefsIterator(refs, texts):
            # Same as above, but only grabs those keyed to a given text
            for text in texts:
                for ref in refs.get(text, []):
                    yield RefWrapper(text, ref)
                for ref in refs.get(text+"\n", []):
                    yield RefWrapper(text, ref)

        # Set up the initial list of refs to query
        if text:
            if exact:
                refs = list(textRefsIterator(self.refs, [text]))
            else:
                textsToSearch = list(linkTextVariations(text, linkType))
                if text.endswith("()") and text in self.methods:
                    textsToSearch += self.methods[text]
                if (linkType is None or linkType in config.lowercaseTypes) and text.lower() != text:
                    textsToSearch += [t.lower() for t in textsToSearch]
                refs = list(textRefsIterator(self.refs, textsToSearch))
        else:
            refs = list(refsIterator(self.refs))
        if not refs:
            return refs, "text"

        if linkType:
            if linkType in config.dfnTypes:
                linkTypes = [linkType]
            elif linkType == "dfn":
                linkTypes = ["dfn"]
            elif linkType in config.linkTypeToDfnType:
                linkTypes = list(config.linkTypeToDfnType[linkType])
            else:
                if error:
                    die("Unknown link type '{0}'.",linkType)
                return []
            refs = [x for x in refs if x.type in linkTypes]
        if not refs:
            return refs, "type"

        if export is not None:
            refs = [x for x in refs if x.export == export]
        if not refs:
            return refs, "export"

        if spec:
            refs = [x for x in refs if x.spec == spec or x.shortname == spec]
        if not refs:
            return refs, "spec"

        if linkFor == "/":
            refs = [x for x in refs if not x.for_]
        elif linkFor:
            refs = [x for x in refs if linkFor in x.for_]
        if not refs:
            return refs, "for"

        if status:
            # If status is ED, kill TR refs unless their spec *only* has a TR url
            if status == "ED":
                refs = [ref for ref in refs if ref.status == "ED" or (ref.status == "TR" and self.specs.get(ref.spec,{}).get('ED') is None)]
            # If status is TR, kill ED refs if there's a corresponding TR ref for the same spec.
            elif status == "TR":
                TRRefSpecs = [ref.spec for ref in refs if ref.status == 'TR']
                refs = [ref for ref in refs if ref.status == "TR" or (ref.status == "ED") and ref.spec not in TRRefSpecs]
            else:
                refs = [x for x in refs if x.status == status]
        if not refs:
            return refs, "status"

        if ignoreObsoletes:
            # Remove any ignored or obsoleted specs
            possibleSpecs = set(ref.spec for ref in refs)
            moreIgnores = set()
            for oldSpec, newSpec in self.replacedSpecs:
                if newSpec in possibleSpecs:
                    moreIgnores.add(oldSpec)
            refs = [ref for ref in refs if ref.spec not in self.ignoredSpecs and ref.spec not in moreIgnores]
        if not refs:
            return refs, "ignored-specs"

        if linkForHint:
            # If anything matches the linkForHint, filter to just those,
            # but don't worry if nothing matches it.
            tempRefs = [x for x in refs if linkForHint in x.for_]
            if tempRefs:
                refs = tempRefs

        # With non-exact texts, you might have multiple "anchors"
        # that point to the same url. Dedup them.
        seenUrls = set()
        tempRefs = []
        for ref in copy.copy(refs):
            if ref.url not in seenUrls:
                tempRefs.append(ref)
                seenUrls.add(ref.url)
        refs = tempRefs

        return refs, None


def linkTextsFromElement(el, preserveCasing=False):
    from .htmlhelpers import textContent
    if el.get('data-lt') == '':
        return []
    elif el.get('data-lt'):
        texts = [x.strip() for x in el.get('data-lt').split('|')]
    else:
        texts = [textContent(el).strip()]
    if el.get('data-local-lt'):
        texts += [x.strip() for x in el.get('data-local-lt').split('|')]
    texts = [x for x in texts if x != '']
    return texts


def linkTextVariations(str, linkType):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding an lt attr isn't usually necessary.
    yield str

    if linkType == "dfn":
        # Berries <-> Berry
        if str[-3:] == "ies":
            yield str[:-3] + "y"
        if str[-1:] == "y":
            yield str[:-1] + "ies"

        # Blockified <-> Blockify
        if str[-3:] == "ied":
            yield str[:-3] + "y"
        if str[-1:] == "y":
            yield str[:-1] + "ied"

        # Zeroes <-> Zero
        if str[-2:] == "es":
            yield str[:-2]
        else:
            yield str + "es"

        # Bikeshed's <-> Bikeshed
        if str[-2:] == "'s" or str[-2:] == "’s":
            yield str[:-2]
        else:
            yield str + "'s"

        # Bikesheds <-> Bikeshed
        if str[-1:] == "s":
            yield str[:-1]
        else:
            yield str + "s"

        # Bikesheds <-> Bikesheds'
        if str[-1:] == "'" or str[-1:] == "’":
            yield str[:-1]
        else:
            yield str + "'"

        # Bikesheded (bikeshod?) <-> Bikeshed
        if str[-2:] == "ed":
            yield str[:-2]
        else:
            yield str + "ed"

        # Navigating <-> Navigate
        if str[-3:] == "ing":
            yield str[:-3]
            yield str[:-3]+"e"
        elif str[-1:] == "e":
            yield str[:-1] + "ing"
        else:
            yield str + "ing"


def stripLineBreaks(obj):
    it = obj.items() if isinstance(obj, dict) else enumerate(obj)
    for key, val in it:
        if isinstance(val, str):
            obj[key] = unicode(val, encoding="utf-8").rstrip("\n")
        elif isinstance(val, unicode):
            obj[key] = val.rstrip("\n")
        elif isinstance(val, dict) or isinstance(val, list):
            stripLineBreaks(val)
    return obj

def splitForValues(forValues):
    '''
    Splits a string of 1+ "for" values into an array of individual value.
    Respects function args, etc.
    Currently, for values are separated by commas.
    '''
    return [value.strip() for value in re.split(r',(?![^()]*\))', forValues) if value.strip()]


class RefWrapper(object):
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.
    def __init__(self, text, ref):
        self.text = text
        self.ref = stripLineBreaks(ref)

    def __getattr__(self, name):
        if name == "for_":
            name = "for"
        val = self.ref[name]
        if isinstance(val, basestring):
            val = val.strip()
        return val

    def __json__(self):
        refCopy = copy.copy(self.ref)
        refCopy['text'] = self.text
        return refCopy

    def __repr__(self):
        return "RefWrapper("+repr(self.text)+", "+repr(self.ref)+")"

def simplifyPossibleRefs(refs):
    # "Simplifies" the set of possible refs according to their 'for' value;
    # returns a list of text/type/spec/for objects,
    # with the for value filled in *only if necessary for disambiguation*.
    forVals = defaultdict(list)
    for ref in refs:
        if ref.for_:
            for for_ in ref.for_: # ref.for_ is a list
                forVals[(ref.text, ref.type, ref.spec)].append(for_)
        else:
            forVals[(ref.text, ref.type, ref.spec)] = []
    retRefs = []
    for (text, type, spec), fors in forVals.items():
        if len(fors) >= 2:
            for for_ in fors:
                retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':for_})
        else:
            retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':None})
    return retRefs


def decodeAnchors(linesIter):
    # Decodes the anchor storage format into a list of dicts
    anchors = defaultdict(list)
    try:
        while True:
            key = linesIter.next().decode('utf-8')
            a = {
                "type": linesIter.next(),
                "spec": linesIter.next(),
                "shortname": linesIter.next(),
                "level": linesIter.next(),
                "status": linesIter.next(),
                "url": linesIter.next(),
                "export": linesIter.next() != "\n",
                "normative": linesIter.next() != "\n",
                "for": []
            }
            while True:
                line = linesIter.next()
                if line == b"-\n":
                    break
                a['for'].append(line)
            anchors[key].append(a)
    except StopIteration:
        return anchors
