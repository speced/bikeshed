import re

from .. import config
from ..h import E, outerHTML
from ..messages import die

from . import steps

class ElementShorthand:
    def __init__(self):
        self.stage = "start"
        self.escapedText = None
        self.linkText = []
        self.bsAutolink = ""

    def respond(self, match, dom=None):
        if self.stage == "start":
            return self.respondStart(match)
        elif self.stage == "link text":
            return self.respondLinkText(match, dom)
        elif self.stage == "end":
            return self.respondEnd()

    def respondStart(self, match):
        self.bsAutolink = match.group(0)
        groupdict = match.groupdict()
        if groupdict["escape"]:
            self.escapedText = match.group(0)[1:]
        if groupdict["attr"] is None and groupdict["value"] is None:
            self.linkType = "element"
            self.linkFor = None
            self.lt = groupdict["element"]
        elif groupdict["value"] is None:
            self.linkType = "element-sub"
            self.linkFor = groupdict["element"]
            self.lt = groupdict["attr"]
        else:
            self.linkType = "attr-value"
            self.linkFor = groupdict["element"] + "/" + groupdict["attr"]
            self.lt = groupdict["value"]
        if groupdict["linkType"] is not None:
            self.linkType = groupdict["linkType"]

        if groupdict["hasLinkText"]:
            self.stage = "link text"
            return steps.NextBody(endRe)
        else:
            self.stage = "end"
            return steps.NextLiteral(endRe)

    def respondLinkText(self, match, dom):
        self.linkText = dom
        self.bsAutolink += outerHTML(dom)
        return self.respondEnd()

    def respondEnd(self):
        if self.escapedText:
            return steps.Success(skips=["<"], nodes=[self.escapedText[1:], *self.linkText, "}>"])

        self.bsAutolink += "}>"

        if self.linkType not in config.markupTypes and self.linkType != "element-sub":
            die("Shorthand {0} gives type as '{1}', but only markup types ({2}) are allowed.",
                self.bsAutolink,
                self.linkType,
                config.englishFromList(config.idlTypes))
            return steps.Success(E.span({}, self.bsAutolink))

        if not self.linkText:
            self.linkText = self.lt

        attrs = {
            "data-link-type":self.linkType,
            "for":self.linkFor,
            "lt":self.lt,
            "bs-autolink-syntax":self.bsAutolink}
        return steps.Success(
            E.a(attrs, linkText))


ElementShorthand.startRe = re.compile(r"""
                        (?P<escape>\\)?
                        <{
                        (?P<element>[\w*-]+)
                        (?:/
                            (?P<attr>[\w*-]+)
                            (?:/(?P<value>[^}!|]+))?
                        )?
                        (?:!!(?P<linkType>[\w-]+))?
                        (?P<linkText>\|)?""", re.X)

endRe = re.compile("}>")
