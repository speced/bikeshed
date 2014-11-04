# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
import io
import collections
from collections import defaultdict
from operator import itemgetter
from . import config
from . import biblio
from . import enum
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
        self.status = specStatus
        self.biblios = defaultdict(list)

    def initializeRefs(self):
        # Load up the xref data
        self.specs.update(json.loads(
            config.retrieveCachedFile(
                cacheLocation=config.scriptPath+"/spec-data/specs.json",
                type="spec list",
                quiet=True,
                str=True)))
        with config.retrieveCachedFile(cacheLocation=config.scriptPath+"/spec-data/anchors.data", type="anchor data", quiet=True) as lines:
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

        self.defaultSpecs.update(json.loads(
            config.retrieveCachedFile(
                cacheLocation=config.scriptPath+"/spec-data/link-defaults.json",
                type="link defaults",
                quiet=True,
                str=True)))

    def initializeBiblio(self):
        with config.retrieveCachedFile(cacheLocation=config.scriptPath + "/spec-data/biblio.data", type="bibliography") as lines:
            try:
                while True:
                    key = lines.next()
                    b = {
                        "linkText": lines.next(),
                        "date": lines.next(),
                        "status": lines.next(),
                        "title": lines.next(),
                        "url": lines.next(),
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
            self.refs[term] = [ref for ref in refs if ref['shortname'].rstrip("\n")!=self.specName]
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
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                    if self.getLocalRef(type, linkText):
                        die("Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, type)
                        continue
                else:
                    dfnFor = set(dfnFor.split())
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
        refs = filterRefsByTypeAndText(self.refs, linkType, text)
        refs = [ref for ref in refs if ref['status'] == "local"]
        if linkFor:
            refs = [ref for ref in refs if linkFor in ref['for']]
        return refs

    def getRef(self, linkType, text, spec=None, status=None, linkFor=None, error=True, el=None):
        # If error is False, this function just shuts up and returns a url or None
        # Otherwise, it pops out debug messages for the user.

        # 'maybe' links might not link up, so it's fine for them to have no references.
        # The relevent errors are gated by this variable.
        zeroRefsError = error and linkType!="maybe"

        text = unfixTypography(text).lower()

        status = status or self.status
        if status not in ("ED", "TR", "local"):
            if error:
                die("Unknown spec status '{0}'. Status must be ED, TR, or local.", status)
            return None

        # Local refs always get precedence, no matter what.
        localRefs = self.getLocalRef(linkType, text, linkFor, el)
        if len(localRefs) == 1:
            return localRefs[0]['url']
        elif len(localRefs) > 1:
            if error:
                warn("Multiple possible '{0}' local refs for '{1}'.\nArbitrarily chose the one with type '{2}' and for '{3}'.",
                     linkType,
                     text,
                     localRefs[0]['type'],
                     "' or '".join(localRefs[0]['for']))
            return localRefs[0]['url']

        # Take defaults into account
        if (not spec or not status):
            variedTexts = [v for v in linkTextVariations(text) if v in self.defaultSpecs]
            if variedTexts:
                for dfnSpec, dfnType, dfnStatus, dfnFor in self.defaultSpecs[variedTexts[0]]:
                    if dfnType in config.linkTypeToDfnType[linkType]:
                        spec = spec or dfnSpec
                        status = status or dfnStatus
                        linkFor = linkFor or dfnFor
                        break

        # Get the relevant refs
        refs = filterRefsByTypeAndText(self.refs, linkType, text, error)
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}'.", linkType, text)
            return None

        # Unless you've specified a particular spec to look in, cut out all non-exported things.
        if not spec:
            refs = [ref for ref in refs if ref['export']]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' that are marked for export.", linkType, text)
            return None

        # If spec is specified, kill anything that doesn't match
        if spec:
            refs = [ref for ref in refs if ref['shortname'].lower() == spec.lower() or ref['spec'].lower() ==spec.lower()]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with spec '{2}'.", linkType, text, spec)
            return None

        # If linkFor is specified, kill anything that doesn't match
        if linkFor:
            refs = [ref for ref in refs if linkFor in ref['for']]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with for='{2}'.", linkType, text, linkFor)
            return None

        # If status is ED, kill TR refs unless their spec *only* has a TR url
        if status == "ED":
            refs = [ref for ref in refs if ref['status'] == "ED" or (ref['status'] == "TR" and self.specs[ref['spec']].get('ED') is None)]
        # If status is TR, kill ED refs if there's a corresponding TR ref for the same spec.
        if status == "TR":
            TRRefSpecs = [ref['spec'] for ref in refs if ref['status'] == 'TR']
            refs = [ref for ref in refs if ref['status'] == "TR" or (ref['status'] == "ED") and ref['spec'] not in TRRefSpecs]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' compatible with status '{2}'.", linkType, text, status)
            return None

        # Remove any ignored or obsoleted specs
        def ignoredSpec(spec, moreIgnores=set()):
            if spec in self.ignoredSpecs:
                return True
            if spec in moreIgnores:
                return True
            return False
        possibleSpecs = set(ref['spec'] for ref in refs)
        moreIgnores = set()
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
        refs = [ref for ref in refs if not ignoredSpec(ref['spec'], moreIgnores)]

        # At this point, all the filtering is done.
        # We won't error out due to no refs being found past this point,
        # only for there being *too many* refs.
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}':\n{2}", linkType, text, outerHTML(el))
            return None

        if len(refs) == 1:
            # Success!
            return refs[0]['url']

        # If all the refs are for the same shortname,
        # assume you want to link to the latest one (highest level).
        if all(ref['shortname'] == refs[0]['shortname'] for ref in refs):
            maxLevel = config.HierarchicalNumber("-1")
            for ref in refs:
                if ref['level'] > maxLevel:
                    maxLevel = ref['level']
            leveledRefs = [ref for ref in refs if ref['level'] == maxLevel]
            # Still potentially possible for a non-Bikeshed spec to have duplicate refs here,
            # so I have to check for singularity.
            if len(leveledRefs) == 1:
                return leveledRefs[0]['url']

        # If we hit this point, there are >1 possible refs to choose from.
        # Default to linking to the first one.
        defaultRef = refs[0]
        if linkType == "propdesc":
            # If both props and descs are possible, default to prop.
            for ref in refs:
                if ref['type'] == "property":
                    defaultRef = ref
                    break
        if error:
            warn("Multiple possible '{0}' refs for '{1}'.\nArbitrarily chose the one in {2}.\nIf this is wrong, insert one of the following lines into 'Link Defaults':\n{3}",
                 linkType,
                 text,
                 defaultRef['spec'],
                 '\n'.join('    {2} ({1}) {0}'.format(text, ref['type'], ref['spec']) for ref in refs))
        return defaultRef['url']

    def getBiblioRef(self, text, el=None):
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
        return biblio.BiblioEntry(**candidates[0])

    def queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, status=None, exact=True, **kwargs):
        def refsIterator(refs):
            # Turns a dict of arrays of refs into an iterator of refs
            for key, group in refs.items():
                for ref in group:
                    yield key,ref
        def textRefsIterator(refs, texts):
            # Same as above, but only grabs those keyed to a given text
            for text in texts:
                for ref in self.refs.get(text, []):
                    yield text, ref
                for ref in self.refs.get(text+"\n", []):
                    yield text, ref
        if text:
            if exact:
                texts = [text]
            else:
                texts = linkTextVariations(text)
            refs = textRefsIterator(self.refs, texts)
        else:
            refs = refsIterator(self.refs)
        if spec:
            refs = (x for x in refs if x[1]['spec'] in (spec, spec+"\n"))
        if linkType:
            refs = (x for x in refs if x[1]['type'] in (linkType, linkType+"\n"))
        if status:
            refs = (x for x in refs if x[1]['status'] in (status, status+"\n"))
        if linkFor:
            refs = (x for x in refs if linkFor in x[1]['for'] or (linkFor+"\n") in x[1]['for'])
        return refs


