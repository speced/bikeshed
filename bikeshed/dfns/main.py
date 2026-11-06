from __future__ import annotations

import re

from .. import config, h, t
from .. import messages as m


def processDfns(doc: t.SpecT) -> None:
    dfns = h.findAll(config.dfnElementsSelector, doc)
    classifyDfns(doc, dfns)
    h.fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(doc, (dfn for dfn in dfns if dfn.get("id") is not None))


def determineDfnType(doc: t.SpecT, dfn: t.ElementT, inferCSS: bool = False) -> str:
    # 1. Look at data-dfn-type
    if dfn.get("data-dfn-type"):
        return t.cast(str, dfn.get("data-dfn-type"))
    # 2. Look for a prefix on the id
    if dfn.get("id"):
        id = t.cast(str, dfn.get("id"))
        for prefix, type in config.dfnClassToType.items():
            if id.startswith(prefix):
                return type
    # 3. Look for a class or data-dfn-type on the ancestors
    for ancestor in dfn.iterancestors():
        if ancestor.get("data-dfn-type"):
            return t.cast(str, ancestor.get("data-dfn-type"))
        for cls, type in config.dfnClassToType.items():
            if h.hasClass(doc, ancestor, cls):
                return type
            if h.hasClass(doc, ancestor, "idl") and not h.hasClass(doc, ancestor, "extract"):
                return "interface"
    # 4. Introspect on the text
    if inferCSS:
        text = h.textContent(dfn)
        if text[0:1] == "@":
            return "at-rule"
        if (
            len(dfn) == 1
            and dfn[0].get("data-link-type") == "maybe"
            and h.emptyText(dfn.text)
            and h.emptyText(dfn[0].tail)
        ):
            return "value"
        if text[0:1] == "<" and text[-1:] == ">":
            if "[" in text and "]" in text:
                # has a range, *must* be a value
                return "value"
            if "@" in text:
                # Trying to dfn an at-rule production
                m.die(
                    "CSS at-rules must be defined in prose, with <dfn>@foo</dfn>. Remove the dfn from this grammar term.",
                    el=dfn,
                )
            elif "(" in text and ")" in text:
                # Trying to define a function production
                m.die(
                    "CSS functions must be defined in prose, with <dfn>foo(args)</dfn>. Remove the dfn from this grammar term.",
                    el=dfn,
                )
            elif "''" in text:
                m.die(
                    "CSS values must be defined in prose, with <dfn value>foo</dfn>. Remove the dfn from this grammar term.",
                    el=dfn,
                )
            elif "'" in text:
                m.die(
                    "CSS properties must be defined in prose, with a <pre class=propdef> table or <dfn property>foo</dfn>. Remove the dfn from this grammar term.",
                    el=dfn,
                )
            # Regardless of errors above, return "type""
            return "type"
        if text[0:1] == ":":
            return "selector"
        if re.match(r"^[\w-]+\(.*\)$", text) and not (dfn.get("id") or "").startswith("dom-"):
            return "function"
    # 5. Assume it's a "dfn"
    return "dfn"


