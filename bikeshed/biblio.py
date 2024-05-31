from __future__ import annotations

import abc
import dataclasses
import re
from collections import defaultdict

from . import constants, h, t
from . import messages as m


@dataclasses.dataclass
class BiblioEntry(metaclass=abc.ABCMeta):
    linkText: str
    title: str | None = None
    snapshotURL: str | None = None
    currentURL: str | None = None
    preferredStatus: str = constants.refStatus.snapshot
    originalLinkText: str | None = None
    obsoletedBy: str | None = None
    order: int = 0

    @property
    def url(self) -> str:
        if self.snapshotURL is None and self.currentURL is None:
            return ""

        if self.preferredStatus == constants.refStatus.snapshot:
            # At least one of these is non-None so this is safe
            return t.cast(str, self.snapshotURL or self.currentURL)
        elif self.preferredStatus == constants.refStatus.current:
            return t.cast(str, self.currentURL or self.snapshotURL)
        else:
            msg = f"Invalid preferredStatus value: {self.preferredStatus}"
            raise ValueError(msg)

    @abc.abstractmethod
    def toHTML(self) -> t.NodesT: ...

    @abc.abstractmethod
    def valid(self) -> bool: ...

    def strip(self) -> BiblioEntry:
        self.linkText = self.linkText.strip()
        if self.title:
            self.title = self.title.strip()
        if self.snapshotURL:
            self.snapshotURL = self.snapshotURL.strip()
        if self.currentURL:
            self.currentURL = self.currentURL.strip()
        if self.obsoletedBy:
            self.obsoletedBy = self.obsoletedBy.strip()
        return self


@dataclasses.dataclass
class NormalBiblioEntry(BiblioEntry):
    authors: list[str] = dataclasses.field(default_factory=list)
    etAl: bool = False
    status: str | None = None
    date: str | None = None
    other: str | None = None

    def toHTML(self) -> t.NodesT:
        ret: list[t.NodesT] = []

        s = ""
        etAl = self.etAl
        if len(self.authors) == 1:
            s += self.authors[0]
        elif len(self.authors) < 4:
            s += "; ".join(self.authors)
        elif len(self.authors) != 0:
            s += self.authors[0]
            etAl = True

        if s != "":
            s += "; et al. " if etAl else ". "
        ret.append(s)

        if self.url:
            ret.append(h.E.a({"href": self.url}, h.E.cite(self.title)))
            ret.append(". ")
        else:
            ret.append(h.E.cite(self.title))
            ret.append(". ")

        s = ""
        if self.preferredStatus == "current" and self.currentURL:
            pass
        else:
            if self.date:
                s += self.date + ". "
            if self.status:
                s += self.status + ". "
        if self.other:
            s += self.other + " "
        ret.append(s)

        if self.url:
            ret.append("URL: ")
            ret.append(h.E.a({"href": self.url}, self.url))

        return ret

    def valid(self) -> bool:
        return self.title is not None

    def strip(self) -> NormalBiblioEntry:
        super().strip()
        if self.authors:
            self.authors = [x.strip() for x in self.authors]
        if self.status:
            self.status = self.status.strip()
        if self.date:
            self.date = self.date.strip()
        if self.other:
            self.other = self.other.strip()
        return self


class SpecBiblioEntry(BiblioEntry):
    """
    Generates a "fake" biblio entry from a spec reference,
    for when we don't have "real" bibliography data for a reference.
    """

    def __init__(self, spec: dict[str, str], preferredStatus: str | None = None, order: int = 0) -> None:
        super().__init__(
            linkText=spec["vshortname"],
            title=spec["description"],
            snapshotURL=spec["snapshot_url"],
            currentURL=spec["current_url"],
            preferredStatus=preferredStatus or constants.refStatus.snapshot,
            order=order,
        )

    def valid(self) -> bool:
        return self.snapshotURL is not None or self.currentURL is not None

    def toHTML(self) -> t.NodesT:
        return [self.title, " URL: ", h.E.a({"href": self.url}, self.url)]


