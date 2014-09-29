# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from collections import defaultdict
from .messages import *
from .htmlhelpers import *

class BiblioEntry(object):

    def __init__(self, **kwargs):
        self.linkText = None
        self.title = None
        self.authors = []
        self.etAl = False
        self.status = None
        self.date = None
        self.url = None
        self.other = None
        for key, val in kwargs.items():
            setattr(self, key, val)

    def __str__(self):
        str = ""
        etAl = self.etAl

        if len(self.authors) == 0:
            str += "???"
        elif len(self.authors) == 1:
            str += self.authors[0]
        elif len(self.authors) < 4:
            str += "; ".join(self.authors)
        else:
            str += self.authors[0]
            etAl = True

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
        if len(self.authors) == 0:
            str += "???"
        elif len(self.authors) == 1:
            str += self.authors[0]
        elif len(self.authors) < 4:
            str += "; ".join(self.authors)
        else:
            str += self.authors[0]
            etAl = True

        str += "; et al. " if etAl else ". "
        ret.append(str)

        if self.url:
            ret.append(E.a({"href":self.url}, self.title), ". ")
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
            ret.append("URL: ", E.a({"href":self.url}, self.url))

        return ret

    def valid(self):
        if self.title is None:
            return False
        return True

def processReferBiblioFile(lines, storage, order):
    singularReferCodes = {
        "U": "url",
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
        if re.match("\s*$", line):
            # Empty line
            if biblio is not None:
                storage[biblio['linkText'].lower()].append(biblio)
                biblio = None
            continue
        elif re.match("\s*%?#", line):
            # Comment
            continue
        else:
            if biblio is None:
                biblio = defaultdict(list)
                biblio['order'] = order

        match = re.match("\s*%(\w)\s+(.*)", line)
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
    import json
    try:
        datas = json.loads(text)
    except Exception, e:
        die("Couldn't read the local JSON file:\n{0}", str(e))

    # JSON field name: BiblioEntry name
    fields = {
        "authors": "authors",
        "etAl": "etAl",
        "href": "url",
        "title": "title",
        "rawDate": "date",
        "status": "status"
    }
    # Required BiblioEntry fields
    requiredFields = ["url", "title"]

    for biblioKey, data in datas.items():
        if isinstance(data, basestring):
            # Need to handle the preformatted string entries eventually
            continue
        biblio = {"linkText": biblioKey, "order": order}
        for jsonField, biblioField in fields.items():
            if jsonField in data:
                biblio[biblioField] = data[jsonField]
        if "title" not in biblio:
            # Aliases should hit this case, I'll deal with them later
            continue
        storage[biblioKey.lower()].append(biblio)
    return storage
