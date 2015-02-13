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
        self.refs = defaultdict(list)
        self.specs = dict()
        self.defaultSpecs = defaultdict(list)
        self.css21Replacements = set()
        self.ignoredSpecs = set()
        self.replacedSpecs = set()
        self.status = specStatus
        self.biblios = defaultdict(list)
        self.anchorMacros = dict()

    def initializeRefs(self, doc):
        # Load up the xref data
        self.specs.update(json.loads(config.retrieveCachedFile("specs.json", quiet=True, str=True)))
        with config.retrieveCachedFile("anchors.data", quiet=True) as lines:
            try:
                while True:
                    key = lines.next()
                    a = {
                        "type": lines.next(),
                        "spec": lines.next(),
                        "shortname": lines.next(),
                        "level": lines.next(),
                        "status": lines.next(),
                        "url": lines.next(),
                        "export": lines.next() != "\n",
                        "normative": lines.next() != "\n",
                        "for": []
                    }
                    while True:
                        line = lines.next()
                        if line == b"-\n":
                            break
                        a['for'].append(line)
                    self.refs[key].append(a)
            except StopIteration:
                pass
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
        if md.level is not None:
            self.specLevel = md.level
            self.specVName = "{0}-{1}".format(md.shortname, md.level)
        else:
            self.specLevel = 1
            self.specVName = self.specName

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
            self.refs[term] = [ref for ref in refs if ref.get('shortname', '').rstrip("\n")!=self.specName]
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
                type = treeAttr(el, 'data-dfn-type')
                if type in config.lowercaseTypes:
                    linkText = linkText.lower()
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                    if self.getLocalRef(type, linkText):
                        die("Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, type)
                        continue
                else:
                    dfnFor = set(splitForValues(dfnFor))
                    encounteredError = False
                    for singleFor in dfnFor:
                        if self.getLocalRef(type, linkText, linkFor=singleFor):
                            encounteredError = True
                            die("Multiple local '{1}' <dfn>s for '{2}' have the same linking text '{0}'.", linkText, type, singleFor)
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
                if type in config.dfnTypes.union(["dfn"]):
                    existingAnchors = self.refs[linkText]
                    ref = {
                        "type":type,
                        "status":"local",
                        "spec":self.specVName,
                        "shortname":self.specName,
                        "level":self.specLevel,
                        "url":"#"+el.get('id'),
                        "export":True,
                        "for": dfnFor
                    }
                    self.refs[linkText].append(ref)

    def getLocalRef(self, linkType, text, linkFor=None, el=None):
        return self.queryRefs(text=text, linkType=linkType, status="local", linkFor=linkFor)[0]

    def getRef(self, linkType, text, spec=None, status=None, linkFor=None, error=True, el=None):
        # If error is False, this function just shuts up and returns a url or None
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
        localRefs = self.getLocalRef(linkType, text, linkFor, el)
        if len(localRefs) == 1:
            return localRefs[0]
        elif len(localRefs) > 1:
            if error:
                warn("Multiple possible '{0}' local refs for '{1}'.\nArbitrarily chose the one with type '{2}' and for '{3}'.",
                     linkType,
                     text,
                     localRefs[0].type,
                     "' or '".join(localRefs[0].for_))
                if text == "encoding":
                    warn("{0}", config.printjson(localRefs))
            return localRefs[0]

        # Take defaults into account
        if (not spec or not status):
            variedTexts = [v for v in linkTextVariations(text, linkType) if v in self.defaultSpecs]
            if variedTexts:
                for dfnSpec, dfnType, dfnStatus, dfnFor in self.defaultSpecs[variedTexts[0]]:
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
        refs, failure = self.queryRefs(text=text, linkType=linkType, spec=spec, status=status, linkFor=linkFor, export=export, ignoreObsoletes=True)

        if failure and linkType in config.idlMethodTypes and text.endswith("()"):
            # Allow foo(bar) to be linked to with just foo(), but only if it's completely unambiguous.
            textPrefix = text[:-1]
            candidates, _ = self.queryRefs(linkType=linkType, status="local", linkFor=linkFor)
            candidateRefs = list(set(c for c in candidates if c.text.startswith(textPrefix)))
            if len(candidateRefs) == 1:
                return candidateRefs[0]
            # And repeat for non-locals
            candidates, _ = self.queryRefs(linkType=linkType, spec=spec, status=status, linkFor=linkFor, export=export, ignoreObsoletes=True)
            candidateRefs = list(set(c for c in candidates if c.text.startswith(textPrefix)))
            if len(candidateRefs) == 1:
                return candidateRefs[0]
            if len(urls) > 1 and zeroRefsError:
                die("Too many possible '{0}' targets to disambiguate. Please specify the names of the required args, like 'foo(bar, baz)'.", text)

        if failure and linkType in ("argument", "idl") and linkFor is not None and linkFor.endswith("()"):
            # Allow foo(bar) to be for'd to with just foo() if it's completely unambiguous.
            candidateFor, _, forPrefix = linkFor.partition("/") if "/" in linkFor else (None, None, '')
            forPrefix = forPrefix[:-1]
            candidates, _ = self.queryRefs(linkType="functionish", status="local", linkFor=candidateFor)
            localRefs = list(set(c for c in candidates if c.text.startswith(forPrefix)))
            if len(localRefs) == 1:
                return localRefs[0]
            # And repeat for non-locals
            candidates, _ = self.queryRefs(linkType="functionish", spec=spec, status=status, linkFor=candidateFor, export=export, ignoreObsoletes=True)
            remoteUrls = list(set(c for c in candidates if c.text.startwith(forPrefix)))
            if len(remoteRefs) == 1:
                return remoteRefs[0]
            if zeroRefsError and (len(localRefs) or len(remoteRefs)):
                die("Too many possible method targets to disambiguate '{0}/{1}'. Please specify the names of the required args, like 'foo(bar, baz)', in the 'for' attribute.", linkFor, text)

        if failure == "text" or failure == "type":
            if spec and spec in self.anchorMacros:
                # If there's a macro registered for this spec, use it to generate a ref.
                return {
                    "spec": spec,
                    "shortname": spec,
                    "url": anchorMacros[spec]['url'] + config.simplifyText(text),
                    "for": linkFor,
                    "text": text,
                    "type": linkType
                }
            if zeroRefsError:
                die("No '{0}' refs found for '{1}'.", linkType, text)
            return None
        elif failure == "export":
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' that are marked for export.", linkType, text)
            return None
        elif failure == "spec":
            # If there's a macro registered for this spec, use it to generate a ref.
            if spec in self.anchorMacros:
                return {
                    "spec": spec,
                    "shortname": spec,
                    "url": anchorMacros[spec]['url'] + config.simplifyText(text),
                    "for": linkFor,
                    "text": text,
                    "type": linkType
                }
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

    def getBiblioRef(self, text, status, el=None):
        key = text.lower()
        if key in self.biblios:
            candidates = self.biblios[key]
        elif key+"\n" in self.biblios:
            candidates = self.biblios[key+"\n"]
        else:
            die("Couldn't find '{0}' in bibliography data.", text)
            return None
        candidates = sorted(stripLineBreaks(candidates), key=itemgetter('order'))
        # TODO: When SpecRef definitely has all the CSS specs, turn on this code.
        # if candidates[0]['order'] > 3: # 3 is SpecRef level
        #    warn("Bibliography term '{0}' wasn't found in SpecRef.\n         Please find the equivalent key in SpecRef, or submit a PR to SpecRef.", text)
        return biblio.BiblioEntry(preferredURL=status, **candidates[0])

    def queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, status=None, refs=None, export=None, ignoreObsoletes=False, **kwargs):
        results, error = self._queryRefs(text, spec, linkType, linkFor, status, refs, export, ignoreObsoletes, exact=True)
        if error:
            return self._queryRefs(text, spec, linkType, linkFor, status, refs, export, ignoreObsoletes)
        else:
            return results, error

    def _queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, status=None, refs=None, export=None, ignoreObsoletes=False, exact=False, **kwargs):
        # Query the ref database.
        # If it fails to find a ref, also returns the stage at which it finally ran out of possibilities.
        if refs is None:
            refs = self.refs
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

        if text:
            if exact:
                refs = list(textRefsIterator(refs, [text]))
            else:
                refs = list(textRefsIterator(refs, linkTextVariations(text, linkType)))
                if (linkType is None or linkType in config.lowercaseTypes) and text.lower() != text:
                    refs += list(textRefsIterator(refs, linkTextVariations(text.lower(), linkType)))
        else:
            refs = list(refsIterator(refs))
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

        if linkFor:
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
            # All the individual CSS specs replace SVG.
            if bool(possibleSpecs.intersection(self.css21Replacements)):
                moreIgnores.add("css21")
                moreIgnores.add("svg")
                moreIgnores.add("svg2")
            # CSS21 also replaces SVG
            if "css21" in possibleSpecs:
                moreIgnores.add("svg")
                moreIgnores.add("svg2")
            # SVG2 replaces SVG1
            if "svg2" in possibleSpecs:
                moreIgnores.add("svg")
            refs = [ref for ref in refs if ref.spec not in self.ignoredSpecs and ref.spec not in moreIgnores]
        if not refs:
            return refs, "ignored-specs"

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
    startIndex = 0
    mode = "between"
    arr = []
    for i,c in enumerate(forValues):
        if mode == "between":
            if c.isspace():
                continue
            else:
                mode = "in-for"
                startIndex = i
        elif mode == "in-args":
            if c == ")":
                mode = "in-for"
        elif mode == "in-for":
            if c == "(":
                mode = "in-args"
            elif c == ",":
                arr.append(forValues[startIndex:i].strip())
                mode = "between"
            else:
                continue
    arr.append(forValues[startIndex:].strip())
    return arr


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
        if name not in self.ref:
            return None
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
