from __future__ import annotations

import dataclasses
import json
import random
import re
from collections import defaultdict

from .. import biblio, config, constants, h, retrieve, t
from .. import messages as m
from . import headingdata, source, utils, wrapper

if t.TYPE_CHECKING:
    from .wrapper import RefWrapper

    SpecDataT: t.TypeAlias = dict[str, str]


class ReferenceManager:
    __slots__ = [
        "dataFile",
        "specs",
        "defaultSpecs",
        "ignoredSpecs",
        "replacedSpecs",
        "biblios",
        "loadedBiblioGroups",
        "biblioKeys",
        "biblioNumericSuffixes",
        "preferredBiblioNames",
        "headings",
        "defaultStatus",
        "localRefs",
        "anchorBlockRefs",
        "foreignRefs",
        "shortname",
        "specLevel",
        "spec",
        "testing",
    ]

    def __init__(
        self,
        defaultStatus: str | None = None,
        fileRequester: t.DataFileRequester | None = None,
        testing: bool = False,
    ) -> None:
        self.dataFile: t.DataFileRequester
        if fileRequester is None:
            self.dataFile = retrieve.defaultRequester
        else:
            self.dataFile = fileRequester

        self.testing: bool = testing

        # Dict of {spec vshortname => spec data}
        self.specs: dict[str, SpecDataT] = {}

        # Dict of {linking text => link-defaults data}
        self.defaultSpecs: t.LinkDefaultsT = defaultdict(list)

        # Set of spec vshortnames to remove from consideration when there are other possible anchors
        self.ignoredSpecs: set[str] = set()

        # Set of (obsolete spec vshortname, replacing spec vshortname), when both obsolete and replacing specs are possible anchors
        self.replacedSpecs: set[tuple[str, str]] = set()

        # Dict of {biblio term => biblio data}
        # Sparsely populated, with more loaded on demand
        self.biblios: defaultdict[str, list[biblio.BiblioEntry]] = defaultdict(list)
        self.loadedBiblioGroups: set[str] = set()

        # Most of the biblio keys, for biblio near-miss correction
        # (Excludes dated versions, and all huge "foo\d+" groups that can't usefully correct typos.)
        self.biblioKeys: set[str] = set()

        # Dict of {suffixless key => [keys with numeric suffixes]}
        # (So you can tell when it's appropriate to default a numeric-suffix ref to a suffixless one.)
        self.biblioNumericSuffixes: dict[str, list[str]] = {}

        # Dict of {base key name => preferred display name}
        self.preferredBiblioNames: dict[str, str] = {}

        # Dict of {spec vshortname => headings}
        self.headings: dict[str, headingdata.SpecHeadings] = {}

        self.defaultStatus: str
        if defaultStatus is None:
            self.defaultStatus = constants.refStatus.current
        else:
            self.defaultStatus = constants.refStatus[defaultStatus]

        self.localRefs: source.RefSource = source.RefSource("local", fileRequester=fileRequester)
        self.anchorBlockRefs: source.RefSource = source.RefSource("anchor-block", fileRequester=fileRequester)
        self.foreignRefs: source.RefSource = source.RefSource(
            "foreign",
            specs=self.specs,
            ignored=self.ignoredSpecs,
            replaced=self.replacedSpecs,
            fileRequester=fileRequester,
        )
        self.shortname: str | None = None
        self.specLevel: str | None = None
        self.spec: str | None = None

    def initializeRefs(self, datablocks: t.ModuleType, doc: t.SpecT | None = None) -> None:
        """
        Load up the xref data
        This is oddly split up into sub-functions to make it easier to track performance.
        """

        def initSpecs() -> None:
            self.specs.update(json.loads(self.dataFile.fetch("specs.json", str=True)))

        initSpecs()

        def initMethods() -> None:
            for arglessSig, argfulls in json.loads(self.dataFile.fetch("methods.json", str=True)).items():
                variants = source.MethodVariants(arglessSig, {})
                self.foreignRefs.methods[arglessSig] = variants
                for argfullSig, data in argfulls.items():
                    variants.variants[argfullSig] = source.MethodVariant(
                        argfullSig,
                        data["args"],
                        data["for"],
                        data["shortname"],
                    )

        initMethods()

        def initFors() -> None:
            self.foreignRefs.fors.update(json.loads(self.dataFile.fetch("fors.json", str=True)))

        initFors()
        if doc and doc.inputSource and doc.inputSource.hasDirectory():
            ldLines = self.dataFile.fetch("link-defaults.infotree").read().split("\n")
            datablocks.transformInfo(lines=ldLines, doc=doc, firstLine=ldLines[0], tagName="pre", lineNum=None)

            # Get local anchor data
            shouldGetLocalAnchorData = doc.md.externalInfotrees["anchors.bsdata"]
            if not shouldGetLocalAnchorData and doc.inputSource.cheaplyExists("anchors.bsdata"):
                m.warn(
                    "Found anchors.bsdata next to the specification without a matching\n"
                    + "External Infotrees: anchors.bsdata yes\n"
                    + "in the metadata. This data won't be found when building via a URL.",
                )
                # We should remove this after giving specs time to react to the warning:
                shouldGetLocalAnchorData = True
            if shouldGetLocalAnchorData:
                try:
                    anchorFile = doc.inputSource.relative("anchors.bsdata")
                    if not anchorFile:
                        raise OSError
                    anchorLines = anchorFile.read().rawLines
                    datablocks.transformAnchors(
                        lines=anchorLines,
                        doc=doc,
                        firstLine=anchorLines[0],
                        tagName="pre",
                        lineNum=None,
                    )
                except OSError:
                    m.warn("anchors.bsdata not found despite being listed in the External Infotrees metadata.")

            # Get local link defaults
            shouldGetLocalLinkDefaults = doc.md.externalInfotrees["link-defaults.infotree"]
            if not shouldGetLocalLinkDefaults and doc.inputSource.cheaplyExists("link-defaults.infotree"):
                m.warn(
                    "Found link-defaults.infotree next to the specification without a matching\n"
                    + "External Infotrees: link-defaults.infotree yes\n"
                    + "in the metadata. This data won't be found when building via a URL.",
                )
                # We should remove this after giving specs time to react to the warning:
                shouldGetLocalLinkDefaults = True
            if shouldGetLocalLinkDefaults:
                try:
                    ldFile = doc.inputSource.relative("link-defaults.infotree")
                    if not ldFile:
                        raise OSError
                    ldLines = ldFile.read().rawLines
                    datablocks.transformInfo(
                        lines=ldLines,
                        doc=doc,
                        firstLine=ldLines[0],
                        tagName="pre",
                        lineNum=None,
                    )
                except OSError:
                    m.warn("link-defaults.infotree not found despite being listed in the External Infotrees metadata.")

    def fetchHeadings(self, spec: str) -> headingdata.SpecHeadings:
        if spec in self.headings:
            return self.headings[spec]
        with self.dataFile.fetch("headings", f"headings-{spec}.json", okayToFail=True) as fh:
            try:
                data = json.load(fh)
            except ValueError:
                # JSON couldn't be decoded, *should* only be because of empty file
                data = {}
            specHeadings = headingdata.SpecHeadings(spec, data)
            self.headings[spec] = specHeadings
            return specHeadings

    def fetchHeading(
        self,
        spec: str,
        id: str,
        status: str | None = None,
        el: t.ElementT | None = None,
    ) -> dict[str, str] | None:
        specHeadings = self.fetchHeadings(spec)
        if status is None:
            status = self.defaultStatus
        return specHeadings.get(id, status, el)

    def initializeBiblio(self) -> None:
        self.biblioKeys.update(json.loads(self.dataFile.fetch("biblio-keys.json", str=True)))
        self.biblioNumericSuffixes.update(json.loads(self.dataFile.fetch("biblio-numeric-suffixes.json", str=True)))

        # Get local bibliography data
        try:
            storage: t.BiblioStorageT = defaultdict(list)
            with open("biblio.json", encoding="utf-8") as fh:
                biblio.processSpecrefBiblioFile(fh.read(), storage, order=2)
        except OSError:
            # Missing file is fine
            pass
        for k, vs in storage.items():
            self.biblioKeys.add(k)
            self.biblios[k].extend(vs)

        # Hardcode RFC2119, used in most spec's boilerplates,
        # to avoid having to parse the entire biblio-rf.data file for this single reference.
        self.biblioKeys.add("rfc2119")
        self.biblios["rfc2119"].append(
            biblio.NormalBiblioEntry(
                linkText="rfc2119",
                date="March 1997",
                status="Best Current Practice",
                title="Key words for use in RFCs to Indicate Requirement Levels",
                snapshotURL="https://datatracker.ietf.org/doc/html/rfc2119",
                order=3,
                authors=["S. Bradner"],
            ),
        )

    def setSpecData(self, doc: t.SpecT) -> None:
        if doc.md.defaultRefStatus:
            self.defaultStatus = doc.md.defaultRefStatus
        elif doc.doctype.status:
            if "TR" in doc.doctype.status.requires:
                self.defaultStatus = constants.refStatus.snapshot
            else:
                self.defaultStatus = constants.refStatus.current
        self.shortname = doc.md.shortname
        self.specLevel = doc.md.level
        self.spec = doc.md.vshortname

        for term, defaults in doc.md.linkDefaults.items():
            for default in defaults:
                self.defaultSpecs[term].append(default)

        # Need to get a real versioned shortname,
        # with the possibility of overriding the "shortname-level" pattern.
        self.removeSameSpecRefs()

    def removeSameSpecRefs(self) -> None:
        # Kill all the non-local anchors with the same shortname as the current spec,
        # so you don't end up accidentally linking to something that's been removed from the local copy.
        # TODO: This is dumb.
        for _, refs in self.foreignRefs.refs.items():
            for ref in refs:
                if ref.status != "local" and ref.shortname.rstrip() == self.shortname:
                    ref._ref["export"] = False  # pylint: disable=protected-access

    def addLocalDfns(self, doc: t.SpecT, dfns: t.Iterable[t.ElementT]) -> None:
        for el in dfns:
            if h.hasClass(doc, el, "no-ref"):
                continue
            elId = el.get("id")
            assert elId is not None
            try:
                linkTexts = h.linkTextsFromElement(el)
            except h.DuplicatedLinkText as e:
                m.die(
                    f"The term '{e.offendingText}' is in both lt and local-lt of the element {h.outerHTML(e.el)}.",
                    el=e.el,
                )
                linkTexts = e.allTexts
            for linkText in linkTexts:
                linkText = h.unfixTypography(linkText)
                linkText = re.sub(r"\s+", " ", linkText)
                linkType = h.treeAttr(el, "data-dfn-type")
                if linkType not in config.dfnTypes:
                    m.die(f"Unknown local dfn type '{linkType}':\n  {h.outerHTML(el)}", el=el)
                    continue
                if linkType in config.lowercaseTypes:
                    linkText = linkText.lower()
                dfnForAttr = h.treeAttr(el, "data-dfn-for")
                if dfnForAttr is None:
                    dfnFor: set[str] = set()
                    existingRefs = self.localRefs.queryRefs(linkType=linkType, text=linkText, linkFor="/", exact=True)[
                        0
                    ]
                    if existingRefs and existingRefs[0].el is not el:
                        m.die(f"Multiple local '{linkType}' <dfn>s have the same linking text '{linkText}'.", el=el)
                        continue
                else:
                    dfnFor = set(config.splitForValues(dfnForAttr))
                    encounteredError = False
                    for singleFor in dfnFor:
                        existingRefs = self.localRefs.queryRefs(
                            linkType=linkType,
                            text=linkText,
                            linkFor=singleFor,
                            exact=True,
                        )[0]
                        if existingRefs and existingRefs[0].el is not el:
                            encounteredError = True
                            m.die(
                                f"Multiple local '{linkType}' <dfn>s for '{singleFor}' have the same linking text '{linkText}'.",
                                el=el,
                            )
                            break
                    if encounteredError:
                        continue
                for term in dfnFor.copy():
                    # Saying a value is for a descriptor with @foo/bar
                    # should also make it for the bare descriptor bar.
                    match = re.match(r"@[a-zA-Z0-9-_]+/(.*)", term)
                    if match:
                        dfnFor.add(match.group(1).strip())
                # convert back into a list now, for easier JSONing
                dfnForList = sorted(dfnFor)
                refKey, displayKey = config.adjustKey(linkText, linkType)
                ref = wrapper.RefWrapper(
                    refKey,
                    displayKey,
                    {
                        "type": linkType,
                        "status": "local",
                        "spec": self.spec,
                        "shortname": self.shortname,
                        "level": self.specLevel,
                        "url": "#" + elId,
                        "export": True,
                        "normative": True,
                        "for_": dfnForList,
                        "el": el,
                    },
                )
                self.localRefs.refs[linkText].append(ref)
                for for_ in dfnFor:
                    self.localRefs.fors[for_].append(linkText)
                methodishStart = re.match(r"([^(]+\()[^)]", linkText)
                if methodishStart:
                    self.localRefs.addMethodVariants(linkText, dfnForList, ref.shortname)

    def filterObsoletes(self, refs: list[RefWrapper]) -> list[RefWrapper]:
        return utils.filterObsoletes(
            refs,
            replacedSpecs=self.replacedSpecs,
            ignoredSpecs=self.ignoredSpecs,
            localShortname=self.shortname,
            localSpec=self.spec,
        )

    def queryAllRefs(self, **kwargs: t.Any) -> list[RefWrapper]:
        r1, _ = self.localRefs.queryRefs(**kwargs)
        r2, _ = self.anchorBlockRefs.queryRefs(**kwargs)
        r3, _ = self.foreignRefs.queryRefs(**kwargs)
        refs = r1 + r2 + r3
        if kwargs.get("ignoreObsoletes") is True:
            refs = self.filterObsoletes(refs)
        return refs

    def getRef(
        self,
        linkType: str,
        text: str,
        spec: str | None = None,
        status: str | None = None,
        statusHint: str | None = None,
        linkFor: str | list[str] | None = None,
        explicitFor: bool = False,
        linkForHint: str | None = None,
        error: bool = True,
        el: t.ElementT | None = None,
    ) -> RefWrapper | None:
        # If error is False, this function just shuts up and returns a reference or None
        # Otherwise, it pops out debug messages for the user.

        # 'maybe' links might not link up, so it's fine for them to have no references.
        # The relevent errors are gated by this variable.
        zeroRefsError = error and linkType not in ["maybe", "extended-attribute"]

        text = h.unfixTypography(text)
        if linkType in config.lowercaseTypes:
            text = text.lower()
        if spec is not None:
            spec = spec.lower()
        if statusHint is None:
            statusHint = self.defaultStatus
        if status not in config.linkStatuses and status is not None:
            if error:
                m.die(
                    f"Unknown spec status '{status}'. Status must be {config.englishFromList(config.linkStatuses)}.",
                    el=el,
                )
            return None

        # Local refs always get precedence, unless you manually specified a spec.
        if spec is None:
            localRefs, _ = self.localRefs.queryRefs(
                linkType=linkType,
                text=text,
                linkFor=linkFor,
                linkForHint=linkForHint,
                explicitFor=explicitFor,
                el=el,
            )
            # If the autolink was for-less, it found a for-full local link,
            # but there was a for-less version in a foreign spec,
            # emit a warning (unless it was supressed).
            if localRefs and linkFor is None and any(x.for_ for x in localRefs):
                forlessRefs, _ = self.anchorBlockRefs.queryRefs(
                    linkType=linkType,
                    text=text,
                    linkFor="/",
                    export=True,
                    el=el,
                )
                forlessRefs = self.filterObsoletes(forlessRefs)
                if not forlessRefs:
                    forlessRefs, _ = self.foreignRefs.queryRefs(
                        linkType=linkType,
                        text=text,
                        linkFor="/",
                        export=True,
                        el=el,
                    )
                forlessRefs = self.filterObsoletes(forlessRefs)
                if forlessRefs:
                    reportAmbiguousForlessLink(el, text, forlessRefs, localRefs)
                    return None
            if len(localRefs) == 1:
                return localRefs[0]
            elif len(localRefs) > 1:
                if self.testing:
                    # Generate a stable answer
                    chosenRef = sorted(localRefs, key=lambda x: x.url)[0]
                else:
                    # CHAOS MODE (so you're less likely to rely on it)
                    chosenRef = random.choice(localRefs)  # noqa: S311
                if error:
                    m.linkerror(
                        f"Multiple possible '{linkType}' local refs for '{text}'.\nRandomly chose one of them; other instances might get a different random choice.",
                        el=el,
                    )
                return chosenRef

        if status == "local":
            # Already checked local refs, can early-exit now.
            return None

        # Take defaults into account
        if not spec or not status or not linkFor:
            variedTexts = [v for v in utils.linkTextVariations(text, linkType) if v in self.defaultSpecs]
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
        blockRefs, _ = self.anchorBlockRefs.queryRefs(
            linkType=linkType,
            text=text,
            spec=spec,
            linkFor=linkFor,
            linkForHint=linkForHint,
            explicitFor=explicitFor,
            el=el,
        )
        if blockRefs and linkFor is None and any(x.for_ for x in blockRefs):
            forlessRefs, _ = self.foreignRefs.queryRefs(linkType=linkType, text=text, linkFor="/", export=True, el=el)
            forlessRefs = self.filterObsoletes(forlessRefs)
            if forlessRefs:
                reportAmbiguousForlessLink(el, text, forlessRefs, blockRefs)
                return None
        if len(blockRefs) == 1:
            return blockRefs[0]
        elif len(blockRefs) > 1:
            reportMultiplePossibleRefs(
                simplifyPossibleRefs(blockRefs),
                linkText=text,
                linkType=linkType,
                linkFor=linkFor,
                defaultRef=blockRefs[0],
                el=el,
            )
            return blockRefs[0]

        # Get the relevant refs
        if spec is None:
            export = True
        else:
            export = None
        refs, failure = self.foreignRefs.queryRefs(
            text=text,
            linkType=linkType,
            spec=spec,
            status=status,
            statusHint=statusHint,
            linkFor=linkFor,
            linkForHint=linkForHint,
            explicitFor=explicitFor,
            export=export,
            ignoreObsoletes=True,
        )

        if (
            failure
            and linkType in ("argument", "idl")
            and linkFor is not None
            and any(x.endswith("()") for x in linkFor)
        ):
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
                possibleMethodsDict: defaultdict[str, list[str]] = defaultdict(list)
                for variant in methodSignatures.variants.values():
                    if (
                        text in variant.args
                        and (interfaceName in variant.for_ or interfaceName is None)
                        and variant.shortname != self.shortname
                    ):
                        possibleMethodsDict[variant.shortname or ""].append(variant.signature)
                possibleMethods = list(possibleMethodsDict.values())
                if not possibleMethods:
                    # No method signatures with this argument/interface.
                    # Jump out and fail in a normal way.
                    break
                if len(possibleMethods) > 1:
                    # Too many to disambiguate.
                    m.linkerror(
                        f"The argument autolink '{text}' for '{linkFor}' has too many possible overloads to disambiguate. Please specify the full method signature this argument is for.",
                        el=el,
                    )
                # Try out all the combinations of interface/status/signature
                linkForPatterns = ["{interface}/{method}", "{method}"]
                statuses = ["local", status]
                for p in linkForPatterns:
                    for s in statuses:
                        for method in possibleMethods[0]:
                            refs, failure = self.foreignRefs.queryRefs(
                                text=text,
                                linkType=linkType,
                                spec=spec,
                                status=s,
                                linkFor=p.format(interface=interfaceName, method=method),
                                ignoreObsoletes=True,
                            )
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
                c1, _ = self.anchorBlockRefs.queryRefs(
                    linkType="functionish",
                    spec=spec,
                    status=status,
                    statusHint=statusHint,
                    linkFor=interfaceName,
                    export=export,
                    ignoreObsoletes=True,
                )
                c2, _ = self.foreignRefs.queryRefs(
                    linkType="functionish",
                    spec=spec,
                    status=status,
                    statusHint=statusHint,
                    linkFor=interfaceName,
                    export=export,
                    ignoreObsoletes=True,
                )
                candidates = c1 + c2
                methodRefs = list({c.url: c for c in candidates if c.text.startswith(methodPrefix)}.values())
            if zeroRefsError and len(methodRefs) > 1:
                # More than one possible foo() overload, can't tell which to link to
                m.linkerror(
                    f"Too many possible method targets to disambiguate '{linkFor}/{text}'. Please specify the names of the required args, like 'foo(bar, baz)', in the 'for' attribute.",
                    el=el,
                )
                return None
            # Otherwise

        if failure in ("text", "type"):
            if linkType in ("property", "propdesc", "descriptor") and text.startswith("--"):
                # Custom properties/descriptors aren't ever defined anywhere
                return None
            if zeroRefsError:
                m.linkerror(f"No '{linkType}' refs found for '{text}'.", el=el)
            return None
        elif failure == "export":
            if zeroRefsError:
                m.linkerror(f"No '{linkType}' refs found for '{text}' that are marked for export.", el=el)
            return None
        elif failure == "spec":
            if zeroRefsError:
                m.linkerror(f"No '{linkType}' refs found for '{text}' with spec '{spec}'.", el=el)
            return None
        elif failure == "for":
            if zeroRefsError:
                if spec is None:
                    m.linkerror(f"No '{linkType}' refs found for '{text}' with for='{linkFor}'.", el=el)
                else:
                    m.linkerror(
                        f"No '{linkType}' refs found for '{text}' with for='{linkFor}' in spec '{spec}'.",
                        el=el,
                    )
            return None
        elif failure == "status":
            if zeroRefsError:
                if spec is None:
                    m.linkerror(f"No '{linkType}' refs found for '{text}' compatible with status '{status}'.", el=el)
                else:
                    m.linkerror(
                        f"No '{linkType}' refs found for '{text}' compatible with status '{status}' in spec '{spec}'.",
                        el=el,
                    )
            return None
        elif failure == "ignored-specs":
            if zeroRefsError:
                m.linkerror(f"The only '{linkType}' refs for '{text}' were in ignored specs:\n{h.outerHTML(el)}", el=el)
            return None
        elif failure:
            m.die(f"Programming error - I'm not catching '{failure}'-type link failures. Please report!", el=el)
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
            reportMultiplePossibleRefs(
                simplifyPossibleRefs(refs),
                linkText=text,
                linkType=linkType,
                linkFor=linkFor,
                defaultRef=defaultRef,
                el=el,
            )
        return defaultRef

    def getBiblioRef(
        self,
        text: str,
        status: str | None = None,
        generateFakeRef: bool = False,
        allowObsolete: bool = False,
        el: t.ElementT | None = None,
        quiet: bool = False,
        depth: int = 0,
    ) -> biblio.BiblioEntry | None:
        if depth > 100:
            m.die(f"Data error in biblio files; infinitely recursing trying to find [{text}].")
            return None
        key = text.lower()
        if status is None:
            status = self.defaultStatus
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
                return biblio.SpecBiblioEntry(spec, preferredStatus=status)

            if failFromWrongSuffix and not quiet:
                numericSuffixes = self.biblioNumericSuffixes[unversionedKey]
                m.die(
                    f"A biblio link references {text}, but only {config.englishFromList(numericSuffixes)} exists in SpecRef.",
                )
            return None

        bib: biblio.BiblioEntry = self._bestCandidateBiblio(candidates)
        # TODO: When SpecRef definitely has all the CSS specs, turn on this code.
        # if candidates[0].order > 3: # 3 is SpecRef level
        #    m.warn(f"Bibliography term '{text}' wasn't found in SpecRef.\n         Please find the equivalent key in SpecRef, or submit a PR to SpecRef.")
        if isinstance(bib, biblio.AliasBiblioEntry):
            # Follow the chain to the real candidate
            newBib = self.getBiblioRef(bib.aliasOf, status=status, el=el, quiet=True, depth=depth + 1)
            if newBib is None:
                if not quiet:
                    m.die(f"Biblio ref [{text}] claims to be an alias of [{bib.aliasOf}], which doesn't exist.")
                return None
            else:
                bib = newBib
        elif bib.obsoletedBy:
            # Obsoleted by something. Unless otherwise indicated, follow the chain.
            if allowObsolete:
                pass
            else:
                newBib = self.getBiblioRef(
                    bib.obsoletedBy,
                    status=status,
                    el=el,
                    quiet=True,
                    depth=depth + 1,
                )
                if newBib is None:
                    if not quiet:
                        m.die(
                            f"[{bib.linkText}] claims to be obsoleted by [{bib.obsoletedBy}], which doesn't exist. Either change the reference, of use [{bib.linkText} obsolete] to ignore the obsoletion chain.",
                        )
                    return None
                if not quiet:
                    m.linkerror(
                        f"Obsolete biblio ref: [{bib.linkText}] is replaced by [{newBib.linkText}]. Either update the reference, or use [{bib.linkText} obsolete] if this is an intentionally-obsolete reference.",
                    )
                bib = newBib

        # If a canonical name has been established, use it.
        if bib.linkText in self.preferredBiblioNames:
            bib.originalLinkText, bib.linkText = (
                bib.linkText,
                self.preferredBiblioNames[bib.linkText],
            )

        bib.preferredStatus = status
        return bib

    def bibliosFromKey(self, key: str) -> list[biblio.BiblioEntry]:
        # Load up the biblio data necessary to fetch the given key
        # and then actually fetch it.
        # If you don't call this,
        # the current data might not be reliable.
        if key not in self.biblios:
            # Try to load the group up, if necessary
            group = key[0:2]
            if group not in self.loadedBiblioGroups:
                with self.dataFile.fetch("biblio", f"biblio-{group}.data", okayToFail=True) as fh:
                    biblio.loadBiblioDataFile(fh, self.biblios)
            self.loadedBiblioGroups.add(group)
        return self.biblios.get(key, [])

    def _bestCandidateBiblio(self, candidates: list[biblio.BiblioEntry]) -> biblio.BiblioEntry:
        return sorted(candidates, key=lambda x: x.order or 0)[0].strip()

    def getLatestBiblioRef(self, key: str) -> biblio.BiblioEntry | None:
        # Takes a biblio reference name,
        # returns the latest dated variant of that name
        # (names in the form FOO-19700101)
        candidates = self.bibliosFromKey(key)
        if not candidates:
            return None
        latestDate = None
        latestRefs = None
        for k, biblios in self.biblios.items():
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
        return self._bestCandidateBiblio(latestRefs)

    def vNamesFromSpecNames(self, specName: str) -> list[str]:
        # Takes an unversioned specName,
        # returns the versioned names that Shepherd knows about.

        chosenVNames = []
        for vSpecName in self.specs:
            if not vSpecName.startswith(specName):
                continue
            match = re.match(r"-?(\d+)", vSpecName[len(specName) :])
            if match is None:
                continue
            chosenVNames.append(vSpecName)
        return chosenVNames


