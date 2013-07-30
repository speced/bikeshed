import re
from collections import defaultdict
from lib.fuckunicode import u
from lib.messages import *

class ReferenceManager(object):
    refs = defaultdict(list)
    specs = dict()

    # dict(term=>(type, spec))
    defaultSpecs = defaultdict(list)

    specStatus = None

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


    def addLocalDfns(self, dfns):
        dfnTypes = tuple(config.dfnTypes.values())
        for el in dfns:
            if "no-ref" in (el.get('class') or ""):
                continue
            for linkText in linkTextsFromElement(el):
                type = el.get('data-dfn-type')
                if type in dfnTypes or type == "dfn":
                    existingAnchors = self.refs[linkText]
                    if any(ref['spec'] == "local" and ref['type'] == type for ref in existingAnchors):
                        die(u"Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, type)
                    ref = {
                        "type":type,
                        "spec":"local",
                        "id":"#"+el.get('id'),
                        "exported":True
                    }
                    # Insert at the front of the references, so it'll get grabbed first.
                    self.refs[linkText].insert(0,ref)


    def getRef(self, linkType, text, spec=None, status=None, error=True):
        status = status or self.specStatus
        if status is None:
            raise "Can't calculate an ref without knowing the desired spec status."

        if spec is None and text in self.defaultSpecs:
            for type, spec in self.defaultSpecs[text]:
                if type == linkType:
                    spec = spec
                    break

        # Filter by type/text to find all the candidate refs
        def findRefs(allRefs, dfnTypes, linkTexts):
            # Allow either a string or an iter of strings
            if isinstance(dfnTypes, basestring):
                dfnTypes = [dfnTypes]
            if isinstance(linkTexts, basestring):
                linkTexts = [linkTexts]
            # I'll re-use linkTexts a lot, so I can't have it be an iterator!
            linkTexts = list(linkTexts)
            for dfnText,refs in allRefs.items():
                for linkText in linkTexts:
                    if linkText == dfnText:
                        return [ref for dfnType in dfnTypes for ref in refs if ref['type'] == dfnType and ref['exported']]
            return []

        if linkType in list(config.dfnTypes.values()):
            refs = findRefs(self.refs, [linkType, "dfn"], text)
        elif linkType == "propdesc":
            refs = findRefs(self.refs, ["property", "descriptor"], text)
        elif linkType == "dfn":
            refs = findRefs(self.refs, "dfn", linkTextVariations(text))
        elif linkType == "maybe":
            refs = findRefs(self.refs, ["value", "type", "function", "at-rule"], text) + findRefs(self.refs, "dfn", linkTextVariations(text))
        else:
            die("Unknown link type '{0}'.",linkType)
            return None

        if len(refs) == 0:
            if linkType == "maybe":
                return None
            if error:
                die("No '{1}' refs found for '{0}'.", text, linkType)
            return None

        # Filter by spec, if needed
        if spec:
            refs = [ref for ref in refs if ref['spec'] == spec]
            if len(refs) == 0:
                if linkType == "maybe":
                    return None
                if error:
                    die("No refs found for text '{0}' in spec '{1}'.", text, spec)
                return None

        # Filter by status, set url
        if status == "ED":
            for ref in refs[:]:
                # Take local refs first
                if ref.get('id'):
                    ref['url'] = ref['id']
                    continue
                # Prefer linking to EDs
                if ref.get('ED_url'):
                    ref['url'] = ref['ED_url']
                    continue
                # Only link to TRs if there *is* no ED
                # Don't do it otherwise, as it means the link was removed from the latest draft
                if ref.get('TR_url') and not self.specs[ref['spec']]['ED']:
                    ref['url'] = ref['TR_url']
                    continue
                # Otherwise, filter out the ref
                refs.remove(ref)
        elif status == "TR":
            for ref in refs[:]:
                # Take local refs first
                if ref.get('id'):
                    ref['url'] = ref['id']
                    continue
                # Prefer linking to TRs
                if ref.get('TR_url'):
                    ref['url'] = ref['TR_url']
                    continue
                # Allow downgrading to EDs, though.
                # Later, I'll restrict this further.
                if ref.get('ED_url'):
                    ref['url'] = ref['ED_url']
                    continue
                # Otherwise, filter out the ref
                refs.remove(ref)
        else:
            if error:
                die("Unknown specref status '{0}'", status)
            return None

        if len(refs) == 0:
            if linkType == "maybe":
                return None
            if error:
                die("No refs suitable for '{1}' status were found for '{0}'.", text, status)
            return None

        if len(refs) == 1:
            return refs[0]['url']

        # Accept local dfns even if there are xrefs with the same text.
        for ref in refs:
            if ref['spec'] == "local":
                return ref['url']

        if error:
            die("Too many '{1}' refs for '{0}' to choose between.\nDeclare this in Ignored Terms, or specify a spec:\n{2}", text, linkType, '\n'.join('  {0}: {1}'.format(ref['spec'], ref['url']) for ref in refs))
        

def linkTextsFromElement(el, preserveCasing=False):
    from lib.htmlhelpers import textContent
    if el.get('title') == '':
        return []
    elif el.get('title'):
        return [u(x.strip()) for x in el.get('title').split('|')]
    elif preserveCasing:
        return [textContent(el).strip()]
    else:
        return [textContent(el).strip().lower()]


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
    if str[-1:] == u"s":
        yield str[:-1]
    if str[-1:] == u"'":
        yield str[:-1]