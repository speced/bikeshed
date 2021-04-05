import re
from collections import defaultdict

import html5lib
import attr

from . import constants
from .h import *
from .messages import *


@attr.s(slots=True)
class BiblioEntry:
    linkText = attr.ib(default=None)
    originalLinkText = attr.ib(default=None)
    title = attr.ib(default=None)
    authors = attr.ib(default=attr.Factory(list))
    etAl = attr.ib(default=False)
    status = attr.ib(default=None)
    date = attr.ib(default=None)
    snapshot_url = attr.ib(default=None)
    current_url = attr.ib(default=None)
    preferredURL = attr.ib(default=None)
    url = attr.ib(default=None)
    obsoletedBy = attr.ib(default="")
    other = attr.ib(default=None)
    biblioFormat = attr.ib(default=None)
    order = attr.ib(default=None)

    def __attrs_post_init__(self):
        if self.preferredURL is None:
            self.preferredURL = constants.refStatus.snapshot
        else:
            self.preferredURL = constants.refStatus[self.preferredURL]
        if self.preferredURL == constants.refStatus.snapshot:
            self.url = self.snapshot_url or self.current_url
        elif self.preferredURL == constants.refStatus.current:
            self.url = self.current_url or self.snapshot_url
        else:
            raise ValueError(f"Invalid preferredURL value: {self.preferredURL}")

        if isinstance(self.authors, str):
            self.authors = [self.authors]

    def __str__(self):
        str = ""
        etAl = self.etAl

        if len(self.authors) == 1:
            str += self.authors[0]
        elif len(self.authors) < 4:
            str += "; ".join(self.authors)
        elif len(self.authors) != 0:
            str += self.authors[0]
            etAl = True

        if str != "":
            str += "; et al. " if etAl else ". "

        if self.url:
            str += f"<a href='{self.url}'>{self.title}</a>. "
        else:
            str += f"{self.title}. "

        if self.preferredURL == "current" and self.current_url:
            pass
        else:
            if self.date:
                str += self.date + ". "
            if self.status:
                str += self.status + ". "

        if self.other:
            str += self.other + " "

        if self.url:
            str += "URL: <a href='{0}'>{0}</a>".format(self.url)

        return str

    def toHTML(self):
        ret = []

        str = ""
        etAl = self.etAl
        if len(self.authors) == 1:
            str += self.authors[0]
        elif len(self.authors) < 4:
            str += "; ".join(self.authors)
        elif len(self.authors) != 0:
            str += self.authors[0]
            etAl = True

        if str != "":
            str += "; et al. " if etAl else ". "
        ret.append(str)

        if self.url:
            ret.append(E.a({"href": self.url}, self.title))
            ret.append(". ")
        else:
            ret.append(self.title + ". ")

        str = ""
        if self.preferredURL == "current" and self.current_url:
            pass
        else:
            if self.date:
                str += self.date + ". "
            if self.status:
                str += self.status + ". "
        if self.other:
            str += self.other + " "
        ret.append(str)

        if self.url:
            ret.append("URL: ")
            ret.append(E.a({"href": self.url}, self.url))

        return ret

    def valid(self):
        if self.title is None:
            return False
        return True


class SpecBasedBiblioEntry(BiblioEntry):
    """
    Generates a "fake" biblio entry from a spec reference,
    for when we don't have "real" bibliography data for a reference.
    """

    def __init__(self, spec, preferredURL=None):
        super().__init__()
        if preferredURL is None:
            preferredURL = constants.refStatus.snapshot
        self.spec = spec
        self.linkText = spec["vshortname"]
        self._valid = True
        preferredURL = constants.refStatus[preferredURL]
        if preferredURL == constants.refStatus.snapshot:
            self.url = spec["snapshot_url"] or spec["current_url"]
        elif preferredURL == constants.refStatus.current:
            self.url = spec["current_url"] or spec["snapshot_url"]
        else:
            raise ValueError(f"Invalid preferredURL value: {preferredURL}")
        if not self.url:
            self._valid = False
        assert self.url

    def valid(self):
        return self._valid

    def toHTML(self):
        return [self.spec["description"], " URL: ", E.a({"href": self.url}, self.url)]


@attr.s(slots=True)
class StringBiblioEntry(BiblioEntry):
    """
    Generates a barebones biblio entry from a preformatted biblio string.
    This only exists because SpecRef still has a few of them;
    don't use it on purpose for real things in the future.
    """

    data = attr.ib(default="")
    linkText = attr.ib(default="")

    def __attrs_post_init__(self):
        doc = html5lib.parse(self.data, treebuilder="lxml", namespaceHTMLElements=False)
        title = find("cite", doc)
        if title is not None:
            self.title = textContent(title)
        else:
            self.title = textContent(doc.getroot())

    def valid(self):
        return True

    def toHTML(self):
        return parseHTML(self.data)

    def __str__(self):
        return self.data