def simplifyPossibleRefs(refs: list[RefWrapper], alwaysShowFor: bool = False) -> list[SimplifiedRef]:
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
            for for_, url in fors:
                retRefs.append(SimplifiedRef(text=text, type=type, spec=spec, for_=for_, url=url))
        else:
            retRefs.append(
                SimplifiedRef(
                    text=text,
                    type=type,
                    spec=spec,
                    for_=None,
                    url=fors[0][1],
                ),
            )
    return retRefs


@dataclasses.dataclass
class SimplifiedRef:
    text: str
    type: str
    spec: str
    for_: str | None
    url: str


def refToText(ref: SimplifiedRef) -> str:
    if ref.for_ is not None:
        return f"spec:{ref.spec}; type:{ref.type}; for:{ref.for_}; text:{ref.text}"
    else:
        return f"spec:{ref.spec}; type:{ref.type}; text:{ref.text}"


def reportMultiplePossibleRefs(
    possibleRefs: t.Sequence[SimplifiedRef],
    linkText: str,
    linkType: str,
    linkFor: str | list[str] | None,
    defaultRef: RefWrapper,
    el: t.ElementT | None,
) -> None:
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
        error = f"Multiple possible '{linkText}' {linkType} refs for '{linkFor}'."
    else:
        error = f"Multiple possible '{linkText}' {linkType} refs."
    error += f"\nArbitrarily chose {defaultRef.url}"
    if uniqueRefs:
        error += "\nTo auto-select one of the following refs, insert one of these lines into a <pre class=link-defaults> block:\n"
        error += "\n".join(refToText(r) for r in uniqueRefs)
    if mergedRefs:
        error += "\nThe following refs show up multiple times in their spec, in a way that Bikeshed can't distinguish between. Either create a manual link, or ask the spec maintainer to add disambiguating attributes (usually a for='' attribute to all of them)."
        for refs in mergedRefs:
            error += "\n" + refToText(refs[0])
            for ref in refs:
                error += "\n  " + ref.url
    m.linkerror(error, el=el)


def reportAmbiguousForlessLink(
    el: t.ElementT | None,
    text: str,
    forlessRefs: list[RefWrapper],
    localRefs: list[RefWrapper],
) -> None:
    localRefText = "\n".join([refToText(ref) for ref in simplifyPossibleRefs(localRefs, alwaysShowFor=True)])
    forlessRefText = "\n".join([refToText(ref) for ref in simplifyPossibleRefs(forlessRefs, alwaysShowFor=True)])
    m.linkerror(
        f"Ambiguous for-less link for '{text}', please see <https://speced.github.io/bikeshed/#ambi-for> for instructions:\nLocal references:\n{localRefText}\nfor-less references:\n{forlessRefText}",
        el=el,
    )