def linkTextsFromElement(el, preserveCasing=False):
    from .htmlhelpers import textContent
    if el.get('title') == '':
        return []
    elif el.get('title'):
        texts = [x.strip() for x in el.get('title').split('|')]
    else:
        texts = [textContent(el).strip()]
    if el.get('data-local-title'):
        texts += [x.strip() for x in el.get('data-local-title').split('|')]
    texts = [x for x in texts if x != '']
    if preserveCasing:
        return texts
    else:
        return [t.lower() for t in texts]


def linkTextVariations(str):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding a title attr isn't usually necessary.
    yield str

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

def filterRefsByTypeAndText(allRefs, linkType, linkText, error=False):
    '''Filter by type/text to find all the candidate refs'''

    if linkType in config.dfnTypes:
        linkTypes = [linkType]
        linkTexts = [linkText]
    elif linkType == "dfn":
        linkTypes = ["dfn"]
        linkTexts = linkTextVariations(linkText)
    elif linkType in config.linkTypeToDfnType:
        linkTypes = config.linkTypeToDfnType[linkType]
        linkTexts = [linkText]
    else:
        if error:
            die("Unknown link type '{0}'.",linkType)
        return None

    refs = []
    for linkText in linkTexts:
        if linkText in allRefs:
            refs.extend(allRefs[linkText])
        if linkText+"\n" in allRefs:
            refs.extend(allRefs[linkText+"\n"])
    stripLineBreaks(refs)
    return [ref for ref in refs if ref['type'] in linkTypes]




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