def classifyDfns(doc: t.SpecT, dfns: list[t.ElementT]) -> None:
    dfnTypeToPrefix = {v: k for k, v in config.dfnClassToType.items()}
    for el in dfns:
        dfnType = determineDfnType(doc, el, inferCSS=doc.md.inferCSSDfns)
        if dfnType not in config.dfnTypes:
            m.die(f"Unknown dfn type '{dfnType}':\n{h.outerHTML(el)}", el=el)
            continue
        dfnFor = h.treeAttr(el, "data-dfn-for")
        primaryDfnText = h.firstLinkTextFromElement(el)
        if primaryDfnText is None:
            m.die(f"Dfn has no linking text:\n{h.outerHTML(el)}", el=el)
            continue
        if len(primaryDfnText) > 300:
            # Almost certainly accidentally missed the end tag
            m.warn(
                f"Dfn has extremely long text - did you forget the </dfn> tag?\n{h.outerHTML(el)}",
                el=el,
            )
        # Check for invalid fors, as it's usually some misnesting.
        if dfnFor and dfnType in config.typesNotUsingFor:
            m.die(
                f"'{dfnType}' definitions don't use a 'for' attribute, but this one claims it's for '{dfnFor}' (perhaps inherited from an ancestor). This is probably a markup error.\n{h.outerHTML(el)}",
                el=el,
            )
        # Push the dfn type down to the <dfn> itself.
        if el.get("data-dfn-type") is None:
            el.set("data-dfn-type", dfnType)
        # Push the for value too.
        if dfnFor:
            el.set("data-dfn-for", dfnFor)
        elif dfnType in config.typesUsingFor:
            m.die(
                f"'{dfnType}' definitions need to specify what they're for.\nAdd a 'for' attribute to {h.outerHTML(el)}, or add 'dfn-for' to an ancestor.",
                el=el,
            )
            continue
        # Some error checking
        if dfnType in config.functionishTypes:
            if not re.search(r"\(.*\)$", primaryDfnText):
                m.die(
                    f"Function/methods must end with a () arglist in their linking text. Got '{primaryDfnText}'.\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            if not re.match(r"^[\w\[\]-]+\s*\(", primaryDfnText):
                m.die(
                    f"Function/method names can only contain alphanums, underscores, dashes, or []. Got '{primaryDfnText}'.\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
            if el.get("data-lt") is None:
                match = re.match(r"^([\w\[\]-]+)\(.*\)$", primaryDfnText)
                if dfnType == "function" and match:
                    # CSS function, define it with no args in the text
                    primaryDfnText = match.group(1) + "()"
                    el.set("data-lt", primaryDfnText)
                elif dfnType in config.idlTypes:
                    # IDL methodish construct, ask the widlparser what it should have.
                    # If the method isn't in any IDL, this tries its best to normalize it anyway.
                    names = list(doc.widl.normalized_method_names(primaryDfnText, el.get("data-dfn-for")))
                    primaryDfnText = names[0]
                    el.set("data-lt", "|".join(names))
                else:
                    m.die(
                        f"BIKESHED ERROR: Unhandled functionish type '{dfnType}' in classifyDfns. Please report this to Bikeshed's maintainer.",
                        el=el,
                    )
        # If type=argument, try to infer what it's for.
        if dfnType == "argument" and el.get("data-dfn-for") is None:
            parent = h.parentElement(el)
            assert parent is not None
            parentFor = parent.get("data-dfn-for")
            if parent.get("data-dfn-type") in config.functionishTypes and parentFor is not None:
                dfnFor = ", ".join(
                    parentFor + "/" + name
                    for name in doc.widl.normalized_method_names(h.textContent(parent), parentFor)
                )
            elif h.treeAttr(el, "data-dfn-for") is None:
                m.die(
                    f"'argument' dfns need to specify what they're for, or have it be inferrable from their parent. Got:\n{h.outerHTML(el)}",
                    el=el,
                )
                continue
        # Automatically fill in id if necessary.
        if el.get("id") is None:
            if dfnFor:
                singleFor: str | None = config.splitForValues(dfnFor)[0]
            else:
                singleFor = None
            if dfnType in config.functionishTypes.intersection(config.idlTypes):
                match = re.match(r"[^(]*", primaryDfnText)
                if match:
                    parenlessID = match.group(0)
                else:
                    parenlessID = primaryDfnText
                id = config.simplifyText(
                    "{_for}-{id}".format(
                        _for=singleFor,
                        id=parenlessID + "()",
                    ),
                )
                el.set(
                    "data-alternate-id",
                    config.simplifyText(f"dom-{singleFor}-{primaryDfnText}"),
                )
                if primaryDfnText.startswith("[["):
                    # Slots get their identifying [] stripped from their ID,
                    # so gotta dedup them some other way.
                    id += "-slot"
                    el.set(
                        "data-alternate-id",
                        "{}-slot".format(el.get("data-alternate-id")),
                    )
            else:
                if dfnFor:
                    id = config.simplifyText(f"{singleFor}-{primaryDfnText}")
                else:
                    id = config.simplifyText(primaryDfnText)
            if dfnType == "dfn":
                pass
            elif dfnType == "interface":
                pass
            elif dfnType == "event":
                # Special case 'event' because it needs a different format from IDL types
                id = config.simplifyText(f"{dfnTypeToPrefix[dfnType]}-{id}")
            elif dfnType == "attribute" and primaryDfnText.startswith("[["):
                # Slots get their identifying [] stripped from their ID, so gotta dedup them some other way.
                id = config.simplifyText(f"dom-{id}-slot")
            elif dfnType in config.idlTypes.intersection(config.typesUsingFor):
                id = config.simplifyText(f"dom-{id}")
            else:
                id = f"{dfnTypeToPrefix[dfnType]}-{id}"
            el.set("id", h.safeID(doc, id))
        # Set lt if it's not set,
        # and doing so won't mess with anything else.
        if el.get("data-lt") is None and "|" not in primaryDfnText:
            el.set("data-lt", primaryDfnText)
        # Push export/noexport down to the definition
        if el.get("data-export") is None and el.get("data-noexport") is None:
            attr, _ = h.closestAttr(el, "data-export", "data-noexport")
            if attr is not None:
                el.set(attr, "")
            else:
                if dfnType == "dfn" or dfnType in config.cddlTypes:
                    el.set("data-noexport", "by-default")
                else:
                    el.set("data-export", "by-default")
        # If it's an code-ish type such as IDL,
        # and doesn't already have a sole <code> child,
        # wrap the contents in a <code>.
        if config.linkTypeIn(dfnType, "codelike"):
            child = h.hasOnlyChild(el)
            if child is not None and child.tag == "code":
                continue
            if el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                # Don't wrap headings, it looks bad.
                continue
            h.wrapContents(el, h.E.code())
