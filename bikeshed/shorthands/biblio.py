import re

from ..h import E, outerHTML
from . import steps


class BiblioShorthand:
    def __init__(self):
        self.stage = "start"
        self.escapedText = None
        self.linkText = []
        self.bsAutolink = ""
        self.term = None
        self.status = None
        self.type = None

    def respond(self, match, dom=None):
        if self.stage == "start":
            return self.respondStart(match)
        elif self.stage == "link text":
            return self.respondLinkText(match, dom)
        elif self.stage == "end":
            return self.respondEnd()

    def respondStart(self, match):
        self.bsAutolink = match.group(0)
        escape, bang, self.term, self.status, hasLinkText = match.groups()
        if escape:
            self.escapedText = match.group(0)[1:]
        if bang == "!":
            self.type = "normative"
        else:
            self.type = "informative"
        if hasLinkText:
            self.stage = "link text"
            return steps.NextBody(biblioEndRe)
        else:
            self.stage = "end"
            return steps.NextLiteral(biblioEndRe)

    def respondLinkText(self, match, dom):  # pylint: disable=unused-argument
        self.linkText = dom
        self.bsAutolink += outerHTML(dom)
        return self.respondEnd()

    def respondEnd(self):
        if self.escapedText:
            return steps.Success(
                skips=["["], nodes=[self.escapedText[1:], *self.linkText, "]]"]
            )

        self.bsAutolink += "]]"

        if not self.linkText:
            self.linkText = f"[{self.term}]"

        attrs = {
            "data-lt": self.term,
            "data-link-type": "biblio",
            "data-biblio-type": self.type,
            "bs-autolink-syntax": self.bsAutolink,
        }
        if self.status is not None:
            attrs["data-biblio-status"] = self.status.strip()

        return steps.Success(E.a(attrs, self.linkText))


BiblioShorthand.startRe = re.compile(
    r"""
    (\\)?
    \[\[
    (!)?
    ([\w.+-]+)
    (?:\s+(current|snapshot))?
    (\|)?""",
    re.X,
)

biblioEndRe = re.compile(r"]]")
