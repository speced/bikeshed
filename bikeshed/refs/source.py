from __future__ import annotations

import copy
import dataclasses
import re
from collections import defaultdict

from .. import config, constants, retrieve, t
from .. import messages as m
from . import utils
from .ref import Ref
from .utils import LinkFailure

# Which sources use lazy-loading; other sources always have all their refs loaded immediately.
LAZY_LOADED_SOURCES: list[str] = ["foreign"]


class RefSource:
    __slots__ = [
        "_loadedAnchorGroups",
        "dataFile",
        "fors",
        "ignoredSpecs",
        "methods",
        "refs",
        "replacedSpecs",
        "source",
        "specs",
    ]

    def __init__(
        self,
        source: str,
        specs: dict[str, dict[str, str]] | None = None,
        ignored: set[str] | None = None,
        replaced: set[tuple[str, str]] | None = None,
        fileRequester: t.DataFileRequester | None = None,
    ) -> None:
        """Initialize a reference source with storage for refs, methods, specs, and anchor groups."""
        # Requester used to retrieve data files.
        if fileRequester is None:
            self.dataFile = retrieve.defaultRequester
        else:
            self.dataFile = fileRequester

        # String identifying which refsource this is.
        self.source = source

        # Dict of {linking text => [anchor data]}
        self.refs: defaultdict[str, list[t.Ref]] = defaultdict(list)

        # Dict of {argless method signatures => {"argfull signature": {"args":[args], "for":[fors]}}}
        self.methods: dict[str, MethodVariants] = {}

        # Dict of {for value => [terms]}
        self.fors: defaultdict[str, list[str]] = defaultdict(list)

        # Dict of {spec name => {metadata}}
        self.specs: dict[str, dict[str, str]] = {} if specs is None else specs

        # Set of spec names to ignore when querying refs
        self.ignoredSpecs = set() if ignored is None else ignored

        # Set of (oldSpec, newSpec) tuples where oldSpec is replaced by newSpec
        self.replacedSpecs = set() if replaced is None else replaced

        # Dict of {group name => AnchorGroup}
        self._loadedAnchorGroups: dict[str, AnchorGroup] = {}

    def fetchRefs(self, key: str) -> list[t.Ref]:
        """Safe, lazy-loading version of self.refs[key]"""

        if (refs := self.refs.get(key)) is not None:
            return refs

        if self.source not in LAZY_LOADED_SOURCES:
            return []

        return self.loadRefsFromKey(key)

    def loadRefsFromKey(self, key: str) -> list[t.Ref]:
        """Grabs the anchor group, loading it if necessary, then does a lazy decode of the requested ref, caching it before returning."""
        group = groupFromKey(key)
        anchorGroup = self._loadedAnchorGroups.get(group)
        if anchorGroup is None:
            raw = self.dataFile.fetch("anchors", f"anchors-{group}.data", str=True, okayToFail=True)
            anchorGroup = AnchorGroup(raw)
            self._loadedAnchorGroups[group] = anchorGroup
        refs = anchorGroup.decodeRefs(key)
        self.refs[key] = refs
        return refs

    def fetchAllRefs(self) -> list[tuple[str, list[t.Ref]]]:
        """Nuts to lazy-loading, just load everything at once."""

        if self.source not in LAZY_LOADED_SOURCES:
            return list(self.refs.items())

        for file in self.dataFile.walkFiles("anchors"):
            match = re.match(r"anchors-(.{2})", file)
            if not match:
                m.warn(f"Ignoring a data file in the /anchors folder with a weird name: '{file}'")
                continue
            group = match[1]
            if (anchorGroup := self._loadedAnchorGroups.get(group)) is not None and anchorGroup.empty:
                # Already loaded
                continue
            with self.dataFile.fetch("anchors", file) as fh:
                # Directly decode and cache all the anchors...
                self.refs.update(decodeAnchors(fh))
                # So insert dummy empty AnchorGroups so misses won't try to load again.
                self._loadedAnchorGroups[group] = AnchorGroup("")
        return [item for item in self.refs.items() if item[1]]

    def queryRefs(
        self,
        *,
        text: str | None = None,
        spec: str | None = None,
        linkType: str | None = None,
        linkFor: str | list[str] | None = None,
        explicitFor: bool = False,
        linkForHint: str | None = None,
        status: str | None = None,
        statusHint: str | None = None,
        export: bool | None = None,
        ignoreObsoletes: bool = False,
        latestOnly: bool = True,
        dedupURLs: bool = True,
        exact: bool | None = None,
        error: bool = False,
        el: t.ElementT | None = None,
    ) -> tuple[list[t.Ref], LinkFailure | None, list[t.Ref]]:
        """Query refs by criteria, trying an exact match first and falling back to conjugating."""
        if exact is not None:
            return self._queryRefs(
                text=text,
                spec=spec,
                linkType=linkType,
                linkFor=linkFor,
                explicitFor=explicitFor,
                linkForHint=linkForHint,
                status=status,
                statusHint=statusHint,
                export=export,
                ignoreObsoletes=ignoreObsoletes,
                latestOnly=latestOnly,
                dedupURLs=dedupURLs,
                error=error,
                el=el,
                exact=exact,
            )
        else:
            # First search for the exact term, and only if it fails fall back to conjugating.
            results, linkFailure, _ = self._queryRefs(
                text=text,
                spec=spec,
                linkType=linkType,
                linkFor=linkFor,
                explicitFor=explicitFor,
                linkForHint=linkForHint,
                status=status,
                statusHint=statusHint,
                export=export,
                ignoreObsoletes=ignoreObsoletes,
                latestOnly=latestOnly,
                dedupURLs=dedupURLs,
                error=error,
                el=el,
                exact=True,
            )
            if linkFailure:
                return self._queryRefs(
                    text=text,
                    spec=spec,
                    linkType=linkType,
                    linkFor=linkFor,
                    explicitFor=explicitFor,
                    linkForHint=linkForHint,
                    status=status,
                    statusHint=statusHint,
                    export=export,
                    ignoreObsoletes=ignoreObsoletes,
                    latestOnly=latestOnly,
                    dedupURLs=dedupURLs,
                    error=error,
                    el=el,
                    exact=False,
                )
            else:
                return results, None, []

    def allRefsIterator(self) -> t.Generator[t.Ref, None, None]:
        """Yield all Ref objects across all loaded anchor groups."""
        for _, group in self.fetchAllRefs():
            yield from group

    def textRefsIterator(self, texts: list[str]) -> t.Generator[t.Ref, None, None]:
        """Yield Ref objects keyed to any of the specified link texts."""
        for x in texts:
            yield from self.fetchRefs(x)

    def forRefsIterator(self, targetFors: str | list[str]) -> t.Generator[t.Ref, None, None]:
        """Yield Ref objects associated with the given 'for' context(s)."""
        if isinstance(targetFors, str):
            targetFors = [targetFors]
        for for_ in targetFors:
            for x in self.fors[for_]:
                yield from self.fetchRefs(x)

    def _queryRefs(
        self,
        *,
        text: str | None = None,
        spec: str | None = None,
        linkType: str | None = None,
        linkFor: str | list[str] | None = None,
        explicitFor: bool = False,
        linkForHint: str | None = None,
        status: str | None = None,
        statusHint: str | None = None,
        export: bool | None = None,
        ignoreObsoletes: bool = False,
        latestOnly: bool = True,
        dedupURLs: bool = True,
        exact: bool = False,
        error: bool = False,
        el: t.ElementT | None = None,
    ) -> tuple[list[t.Ref], LinkFailure | None, list[t.Ref]]:
        """Query the ref database against filtering criteria; if no match is found, return the failure stage."""

        # Set up the initial list of refs to query
        if text:
            if exact:
                refs = list(self.textRefsIterator([text]))
            else:
                textsToSearch = list(utils.linkTextVariations(text, linkType))

                if any(st.endswith("()") for st in textsToSearch):
                    # Let argless methods (either with () at the end, or no parens at all)
                    # pull in their argful variants for searching.
                    for st in textsToSearch[:]:
                        textsToSearch += getArgfulMethodVariants(st, self)

                if (linkType is None or linkType in config.lowercaseTypes) and text.lower() != text:
                    textsToSearch += [t.lower() for t in textsToSearch]
                refs = list(self.textRefsIterator(textsToSearch))
        elif linkFor:
            refs = list(self.forRefsIterator(linkFor))
        else:
            refs = list(self.allRefsIterator())
        if not refs:
            return [], LinkFailure.Text, []

        oldRefs = refs
        if linkType:
            if linkType in config.dfnTypes:
                linkTypes = [linkType]
            elif linkType in config.linkTypeToDfnType:
                linkTypes = list(config.linkTypeToDfnType[linkType])
            else:
                if error:
                    m.linkerror(f"Unknown link type '{linkType}'.", el=el)
                return [], LinkFailure.Type, []
            refs = [x for x in refs if x.type in linkTypes]
        if not refs:
            return [], LinkFailure.Type, oldRefs

        oldRefs = refs
        if export is not None:
            refs = [x for x in refs if x.export == export]
        if not refs:
            return [], LinkFailure.Export, oldRefs

        oldRefs = refs
        if spec:
            refs = [x for x in refs if spec in (x.spec, x.shortname)]
        if not refs:
            return [], LinkFailure.Spec, oldRefs

        """
        for=A | forHint=B | explicitFor
        ✘ | ✘ | ✘ = anything
        ✘ | ✘ | ✔ = /
        ✘ | ✔ | ✘ = B/, fallback to anything
        ✘ | ✔ | ✔ = B/, fallback to /
        ✔ | ✘ | ✘ = A/
        ✔ | ✘ | ✔ = A/
        ✔ | ✔ | ✘ = A/
        ✔ | ✔ | ✔ = A/
        """

        oldRefs = refs
        if linkFor:
            refs = filterByFor(refs, linkFor)
        elif linkForHint:
            if explicitFor:
                tempRefs = filterByFor(refs, linkForHint)
                if not tempRefs:
                    tempRefs = filterByFor(refs, "/")
                refs = tempRefs
            else:
                # Handled later, in the "just a hint" section.
                pass
        elif explicitFor:
            refs = filterByFor(refs, "/")
        if not refs:
            return [], LinkFailure.For, oldRefs

        oldRefs = refs
        if status:
            refs = filterByStatus(self, refs, status)
        if not refs:
            return [], LinkFailure.Status, refs

        if status is None and statusHint:
            tempRefs = filterByStatus(self, refs, statusHint)
            if tempRefs:
                refs = tempRefs

        if linkForHint and not linkFor and not explicitFor:
            tempRefs = filterByFor(refs, linkForHint)
            if tempRefs:
                refs = tempRefs

        oldRefs = refs
        if ignoreObsoletes and not spec:
            # Remove any ignored or obsoleted specs
            # If you specified the spec, don't filter things - you know what you're doing.
            refs = utils.filterObsoletes(refs, replacedSpecs=self.replacedSpecs, ignoredSpecs=self.ignoredSpecs)
        if not refs:
            return [], LinkFailure.IgnoredSpecs, oldRefs

        if dedupURLs:
            # With non-exact texts, you might have multiple "anchors"
            # that point to the same url. Dedup them.
            seenUrls = set()
            tempRefs = []
            # Sort the refs so the kept one doesn't depend on ordering in the RefSource dict.
            for ref in sorted(copy.copy(refs), key=lambda x: x.text):
                if ref.url not in seenUrls:
                    tempRefs.append(ref)
                    seenUrls.add(ref.url)
            refs = tempRefs

        if latestOnly:
            # If multiple levels of the same shortname exist,
            # only use the latest level.
            # If generating for a snapshot, prefer the latest snapshot level,
            # unless that doesn't exist, in which case just prefer the latest level.
            refs = utils.filterOldVersions(refs, status=status or statusHint)

        return refs, None, []

    def addMethodVariants(self, methodSig: str, forVals: t.Iterable[str], shortname: str | None) -> None:
        """Parse a full method signature like 'foo(bar)' and record its variant details under self.methods."""
        match = re.match(r"([^(]+)\((.*)\)", methodSig)
        if not match:
            # Was fed something that's not a method signature.
            return None
        name, args = match.groups()
        arglessMethodSig = name + "()"
        if arglessMethodSig not in self.methods:
            self.methods[arglessMethodSig] = MethodVariants(arglessMethodSig, {})
        variants = self.methods[arglessMethodSig].variants
        if methodSig not in variants:
            args = [x.strip() for x in args.split(",")]
            variants[methodSig] = MethodVariant(signature=methodSig, args=args, for_=[], shortname=shortname)
        variants[methodSig].for_.extend(forVals)


