import re
from collections import defaultdict
from lib.fuckunicode import u
from lib.messages import *
from lib.htmlhelpers import *

class ReferenceManager(object):
    refs = defaultdict(list)
    specs = dict()

    # dict(term=>(type, spec))
    defaultSpecs = defaultdict(list)
    css21Replacements = set()
    ignoredSpecs = set()

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
            if "no-ref" in (el.get('class') or ""):
                continue
            for linkText in linkTextsFromElement(el):
                type = treeAttr(el, 'data-dfn-type')
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                else:
                    dfnFor = set(dfnFor.split())
                for term in dfnFor.copy():
                    match = re.match("@[a-zA-Z0-9-_]+/(.*)", term)
                    if match:
                        dfnFor.add(match.group(1).strip())
                if type in config.dfnTypes or type == "dfn":
                    existingAnchors = self.refs[linkText]
                    if any(ref['spec'] == "local" and ref['type'] == type and ref['for'] == dfnFor for ref in existingAnchors):
                        if dfnFor:
                            die(u"Multiple local '{1}' <dfn>s for '{2}' have the same linking text '{0}'.", linkText, type, dfnFor)
                        else:
                            die(u"Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, type)
                    ref = {
                        "type":type,
                        "spec":"local",
                        "shortname":"local",
                        "level":1,
                        "id":"#"+el.get('id'),
                        "exported":True,
                        "for": dfnFor
                    }
                    self.refs[linkText].append(ref)


    def getRef(self, linkType, text, spec=None, status=None, linkFor=None, error=True, el=None):
        # If error is False, this function just shuts up and returns a url or None
        # Otherwise, it pops out debug messages for the user.
        if linkFor is None:
            linkFor = set()
        else:
            linkFor = set(linkFor.split())

        if (spec is None or status is None) and text in self.defaultSpecs:
            for dfnSpec, dfnType, dfnStatus, dfnFor in self.defaultSpecs[text]:
                if dfnType in config.linkTypeToDfnType[linkType]:
                    spec = spec or dfnSpec
                    status = status or dfnStatus
                    break
        status = status or self.specStatus
        if status is None:
            raise "Can't calculate a ref without knowing the desired spec status."

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
                        return [ref for dfnType in dfnTypes for ref in refs if ref['type'] == dfnType and ref['exported'] and linkFor <= (ref.get('for') or set())]
            return []

        if linkType in config.dfnTypes:
            refs = findRefs(self.refs, [linkType], text)
        elif linkType == "propdesc":
            refs = findRefs(self.refs, ["property", "descriptor"], text)
        elif linkType == "functionish":
            refs = findRefs(self.refs, ["function", "method"], text)
        elif linkType == "idl":
            refs = findRefs(self.refs, config.idlTypes, text)
        elif linkType == "dfn":
            refs = findRefs(self.refs, "dfn", linkTextVariations(text))
        elif linkType == "maybe":
            refs = findRefs(self.refs, config.maybeTypes, text) + findRefs(self.refs, "dfn", linkTextVariations(text))
        else:
            die("Unknown link type '{0}'.",linkType)
            return None

        if len(refs) == 0:
            if linkType == "maybe":
                return None
            if error:
                die("No '{1}' refs found for '{0}':\n{2}", text, linkType, outerHTML(el))
            return None

        # Filter by spec, if needed
        if spec:
            refs = [ref for ref in refs if ref['spec'] == spec]
            if len(refs) == 0:
                if linkType == "maybe":
                    return None
                if error:
                    die("No refs found for text '{0}' in spec '{1}':\n{2}", text, spec, outerHTML(el))
                return None

        # Remove any ignored or obsoleted specs
        possibleSpecs = set(ref['spec'] for ref in refs)
        ignoreCSS21 = bool(possibleSpecs.intersection(self.css21Replacements))
        for ref in refs[:]:
            if ref['spec'] in self.ignoredSpecs:
                refs.remove(ref)
            if ref['spec'] == "css21" and ignoreCSS21:
                refs.remove(ref)

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
        localRefs = [ref for ref in refs if ref['spec'] == "local"]
        if len(localRefs) == 1:
            return localRefs[0]['url']
        elif len(localRefs) > 1:
            warn("Multiple possible '{0}' local refs for '{1}'.\nArbitrarily chose the one for '{2}'.\nIf this is wrong, fix the links with one of the following 'for' values:\n{3}",
                 linkType,
                 text,
                 ' '.join(refs[0]['for']),
                 '\n'.join("    "+dfnFor for ref in localRefs for dfnFor in ref['for']))
            return localRefs[0]['url']

        # Eventually we need a registry for canonical definitions or something,
        # but for now, if all the refs are for the same shortname, take the biggest level
        if all(ref['shortname'] == refs[0]['shortname'] for ref in refs):
            maxLevel = 0
            for ref in refs:
                if ref['level'] > maxLevel:
                    maxLevel = ref['level']
            leveledRefs = [ref for ref in refs if ref['level'] == maxLevel]
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