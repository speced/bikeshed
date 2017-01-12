# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import json
import io
import copy
from collections import defaultdict
from operator import itemgetter
from . import config
from . import biblio
from . import datablocks
from .messages import *
from .htmlhelpers import *

class RefSource(object):
    def __init__(self, source, specs=None, ignored=None, replaced=None):
        # String identifying which refsource this is.
        self.source = source

        # Dict of {linking text => [anchor data]}
        self.refs = defaultdict(list)

        # Dict of {argless method signatures => {"argfull signature": {"args":[args], "for":[fors]}}}
        self.methods = defaultdict(dict)

        # Dict of {for value => [terms]}
        self.fors = defaultdict(list)

        self.specs = {} if specs is None else specs
        self.ignoredSpecs = set() if ignored is None else ignored
        self.replacedSpecs = set() if replaced is None else replaced

    def queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, linkForHint=None, status=None, statusHint=None, excludeStatuses=[], export=None, ignoreObsoletes=False, exact=False, **kwargs):
        results, error = self._queryRefs(text, spec, linkType, linkFor, linkForHint, status, statusHint, excludeStatuses, export, ignoreObsoletes, exact=True)
        if error and not exact:
            return self._queryRefs(text, spec, linkType, linkFor, linkForHint, status, statusHint, excludeStatuses, export, ignoreObsoletes)
        else:
            return results, error

    def _queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, linkForHint=None, status=None, statusHint=None, excludeStatuses=[], export=None, ignoreObsoletes=False, exact=False, error=False, **kwargs):
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
                for ref in refs.get(text + "\n", []):
                    yield RefWrapper(text, ref)

        def forRefsIterator(refs, fors, targetFors):
            # Same as above, but only grabs those for certain values
            for for_ in targetFors:
                for text in fors[for_]:
                    for ref in refs.get(text, []):
                        yield RefWrapper(text, ref)
                    for ref in refs.get(text + "\n", []):
                        yield RefWrapper(text, ref)

        # Set up the initial list of refs to query
        if text:
            if exact:
                refs = list(textRefsIterator(self.refs, [text]))
            else:
                textsToSearch = list(linkTextVariations(text, linkType))
                if text.endswith("()") and text in self.methods:
                    textsToSearch += self.methods[text].keys()
                if (linkType is None or linkType in config.lowercaseTypes) and text.lower() != text:
                    textsToSearch += [t.lower() for t in textsToSearch]
                refs = list(textRefsIterator(self.refs, textsToSearch))
        elif linkFor:
            refs = list(forRefsIterator(self.refs, self.fors, [linkFor]))
        else:
            refs = list(refsIterator(self.refs))
        if not refs:
            return refs, "text"

        if excludeStatuses:
            refs = [x for x in refs if x.status not in excludeStatuses]
        if not refs:
            return refs, "exclude-statuses"

        if linkType:
            if linkType in config.dfnTypes:
                linkTypes = [linkType]
            elif linkType in config.linkTypeToDfnType:
                linkTypes = list(config.linkTypeToDfnType[linkType])
            else:
                if error:
                    linkerror("Unknown link type '{0}'.",linkType)
                return [], "type"
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

        def filterByStatus(refs, status):
            # If status is "current'", kill snapshot refs unless their spec *only* has a snapshot_url
            if status == "current":
                return [ref for ref in refs if ref.status == "current" or (ref.status == "snapshot" and self.specs.get(ref.spec,{}).get('current_url') is None)]
            # If status is "snapshot", kill current refs if there's a corresponding snapshot ref for the same spec.
            elif status == "snapshot":
                snapshotSpecs = [ref.spec for ref in refs if ref.status == 'snapshot']
                return [ref for ref in refs if ref.status == "snapshot" or (ref.status == "current" and ref.spec not in snapshotSpecs)]
            else:
                return [x for x in refs if x.status == status]
        if status:
            refs = filterByStatus(refs, status)
        if not refs:
            return refs, "status"

        if status is None and statusHint:
            tempRefs = filterByStatus(refs, statusHint)
            if tempRefs:
                refs = tempRefs

        if ignoreObsoletes and not spec:
            # Remove any ignored or obsoleted specs
            # If you specified the spec, don't filter things - you know what you're doing.
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

        # If multiple levels of the same shortname exist,
        # only use the latest level.
        # If generating for a snapshot, prefer the latest snapshot level,
        # unless that doesn't exist, in which case just prefer the latest level.
        shortnameLevels = defaultdict(lambda:defaultdict(list))
        snapshotShortnameLevels = defaultdict(lambda:defaultdict(list))
        for ref in refs:
            shortnameLevels[ref.shortname][ref.level].append(ref)
            if status == ref.status == "snapshot":
                snapshotShortnameLevels[ref.shortname][ref.level].append(ref)
        refs = []
        for shortname, levelSet in shortnameLevels.items():
            if status == "snapshot" and snapshotShortnameLevels[shortname]:
                # Get the latest snapshot refs if they exist and you're generating a snapshot...
                maxLevel = max(snapshotShortnameLevels[shortname].keys())
                refs.extend(snapshotShortnameLevels[shortname][maxLevel])
            else:
                # Otherwise just grab the latest refs regardless.
                maxLevel = max(levelSet.keys())
                refs.extend(levelSet[maxLevel])

        return refs, None

    def addMethodVariants(self, methodSig, forVals, shortname):
        # Takes a full method signature, like "foo(bar)",
        # and adds appropriate lines to self.methods for it
        match = re.match(r"([^(]+)\((.*)\)", methodSig)
        if not match:
            # Was fed something that's not a method signature.
            return
        name, args = match.groups()
        arglessMethodSig = name + "()"
        variants = self.methods[arglessMethodSig]
        if methodSig not in variants:
            args = [x.strip() for x in args.split(",")]
            variants[methodSig] = {"args":args, "for":[], "shortname": shortname}
        variants[methodSig]["for"].extend(forVals)

