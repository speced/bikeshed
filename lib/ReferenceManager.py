from fuckunicode import u
import re
from collections import defaultdict
from messages import *

class ReferenceManager(object):
    properties = dict()
    descriptors = dict()
    values = dict()
    links = dict()

    xrefs = dict()
    specs = dict()

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
        for el in dfns:
            if re.search("no-ref", el.get('class') or ""):
                continue
            linkTexts = linkTextsFromElement(el)
            for linkText in linkTexts:
                type = el.get('data-dfn-type')
                if type == "value":
                    if linkText in self.values:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.values[linkText]['el'])
                    self.values[linkText] = {'id':u(el.get('id')), 'el':el}
                elif type == "property":
                    if linkText in self.properties:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.properties[linkText]['el'])
                    self.properties[linkText] = {'id':u(el.get('id')), 'el':el}
                elif type == "descriptor":
                    if linkText in self.descriptors:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.descriptors[linkText]['el'])
                    self.descriptors[linkText] = {'id':u(el.get('id')), 'el':el}
                else:
                    if linkText in self.links:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.links[linkText]['el'])
                    self.links[linkText] = {'id':u(el.get('id')), 'el':el}

    def getRef(self, type, text):
        if type == "property":
            if text in self.properties:
                return self.properties[text]['id']
            elif text in self.descriptors:
                return self.descriptors[text]['id']
        elif type == "value":
            if text in self.values:
                return self.values[text]['id']
        elif type == "link":
            for var in linkTextVariations(text):
                if var in self.links:
                    return self.links[var]['id']
        elif type == "maybe":
            # Most value links will be encoded as maybes.
            if text in self.values:
                return self.values[text]['id']
            for var in linkTextVariations(text):
                if var in self.links:
                    return self.links[var]['id']
        else:
            die("Unknown link type '{0}'.", type)

    def getXref(self, linkType, text, spec=None, status=None):
        status = status or self.specStatus
        if status is None:
            raise "Can't calculate an xref without knowing the desired spec status."

        # Filter by type/text to find all the candidate refs
        def findRefs(allRefs, dfnType, linkTexts):
            # Allow either a string or an iter of strings
            if isinstance(linkTexts, str):
                linkTexts = [linkTexts]
            if isinstance(dfnType, str):
                dfnType = [dfnType]
            for dfnText,refs in allRefs.items():
                for linkText in linkTexts:
                    if linkText == dfnText:
                        ret = []
                        # Preserve the order of the dfntypes
                        for dfnType in dfnTypes:
                            if ref['type'] == dfnType:
                                ret.append(ref)
                        return ret
            return []

        if linkType in ("property", "descriptor", "value", "type"):
            refs = findRefs(self.xrefs, linkType, text)
        elif linkType == "propdesc":
            refs = findRefs(self.xrefs, ["property", "descriptor"], text)
        elif linkType == "link":
            refs = findRefs(self.xrefs, "dfn", linkTextVariations(text))
        elif linkType == "maybe":
            refs = findRefs(self.xrefs, ["value", "type"], text) + findRefs(self.xrefs, "dfn", linkTextVariations(text))
        else:
            die("Unknown link type '{0}'.", linkType)

        if len(refs) == 0:
            die("No xrefs found for text '{0}' with type {1}.", text, linkType)

        # Filter by spec, if needed
        if spec:
            refs = [ref for ref in refs if ref['spec'] == spec]
            if len(refs) == 0:
                die("No xrefs found for text '{0}' in spec {1}.", text, spec)

        # Filter by status, set url
        if status == "ED":
            for ref in refs[:]:
                # Prefer linking to EDs
                if ref.get('ED_url'):
                    ref['url'] = ref['ED_url']
                    continue
                # Only link to TRs if there *is* no ED
                # Don't do it otherwise, as it means the link was removed from the latest draft
                if ref.get('TR_url') and not specs[ref['spec']]['ED']:
                    ref['url'] = ref['TR_url']
                    continue
                # Otherwise, filter out the ref
                refs.remove(ref)
        elif status == "TR":
            for ref in refs[:]:
                # Prefer linking to TRs
                if ref.get('TR_url'):
                    ref['url'] = ref['TR_url']
                    continue
                # Allow downgrading to EDs, though.
                if ref.get('ED_url'):
                    ref['url'] = ref['ED_url']
                    continue
                # Otherwise, filter out the ref
                refs.remove(ref)
        else:
            die("Unknown specref status '{0}'", status)

        if len(refs) == 0:
            die("No xrefs suitable for {1} status were found for '{0}'.", text, status)

        if len(refs) == 1:
            return refs[0]

        die("Too many xrefs for '{0}'.\n{1}", text, '\n'.join(str(ref) for ref in refs))
        

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