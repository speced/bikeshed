from __future__ import annotations

import dataclasses
import re

from . import h, t
from . import messages as m

# Any element can have an include-if or exclude-if attribute,
# containing a comma-separated list of conditions (described below).
# If an element has include-if, it must match at least one condition,
# or else it's removed from the document.
# If an element has exclude-if, if it matches at least one condition,
# it's removed from the document.
# (An element can have both; both of the above conditions apply.)
#
# A condition is either a Status value, or a `!Foo: bar` custom metadata declaration,
# which is compared literally after trimming.
#
# The <if-wrapper> element is a special wrapper element
# that exists *solely* to support conditional inclusion,
# and which never appears in the output document.
# It must have a conditional attribute on it,
# and if it passes the checks,
# it's still removed from the document,
# but its children are left in its place.


def processConditionals(doc: t.SpecT, container: t.ElementT | None = None) -> None:
    for el in h.findAll("[include-if], [exclude-if], if-wrapper", container if container is not None else doc):
        if el.tag == "if-wrapper" and not h.hasAttr(el, "include-if", "exclude-if"):
            m.die(
                "<if-wrapper> elements must have an include-if and/or exclude-if attribute.",
                el=el,
            )
            h.removeNode(el)
            continue

        removeEl = False
        if h.hasAttr(el, "include-if"):
            if not any(evalConditions(doc, el, el.get("include-if", ""))):
                removeEl = True
        if not removeEl and h.hasAttr(el, "exclude-if"):
            if any(evalConditions(doc, el, el.get("exclude-if", ""))):
                removeEl = True

        if removeEl:
            h.removeNode(el)
            continue

        if el.tag == "if-wrapper":
            # Passed the tests, so just remove the wrapper
            h.replaceNode(el, *h.childNodes(el, clear=True))
            continue

        # Otherwise, go ahead and just remove the include/exclude-if attributes,
        # since they're non-standard
        h.removeAttr(el, "include-if", "exclude-if")


def evalConditions(doc: t.SpecT, el: t.ElementT, conditionString: str) -> t.Generator[bool, None, None]:
    for cond in parseConditions(conditionString, el):
        if cond.type == "status":
            yield doc.doctype.status.looselyMatch(cond.value)
        elif cond.type == "text macro":
            for k in doc.macros:
                if k.upper() == cond.value:
                    yield True
                    break
            else:
                yield False
        elif cond.type == "boilerplate":
            yield (h.find(f'[boilerplate="{h.escapeCSSIdent(cond.value)}"]', doc) is not None)
        else:
            m.die(
                f"Program error, some type of include/exclude-if condition wasn't handled: '{cond!r}'. Please report!",
                el,
            )
            yield False


@dataclasses.dataclass
class Condition:
    type: str
    value: str


def parseConditions(s: str, el: t.ElementT | None = None) -> t.Generator[Condition, None, None]:
    for sub in s.split(","):
        sub = sub.strip()
        if sub == "":
            continue
        if re.match(r"([\w-]+/)?[\w-]+$", sub):
            yield Condition(type="status", value=sub)
            continue
        match = re.match(r"text macro:\s*(.+)$", sub, re.I)
        if match:
            yield Condition(type="text macro", value=match.group(1).strip())
            continue
        match = re.match(r"boilerplate:\s*(.+)$", sub, re.I)
        if match:
            yield Condition(type="boilerplate", value=match.group(1).strip())
            continue
        m.die(f"Unknown include/exclude-if condition '{sub}'", el=el)
        continue