class ReferenceManager(object):

    def __init__(self, specStatus=None):
        # Dict of {spec vshortname => spec data}
        self.specs = dict()

        # Dict of {linking text => link-defaults data}
        self.defaultSpecs = defaultdict(list)

        # Set of spec vshortnames to remove from consideration when there are other possible anchors
        self.ignoredSpecs = set()

        # Set of (obsolete spec vshortname, replacing spec vshortname), when both obsolete and replacing specs are possible anchors
        self.replacedSpecs = set()

        # Dict of {biblio term => biblio data}
        # Sparsely populated, with more loaded on demand
        self.biblios = defaultdict(list)

        # All the biblio keys
        self.biblioKeys = set()

        # Dict of {base key name => preferred display name}
        self.preferredBiblioNames = dict()

        # Dict of {spec vshortname => headings}
        # Each heading is either {#foo => heading-dict}, {/foo#bar => heading-dict} or {#foo => [page-heading-keys]}
        # In the latter, it's a list of the heading keys (of the form /foo#bar) that collide for that id.
        self.headings = dict()
        self.status = specStatus

        self.localRefs = RefSource("local")
        self.anchorBlockRefs = RefSource("anchor-block")
        self.foreignRefs = RefSource("foreign", specs=self.specs, ignored=self.ignoredSpecs, replaced=self.replacedSpecs)

    def initializeRefs(self, doc=None):
        # Load up the xref data
        self.specs.update(json.loads(config.retrieveDataFile("specs.json", quiet=True, str=True)))
        self.headings.update(json.loads(config.retrieveDataFile("headings.json", quiet=True, str=True)))
        with config.retrieveDataFile("anchors.data", quiet=True) as lines:
            self.foreignRefs.refs = decodeAnchors(lines)
        self.foreignRefs.methods.update(json.loads(config.retrieveDataFile("methods.json", quiet=True, str=True)))
        self.foreignRefs.fors.update(json.loads(config.retrieveDataFile("fors.json", quiet=True, str=True)))
        if doc is not None:
            # Get local anchor data
            try:
                with io.open("anchors.bsdata", 'r', encoding="utf-8") as lines:
                    datablocks.transformAnchors(lines, doc)
            except IOError:
                pass

            datablocks.transformInfo(config.retrieveDataFile("link-defaults.infotree", quiet=True, str=True).split("\n"), doc)
            # local info
            try:
                with io.open("link-defaults.infotree", 'r', encoding="utf-8") as lines:
                    datablocks.transformInfo(lines, doc)
            except IOError:
                pass

    def initializeBiblio(self):
        self.biblioKeys.update(json.loads(config.retrieveDataFile("biblio-keys.json", quiet=True, str=True)))

        # Get local bibliography data
        try:
            storage = defaultdict(list)
            with io.open("biblio.json", 'r', encoding="utf-8") as fh:
                biblio.processSpecrefBiblioFile(fh.read(), storage, order=2)
        except IOError:
            # Missing file is fine
            pass
        for k,vs in storage.items():
            self.biblioKeys.add(k)
            self.biblios[k].extend(vs)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, val):
        if val is None:
            self._status = None
        elif val in config.snapshotStatuses:
            self._status = "snapshot"
        elif val in config.shortToLongStatus:
            self._status = "current"
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
        for term, refs in self.foreignRefs.refs.items():
            for ref in refs:
                if ref['status'] != "local" and ref['shortname'].rstrip() == self.specName:
                    ref['export'] = False

    def addLocalDfns(self, dfns):
        for el in dfns:
            if hasClass(el, "no-ref"):
                continue
            try:
                linkTexts = config.linkTextsFromElement(el)
            except config.DuplicatedLinkText as e:
                die("The term '{0}' is in both lt and local-lt of the element {1}.", e.offendingText, outerHTML(e.el), el=e.el)
                linkTexts = e.allTexts
            for linkText in linkTexts:
                linkText = unfixTypography(linkText)
                linkText = re.sub("\s+", " ", linkText)
                linkType = treeAttr(el, 'data-dfn-type')
                if linkType not in config.dfnTypes:
                    die("Unknown local dfn type '{0}':\n  {1}", linkType, outerHTML(el), el=el)
                    continue
                if linkType in config.lowercaseTypes:
                    linkText = linkText.lower()
                dfnFor = treeAttr(el, 'data-dfn-for')
                if dfnFor is None:
                    dfnFor = set()
                    if self.getLocalRef(linkType, linkText, linkFor="/", exact=True):
                        die("Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, linkType, el=el)
                        continue
                else:
                    dfnFor = set(config.splitForValues(dfnFor))
                    encounteredError = False
                    for singleFor in dfnFor:
                        if self.getLocalRef(linkType, linkText, linkFor=singleFor, exact=True):
                            encounteredError = True
                            die("Multiple local '{1}' <dfn>s for '{2}' have the same linking text '{0}'.", linkText, linkType, singleFor, el=el)
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
                ref = {
                    "type":linkType,
                    "status":"local",
                    "spec":self.specVName,
                    "shortname":self.specName,
                    "level":self.specLevel,
                    "url":"#" + el.get('id'),
                    "export":True,
                    "for": dfnFor
                }
                self.localRefs.refs[linkText].append(ref)
                methodishStart = re.match(r"([^(]+\()[^)]", linkText)
                if methodishStart:
                    self.localRefs.addMethodVariants(linkText, dfnFor, ref["shortname"])

    def queryAllRefs(self, **kwargs):
        r1,_ = self.localRefs.queryRefs(**kwargs)
        r2,_ = self.anchorBlockRefs.queryRefs(**kwargs)
        r3,_ = self.foreignRefs.queryRefs(**kwargs)
        return r1+r2+r3

    def getLocalRef(self, linkType, text, linkFor=None, linkForHint=None, el=None, exact=False):
        return self.localRefs.queryRefs(text=text, linkType=linkType, status="local", linkFor=linkFor, linkForHint=linkForHint, exact=exact)[0]

    def getRef(self, linkType, text, spec=None, status=None, statusHint=None, linkFor=None, linkForHint=None, error=True, el=None):
        # If error is False, this function just shuts up and returns a reference or None
        # Otherwise, it pops out debug messages for the user.

        # 'maybe' links might not link up, so it's fine for them to have no references.
        # The relevent errors are gated by this variable.
        zeroRefsError = error and linkType not in ["maybe", "extended-attribute"]

        text = unfixTypography(text)
        if linkType in config.lowercaseTypes:
            text = text.lower()
        if spec is not None:
            spec = spec.lower()
        if statusHint is None:
            statusHint = self.status
        if status not in config.linkStatuses and status is not None:
            if error:
                die("Unknown spec status '{0}'. Status must be {1}.", status, config.englishFromList(config.linkStatuses), el=el)
            return None

        # Local refs always get precedence, unless you manually specified a spec.
        if spec is None:
            localRefs = self.getLocalRef(linkType, text, linkFor, linkForHint, el)
            # If the autolink was for-less, it found a for-full local link,
            # but there was a for-less version in a foreign spec,
            # emit a warning (unless it was surpressed).
            if localRefs and linkFor is None and any(x.for_ for x in localRefs):
                forlessRefs,_ = self.anchorBlockRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
                if not forlessRefs:
                    forlessRefs,_ = self.foreignRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
                if forlessRefs:
                    linkerror("Ambiguous for-less link, please see <https://tabatkins.github.io/bikeshed/#ambi-for> for instructions:\n{0}", outerHTML(el), el=el)
                    return None
            if len(localRefs) == 1:
                return localRefs[0]
            elif len(localRefs) > 1:
                if error:
                    linkerror("Multiple possible '{0}' local refs for '{1}'.\nArbitrarily chose the one with type '{2}' and for '{3}'.",
                              linkType,
                              text,
                              localRefs[0].type,
                              "' or '".join(localRefs[0].for_),
                              el=el)
                return localRefs[0]

        # Take defaults into account
        if not spec or not status or not linkFor:
            variedTexts = [v for v in linkTextVariations(text, linkType) if v in self.defaultSpecs]
            if variedTexts:
                for dfnSpec, dfnType, dfnStatus, dfnFor in reversed(self.defaultSpecs[variedTexts[0]]):
                    if not config.linkTypeIn(dfnType, linkType):
                        continue
                    if linkFor and linkFor != dfnFor:
                        continue
                    spec = spec or dfnSpec
                    status = status or dfnStatus
                    linkFor = linkFor or dfnFor
                    linkType = dfnType
                    break

        # Then anchor-block refs get preference
        blockRefs,_ = self.anchorBlockRefs.queryRefs(linkType=linkType, text=text, spec=spec, linkFor=linkFor, linkForHint=linkForHint, el=el, status="anchor-block")
        if blockRefs and linkFor is None and any(x.for_ for x in blockRefs):
            forlessRefs,_ = self.foreignRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
            if forlessRefs:
                linkerror("Ambiguous for-less link, please see <https://tabatkins.github.io/bikeshed/#ambi-for> for instructions:\n{0}", outerHTML(el), el=el)
                return None
        if len(blockRefs) == 1:
            return blockRefs[0]
        elif len(blockRefs) > 1:
            reportMultiplePossibleRefs([refToText(ref) for ref in simplifyPossibleRefs(blockRefs)], text, linkType, blockRefs[0], el)
            return blockRefs[0]


        # Get the relevant refs
        if spec is None:
            export = True
        else:
            export = None
        refs, failure = self.foreignRefs.queryRefs(text=text, linkType=linkType, spec=spec, status=status, statusHint=statusHint, linkFor=linkFor, linkForHint=linkForHint, export=export, ignoreObsoletes=True)

        if failure and linkType in ("argument", "idl") and linkFor is not None and linkFor.endswith("()"):
            # foo()/bar failed, because foo() is technically the wrong signature
            # let's see if we can find the right signature, and it's unambiguous
            while True:  # Hack for early exits
                if "/" in linkFor:
                    interfaceName, _, methodName = linkFor.partition("/")
                else:
                    methodName = linkFor
                    interfaceName = None
                methodSignatures = self.foreignRefs.methods.get(methodName, None)
                if methodSignatures is None:
                    # Nope, foo() is just wrong entirely.
                    # Jump out and fail in a normal way
                    break
                # Find all method signatures that contain the arg in question
                # and, if interface is specified, are for that interface.
                # Dedup/collect by url, so I'll get all the signatures for a given dfn.
                possibleMethods = defaultdict(list)
                for argfullName, metadata in methodSignatures.items():
                    if text in metadata["args"] and (interfaceName in metadata["for"] or interfaceName is None) and metadata["shortname"] != self.specName:
                        possibleMethods[metadata["shortname"]].append(argfullName)
                possibleMethods = possibleMethods.values()
                if not possibleMethods:
                    # No method signatures with this argument/interface.
                    # Jump out and fail in a normal way.
                    break
                if len(possibleMethods) > 1:
                    # Too many to disambiguate.
                    linkerror("The argument autolink '{0}' for '{1}' has too many possible overloads to disambiguate. Please specify the full method signature this argument is for.", text, linkFor, el=el)
                # Try out all the combinations of interface/status/signature
                linkForPatterns = ["{i}/{m}", "{m}"]
                statuses = ["local", status]
                for p in linkForPatterns:
                    for s in statuses:
                        for m in possibleMethods[0]:
                            refs, failure = self.foreignRefs.queryRefs(text=text, linkType=linkType, spec=spec, status=s, linkFor=p.format(i=interfaceName, m=m), ignoreObsoletes=True)
                            if refs:
                                break
                        if refs:
                            break
                    if refs:
                        break
                # Now we can break out and just let the normal error-handling machinery take over.
                break

            # Allow foo(bar) to be for'd to with just foo() if it's completely unambiguous.
            methodPrefix = methodName[:-1]
            candidates, _ = self.localRefs.queryRefs(linkType="functionish", linkFor=interfaceName)
            methodRefs = {c.url: c for c in candidates if c.text.startswith(methodPrefix)}.values()
            if not methodRefs:
                # Look for non-locals, then
                c1,_ = self.anchorBlockRefs.queryRefs(linkType="functionish", spec=spec, status=status, statusHint=statusHint, linkFor=interfaceName, export=export, ignoreObsoletes=True)
                c2,_ = self.foreignRefs.queryRefs(linkType="functionish", spec=spec, status=status, statusHint=statusHint, linkFor=interfaceName, export=export, ignoreObsoletes=True)
                candidates = c1 + c2
                methodRefs = {c.url: c for c in candidates if c.text.startswith(methodPrefix)}.values()
            if zeroRefsError and len(methodRefs) > 1:
                # More than one possible foo() overload, can't tell which to link to
                linkerror("Too many possible method targets to disambiguate '{0}/{1}'. Please specify the names of the required args, like 'foo(bar, baz)', in the 'for' attribute.", linkFor, text, el=el)
                return
            # Otherwise

        if failure == "text" or failure == "type":
            if linkType in ("property", "propdesc", "descriptor") and text.startswith("--"):
                # Custom properties/descriptors aren't ever defined anywhere
                return None
            if zeroRefsError:
                linkerror("No '{0}' refs found for '{1}'.", linkType, text, el=el)
            return None
        elif failure == "export":
            if zeroRefsError:
                linkerror("No '{0}' refs found for '{1}' that are marked for export.", linkType, text, el=el)
            return None
        elif failure == "spec":
            if zeroRefsError:
                linkerror("No '{0}' refs found for '{1}' with spec '{2}'.", linkType, text, spec, el=el)
            return None
        elif failure == "for":
            if zeroRefsError:
                if spec is None:
                    linkerror("No '{0}' refs found for '{1}' with for='{2}'.", linkType, text, linkFor, el=el)
                else:
                    linkerror("No '{0}' refs found for '{1}' with for='{2}' in spec '{3}'.", linkType, text, linkFor, spec, el=el)
            return None
        elif failure == "status":
            if zeroRefsError:
                if spec is None:
                    linkerror("No '{0}' refs found for '{1}' compatible with status '{2}'.", linkType, text, status, el=el)
                else:
                    linkerror("No '{0}' refs found for '{1}' compatible with status '{2}' in spec '{3}'.", linkType, text, status, spec, el=el)
            return None
        elif failure == "ignored-specs":
            if zeroRefsError:
                linkerror("The only '{0}' refs for '{1}' were in ignored specs:\n{2}", linkType, text, outerHTML(el), el=el)
            return None
        elif failure:
            die("Programming error - I'm not catching '{0}'-type link failures. Please report!", failure, el=el)
            return None

        if len(refs) == 1:
            # Success!
            return refs[0]

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
            reportMultiplePossibleRefs([refToText(ref) for ref in simplifyPossibleRefs(refs)], text, linkType, defaultRef, el)
        return defaultRef

    def getBiblioRef(self, text, status="normative", generateFakeRef=False, el=None, quiet=False):
        key = text.lower()
        if key in ["notifications", "fullscreen", "dom", "url", "encoding"]:
            # A handful of specs where W3C is squatting with an out-of-date fork.
            key = "whatwg-" + key
        if key in self.biblios:
            candidates = self.biblios[key]
        elif key in self.biblioKeys:
            # Key exists in biblio db, but its data isn't loaded yet.
            group = key[0:2]
            with config.retrieveDataFile("biblio/biblio-{0}.data".format(group), quiet=True) as lines:
                biblio.loadBiblioDataFile(lines, self.biblios)
            candidates = self.biblios[key]
        elif key in self.specs:
            # First see if the ref is just unnecessarily levelled
            match = re.match(r"(.+?)-\d+", key)
            if match:
                ref = self.getBiblioRef(match.group(1), status, el=el, quiet=True)
                if ref:
                    return ref
            if generateFakeRef:
                return biblio.SpecBasedBiblioEntry(self.specs[key], preferredURL=self.status)
            else:
                return None
        else:
            return None

        candidate = stripLineBreaks(sorted(candidates, key=itemgetter('order'))[0])
        # TODO: When SpecRef definitely has all the CSS specs, turn on this code.
        # if candidates[0]['order'] > 3: # 3 is SpecRef level
        #    warn("Bibliography term '{0}' wasn't found in SpecRef.\n         Please find the equivalent key in SpecRef, or submit a PR to SpecRef.", text)
        if candidate['biblioFormat'] == "string":
            bib = biblio.StringBiblioEntry(**candidate)
        elif candidate['biblioFormat'] == "alias":
            # Follow the chain to the real candidate
            bib = self.getBiblioRef(candidate["aliasOf"], status=status, el=el, quiet=True)
        else:
            bib = biblio.BiblioEntry(preferredURL=self.status, **candidate)

        # If a canonical name has been established, use it.
        if bib.linkText in self.preferredBiblioNames:
            bib.originalLinkText, bib.linkText = bib.linkText, self.preferredBiblioNames[bib.linkText]

        return bib


def linkTextVariations(str, linkType):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding an lt attr isn't usually necessary.
    yield str

    if linkType is None:
        return
    elif linkType == "dfn":
        last1 = str[-1] if len(str) >= 1 else None
        last2 = str[-2:] if len(str) >= 2 else None
        last3 = str[-3:] if len(str) >= 3 else None
        # Berries <-> Berry
        if last3 == "ies":
            yield str[:-3] + "y"
        if last1 == "y":
            yield str[:-1] + "ies"

        # Blockified <-> Blockify
        if last3 == "ied":
            yield str[:-3] + "y"
        if last1 == "y":
            yield str[:-1] + "ied"

        # Zeroes <-> Zero
        if last2 == "es":
            yield str[:-2]
        else:
            yield str + "es"

        # Bikeshed's <-> Bikeshed
        if last2 == "'s" or last2 == "’s":
            yield str[:-2]
        else:
            yield str + "'s"

        # Bikesheds <-> Bikeshed
        if last1 == "s":
            yield str[:-1]
        else:
            yield str + "s"

        # Bikesheds <-> Bikesheds'
        if last1 == "'" or last1 == "’":
            yield str[:-1]
        else:
            yield str + "'"

        # Snapped <-> Snap
        if last2 == "ed" and len(str) >= 4 and str[-3] == str[-4]:
            yield str[:-3]
        elif last1 in "bdfgklmnprstvz":
            yield str + last1 + "ed"

        # Zeroed <-> Zero
        if last2 == "ed":
            yield str[:-2]
        else:
            yield str + "ed"

        # Generated <-> Generate
        if last1 == "d":
            yield str[:-1]
        else:
            yield str + "d"

        # Navigating <-> Navigate
        if last3 == "ing":
            yield str[:-3]
            yield str[:-3] + "e"
        elif last1 == "e":
            yield str[:-1] + "ing"
        else:
            yield str + "ing"

        # Snapping <-> Snap
        if last3 == "ing" and len(str) >= 5 and str[-4] == str[-5]:
            yield str[:-4]
        elif last1 in "bdfgklmnprstvz":
            yield str + last1 + "ing"

    elif config.linkTypeIn(linkType, "idl"):
        # Let people refer to escaped IDL names with their "real" names (without the underscore)
        if str[:1] != "_":
            yield "_" + str


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
        return "RefWrapper(" + repr(self.text) + ", " + repr(self.ref) + ")"


def simplifyPossibleRefs(refs):
    # "Simplifies" the set of possible refs according to their 'for' value;
    # returns a list of text/type/spec/for objects,
    # with the for value filled in *only if necessary for disambiguation*.
    forVals = defaultdict(list)
    for ref in refs:
        if ref.for_:
            for for_ in ref.for_:  # ref.for_ is a list
                forVals[(ref.text, ref.type, ref.spec)].append(for_)
        else:
            forVals[(ref.text, ref.type, ref.spec)].append("/")
    retRefs = []
    for (text, type, spec), fors in forVals.items():
        if len(fors) >= 2:
            for for_ in fors:
                retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':for_})
        else:
            retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':None})
    return retRefs

def refToText(ref):
    if ref['for_']:
        return 'spec:{spec}; type:{type}; for:{for_}; text:{text}'.format(**ref)
    else:
        return 'spec:{spec}; type:{type}; text:{text}'.format(**ref)

def reportMultiplePossibleRefs(possibleRefs, text, linkType, defaultRef, el):
    if len(possibleRefs) == 1:
        # Only happens when the refs can't be disambiguated under Bikeshed's data model.
        linkerror("Multiple possible '{0}' refs for '{1}' in {2}, but they're not distinguishable with Bikeshed's data model. Either create a manual link, or ask the spec maintainer to add sufficient disambiguating attributes to make them distinguishable. Usually this means adding a for='' value to at least one of them.\nArbitrarily chose the {3} one to link to for now.",
                  linkType,
                  text,
                  defaultRef.spec,
                  defaultRef.url,
                  el=el)
    else:
        linkerror("Multiple possible '{0}' refs for '{1}'.\nArbitrarily chose the one in {2}.\nIf this is wrong, insert one of the following lines into a <pre class=link-defaults> block:\n{3}",
                  linkType,
                  text,
                  defaultRef.spec,
                  '\n'.join(possibleRefs),
                  el=el)

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