def filterByFor(refs: t.Sequence[t.Ref], linkFor: str | list[str]) -> list[t.Ref]:
    """Filter refs to those matching the given 'for' target(s)."""
    return [x for x in refs if matchFor(x.for_, linkFor)]


def matchFor(forVals: list[str], forTest: str | list[str]) -> bool:
    """Test whether any value in forVals matches forTest ('/' matches an empty for list)."""
    if forTest == "/":
        return not bool(forVals)
    if isinstance(forTest, str):
        return forTest in forVals
    return any(matchFor(forVals, ft) for ft in forTest)


def filterByStatus(source: RefSource, refs: t.Sequence[t.Ref], status: str) -> list[t.Ref]:
    """Filter refs by specification status (e.g. current vs. snapshot or local)."""
    if status in constants.refStatus:
        # If status is "current'", kill snapshot refs unless their spec *only* has a snapshot_url
        if status == constants.refStatus.current:
            return [
                ref
                for ref in refs
                if ref.status == "current"
                or (ref.status == "snapshot" and source.specs.get(ref.spec, {}).get("current_url") is None)
            ]
        # If status is "snapshot", kill current refs if there's a corresponding snapshot ref for the same spec.
        elif status == constants.refStatus.snapshot:
            snapshotSpecs = [ref.spec for ref in refs if ref.status == "snapshot"]
            return [
                ref
                for ref in refs
                if ref.status == "snapshot" or (ref.status == "current" and ref.spec not in snapshotSpecs)
            ]
    # Status is a non-refStatus, but is a valid linkStatus, like "local"
    elif status in config.linkStatuses:
        return [x for x in refs if x.status == status]

    msg = f"Status value of '{status}' not handled"
    raise Exception(msg)


