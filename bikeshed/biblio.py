# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from .messages import *

class BiblioEntry(object):
    linkText = None
    title = None
    authors = None
    etAl = False
    foreignAuthors = None
    status = None
    date = None
    url = None
    other = None
    bookName = None
    city = None
    issuer = None
    journal = None
    volumeNumber = None
    numberInVolume = None
    pageNumber = None
    reportNumber = None
    abstract = None

    def __init__(self, **kwargs):
        self.authors = []
        self.foreignAuthors = []
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
        if re.match("\s*#", line) or re.match("\s*$", line):
            # Comment or empty line
            if biblio is not None:
                biblios[biblio.linkText] = biblio
            biblio = BiblioEntry()
        else:
            if biblio is None:
                biblio = BiblioEntry()

        for (letter, name) in singularReferCodes.items():
            if re.match("\s*%"+letter+"\s+[^\s]", line):
                setattr(biblio, name, re.match("\s*%"+letter+"\s+(.*)", line).group(1))
        for (letter, name) in pluralReferCodes.items():
            if re.match("\s*%"+letter+"\s+[^\s]", line):
                getattr(biblio, name).append(re.match("\s*%"+letter+"\s+(.*)", line).group(1))
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
