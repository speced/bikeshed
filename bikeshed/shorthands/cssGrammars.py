import re
from ..h import E
from . import steps

class HashMultShorthand:
    def respond(self, match, dom=None):
        return steps.Success(E.a({"data-link-type":"grammar", "data-lt": "#", "for":""}, match.group(0)))
HashMultShorthand.startRe = re.compile(r"#{\s*\d+(\s*,(\s*\d+)?)?\s*}")

class MultShorthand:
    def respond(self, match, dom=None):
        return steps.Success(E.a({"data-link-type":"grammar", "data-lt": "{A}", "for":""}, match.group(0)))
MultShorthand.startRe = re.compile(r"{\s*\d+\s*}")

class MultRangeShorthand:
    def respond(self, match, dom=None):
        return steps.Success(E.a({"data-link-type":"grammar", "data-lt": "{A,B}", "for":""}, match.group(0)))
MultRangeShorthand.startRe = re.compile(r"{\s*\d+\s*,(\s*\d+)?\s*}")

class SimpleTokenShorthand:
    def respond(self, match, dom=None):
        return steps.Success(E.a({"data-link-type":"grammar", "data-lt": match.group(0), "for":""}, match.group(0)))
SimpleTokenShorthand.startRe = re.compile(r"(\?|!|#|\*|\+|\|\||\||&amp;&amp;|&&|,)(?!')")