# Initially we just do a search on the raw text,
# but after enough queries in a group, we pay the
# tax of indexing to make future queries faster.
QUERY_INDEX_SWITCHOVER = 6

# Each entry is separated by a line containing just a single -
ENTRY_SEPARATOR = "\n-\n"

# The minimum entry is 10 lines long. "For" values can make it longer.
MINIMUM_ENTRY_LINES = 10


def groupFromKey(key: str, length: int = 2) -> str:
    """Generates a filename-safe "group" from a key, of a specified length."""
    if key in GROUP_FROM_KEY_CACHE:
        return GROUP_FROM_KEY_CACHE[key]
    safeChars = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
    group = ""
    for char in key.lower():
        if len(group) == length:
            GROUP_FROM_KEY_CACHE[key] = group
            return group
        if char in safeChars:
            group += char
    group = group.ljust(length, "_")
    GROUP_FROM_KEY_CACHE[key] = group
    return group


GROUP_FROM_KEY_CACHE: dict[str, str] = {}


class AnchorGroup:
    __slots__ = ["_indexed", "_lines", "_offsets", "_queries", "_raw", "empty"]

    def __init__(self, raw: str) -> None:
        """Initialize an anchor group with raw text for lazy decoding."""
        self._raw = "\n-\n" + raw if raw else ""
        self._queries = 0
        self._indexed = False
        self._lines: list[str] = []
        self._offsets: dict[str, tuple[int, ...]] = {}
        self.empty = raw == ""

    def decodeRefs(self, key: str) -> list[t.Ref]:
        """
        Decode and return refs for a specific key, indexing the group if queried repeatedly.
        """
        if self.empty:
            return []
        if not self._indexed:
            self._queries += 1
            if self._queries <= QUERY_INDEX_SWITCHOVER:
                return decodeRefsFromRaw(self._raw, key)
            else:
                self._lines, self._offsets = indexAnchorLines(self._raw)
                self._raw = ""
                self._indexed = True
        indices = self._offsets.get(key)
        if not indices:
            return []
        return decodeRefsFromIndex(key, self._lines, indices)