class StringBiblioEntry(BiblioEntry):
    """
    Generates a barebones biblio entry from a preformatted biblio string.
    This only exists because SpecRef still has a few of them;
    don't use it on purpose for real things in the future.
    """

    data: str

    def __init__(self, linkText: str, data: str, order: int = 0) -> None:
        doc = h.parseDocument(data)
        titleEl = h.find("cite", doc)
        if titleEl is not None:
            title = h.textContent(titleEl)
        else:
            title = h.textContent(doc.getroot())
        super().__init__(
            linkText=linkText,
            title=title,
            order=order,
        )
        self.data = data

    def valid(self) -> bool:
        return True

    def toHTML(self) -> t.NodesT:
        return h.parseHTML(self.data.strip())


class AliasBiblioEntry(BiblioEntry):
    """
    Represents an alias entry,
    which is just an alternate name for some other entry.
    """

    aliasOf: str

    def __init__(self, linkText: str, aliasOf: str, order: int = 0) -> None:
        super().__init__(linkText=linkText, order=order)
        self.aliasOf = aliasOf.strip()

    def valid(self) -> bool:
        return True

    def toHTML(self) -> t.NodesT:
        return [h.E.small({}, f"(alias of {self.aliasOf})")]


def processReferBiblioFile(lines: t.Sequence[str], storage: t.BiblioStorageT, order: int) -> t.BiblioStorageT:
    singularReferCodes = {
        "U": "snapshotURL",
        "T": "title",
        "D": "date",
        "S": "status",
        "L": "linkText",
        "O": "other",
    }
    pluralReferCodes = {
        "A": "authors",
        "Q": "authors",
    }
    unusedReferCodes = set("BCIJNPRVX")

    for group in groupsFromReferFile(lines):
        biblio: dict[str, t.Any] = {"order": order}
        for line in group:
            match = re.match(r"%(\w)\s+(.*)", line)
            if match:
                letter, value = match.groups()
            else:
                m.die(f"Biblio line in unexpected format:\n{line}")
                continue

            if letter in singularReferCodes:
                biblio[singularReferCodes[letter]] = value
            elif letter in pluralReferCodes:
                biblio.setdefault(pluralReferCodes[letter], []).append(value)
            elif letter in unusedReferCodes:
                pass
            else:
                m.die(f"Unknown line type {letter}:\n{line}")
                continue
        storage[biblio["linkText"].lower()].append(NormalBiblioEntry(**biblio))
    return storage


def groupsFromReferFile(lines: t.Sequence[str]) -> t.Generator[list[str], None, None]:
    group: list[str] = []
    for line in lines:
        line = line.strip()

        if line == "":
            if group:
                yield group
                group = []
        elif line.startswith("#") or line.startswith("%#"):
            # Comment
            continue
        else:
            group.append(line)
    # yield the final group, if there wasn't a trailing blank line
    if group:
        yield group


def processSpecrefBiblioFile(text: str, storage: t.BiblioStorageT, order: int) -> t.BiblioStorageT:
    r"""
    A SpecRef file is a JSON object, where keys are ids
    and values are either <alias>, <legacyRef>, or <ref>.

    <alias>: {
        *aliasOf: <id>,
        id: <id>
    }

    <legacyRef>: <string>

    <ref>: {
        id: <id>,
        authors: [<string>],
        etAl: <bool>,
        href: <url>,
        *title: <string>,
        date: <date>,
        deliveredBy: [<wg>],
        status: <string>,
        publisher: <string>,
        obsoletes: [<id>],
        obsoletedBy: [<id>],
        versionOf: <id>,
        versions: [<id>],
        edDraft: <url>
    }

    <date>: /^([1-3]?\d\s)?((?:January|February|March|April|May|June|July|August|September|October|November|December)\s)?\d+$/

    <wg>: {*url:<url>, *shortname:<string>}
    """
    import json

    try:
        datas = json.loads(text)
    except Exception as e:
        m.die(f"Couldn't read the local JSON file:\n{e}")
        return storage

    # JSON field name: BiblioEntry name
    fields = {
        "authors": "authors",
        "etAl": "etAl",
        "href": "snapshotURL",
        "edDraft": "currentURL",
        "title": "title",
        "date": "date",
        "status": "status",
    }

    obsoletedBy: dict[str, str] = {}
    biblio: BiblioEntry
    for biblioKey, data in datas.items():
        biblioKey = biblioKey.strip()
        if isinstance(data, str):
            # Handle <legacyRef>
            biblio = StringBiblioEntry(linkText=biblioKey, order=order, data=data.replace("\n", " "))
        elif "aliasOf" in data:
            # Handle <alias>
            if biblioKey.lower() == data["aliasOf"].lower():
                # SpecRef uses aliases to handle capitalization differences,
                # which I don't care about.
                continue
            biblio = AliasBiblioEntry(linkText=biblioKey, order=order, aliasOf=data["aliasOf"])
        else:
            # Handle <ref>
            bib = {"linkText": biblioKey, "order": order}
            for jsonField, biblioField in fields.items():
                if jsonField in data:
                    bib[biblioField] = data[jsonField]
            if "versionOf" in data:
                # "versionOf" entries are all snapshot urls,
                # so you want the href *all* the time.
                bib["currentURL"] = data["href"]
            if "obsoletedBy" in data:
                for v in data["obsoletedBy"]:
                    obsoletedBy[biblioKey.lower()] = v.lower()
            if "obsoletes" in data:
                for v in data["obsoletes"]:
                    obsoletedBy[v.lower()] = biblioKey.lower()
            biblio = NormalBiblioEntry(**bib)
        storage[biblioKey.lower()].append(biblio)
    for old, new in obsoletedBy.items():
        if old in storage:
            for biblio in storage[old]:
                biblio.obsoletedBy = new
    return storage


