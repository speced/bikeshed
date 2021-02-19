import re

from ..h import E, outerHTML
from ..messages import die
from . import steps


class PropdescShorthand:
    def __init__(self):
        self.stage = "start"
        self.escapedText = None
        self.linkText = []
        self.bsAutolink = ""
        self.linkFor = None
        self.lt = None
        self.linkType = None

    def respond(self, match, dom=None):
        if self.stage == "start":
            return self.respondStart(match)
        elif self.stage == "link text":
            return self.respondLinkText(match, dom)
        elif self.stage == "end":
            return self.respondEnd()

    def respondStart(self, match):
        self.bsAutolink = match.group(0)
        escape, self.linkFor, self.lt, self.linkType, hasLinkText = match.groups()
        if escape:
            self.escapedText = match.group(0)[1:]

        if match.groups(0) == "'-":
            # Not a valid property actually.
            return steps.Failure()

        if self.linkFor == "":
            self.linkFor = "/"

        if self.linkType is None:
            self.linkType = "propdesc"

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
                skips=["'"], nodes=[self.escapedText[1:], *self.linkText, "'"]
            )

        self.bsAutolink += "'"

        if self.linkType not in ["property", "descriptor", "propdesc"]:
            die(
                "Shorthand {0} gives type as '{1}', but only 'property' and 'descriptor' are allowed.",
                self.bsAutolink,
                self.linkType,
            )
            return steps.Success(E.span(self.bsAutolink))

        if self.linkText is None:
            self.linkText = self.lt

        attrs = {
            "data-link-type": self.linkType,
            "class": "property",
            "for": self.linkFor,
            "lt": self.lt,
            "bs-autolink-syntax": self.bsAutolink,
        }
        return steps.Success(E.a(attrs, self.linkText))


PropdescShorthand.startRe = re.compile(
    r"""
                        (\\)?
                        '
                        (?:([^\s'|]*)/)?
                        ([\w*-]+)
                        (?:!!([\w-]+))?
                        (\|)?
                        """,
    re.X,
)

endRe = re.compile("'")
