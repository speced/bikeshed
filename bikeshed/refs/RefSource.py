# -*- coding: utf-8 -*-


import copy
import os
import re
from collections import defaultdict

from .. import config
from .. import constants
from .RefWrapper import RefWrapper
from .utils import *

class RefSource(object):

    __slots__ = ["dataFile", "source", "_refs", "methods", "fors", "specs", "ignoredSpecs", "replacedSpecs", "_loadedAnchorGroups"]

    # Which sources use lazy-loading; other sources always have all their refs loaded immediately.
    lazyLoadedSources = ["foreign"]

    def __init__(self, source, specs=None, ignored=None, replaced=None, fileRequester=None):
        if fileRequester is None:
            self.dataFile = config.defaultRequester
        else:
            self.dataFile = fileRequester

        # String identifying which refsource this is.
        self.source = source

        # Dict of {linking text => [anchor data]}
        self._refs = defaultdict(list)

        # Dict of {argless method signatures => {"argfull signature": {"args":[args], "for":[fors]}}}
        self.methods = defaultdict(dict)

        # Dict of {for value => [terms]}
        self.fors = defaultdict(list)

        self.specs = {} if specs is None else specs
        self.ignoredSpecs = set() if ignored is None else ignored
        self.replacedSpecs = set() if replaced is None else replaced
        self._loadedAnchorGroups = set()

    def fetchRefs(self, key):
        '''Safe, lazy-loading version of self._refs[key]'''

        if key in self._refs:
            return self._refs[key]

        if self.source not in self.lazyLoadedSources:
            return []

        group = config.groupFromKey(key)
        if group in self._loadedAnchorGroups:
            # Group was loaded, but previous check didn't find it, so it's just not here.
            return []
        # Otherwise, load the group file.
        with self.dataFile.fetch("anchors", "anchors-{0}.data".format(group), okayToFail=True) as fh:
            self._refs.update(decodeAnchors(fh))
            self._loadedAnchorGroups.add(group)
        return self._refs.get(key, [])

    def fetchAllRefs(self):
        '''Nuts to lazy-loading, just load everything at once.'''

        if self.source not in self.lazyLoadedSources:
            return list(self._refs.items())

        path = config.scriptPath("spec-data", "anchors")
        for file in self.dataFile.walkFiles("anchors"):
            group = re.match("anchors-(.{2})", file).group(1)
            if group in self._loadedAnchorGroups:
                # Already loaded
                continue
            with self.dataFile.fetch("anchors", file) as fh:
                self._refs.update(decodeAnchors(fh))
                self._loadedAnchorGroups.add(group)
        return list(self._refs.items())

    def queryRefs(self, **kwargs):
        if "exact" in kwargs:
            return self._queryRefs(**kwargs)
        else:
            # First search for the exact term, and only if it fails fall back to conjugating.
            results,error = self._queryRefs(exact=True, **kwargs)
            if error:
                return self._queryRefs(exact=False, **kwargs)
            else:
                return results,error

    def _queryRefs(self, text=None, spec=None, linkType=None, linkFor=None, explicitFor=False, linkForHint=None, status=None, statusHint=None, export=None, ignoreObsoletes=False, latestOnly=True, dedupURLs=True, exact=False, error=False, **kwargs):
        # Query the ref database.
        # If it fails to find a ref, also returns the stage at which it finally ran out of possibilities.
        def allRefsIterator():
            # Turns a dict of arrays of refs into an iterator of refs
            for key, group in self.fetchAllRefs():
                for ref in group:
                    yield RefWrapper(key, ref)

        def textRefsIterator(texts):
            # Same as above, but only grabs those keyed to a given text
            for text in texts:
                for ref in self.fetchRefs(text):
                    yield RefWrapper(text, ref)

        def forRefsIterator(targetFors):
            # Same as above, but only grabs those for certain values
            if isinstance(targetFors, str):
                targetFors = [targetFors]
            for for_ in targetFors:
                for text in self.fors[for_]:
                    for ref in self.fetchRefs(text):
                        yield RefWrapper(text, ref)

        # Set up the initial list of refs to query
        if text:
            if exact:
                refs = list(textRefsIterator([text]))
            else:
                textsToSearch = list(linkTextVariations(text, linkType))
                if text.endswith("()") and text in self.methods:
                    textsToSearch += list(self.methods[text].keys())
                if (linkType is None or linkType in config.lowercaseTypes) and text.lower() != text:
                    textsToSearch += [t.lower() for t in textsToSearch]
                refs = list(textRefsIterator(textsToSearch))
        elif linkFor:
            refs = list(forRefsIterator(linkFor))
        else:
            refs = list(allRefsIterator())
        if not refs:
            return refs, "text"

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

        '''
        for=A | forHint=B | explicitFor
        ✘ | ✘ | ✘ = anything
        ✘ | ✘ | ✔ = /
        ✘ | ✔ | ✘ = B/, fallback to anything
        ✘ | ✔ | ✔ = B/, fallback to /
        ✔ | ✘ | ✘ = A/
        ✔ | ✘ | ✔ = A/
        ✔ | ✔ | ✘ = A/
        ✔ | ✔ | ✔ = A/
        '''
        def filterByFor(refs, linkFor):
            return [x for x in refs if matchFor(x.for_, linkFor)]
        def matchFor(forVals, forTest):
            # forTest can be a string, either / for no for or the for value to match,
            # or an array of strings, of which any can match
            if forTest == "/":
                return not bool(forVals)
            if isinstance(forTest, str):
                return forTest in forVals
            return any(matchFor(forVals, ft) for ft in forTest)

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
            return refs, "for"

        def filterByStatus(refs, status):
            if status in constants.refStatus:
                # If status is "current'", kill snapshot refs unless their spec *only* has a snapshot_url
                if status == constants.refStatus.current:
                    return [ref for ref in refs if ref.status == "current" or (ref.status == "snapshot" and self.specs.get(ref.spec,{}).get('current_url') is None)]
                # If status is "snapshot", kill current refs if there's a corresponding snapshot ref for the same spec.
                elif status == constants.refStatus.snapshot:
                    snapshotSpecs = [ref.spec for ref in refs if ref.status == 'snapshot']
                    return [ref for ref in refs if ref.status == "snapshot" or (ref.status == "current" and ref.spec not in snapshotSpecs)]
                else:
                    raise
            # Status is a non-refStatus, but is a valid linkStatus, like "local"
            elif status in config.linkStatuses:
                return [x for x in refs if x.status == status]
            else:
                raise
        if status:
            refs = filterByStatus(refs, status)
        if not refs:
            return refs, "status"

        if status is None and statusHint:
            tempRefs = filterByStatus(refs, statusHint)
            if tempRefs:
                refs = tempRefs

        if linkForHint and not linkFor and not explicitFor:
            tempRefs = filterByFor(refs, linkForHint)
            if tempRefs:
                refs = tempRefs

        if ignoreObsoletes and not spec:
            # Remove any ignored or obsoleted specs
            # If you specified the spec, don't filter things - you know what you're doing.
            refs = filterObsoletes(refs, replacedSpecs=self.replacedSpecs, ignoredSpecs=self.ignoredSpecs)
        if not refs:
            return refs, "ignored-specs"

        if dedupURLs:
            # With non-exact texts, you might have multiple "anchors"
            # that point to the same url. Dedup them.
            seenUrls = set()
            tempRefs = []
            # Sort the refs so the kept one doesn't depend on ordering in the RefSource dict.
            for ref in sorted(copy.copy(refs), key=lambda x:x.text):
                if ref.url not in seenUrls:
                    tempRefs.append(ref)
                    seenUrls.add(ref.url)
            refs = tempRefs

        if latestOnly:
            # If multiple levels of the same shortname exist,
            # only use the latest level.
            # If generating for a snapshot, prefer the latest snapshot level,
            # unless that doesn't exist, in which case just prefer the latest level.
            refs = filterOldVersions(refs, status=status or statusHint)

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


def decodeAnchors(linesIter):
    # Decodes the anchor storage format into {key: [{anchor-data}]}
    anchors = defaultdict(list)
    try:
        while True:
            key = next(linesIter)[:-1]
            a = {
                "type": next(linesIter),
                "spec": next(linesIter),
                "shortname": next(linesIter),
                "level": next(linesIter),
                "status": next(linesIter),
                "url": next(linesIter),
                "export": next(linesIter) != "\n",
                "normative": next(linesIter) != "\n",
                "for": []
            }
            while True:
                line = next(linesIter)
                if line == "-\n":
                    break
                a['for'].append(line)
            anchors[key].append(a)
    except StopIteration:
        return anchors