def loadBiblioDataFile(lines: t.Iterator[str], storage: t.BiblioStorageT) -> None:
    b: dict[str, t.Any]
    biblio: BiblioEntry
    try:
        while True:
            fullKey = next(lines)
            prefix, key = fullKey[0], fullKey[2:].strip()
            if prefix == "d":
                b = {
                    "linkText": next(lines).strip(),
                    "date": next(lines),
                    "status": next(lines),
                    "title": next(lines),
                    "snapshotURL": next(lines),
                    "currentURL": next(lines),
                    "obsoletedBy": next(lines),
                    "other": next(lines),
                    "etAl": next(lines) != "\n",
                    "order": 3,
                    "authors": [],
                }
                while True:
                    line = next(lines)
                    if line == "-\n":
                        break
                    b["authors"].append(line)
                biblio = NormalBiblioEntry(**b)
            elif prefix == "s":
                b = {
                    "linkText": next(lines).strip(),
                    "data": next(lines),
                    "order": 3,
                }
                line = next(lines)  # Eat the -
                biblio = StringBiblioEntry(**b)
            elif prefix == "a":
                b = {
                    "linkText": next(lines).strip(),
                    "aliasOf": next(lines).strip(),
                    "order": 3,
                }
                line = next(lines)  # Eat the -
                biblio = AliasBiblioEntry(**b)
            else:
                m.die(f"Unknown biblio prefix '{prefix}' on key '{fullKey}'")
                continue
            storage[key].append(biblio)
    except StopIteration:
        pass


def levenshtein(a: str, b: str) -> int:
    "Calculates the Levenshtein distance between a and b."
    n, m = len(a), len(b)  # pylint: disable=redefined-outer-name
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a, b = b, a
        n, m = m, n

    current: list[int] = list(range(n + 1))
    for i in range(1, m + 1):
        previous, current = current, [i] + [0] * n
        for j in range(1, n + 1):
            add, delete = previous[j] + 1, current[j - 1] + 1
            change = previous[j - 1]
            if a[j - 1] != b[i - 1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]


def findCloseBiblios(biblioKeys: t.Sequence[str], target: str, n: int = 5) -> list[str]:
    """
    Finds biblio entries close to the target.
    Returns all biblios with target as the substring,
    plus the 5 closest ones per levenshtein distance.
    """
    target = target.lower()
    names: list[tuple[str, int]] = []
    superStrings: list[str] = []

    for name in sorted(biblioKeys):
        if target in name:
            superStrings.append(name)
        else:
            distance = levenshtein(name, target)
            tup = (name, distance)
            if len(names) < n:
                names.append(tup)
                names.sort(key=lambda x: x[1])
            elif distance >= names[-1][1]:
                pass
            else:
                for i, entry in enumerate(names):
                    if distance < entry[1]:
                        names.insert(i, tup)
                        names.pop()
                        break
    return sorted(s.strip() for s in superStrings) + [name.strip() for name, d in names]


