# -*- coding: utf-8 -*-


import io
import json
import os
import random
import re
from collections import defaultdict
from operator import itemgetter

from .RefSource import RefSource
from .utils import *
from .. import biblio
from .. import config
from .. import constants
from .. import datablocks
from ..h import *
from ..messages import *

class ReferenceManager(object):

    __slots__ = ["dataFile", "specs", "defaultSpecs", "ignoredSpecs", "replacedSpecs", "biblios", "loadedBiblioGroups",
        "biblioKeys", "biblioNumericSuffixes", "preferredBiblioNames", "headings", "defaultStatus", "localRefs", "anchorBlockRefs", "foreignRefs",
        "shortname", "specLevel", "spec", "testing"]

    def __init__(self, defaultStatus=None, fileRequester=None, testing=False):
        if fileRequester is None:
            self.dataFile = config.defaultRequester
        else:
            self.dataFile = fileRequester

        self.testing = testing

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
        self.loadedBiblioGroups = set()

        # Most of the biblio keys, for biblio near-miss correction
        # (Excludes dated versions, and all huge "foo\d+" groups that can't usefully correct typos.)
        self.biblioKeys = set()

        # Dict of {suffixless key => [keys with numeric suffixes]}
        # (So you can tell when it's appropriate to default a numeric-suffix ref to a suffixless one.)
        self.biblioNumericSuffixes = dict()

        # Dict of {base key name => preferred display name}
        self.preferredBiblioNames = dict()

        # Dict of {spec vshortname => headings}
        # Each heading is either {#foo => heading-dict}, {/foo#bar => heading-dict} or {#foo => [page-heading-keys]}
        # In the latter, it's a list of the heading keys (of the form /foo#bar) that collide for that id.
        self.headings = dict()

        if defaultStatus is None:
            self.defaultStatus = constants.refStatus.current
        else:
            self.defaultStatus = constants.refStatus[defaultStatus]

        self.localRefs = RefSource("local", fileRequester=fileRequester)
        self.anchorBlockRefs = RefSource("anchor-block", fileRequester=fileRequester)
        self.foreignRefs = RefSource("foreign", specs=self.specs, ignored=self.ignoredSpecs, replaced=self.replacedSpecs, fileRequester=fileRequester)

    def initializeRefs(self, doc=None):
        '''
        Load up the xref data
        This is oddly split up into sub-functions to make it easier to track performance.
        '''

        def initSpecs():
            self.specs.update(json.loads(self.dataFile.fetch("specs.json", str=True)))
        initSpecs()
        def initMethods():
            self.foreignRefs.methods.update(json.loads(self.dataFile.fetch("methods.json", str=True)))
        initMethods()
        def initFors():
            self.foreignRefs.fors.update(json.loads(self.dataFile.fetch("fors.json", str=True)))
        initFors()
        if doc and doc.inputSource and doc.inputSource.hasDirectory:
            datablocks.transformInfo(self.dataFile.fetch("link-defaults.infotree", str=True).split("\n"), doc)

            # Get local anchor data
            shouldGetLocalAnchorData = doc.md.externalInfotrees["anchors.bsdata"]
            if not shouldGetLocalAnchorData and doc.inputSource.cheaplyExists("anchors.bsdata"):
                warn("Found anchors.bsdata next to the specification without a matching\n"+
                    "External Infotrees: anchors.bsdata yes\n"+
                    "in the metadata. This data won't be found when building via a URL.")
                # We should remove this after giving specs time to react to the warning:
                shouldGetLocalAnchorData = True
            if shouldGetLocalAnchorData:
                try:
                    datablocks.transformAnchors(doc.inputSource.relative("anchors.bsdata").read().rawLines, doc)
                except IOError:
                    warn("anchors.bsdata not found despite being listed in the External Infotrees metadata.")

            # Get local link defaults
            shouldGetLocalLinkDefaults = doc.md.externalInfotrees["link-defaults.infotree"]
            if not shouldGetLocalLinkDefaults and doc.inputSource.cheaplyExists("link-defaults.infotree"):
                warn("Found link-defaults.infotree next to the specification without a matching\n"+
                    "External Infotrees: link-defaults.infotree yes\n"+
                    "in the metadata. This data won't be found when building via a URL.")
                # We should remove this after giving specs time to react to the warning:
                shouldGetLocalLinkDefaults = True
            if shouldGetLocalLinkDefaults:
                try:
                    datablocks.transformInfo(doc.inputSource.relative("link-defaults.infotree").read().rawLines, doc)
                except IOError:
                    warn("link-defaults.infotree not found despite being listed in the External Infotrees metadata.")

    def fetchHeadings(self, spec):
        if spec in self.headings:
            return self.headings[spec]
        with self.dataFile.fetch("headings", "headings-{0}.json".format(spec), okayToFail=True) as fh:
            try:
                data = json.load(fh)
            except ValueError:
                # JSON couldn't be decoded, *should* only be because of empty file
                return
            self.headings[spec] = data
            return data

    def initializeBiblio(self):
        self.biblioKeys.update(json.loads(self.dataFile.fetch("biblio-keys.json", str=True)))
        self.biblioNumericSuffixes.update(json.loads(self.dataFile.fetch("biblio-numeric-suffixes.json", str=True)))

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

        # Hardcode RFC2119, used in most spec's boilerplates,
        # to avoid having to parse the entire biblio-rf.data file for this single reference.
        self.biblioKeys.add("rfc2119")
        self.biblios["rfc2119"].append({
            "linkText": "rfc2119\n",
            "date": "March 1997\n",
            "status": "Best Current Practice\n",
            "title": "Key words for use in RFCs to Indicate Requirement Levels\n",
            "snapshot_url": "https://tools.ietf.org/html/rfc2119\n",
            "current_url": "\n",
            "obsoletedBy": "\n",
            "other": "\n",
            "etAl": False,
            "order": 3,
            "biblioFormat": "dict",
            "authors": ["S. Bradner\n"]
            })

    def setSpecData(self, md):
        if md.defaultRefStatus:
            self.defaultStatus = md.defaultRefStatus
        elif md.status in config.snapshotStatuses:
            self.defaultStatus = constants.refStatus.snapshot
        elif md.status in config.shortToLongStatus:
            self.defaultStatus = constants.refStatus.current
        self.shortname = md.shortname
        self.specLevel = md.level
        self.spec = md.vshortname

        for term, defaults in md.linkDefaults.items():
            for default in defaults:
                self.defaultSpecs[term].append(default)

        # Need to get a real versioned shortname,
        # with the possibility of overriding the "shortname-level" pattern.
        self.removeSameSpecRefs()

    def removeSameSpecRefs(self):
        # Kill all the non-local anchors with the same shortname as the current spec,
        # so you don't end up accidentally linking to something that's been removed from the local copy.
        # TODO: This is dumb.
        for term, refs in self.foreignRefs._refs.items():
            for ref in refs:
                if ref['status'] != "local" and ref['shortname'].rstrip() == self.shortname:
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
                    existingRefs = self.localRefs.queryRefs(linkType=linkType, text=linkText, linkFor="/", exact=True)[0]
                    if existingRefs and existingRefs[0].el is not el:
                        die("Multiple local '{1}' <dfn>s have the same linking text '{0}'.", linkText, linkType, el=el)
                        continue
                else:
                    dfnFor = set(config.splitForValues(dfnFor))
                    encounteredError = False
                    for singleFor in dfnFor:
                        existingRefs = self.localRefs.queryRefs(linkType=linkType, text=linkText, linkFor=singleFor, exact=True)[0]
                        if existingRefs and existingRefs[0].el is not el:
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
                dfnFor = sorted(dfnFor)
                ref = {
                    "type":linkType,
                    "status":"local",
                    "spec":self.spec,
                    "shortname":self.shortname,
                    "level":self.specLevel,
                    "url":"#" + el.get('id'),
                    "export":True,
                    "for": dfnFor,
                    "el": el
                }
                self.localRefs._refs[linkText].append(ref)
                for for_ in dfnFor:
                    self.localRefs.fors[for_].append(linkText)
                methodishStart = re.match(r"([^(]+\()[^)]", linkText)
                if methodishStart:
                    self.localRefs.addMethodVariants(linkText, dfnFor, ref["shortname"])

    def filterObsoletes(self, refs):
        return filterObsoletes(refs,
                               replacedSpecs=self.replacedSpecs,
                               ignoredSpecs=self.ignoredSpecs,
                               localShortname=self.shortname,
                               localSpec=self.spec)

    def queryAllRefs(self, **kwargs):
        r1,_ = self.localRefs.queryRefs(**kwargs)
        r2,_ = self.anchorBlockRefs.queryRefs(**kwargs)
        r3,_ = self.foreignRefs.queryRefs(**kwargs)
        refs = r1+r2+r3
        if kwargs.get("ignoreObsoletes") is True:
            refs = self.filterObsoletes(refs)
        return refs

    def getRef(self, linkType, text, spec=None, status=None, statusHint=None, linkFor=None, explicitFor=False, linkForHint=None, error=True, el=None):
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
            statusHint = self.defaultStatus
        if status not in config.linkStatuses and status is not None:
            if error:
                die("Unknown spec status '{0}'. Status must be {1}.", status, config.englishFromList(config.linkStatuses), el=el)
            return None

        # Local refs always get precedence, unless you manually specified a spec.
        if spec is None:
            localRefs,_ = self.localRefs.queryRefs(linkType=linkType, text=text, linkFor=linkFor, linkForHint=linkForHint, explicitFor=explicitFor, el=el)
            # If the autolink was for-less, it found a for-full local link,
            # but there was a for-less version in a foreign spec,
            # emit a warning (unless it was supressed).
            if localRefs and linkFor is None and any(x.for_ for x in localRefs):
                forlessRefs,_ = self.anchorBlockRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
                forlessRefs = self.filterObsoletes(forlessRefs)
                if not forlessRefs:
                    forlessRefs,_ = self.foreignRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
                forlessRefs = self.filterObsoletes(forlessRefs)
                if forlessRefs:
                    reportAmbiguousForlessLink(el, text, forlessRefs, localRefs)
                    return None
            if len(localRefs) == 1:
                return localRefs[0]
            elif len(localRefs) > 1:
                if self.testing:
                    # Generate a stable answer
                    chosenRef = sorted(localRefs, key=lambda x:x.url)[0]
                else:
                    # CHAOS MODE (so you're less likely to rely on it)
                    chosenRef = random.choice(localRefs)
                if error:
                    linkerror(f"Multiple possible '{linkType}' local refs for '{text}'.\nRandomly chose one of them; other instances might get a different random choice.", el=el)
                return chosenRef

        if status == "local":
            # Already checked local refs, can early-exit now.
            return

        # Take defaults into account
        if not spec or not status or not linkFor:
            variedTexts = [v for v in linkTextVariations(text, linkType) if v in self.defaultSpecs]
            if variedTexts:
                for dfnSpec, dfnType, dfnStatus, dfnFor in reversed(self.defaultSpecs[variedTexts[0]]):
                    if not config.linkTypeIn(dfnType, linkType):
                        continue
                    if linkFor and dfnFor:
                        if isinstance(linkFor, str) and linkFor != dfnFor:
                            continue
                        if dfnFor not in linkFor:
                            continue
                    spec = spec or dfnSpec
                    status = status or dfnStatus
                    linkFor = linkFor or dfnFor
                    linkType = dfnType
                    break

        # Then anchor-block refs get preference
        blockRefs,_ = self.anchorBlockRefs.queryRefs(linkType=linkType, text=text, spec=spec, linkFor=linkFor, linkForHint=linkForHint, explicitFor=explicitFor, el=el)
        if blockRefs and linkFor is None and any(x.for_ for x in blockRefs):
            forlessRefs,_ = self.foreignRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
            forlessRefs = self.filterObsoletes(forlessRefs)
            if forlessRefs:
                reportAmbiguousForlessLink(el, text, forlessRefs, blockRefs)
                return None
        if len(blockRefs) == 1:
            return blockRefs[0]
        elif len(blockRefs) > 1:
            reportMultiplePossibleRefs(simplifyPossibleRefs(blockRefs), linkText=text, linkType=linkType, linkFor=linkFor, defaultRef=blockRefs[0], el=el)
            return blockRefs[0]


        # Get the relevant refs
        if spec is None:
            export = True
        else:
            export = None
        refs, failure = self.foreignRefs.queryRefs(text=text, linkType=linkType, spec=spec, status=status, statusHint=statusHint, linkFor=linkFor, linkForHint=linkForHint, explicitFor=explicitFor, export=export, ignoreObsoletes=True)

        if failure and linkType in ("argument", "idl") and linkFor is not None and any(x.endswith("()") for x in linkFor):
            # foo()/bar failed, because foo() is technically the wrong signature
            # let's see if we can find the right signature, and it's unambiguous
            for lf in linkFor:
                if not lf.endswith("()"):
                    continue
                if "/" in lf:
                    interfaceName, _, methodName = lf.partition("/")
                else:
                    methodName = lf
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
                    if text in metadata["args"] and (interfaceName in metadata["for"] or interfaceName is None) and metadata["shortname"] != self.shortname:
                        possibleMethods[metadata["shortname"]].append(argfullName)
                possibleMethods = list(possibleMethods.values())
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
            methodRefs = list({c.url: c for c in candidates if c.text.startswith(methodPrefix)}.values())
            if not methodRefs:
                # Look for non-locals, then
                c1,_ = self.anchorBlockRefs.queryRefs(linkType="functionish", spec=spec, status=status, statusHint=statusHint, linkFor=interfaceName, export=export, ignoreObsoletes=True)
                c2,_ = self.foreignRefs.queryRefs(linkType="functionish", spec=spec, status=status, statusHint=statusHint, linkFor=interfaceName, export=export, ignoreObsoletes=True)
                candidates = c1 + c2
                methodRefs = list({c.url: c for c in candidates if c.text.startswith(methodPrefix)}.values())
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
            reportMultiplePossibleRefs(simplifyPossibleRefs(refs), linkText=text, linkType=linkType, linkFor=linkFor, defaultRef=defaultRef, el=el)
        return defaultRef

    def getBiblioRef(self, text, status=None, generateFakeRef=False, el=None, quiet=False, depth=0):
        if depth > 100:
            die("Data error in biblio files; infinitely recursing trying to find [{0}].", text)
            return
        key = text.lower()
        while True:
            candidates = self.bibliosFromKey(key)
            if candidates:
                break

            # Did it fail because SpecRef *only* has the *un*versioned name?
            # Aka you said [[foo-1]], but SpecRef only has [[foo]].
            # "Only" is important - if there are versioned names that just don't match what you gave,
            # then I shouldn't autofix;
            # if you say [[foo-2]], and [[foo]] and [[foo-1]] exist,
            # then [[foo-2]] is just an error.
            match = re.match(r"(.+)-\d+$", key)
            failFromWrongSuffix = False
            if match and match.group(1) in self.biblios:
                unversionedKey = match.group(1)
                if unversionedKey in self.biblioNumericSuffixes:
                    # Nope, there are more numeric-suffixed versions,
                    # just not the one you asked for
                    failFromWrongSuffix = True
                else:
                    # Load up the unversioned url!
                    candidates = self.biblios[unversionedKey]
                    break

            # Did it fail because I only know about the spec from Shepherd?
            if key in self.specs and generateFakeRef:
                spec = self.specs[key]
                return biblio.SpecBasedBiblioEntry(spec, preferredURL=status)

            if failFromWrongSuffix and not quiet:
                numericSuffixes = self.biblioNumericSuffixes[unversionedKey]
                die("A biblio link references {0}, but only {1} exists in SpecRef.", text, config.englishFromList(numericSuffixes))
            return None

        candidate = self._bestCandidateBiblio(candidates)
        # TODO: When SpecRef definitely has all the CSS specs, turn on this code.
        # if candidates[0]['order'] > 3: # 3 is SpecRef level
        #    warn("Bibliography term '{0}' wasn't found in SpecRef.\n         Please find the equivalent key in SpecRef, or submit a PR to SpecRef.", text)
        if candidate['biblioFormat'] == "string":
            bib = biblio.StringBiblioEntry(**candidate)
        elif candidate['biblioFormat'] == "alias":
            # Follow the chain to the real candidate
            bib = self.getBiblioRef(candidate["aliasOf"], status=status, el=el, quiet=True, depth=depth+1)
            if bib is None:
                die("Biblio ref [{0}] claims to be an alias of [{1}], which doesn't exist.", text, candidate["aliasOf"])
                return None
        elif candidate.get("obsoletedBy", "").strip():
            # Obsoleted by - throw an error and follow the chain
            bib = self.getBiblioRef(candidate["obsoletedBy"], status=status, el=el, quiet=True, depth=depth+1)
            if not quiet:
                die("Obsolete biblio ref: [{0}] is replaced by [{1}].", candidate["linkText"], bib.linkText)
        else:
            bib = biblio.BiblioEntry(preferredURL=status, **candidate)

        # If a canonical name has been established, use it.
        if bib.linkText in self.preferredBiblioNames:
            bib.originalLinkText, bib.linkText = bib.linkText, self.preferredBiblioNames[bib.linkText]

        return bib


    def bibliosFromKey(self, key):
        # Load up the biblio data necessary to fetch the given key
        # and then actually fetch it.
        # If you don't call this,
        # the current data might not be reliable.
        if key not in self.biblios:
            # Try to load the group up, if necessary
            group = key[0:2]
            if group not in self.loadedBiblioGroups:
                with self.dataFile.fetch("biblio", "biblio-{0}.data".format(group), okayToFail=True) as lines:
                    biblio.loadBiblioDataFile(lines, self.biblios)
            self.loadedBiblioGroups.add(group)
        return self.biblios.get(key, [])


    def _bestCandidateBiblio(self, candidates):
        return stripLineBreaks(sorted(candidates, key=itemgetter('order'))[0])


    def getLatestBiblioRef(self, key, el=None, quiet=False):
        # Takes a biblio reference name,
        # returns the latest dated variant of that name
        # (names in the form FOO-19700101)
        candidates = self.bibliosFromKey(key)
        if not candidates:
            return None
        latestDate = None
        latestRefs = None
        for k,biblios in self.biblios.items():
            if not k.startswith(key):
                continue
            match = re.search(r"(\d{8})$", k)
            if not match:
                continue
            date = match.group(1)
            if latestDate is None or date > latestDate:
                latestDate = date
                latestRefs = biblios
        if latestRefs is None:
            return None
        return biblio.BiblioEntry(**self._bestCandidateBiblio(latestRefs))


    def vNamesFromSpecNames(self, specName):
        # Takes an unversioned specName,
        # returns the versioned names that Shepherd knows about.

        chosenVNames = []
        for vSpecName in self.specs.keys():
            if not vSpecName.startswith(specName):
                continue
            match = re.match(r"-?(\d+)", vSpecName[len(specName):])
            if match is None:
                continue
            chosenVNames.append(vSpecName)
        return chosenVNames



