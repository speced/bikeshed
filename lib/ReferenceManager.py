# -*- coding: utf-8 -*-
import re
from collections import defaultdict
from lib.fuckunicode import u
from lib.messages import *
from lib.htmlhelpers import *

class ReferenceManager(object):
    refs = defaultdict(list)
    specs = dict()

    defaultSpecs = defaultdict(list)
    css21Replacements = set()
    ignoredSpecs = set()

    def __init__(self, specStatus=None):
        if specStatus is not None:
            self.setStatus(specStatus)

    def setStatus(self, specStatus):
        if specStatus in ("ED", "DREAM", "UD"):
            self.specStatus = "ED"
        else:
            self.specStatus = "TR"
            # I'll want to make this more complex later,
            # to enforce pubrules linking policy.

    def setSpecData(self, spec):
        if spec.status in ("ED", "DREAM", "UD"):
            self.specStatus = "ED"
        else:
            self.specStatus = "TR"
            # I'll want to make this more complex later,
            # to enforce pubrules linking policy.
        self.specLevel = spec.level
        self.specName = spec.shortname
        self.specVName = spec.shortname + "-" + u(spec.level)
        # Need to get a real versioned shortname,
        # with the possibility of overriding the "shortname-level" pattern.
        self.removeSameSpecRefs()

    def removeSameSpecRefs(self):
        # Kill all the non-local anchors with the same shortname as the current spec,
        # so you don't end up accidentally linking to something that's been removed from the local copy.
        for term, refs in self.refs.items():
            self.refs[term] = [ref for ref in refs if ref['shortname']!=self.specName]

    def addLocalDfns(self, dfns):
        for el in dfns:
            if hasClass(el, "no-ref"):
                continue
            for linkText in linkTextsFromElement(el):
                type = treeAttr(el, 'data-dfn-type')
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                else:
                    dfnFor = set(dfnFor.split())
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
                    if any(ref['spec'] == "local" and ref['type'] == type and ref['for'] == dfnFor for ref in existingAnchors):
                        if dfnFor:
                            die(u"Multiple local '{1}' <dfn>s for '{2}' have the same linking text '{0}'.", linkText, type, dfnFor)
                        else:
                            die(u"Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, type)
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

        status = status or self.specStatus
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
        if (spec is None or status is None) and text in self.defaultSpecs:
            for dfnSpec, dfnType, dfnStatus, dfnFor in self.defaultSpecs[text]:
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
        if spec is None:
            refs = [ref for ref in refs if ref['export']]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' that are marked for export.", linkType, text)
            return None

        # If spec is specified, kill anything that doesn't match
        if spec is not None:
            refs = [ref for ref in refs if ref['shortname']==spec or ref['spec']==spec]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with spec '{2}'.", linkType, text, spec)
            return None

        # If linkFor is specified, kill anything that doesn't match
        if linkFor is not None:
            refs = [ref for ref in refs if linkFor in ref['for']]
        if len(refs) == 0:
            if zeroRefsError:
                die("No '{0}' refs found for '{1}' with for='{2}'.", linkType, text, linkFor)

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
        def ignoredSpec(spec, ignoreCSS21=False, ignoreSVG=False):
            if spec in self.ignoredSpecs:
                return True
            if spec == "css21" and ignoreCSS21:
                return True
            if spec in ("svg", "svg2") and ignoreSVG:
                return True
            return False
        possibleSpecs = set(ref['spec'] for ref in refs)
        ignoreCSS21 = bool(possibleSpecs.intersection(self.css21Replacements))
        # CSS21 also replaces SVG
        ignoreSVG = ignoreCSS21 or "css21" in possibleSpecs
        refs = [ref for ref in refs if not ignoredSpec(ref['spec'], ignoreCSS21, ignoreSVG)]

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
            maxLevel = -1
            for ref in refs:
                if ref['level'] > maxLevel:
                    maxLevel = ref['level']
            leveledRefs = [ref for ref in refs if ref['level'] == maxLevel]
            # Still potentially possible for a non-Bikeshed spec to have duplicate refs here,
            # so I have to check for singularity.
            if len(leveledRefs) == 1:
                return leveledRefs[0]['url']

        # If we hit this point, there are >1 possible refs to choose from.
        if error:
            warn("Multiple possible '{0}' refs for '{1}'.\nArbitrarily chose the one in {2}.\nIf this is wrong, insert one of the following lines into 'Link Defaults':\n{3}",
                 linkType,
                 text,
                 refs[0]['spec'],
                 '\n'.join('    {2} ({1}) {0}'.format(text, ref['type'], ref['spec']) for ref in refs))
        return refs[0]['url']
        

def linkTextsFromElement(el, preserveCasing=False):
    from lib.htmlhelpers import textContent
    if el.get('title') == '':
        return []
    elif el.get('title'):
        texts = [u(x.strip()) for x in el.get('title').split('|')]
    else:
        texts = [textContent(el).strip()]
    if preserveCasing:
        return texts
    else:
        return [t.lower() for t in texts]


def linkTextVariations(str):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding a title attr isn't usually necessary.
    yield str

    if str[-3:] == u"ies":
        yield str[:-3]+u"y"
    if str[-2:] == u"es":
        yield str[:-2]
    if str[-2:] == u"'s":
        yield str[:-2]
    if str[-2:] == u"’s":
        yield str[:-2]
    if str[-1:] == u"s":
        yield str[:-1]
    if str[-1:] == u"'":
        yield str[:-1]
    if str[-1:] == u"’":
        yield str[:-1]

def filterRefsByTypeAndText(allRefs, linkType, linkText, error=False):
    '''Filter by type/text to find all the candidate refs'''

    def filterRefs(allRefs, dfnTypes, linkTexts):
        # Allow either a string or an iter of strings
        if isinstance(dfnTypes, basestring):
            dfnTypes = [dfnTypes]
        if isinstance(linkTexts, basestring):
            linkTexts = [linkTexts]
        dfnTypes = set(dfnTypes)
        return [ref for linkText in linkTexts for ref in allRefs.get(linkText,[]) if ref['type'] in dfnTypes]

    if linkType in config.dfnTypes:
        return filterRefs(allRefs, [linkType], linkText)
    elif linkType == "propdesc":
        return filterRefs(allRefs, ["property", "descriptor"], linkText)
    elif linkType == "functionish":
        return filterRefs(allRefs, ["function", "method"], linkText)
    elif linkType == "idl":
        return filterRefs(allRefs, config.idlTypes, linkText)
    elif linkType == "dfn":
        return filterRefs(allRefs, "dfn", linkTextVariations(linkText))
    elif linkType == "maybe":
        return filterRefs(allRefs, config.maybeTypes, linkText) + filterRefs(allRefs, "dfn", linkTextVariations(linkText))
    else:
        if error:
            die("Unknown link type '{0}'.",linkType)
        return None