def dedupBiblioReferences(doc: t.SpecT) -> None:
    """
    SpecRef has checks in its database preventing multiple references from having the same URL.
    Shepherd, while it doesn't have an explicit check for this,
    should also generally have unique URLs.
    But these aren't uniqued against each other.
    So, if you explicitly biblio-link to a SpecRef spec,
    and autolink to a Shepherd spec,
    you might get two distinct biblio entries with the exact same URL.

    This code checks for this,
    and deletes Shepherd biblio if there's a SpecRef biblio with the same URL.
    It then adjusts doc.externalRefsUsed to point to the SpecRef biblio.
    """

    def isShepherdRef(ref: BiblioEntry) -> bool:
        return isinstance(ref, SpecBiblioEntry)

    normSpecRefRefs = {}
    normShepherdRefs = {}
    informSpecRefRefs = {}
    informShepherdRefs = {}
    for ref in doc.normativeRefs.values():
        if isShepherdRef(ref):
            normShepherdRefs[ref.url] = ref
        else:
            normSpecRefRefs[ref.url] = ref
    for ref in doc.informativeRefs.values():
        if isShepherdRef(ref):
            informShepherdRefs[ref.url] = ref
        else:
            informSpecRefRefs[ref.url] = ref
    normSpecRefUrls = set(normSpecRefRefs.keys())
    normShepherdUrls = set(normShepherdRefs.keys())
    informSpecRefUrls = set(informSpecRefRefs.keys())
    informShepherdUrls = set(informShepherdRefs.keys())
    specRefUrls = normSpecRefUrls | informSpecRefUrls
    shepherdUrls = normShepherdUrls | informShepherdUrls
    dupedUrls = shepherdUrls & specRefUrls

    if not dupedUrls:
        return

    # If an informative duped URL is SpecRef,
    # and a normative Shepherd version also exists,
    # mark it for "upgrading", so the SpecRef becomes normative.
    upgradeUrls = dupedUrls & informSpecRefUrls & normShepherdUrls
    upgradeRefs = {}
    popInformatives = []
    for key, ref in doc.informativeRefs.items():
        if ref.url in upgradeUrls and not isShepherdRef(ref):
            upgradeRefs[ref.url] = ref
            popInformatives.append(key)
    for key in popInformatives:
        doc.informativeRefs.pop(key)
    for key, ref in doc.normativeRefs.items():
        if ref.url in upgradeUrls:
            doc.normativeRefs[key] = upgradeRefs[ref.url]

    for url in upgradeUrls:
        normShepherdUrls.discard(url)
        informSpecRefUrls.discard(url)
        normSpecRefUrls.add(url)
    shepherdUrls = normShepherdUrls | informShepherdUrls
    specRefUrls = normSpecRefUrls | informSpecRefUrls
    dupedUrls = shepherdUrls & specRefUrls

    # Remove all the Shepherd refs that are left in duped
    poppedKeys: t.DefaultDict[str, dict[str, str]] = defaultdict(dict)
    for key, ref in list(doc.informativeRefs.items()):
        if ref.url in dupedUrls:
            if isShepherdRef(ref):
                doc.informativeRefs.pop(key)
                poppedKeys[ref.url]["shepherd"] = key
            else:
                poppedKeys[ref.url]["specref"] = key
    for key, ref in list(doc.normativeRefs.items()):
        if ref.url in dupedUrls:
            if isShepherdRef(ref):
                doc.normativeRefs.pop(key)
                poppedKeys[ref.url]["shepherd"] = key
            else:
                poppedKeys[ref.url]["specref"] = key

    # For every key that was popped,
    # swap out the "externalRefsUsed" for that key
    for keys in poppedKeys.values():
        if "shepherd" not in keys or "specref" not in keys:
            continue
        oldName = keys["shepherd"]
        newName = keys["specref"]
        if oldName in doc.externalRefsUsed.specs:
            oldSpecData = doc.externalRefsUsed.specs[oldName]
            del doc.externalRefsUsed.specs[oldName]
            if newName not in doc.externalRefsUsed.specs:
                # just move it over
                doc.externalRefsUsed.specs[newName] = oldSpecData
                continue
            else:
                # Merge it in
                newSpecData = doc.externalRefsUsed.specs[newName]
                if newSpecData.biblio is None:
                    newSpecData.biblio = oldSpecData.biblio
                for refGroup in oldSpecData.refs.values():
                    for forVal, refWrapper in refGroup.valuesByFor.items():
                        newSpecData.addRef(refWrapper, forVal)
