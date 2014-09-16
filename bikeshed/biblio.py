# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from .messages import *

class BiblioEntry(object):

    def __init__(self, **kwargs):
        self.linkText = None
        self.title = None
        self.authors = []
        self.etAl = False
        self.foreignAuthors = []
        self.status = None
        self.date = None
        self.url = None
        self.other = None
        self.bookName = None
        self.city = None
        self.issuer = None
        self.journal = None
        self.volumeNumber = None
        self.numberInVolume = None
        self.pageNumber = None
        self.reportNumber = None
        self.abstract = None
        for key, val in kwargs.items():
            setattr(self, key, val)

    def __str__(self):
        str = ""
        authors = self.authors + self.foreignAuthors
        etAl = self.etAl

        if len(authors) == 0:
            str += "???"
        elif len(authors) == 1:
            str += authors[0]
        elif len(authors) < 4:
            str += "; ".join(authors)
        else:
            str += authors[0]
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

    def valid(self):
        if self.title is None:
            return False
        return True


def processReferBiblioFile(lines):
    biblios = {}
    biblio = None
    singularReferCodes = {
        "B": "bookName",
        "C": "city",
        "D": "date",
        "I": "issuer",
        "J": "journal",
        "L": "linkText",
        "N": "numberInVolume",
        "O": "other",
        "P": "pageNumber",
        "R": "reportNumber",
        "S": "status",
        "T": "title",
        "U": "url",
        "V": "volumeNumber",
        "X": "abstract"
    }
    pluralReferCodes = {
        "A": "authors",
        "Q": "foreignAuthors",
    }
    for line in lines:
        if re.match("\s*$", line):
            # Empty line
            if biblio is not None:
                biblios[biblio.linkText] = biblio
                biblio = None
            continue
        elif re.match("\s*%?#", line):
            # Comment
            continue
        else:
            if biblio is None:
                biblio = BiblioEntry()

        match = re.match("\s*%(\w)\s+(.*)", line)
        if match:
            letter, value = match.groups()
        else:
            die("Biblio line in unexpected format:\n{0}", line)
            continue

        if letter in singularReferCodes:
            setattr(biblio, singularReferCodes[letter], value)
        elif letter in pluralReferCodes:
            getattr(biblio, pluralReferCodes[letter]).append(value)
        else:
            die("Unknown line type ")
    return biblios

def processSpecrefBiblioFile(text):
    import json
    biblios = {}
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
        biblio = BiblioEntry()
        biblio.linkText = biblioKey
        for jsonField, biblioField in fields.items():
            if jsonField in data:
                setattr(biblio, biblioField, data[jsonField])
        if not biblio.valid():
            missingFields = []
            for field in requiredFields:
                try:
                    getattr(biblio, field)
                except:
                    missingFields.append(field)
            die("Missing the field(s) {1} from biblio entry for {0}", biblioKey, ', '.join(map("'{0}'".format, missingFields)))
            continue
        biblios[biblioKey] = biblio
    return biblios
