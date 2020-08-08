# -*- coding: utf-8 -*-

import re

from .. import config
from .. import h
from ..messages import *


def addAttributeInfoSpans(doc):
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
        spanFor = config.firstLinkTextFromElement(dfn)
        if spanFor is None:
            continue
        # Internal slots (denoted by [[foo]] naming scheme) don't have attribute info
        if spanFor.startswith("[["):
            continue
        if dfn.get("data-dfn-for"):
            spanFor = dfn.get("data-dfn-for") + "/" + spanFor
        # If there's whitespace after the dfn, clear it out
        if h.emptyText(dfn.tail, wsAllowed=True):
            dfn.tail = None
        h.insertAfter(dfn,
                    ", ",
                    h.E.span({attrName:"", "for":spanFor}))


def fillAttributeInfoSpans(doc):
    for el in h.findAll("span[data-attribute-info], span[data-dict-member-info]", doc):
        if not h.isEmpty(el):
            # Manually filled, bail
            return

        info = getTargetInfo(doc, el)
        if info is None:
            continue

        h.appendChild(el, htmlFromInfo(info))


def getTargetInfo(doc, el):
    if el.get('data-attribute-info') is not None:
        refType = "attribute"
    else:
        refType = "dict-member"

    referencedAttribute = el.get("for")
    if not referencedAttribute:
        die("Missing for='' reference in attribute info span.", el=el)
        return
    if "/" in referencedAttribute:
        interface, referencedAttribute = referencedAttribute.split("/")
        targets = h.findAll('a[data-link-type={2}][data-lt="{0}"][data-link-for="{1}"]'.format(referencedAttribute, interface, refType), doc)
    else:
        targets = h.findAll('a[data-link-type={1}][data-lt="{0}"]'.format(referencedAttribute, refType), doc)

    if len(targets) == 0:
        die("Couldn't find target {1} '{0}':\n{2}", referencedAttribute, refType, h.outerHTML(el), el=el)
        return
    elif len(targets) > 1:
        die("Multiple potential target {1}s '{0}':\n{2}", referencedAttribute, refType, h.outerHTML(el), el=el)
        return

    target = targets[0]

    info = {}
    info['type'] = target.get("data-type").strip()
    if info['type'].endswith("?"):
        info['nullable'] = True
        info['type'] = info['type'][:-1]
    else:
        info['nullable'] = False
    info['default'] = target.get("data-default")
    info['readonly'] = target.get("data-readonly") is not None
    return info


def htmlFromInfo(info):
    deco = []
    if re.match(r"\w+<\w+(\s*,\s*\w+)*>", info['type']):
        # Simple higher-kinded types
        match = re.match(r"(\w+)<(\w+(?:\s*,\s*\w+)*)>", info['type'])
        types = [h.E.a({"data-link-type":"idl-name"}, x.strip()) for x in match.group(2).split(",")]
        deco.extend([
                    " of type ",
                    match.group(1),
                    "<",
                    config.intersperse(types, ", "),
                    ">"])
    elif "<" in info['type'] or "(" in info['type']:
        # Unions or more-complex higher-kinded types
        # Currently just bail, but I need to address this at some point.
        deco.extend([
                    " of type ",
                    h.E.code(
                        {"class":"idl-code"},
                        info['type']),
                    ])
    else:
        # Everything else
        deco.extend([
                    " of type ",
                    h.E.a(
                        {"data-link-type":"idl-name"},
                        info['type']),
                    ])

    if info['readonly']:
        deco.append(", readonly")
    if info['nullable']:
        deco.append(", nullable")
    if info['default'] is not None:
        deco.append(", defaulting to ")
        deco.append(h.E.code(info['default']))

    return deco
