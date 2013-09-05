import re
from fuckunicode import u

class BiblioEntry(object):
    linkText = None
    title = None
    authors = None
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
            setattr(self, key, u(val))

    def __str__(self):
        str = u""
        authors = self.authors + self.foreignAuthors

        if len(authors) == 0:
            str += u"???. "
        elif len(authors) == 1:
            str += u(authors[0]) + u". "
        elif len(authors) < 4:
            str += u"; ".join(map(u, authors)) + u". "
        else:
            str += u(authors[0]) + u"; et al. "

        str += u"<a href='{0}'>{1}</a>. ".format(u(self.url), u(self.title))

        if self.date:
            str += self.date + u". "

        if self.status:
            str += self.status + u". "

        if self.other:
            str += self.other + u" "

        str += u"URL: <a href='{0}'>{0}</a>".format(u(self.url))
        return str


def processReferBiblioFile(file):
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
    for line in file:
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