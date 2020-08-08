import re

from .. import config
from ..h import E, outerHTML
from ..messages import die

from . import steps

class IdlShorthand:
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
        escape, self.linkFor, self.lt, self.linkType, hasLinkText = match.groups()
        if escape:
            self.escapedText = match.group(0)[1:]

        if self.linkFor == "":
            self.linkFor = "/"

        if self.linkType is None:
            self.linkType = "idl"

        if hasLinkText:
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
            return steps.Success(skips=["{"], nodes=[self.escapedText[1:], *self.linkText, "}}"])

        self.bsAutolink += "}}"

        if self.linkType not in config.idlTypes:
            die("Shorthand {0} gives type as '{1}', but only IDL types are allowed.", self.bsAutolink, self.linkType)
            return steps.Success(E.span({}, self.bsAutolink))

        if not self.linkText:
            if self.lt.startswith("constructor(") and self.linkFor and self.linkFor != "/":
                # make {{Foo/constructor()}} output as "Foo()" so you know what it's linking to.
                self.linkText = self.linkFor + self.lt[11:]
            else:
                self.linkText = self.lt

        attrs = {
            "data-link-type":self.linkType,
            "for":self.linkFor,
            "lt":self.lt,
            "bs-autolink-syntax":self.bsAutolink}
        return steps.Success(
            E.code({"class":"idl", "nohighlight":""},
                E.a(attrs, linkText)))


IdlShorthand.startRe = re.compile(r"""
(\\)?
{{
(?:([^}|]*)/)?
([^}/|]+?)
(?:!!([\w-]+))?
(\|)?""", re.X)

endRe = re.compile("}}")