from __future__ import annotations

import dataclasses
import re

from .. import config, h, t
from .. import messages as m


def addAttributeInfoSpans(doc: t.SpecT) -> None:
    # <dt><dfn attribute> automatically gets a <span attribute-info> appended to it
    # (and same for <dfn dict-member> and <span dict-member-info>).
    for dt in h.findAll("dt", doc):
        dfn = h.find("dfn", dt)
        if dfn is None:
            continue
        if h.find("span[data-attribute-info], span[data-dict-member-info]", dt) is not None:
            # Already has a span, nothing to add
            continue
        dfnType = dfn.get("data-dfn-type")
        if dfnType == "attribute":
            attrName = "data-attribute-info"
        elif dfnType == "dict-member":
            attrName = "data-dict-member-info"
        else:
            continue
        spanFor = h.firstLinkTextFromElement(dfn)
        if spanFor is None:
            continue
        # Internal slots (denoted by [[foo]] naming scheme) don't have attribute info
        if spanFor.startswith("[["):
            continue
        if dfn.get("data-dfn-for"):
            spanFor = dfn.get("data-dfn-for", "") + "/" + spanFor
        # If there's whitespace after the dfn, clear it out
        if h.emptyText(dfn.tail, wsAllowed=True):
            dfn.tail = None
        h.insertAfter(dfn, ", ", h.E.span({attrName: "", "for": spanFor}))


def fillAttributeInfoSpans(doc: t.SpecT) -> None:
    for el in h.findAll("span[data-attribute-info], span[data-dict-member-info]", doc):
        if not h.isEmpty(el):
            # Manually filled, bail
            return

        info = getTargetInfo(doc, el)
        if info is None:
            continue

        h.appendChild(el, htmlFromInfo(info))


@dataclasses.dataclass
class TargetInfo:
    type: str
    nullable: bool = False
    readonly: bool = False
    default: str | None = None


def getTargetInfo(doc: t.SpecT, el: t.ElementT) -> TargetInfo | None:
    if el.get("data-attribute-info") is not None:
        refType = "attribute"
    else:
        refType = "dict-member"

    referencedAttribute = el.get("for")
    if not referencedAttribute:
        m.die("Missing for='' reference in attribute info span.", el=el)
        return None
    if "/" in referencedAttribute:
        interface, referencedAttribute = referencedAttribute.split("/")
        targets = h.findAll(
            'a[data-link-type={2}][data-lt="{0}"][data-link-for="{1}"]'.format(referencedAttribute, interface, refType),
            doc,
        )
    else:
        targets = h.findAll(
            f'a[data-link-type={refType}][data-lt="{referencedAttribute}"]',
            doc,
        )

    if len(targets) == 0:
        m.die(f"Couldn't find target {referencedAttribute} '{refType}':\n{h.outerHTML(el)}", el=el)
        return None
    elif len(targets) > 1:
        m.die(f"Multiple potential target {referencedAttribute}s '{refType}':\n{h.outerHTML(el)}", el=el)
        return None

    target = targets[0]

    type = target.get("data-type", "").strip()
    if type.endswith("?"):
        nullable = True
        type = type[:-1]
    else:
        nullable = False
    default = target.get("data-default")
    readonly = target.get("data-readonly") is not None
    return TargetInfo(type, nullable, readonly, default)


def htmlFromInfo(info: TargetInfo) -> t.NodesT:
    deco = []
    if re.match(r"\w+<\w+(\s*,\s*\w+)*>", info.type):
        # Simple higher-kinded types
        match = re.match(r"(\w+)<(\w+(?:\s*,\s*\w+)*)>", info.type)
        assert match is not None
        types = [h.E.a({"data-link-type": "idl-name"}, x.strip()) for x in match.group(2).split(",")]
        deco.extend([" of type ", match.group(1), "<", config.intersperse(types, ", "), ">"])
    elif "<" in info.type or "(" in info.type:
        # Unions or more-complex higher-kinded types
        # Currently just bail, but I need to address this at some point.
        deco.extend(
            [
                " of type ",
                h.E.code({"class": "idl-code"}, info.type),
            ],
        )
    else:
        # Everything else
        deco.extend(
            [
                " of type ",
                h.E.a({"data-link-type": "idl-name"}, info.type),
            ],
        )

    if info.readonly:
        deco.append(", readonly")
    if info.nullable:
        deco.append(", nullable")
    if info.default is not None:
        deco.append(", defaulting to ")
        deco.append(h.E.code(info.default))

    return deco