def simplifyPossibleRefs(refs, alwaysShowFor=False):
    # "Simplifies" the set of possible refs according to their 'for' value;
    # returns a list of text/type/spec/for objects,
    # with the for value filled in *only if necessary for disambiguation*.
    forVals = defaultdict(list)
    for ref in refs:
        if ref.for_:
            for for_ in ref.for_:  # ref.for_ is a list
                forVals[(ref.text, ref.type, ref.spec)].append((for_, ref.url))
        else:
            forVals[(ref.text, ref.type, ref.spec)].append(("/", ref.url))
    retRefs = []
    for (text, type, spec), fors in forVals.items():
        if len(fors) >= 2 or alwaysShowFor:
            # Needs for-based disambiguation
            for for_,url in fors:
                retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':for_, 'url': url})
        else:
            retRefs.append({'text':text, 'type':type, 'spec':spec, 'for_':None, 'url': fors[0][1]})
    return retRefs


def refToText(ref):
    if ref['for_']:
        return 'spec:{spec}; type:{type}; for:{for_}; text:{text}'.format(**ref)
    else:
        return 'spec:{spec}; type:{type}; text:{text}'.format(**ref)


def reportMultiplePossibleRefs(possibleRefs, linkText, linkType, linkFor, defaultRef, el):
    # Sometimes a badly-written spec has indistinguishable dfns.
    # Detect this by seeing if more than one stringify to the same thing.
    allRefs = defaultdict(list)
    for ref in possibleRefs:
        allRefs[refToText(ref)].append(ref)
    uniqueRefs = []
    mergedRefs = []
    for refs in allRefs.values():
        if len(refs) == 1:
            uniqueRefs.append(refs[0])
        else:
            mergedRefs.append(refs)

    if linkFor:
        error = "Multiple possible '{0}' {1} refs for '{2}'.".format(linkText, linkType, linkFor)
    else:
        error = "Multiple possible '{0}' {1} refs.".format(linkText, linkType)
    error += "\nArbitrarily chose {0}".format(defaultRef.url)
    if uniqueRefs:
        error += "\nTo auto-select one of the following refs, insert one of these lines into a <pre class=link-defaults> block:\n"
        error += "\n".join(refToText(r) for r in uniqueRefs)
    if mergedRefs:
        error += "\nThe following refs show up multiple times in their spec, in a way that Bikeshed can't distinguish between. Either create a manual link, or ask the spec maintainer to add disambiguating attributes (usually a for='' attribute to all of them)."
        for refs in mergedRefs:
            error += "\n" + refToText(refs[0])
            for ref in refs:
                error += "\n  " + ref['url']
    linkerror(error, el=el)


def reportAmbiguousForlessLink(el, text, forlessRefs, localRefs):
    linkerror("Ambiguous for-less link for '{0}', please see <https://tabatkins.github.io/bikeshed/#ambi-for> for instructions:\nLocal references:\n{1}\nfor-less references:\n{2}", text, "\n".join([refToText(ref) for ref in simplifyPossibleRefs(localRefs, alwaysShowFor=True)]), "\n".join([refToText(ref) for ref in simplifyPossibleRefs(forlessRefs, alwaysShowFor=True)]), el=el)
