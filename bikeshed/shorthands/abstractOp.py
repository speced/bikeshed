import re

from ..h import E, outerHTML
from . import steps


class AbstractOpShorthand:
    def __init__(self):
        self.stage = "start"
        self.escapedText = None
        self.linkText = []
        self.bsAutolink = ""
        self.linkFor = None
        self.lt = None

    def respond(self, match, dom=None):
        if self.stage == "start":
            return self.respondStart(match)
        elif self.stage == "link text":
            return self.respondLinkText(match, dom)
        elif self.stage == "end":
            return self.respondEnd()

    def respondStart(self, match):
        self.bsAutolink = match.group(0)
        escape, self.linkFor, self.lt, hasLinkText = match.groups()
        if escape:
            self.escapedText = match.group(0)[1:]

        if self.linkFor == "":
            self.linkFor = "/"

        if hasLinkText:
            self.stage = "link text"
            return steps.NextBody(endRe)
        else:
            self.stage = "end"
            return steps.NextLiteral(endRe)

    def respondLinkText(self, match, dom):  # pylint: disable=unused-argument
        self.linkText = dom
        self.bsAutolink += outerHTML(dom)
        return self.respondEnd()

    def respondEnd(self):
        if self.escapedText:
            return steps.Success(
                skips=["["], nodes=[self.escapedText[1:], *self.linkText, "$]"]
            )

        self.bsAutolink += "$]"

        if not self.linkText:
            self.linkText = self.lt

        attrs = {
            "data-link-type": "abstract-op",
            "for": self.linkFor,
            "lt": self.lt,
            "bs-autolink-syntax": self.bsAutolink,
        }
        return steps.Success(E.a(attrs, self.linkText))


AbstractOpShorthand.startRe = re.compile(
    r"""
    (\\)?
    \[\$
    (?!\s)(?:([^$|]*)/)?
    ([^\"$]+?)
    (?:\|)?""",
    re.X,
)

endRe = re.compile("$]")