def decodeRefsFromRaw(rawGroup: str, key: str) -> list[t.Ref]:
    """Find and decode refs for a key directly within raw anchor file text without indexing."""
    if not rawGroup:
        return []
    needle = f"{ENTRY_SEPARATOR}{key}\n"
    pos = rawGroup.find(needle)
    if pos == -1:
        return []
    res: list[t.Ref] = []
    needleLen = len(needle)
    while pos != -1:
        start = pos + needleLen
        end = rawGroup.find(ENTRY_SEPARATOR, start)
        lines = rawGroup[start:end].split("\n")
        res.append(
            Ref(
                text=key,
                displayText=lines[0],
                type=lines[1],
                spec=lines[2],
                shortname=lines[3],
                level=lines[4],
                status=lines[5],
                url=lines[6],
                export=bool(lines[7]),
                normative=bool(lines[8]),
                for_=lines[9:],
            ),
        )
        pos = rawGroup.find(needle, end)
    return res


def indexAnchorLines(raw: str) -> tuple[list[str], dict[str, tuple[int, ...]]]:
    """Parse raw anchor text into lines and build an offset mapping from anchor key to line indices."""
    if not raw:
        return [], {}
    lines = raw.split("\n")
    n = len(lines) - 1
    offsets: dict[str, tuple[int, ...]] = {}
    i = 1  # Line 0 is the ENTRY_SEPARATOR
    while i < n:
        aText = lines[i]
        j = i + MINIMUM_ENTRY_LINES
        while lines[j] != "-":
            j += 1
        nxt = j + 1
        if aText in offsets:
            offsets[aText] = (*offsets[aText], i)
        else:
            offsets[aText] = (i,)
        i = nxt
    return lines, offsets


