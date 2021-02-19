import re

from ..h import E, outerHTML
from . import steps


class SectionShorthand:
    def __init__(self):
        self.stage = "start"
        self.escapedText = None
        self.linkText = []
        self.bsAutolink = ""
        self.spec = None
        self.section = None
        self.justPage = None

    def respond(self, match, dom=None):
        if self.stage == "start":
            return self.respondStart(match)
        elif self.stage == "link text":
            return self.respondLinkText(match, dom)
        elif self.stage == "end":
            return self.respondEnd()

    def respondStart(self, match):
        self.bsAutolink = match.group(0)
        escape, self.spec, self.section, self.justPage, hasLinkText = match.groups()
        if escape:
            self.escapedText = match.group(0)[1:]
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
                skips=["["], nodes=[self.escapedText[1:], *self.linkText, "]]"]
            )

        self.bsAutolink += "]]"

        if not self.linkText:
            self.linkText = ""  # will get filled in by a later step

        if self.spec is None:
            # local section link
            attrs = {
                "section": "",
                "href": self.section,
                "bs-autolink-syntax": self.bsAutolink,
            }
            return steps.Success(E.a(attrs, self.linkText))
        elif self.justPage is not None:
            # foreign link, to an actual page from a multipage spec
            attrs = {
                "spec-section": self.justPage + "#",
                "spec": self.spec,
                "bs-autolink-syntax": self.bsAutolink,
            }
            return steps.Success(E.span(attrs, self.linkText))
        else:
            # foreign link
            attrs = {
                "spec-section": self.section,
                "spec": self.spec,
                "bs-autolink-syntax": self.bsAutolink,
            }
            return steps.Success(E.span(attrs, self.linkText))


SectionShorthand.startRe = re.compile(
    r"""
    (\\)?
    \[\[
    ([\w.+-]+)?
    (?:
        ((?:\/[\w.+-]*)?(?:\#[\w.+-]+)) |
        (\/[\w.+-]+)
    )
    (\|)?
    """,
    re.X,
)

endRe = re.compile(r"]]")
