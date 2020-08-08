import re
from ..h import E
from . import steps

class VarShorthand:
    def respond(self, match, dom=None):
	escape, text = match.groups()
	    if escape:
	        return steps.Success(skips=["|"], nodes=[match.group(0)[1:]])
    return steps.Success(E.var({"bs-autolink-syntax":match.group(0)}, text)

VarShorthand.startRe = re.compile(r"""
                    (\\)?
                    \|
                    (\w(?:[\w\s-]*\w)?)
                    \|""", re.X)