def processReferBiblioFile(lines, storage, order):
    singularReferCodes = {
        "U": "snapshot_url",
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

    biblio = None
    for _, line in enumerate(lines):
        line = line.strip()
        if line == "":
            # Empty line
            if biblio is not None:
                storage[biblio["linkText"].lower()].append(biblio)
                biblio = None
            continue
        if line.startswith("#") or line.startswith("%#"):
            # Comment
            continue

        if biblio is None:
            biblio = defaultdict(list)
            biblio["order"] = order
            biblio["biblioFormat"] = "dict"

        match = re.match(r"%(\w)\s+(.*)", line)
        if match:
            letter, value = match.groups()
        else:
            die("Biblio line in unexpected format:\n{0}", line)
            continue

        if letter in singularReferCodes:
            biblio[singularReferCodes[letter]] = value
        elif letter in pluralReferCodes:
            biblio[pluralReferCodes[letter]].append(value)
        elif letter in unusedReferCodes:
            pass
        else:
            die("Unknown line type ")
    if biblio is not None:
        storage[biblio["linkText"].lower()] = biblio
    return storage


def processSpecrefBiblioFile(text, storage, order):
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
        die("Couldn't read the local JSON file:\n{0}", str(e))
        return storage

    # JSON field name: BiblioEntry name
    fields = {
        "authors": "authors",
        "etAl": "etAl",
        "href": "snapshot_url",
        "edDraft": "current_url",
        "title": "title",
        "date": "date",
        "status": "status",
    }

    obsoletedBy = {}
    for biblioKey, data in datas.items():
        biblio = {"linkText": biblioKey, "order": order}
        if isinstance(data, str):
            # Handle <legacyRef>
            biblio["biblioFormat"] = "string"
            biblio["data"] = data.replace("\n", " ")
        elif "aliasOf" in data:
            # Handle <alias>
            if biblioKey.lower() == data["aliasOf"].lower():
                # SpecRef uses aliases to handle capitalization differences,
                # which I don't care about.
                continue
            biblio["biblioFormat"] = "alias"
            biblio["aliasOf"] = data["aliasOf"].lower()
        else:
            # Handle <ref>
            biblio["biblioFormat"] = "dict"
            for jsonField, biblioField in fields.items():
                if jsonField in data:
                    biblio[biblioField] = data[jsonField]
            if "versionOf" in data:
                # "versionOf" entries are all snapshot urls,
                # so you want the href *all* the time.
                biblio["current_url"] = data["href"]
            if "obsoletedBy" in data:
                for v in data["obsoletedBy"]:
                    obsoletedBy[biblioKey.lower()] = v.lower()
            if "obsoletes" in data:
                for v in data["obsoletes"]:
                    obsoletedBy[v.lower()] = biblioKey.lower()
        storage[biblioKey.lower()].append(biblio)
    for old, new in obsoletedBy.items():
        if old in storage:
            for biblio in storage[old]:
                biblio["obsoletedBy"] = new
    return storage


def loadBiblioDataFile(lines, storage):
    try:
        while True:
            fullKey = next(lines)
            prefix, key = fullKey[0], fullKey[2:].strip()
            if prefix == "d":
                b = {
                    "linkText": next(lines),
                    "date": next(lines),
                    "status": next(lines),
                    "title": next(lines),
                    "snapshot_url": next(lines),
                    "current_url": next(lines),
                    "obsoletedBy": next(lines),
                    "other": next(lines),
                    "etAl": next(lines) != "\n",
                    "order": 3,
                    "biblioFormat": "dict",
                    "authors": [],
                }
                while True:
                    line = next(lines)
                    if line == "-\n":
                        break
                    b["authors"].append(line)
            elif prefix == "s":
                b = {
                    "linkText": next(lines),
                    "data": next(lines),
                    "biblioFormat": "string",
                    "order": 3,
                }
                line = next(lines)  # Eat the -
            elif prefix == "a":
                b = {
                    "linkText": next(lines),
                    "aliasOf": next(lines),
                    "biblioFormat": "alias",
                    "order": 3,
                }
                line = next(lines)  # Eat the -
            else:
                die("Unknown biblio prefix '{0}' on key '{1}'", prefix, fullKey)
                continue
            storage[key].append(b)
    except StopIteration:
        pass


def levenshtein(a, b):
    "Calculates the Levenshtein distance between a and b."
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a, b = b, a
        n, m = m, n

    current = list(range(n + 1))
    for i in range(1, m + 1):
        previous, current = current, [i] + [0] * n
        for j in range(1, n + 1):
            add, delete = previous[j] + 1, current[j - 1] + 1
            change = previous[j - 1]
            if a[j - 1] != b[i - 1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]


def findCloseBiblios(biblioKeys, target, n=5):
    """
    Finds biblio entries close to the target.
    Returns all biblios with target as the substring,
    plus the 5 closest ones per levenshtein distance.
    """
    target = target.lower()
    names = []
    superStrings = []

    def addName(name, distance):
        tuple = (name, distance)
        if len(names) < n:
            names.append(tuple)
            names.sort(key=lambda x: x[1])
        elif distance >= names[-1][1]:
            pass
        else:
            for i, entry in enumerate(names):
                if distance < entry[1]:
                    names.insert(i, tuple)
                    names.pop()
                    break
        return names

    for name in biblioKeys:
        if target in name:
            superStrings.append(name)
        else:
            addName(name, levenshtein(name, target))
    return sorted(s.strip() for s in superStrings) + [name.strip() for name, d in names]


def dedupBiblioReferences(doc):
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

    def isShepherdRef(ref):
        return isinstance(ref, SpecBasedBiblioEntry)

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
    poppedKeys = defaultdict(dict)
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
        if keys["shepherd"] in doc.externalRefsUsed:
            for k, v in list(doc.externalRefsUsed[keys["shepherd"]].items()):
                doc.externalRefsUsed[keys["specref"]][k] = v
        del doc.externalRefsUsed[keys["shepherd"]]
