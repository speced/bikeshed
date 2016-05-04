# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
import copy
from collections import defaultdict, deque
from .messages import *
from .htmlhelpers import *

class BiblioEntry(object):

    def __init__(self, preferredURL="dated", **kwargs):
        self.linkText = None
        self.title = None
        self.authors = []
        self.etAl = False
        self.status = None
        self.date = None
        self.dated_url = None
        self.current_url = None
        self.url = None
        self.other = None
        for key, val in kwargs.items():
            if key == "authors":
                setattr(self, key, val)
            elif key == "etAl":
                self.etAl = val
            else:
                setattr(self, key, val)
        if preferredURL == "dated":
            self.url = self.dated_url or self.current_url
        else:
            self.url = self.current_url or self.dated_url

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
            str += "<a href='{0}'>{1}</a>. ".format(self.url, self.title)
        else:
            str += "{0}. ".format(self.title)

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
            ret.append(E.a({"href":self.url}, self.title))
            ret.append(". ")
        else:
            ret.append(self.title + ". ")

        str = ""
        if self.date:
            str += self.date + ". "
        if self.status:
            str += self.status + ". "
        if self.other:
            str += self.other + " "
        ret.append(str)

        if self.url:
            ret.append("URL: ")
            ret.append(E.a({"href":self.url}, self.url))

        return ret

    def valid(self):
        if self.title is None:
            return False
        return True

class SpecBasedBiblioEntry(BiblioEntry):
    '''
    Generates a "fake" biblio entry from a spec reference,
    for when we don't have "real" bibliography data for a reference.
    '''

    def __init__(self, spec, preferredURL="dated"):
        self.spec = spec
        self.linkText = spec['vshortname']
        self._valid = True
        if preferredURL == "dated" and spec.get("TR", None) is not None:
            self.url = spec['TR']
        elif spec.get('ED', None) is not None:
            self.url = spec['ED']
        elif spec.get('TR', None) is not None:
            self.url = spec['TR']
        else:
            self._valid = False

    def valid(self):
        return self._valid

    def toHTML(self):
        return [
            self.spec['description'],
            " URL: ",
            E.a({"href":self.url}, self.url)
        ]

class StringBiblioEntry(BiblioEntry):
    '''
    Generates a barebones biblio entry from a preformatted biblio string.
    This only exists because SpecRef still has a few of them;
    don't use it on purpose for real things in the future.
    '''

    def __init__(self, data, linkText, **kwargs):
        self.data = data
        self.linkText = linkText

    def valid(self):
        return True

    def toHTML(self):
        return parseHTML(self.data)

    def __str__(self):
        return self.data

def processReferBiblioFile(lines, storage, order):
    singularReferCodes = {
        "U": "dated_url",
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
    for i,line in enumerate(lines):
        line = line.strip()
        if line == "":
            # Empty line
            if biblio is not None:
                storage[biblio['linkText'].lower()].append(biblio)
                biblio = None
            continue
        elif line.startswith("#") or line.startswith("%#"):
            # Comment
            continue
        else:
            if biblio is None:
                biblio = defaultdict(list)
                biblio['order'] = order
                biblio['biblioFormat'] = "dict"

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
        storage[biblio['linkText'].lower()] = biblio
    return storage

def processSpecrefBiblioFile(text, storage, order):
    '''
    A SpecRef file is a JSON object, where keys are ids
    and values are either <alia>, <legacyRef>, or <ref>.

    <alias>: {
        *aliasOf: <id>,
        *id: <id>
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
    '''
    import json
    try:
        datas = json.loads(text)
    except Exception, e:
        die("Couldn't read the local JSON file:\n{0}", str(e))
        return storage

    # JSON field name: BiblioEntry name
    fields = {
        "authors": "authors",
        "etAl": "etAl",
        "href": "dated_url",
        "edDraft": "current_url",
        "title": "title",
        "date": "date",
        "status": "status"
    }
    # Required BiblioEntry fields
    requiredFields = ["url", "title"]

    aliases = {}
    for biblioKey, data in datas.items():
        biblio = {"linkText": biblioKey, "order": order}
        if isinstance(data, basestring):
            # Handle <legacyRef>
            biblio['biblioFormat'] = "string"
            biblio['data'] = data.replace("\n", " ")
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
            biblio['biblioFormat'] = "dict"
            for jsonField, biblioField in fields.items():
                if jsonField in data:
                    biblio[biblioField] = data[jsonField]
                if "versionOf" in data:
                    # "versionOf" entries are all dated urls,
                    # so you want the href *all* the time.
                    biblio["current_url"] = data["href"]
        storage[biblioKey.lower()].append(biblio)
    return storage

def loadBiblioDataFile(lines, storage):
    try:
        while True:
            fullKey = lines.next()
            prefix, key = fullKey[0], fullKey[2:].strip()
            if prefix == "d":
                b = {
                    "linkText": lines.next(),
                    "date": lines.next(),
                    "status": lines.next(),
                    "title": lines.next(),
                    "dated_url": lines.next(),
                    "current_url": lines.next(),
                    "other": lines.next(),
                    "etAl": lines.next() != "\n",
                    "order": 3,
                    "biblioFormat": "dict",
                    "authors": []
                }
                while True:
                    line = lines.next()
                    if line == b"-\n":
                        break
                    b['authors'].append(line)
            elif prefix == "s":
                b = {
                    "linkText": lines.next(),
                    "data": lines.next(),
                    "biblioFormat": "string",
                    "order": 3
                }
                line = lines.next() # Eat the -
            elif prefix == "a":
                b = {
                    "linkText": lines.next(),
                    "aliasOf": lines.next(),
                    "biblioFormat": "alias",
                    "order": 3
                }
                line = lines.next() # Eat the -
            else:
                die("Unknown biblio prefix '{0}' on key '{1}'", prefix, fullKey)
                continue
            storage[key].append(b)
    except StopIteration:
        pass


def levenshtein(a,b):
    "Calculates the Levenshtein distance between a and b."
    n, m = len(a), len(b)
    if n > m:
        # Make sure n <= m, to use O(min(n,m)) space
        a,b = b,a
        n,m = m,n

    current = range(n+1)
    for i in range(1,m+1):
        previous, current = current, [i]+[0]*n
        for j in range(1,n+1):
            add, delete = previous[j]+1, current[j-1]+1
            change = previous[j-1]
            if a[j-1] != b[i-1]:
                change = change + 1
            current[j] = min(add, delete, change)

    return current[n]

def findCloseBiblios(biblioKeys, target, n=5):
    '''
    Finds biblio entries close to the target.
    Returns all biblios with target as the substring,
    plus the 5 closest ones per levenshtein distance.
    '''
    target = target.lower()
    names = []
    superStrings = []
    def addName(name, distance):
        tuple = (name, distance)
        if len(names) < n:
            names.append(tuple)
            names.sort(key=lambda x:x[1])
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
    return sorted(s.strip() for s in superStrings) + [n.strip() for n,d in names]