def decodeRefsFromIndex(key: str, lines: list[str], indices: tuple[int, ...]) -> list[t.Ref]:
    """Decode refs for a key from pre-split lines using the given line offset indices."""
    res: list[t.Ref] = []
    for i in indices:
        j = i + MINIMUM_ENTRY_LINES
        while lines[j] != "-":
            j += 1
        res.append(
            Ref(
                text=key,
                displayText=lines[i + 1],
                type=lines[i + 2],
                spec=lines[i + 3],
                shortname=lines[i + 4],
                level=lines[i + 5],
                status=lines[i + 6],
                url=lines[i + 7],
                export=bool(lines[i + 8]),
                normative=bool(lines[i + 9]),
                for_=lines[i + 10 : j],
            ),
        )
    return res


def decodeAnchors(linesIter: t.Iterator[str] | str) -> defaultdict[str, list[t.Ref]]:
    """Decode an entire anchor data file into a mapping of {key: [Ref, ...]}."""
    anchors: defaultdict[str, list[t.Ref]] = defaultdict(list)
    if isinstance(linesIter, str):
        raw = linesIter
    else:
        read = getattr(linesIter, "read", None)
        raw = read() if callable(read) else "".join(linesIter)
    if not raw:
        return anchors
    lines = raw.split("\n")
    n = len(lines) - 1
    i = 0
    while i < n:
        aText = lines[i]
        displayText = lines[i + 1]
        j = i + MINIMUM_ENTRY_LINES
        while lines[j] != "-":
            j += 1
        for_ = lines[i + MINIMUM_ENTRY_LINES : j]
        nxt = j + 1
        anchors[aText].append(
            Ref(
                text=aText,
                displayText=displayText,
                type=lines[i + 2],
                spec=lines[i + 3],
                shortname=lines[i + 4],
                level=lines[i + 5],
                status=lines[i + 6],
                url=lines[i + 7],
                export=bool(lines[i + 8]),
                normative=bool(lines[i + 9]),
                for_=for_,
            ),
        )
        i = nxt
    return anchors


def getArgfulMethodVariants(maybeMethodSig: str, refs: RefSource) -> list[str]:
    """Return all known argument-bearing signatures matching an argless method signature like 'foo()'."""
    if maybeMethodSig.endswith("()") and maybeMethodSig in refs.methods:
        return list(refs.methods[maybeMethodSig].variants.keys())
    return []


@dataclasses.dataclass(slots=True)
class MethodVariants:
    arglessSignature: str
    variants: dict[str, MethodVariant]


@dataclasses.dataclass(slots=True)
class MethodVariant:
    signature: str
    args: list[str]
    for_: list[str]
    shortname: str | None
