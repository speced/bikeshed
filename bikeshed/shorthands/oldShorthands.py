from __future__ import annotations

import re

from .. import config, h, t
from .. import messages as m


def transformProductionPlaceholders(doc: t.SpecT) -> None:
    propdescRe = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")  # pylint: disable=redefined-outer-name
    funcRe = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
    atruleRe = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
    typeRe = re.compile(
        r"""
        ^(?:(\S*)/)?
        (\S+)
        (?:\s+
            \[\s*
            (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;))\s*
            ,\s*
            (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;))\s*
            \]\s*
        )?$
        """,
        re.X,
    )
    typeWithArgsRe = re.compile(
        r"""
        ^(?:(\S*)/)?
        (\S+)
        \s*\[([^\]]*)\]\s*$
        """,
        re.X,
    )
    for el in h.findAll("fake-production-placeholder", doc):
        addLineNumber(el)
        text = h.textContent(el)
        h.clearContents(el)
        lt = text
        match = propdescRe.match(lt)
        if match:
            linkFor, lt, linkType = match.groups()
            if linkFor == "":
                linkFor = "/"
            if linkType is None:
                if linkFor is None:
                    linkType = "property"
                else:
                    linkType = "propdesc"
            elif linkType in ("property", "descriptor"):
                pass
            else:
                m.die(
                    f"Shorthand <<{match.group(0)}>> gives type as '{match.group(3)}', but only 'property' and 'descriptor' are allowed.",
                    el=el,
                )
                el.tag = "span"
                el.text = "<‘" + text[1:-1] + "’>"
                continue
            el.tag = "a"
            el.set("data-link-type", linkType)
            el.set("data-lt", lt)
            if linkFor is not None:
                el.set("for", linkFor)
            el.text = "<'" + lt + "'>"
            continue
        match = funcRe.match(lt)
        if match:
            el.tag = "a"
            el.set("data-link-type", "function")
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<" + match.group(2) + ">"
            continue
        match = atruleRe.match(lt)
        if match:
            el.tag = "a"
            el.set("data-link-type", "at-rule")
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<" + match.group(2) + ">"
            continue
        match = typeRe.match(lt)
        if match:
            for_, term, rangeStart, rangeEnd = match.groups()
            el.tag = "a"
            el.set("data-lt", f"<{term}>")
            el.set("data-link-type", "type")
            if for_ is not None:
                el.set("for", for_)
            if rangeStart is not None:
                formattedStart, numStart = parseRangeComponent(rangeStart)
                formattedEnd, numEnd = parseRangeComponent(rangeEnd)
                if formattedStart is None or formattedEnd is None:
                    m.die(f"Shorthand <<{text}>> has an invalid range.", el=el)
                    el.text = f"<{match.group(0)}>"
                elif numStart >= numEnd:
                    m.die(
                        f"Shorthand <<{text}>> has a range whose start is not less than its end.",
                        el=el,
                    )
                    el.text = f"<{term} [{formattedStart},{formattedEnd}]>"
                else:
                    el.text = f"<{term} [{formattedStart},{formattedEnd}]>"
            else:
                el.text = f"<{term}>"
            continue
        match = typeWithArgsRe.match(lt)
        if match:
            for_, term, arg = match.groups()
            el.tag = "a"
            el.set("data-lt", f"<{term}>")
            el.set("data-link-type", "type")
            if "<<" in arg:
                arg = arg.replace("<<", "<").replace(">>", ">")
            el.text = f"<{term}[{arg}]>"
            if for_ is not None:
                el.set("for", for_)
            continue
        m.die(f"Shorthand <<{text}>> does not match any recognized shorthand grammar.", el=el)
        el.tag = "span"
        el.text = el.get("bs-autolink-syntax")
        continue


def parseRangeComponent(val: str) -> tuple[str | None, float | int]:
    sign = ""
    signVal = 1
    num: float | int
    val = val.strip()
    if val[0] in ["-", "−"]:
        sign = "-"
        signVal = -1
        val = val[1:]

    if val.lower() == "infinity":
        val = "∞"
    if val.lower() == "&infin;":
        val = "∞"
    if val == "∞":
        return sign + val, signVal * float("inf")

    match = re.match(r"(\d+)([\w-]*)", val)
    if match is None:
        return None, 0
    (digits, unit) = match.groups()
    num = int(digits) * signVal
    val = str(num)

    return val + unit, num


def transformMaybePlaceholders(doc: t.SpecT) -> None:
    propRe = re.compile(r"^([\w-]+): .+")
    valRe = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")
    for el in h.findAll("fake-maybe-placeholder", doc):
        text = el.get("bs-original-contents")
        assert text is not None
        match = propRe.match(text)
        if match:
            el.tag = "a"
            el.set("class", "css")
            el.set("data-link-type", "propdesc")
            el.set("data-lt", match.group(1))
            continue
        match = valRe.match(text)
        if match:
            if match.group(3) is None:
                linkType = "maybe"
            elif match.group(3) in config.maybeTypes:
                linkType = match.group(3)
            else:
                m.die(
                    f"Shorthand ''{match.group(0)}'' gives type as '{match.group(3)}', but only “maybe” types are allowed.",
                    el=el,
                )
                el.tag = "css"
                continue
            el.tag = "a"
            el.set("class", "css")
            el.set("data-link-type", linkType)
            el.set("data-lt", match.group(2))
            # Three cases to worry about:
            # 1. ''foo/valid-value'' (successful link)
            # 2. ''foo/invalid-value'' (intended link, but unsuccessful)
            # 3. ''foo&0x2f;bar'' (not a link, just wants a slash in text)
            #
            # Handling (1) is easy - on successful link, I'll swap the text
            # for the reffed value.
            # Distinguish (2) from (3) is hard, and they need to be treated
            # differently - (3) should be left alone, while (2) needs to
            # have its text swapped to "invalid-value".
            #
            # Compromise: if it looks *sufficiently close* to a link
            # I'll swap the text ahead of time, to remove any metadata
            # that shouldn't display for a link.
            # Otherwise I'll leave it alone, but if it successfully links
            # based on literal text, it'll swap its text out.
            #
            # "Sufficiently close" means it has a for or type value,
            # and *doesn't* contain what looks like a close tag
            # (which would otherwise look like a for value due to the slash).
            if (match.group(1) is not None or match.group(3) is not None) and "</" not in text:
                h.clearContents(el)
                el.text = match.group(2)
            else:
                el.set("bs-replace-text-on-link-success", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            continue
        el.tag = "css"


def transformAutolinkShortcuts(doc: t.SpecT) -> None:
    # Do the remaining textual replacements

    addedNodes = []

    def transformElement(parentEl: t.ElementT) -> None:
        processContents = h.isElement(parentEl) and not doc.isOpaqueElement(parentEl)
        if not processContents:
            return
        children = h.childNodes(parentEl, clear=True)
        newChildren = []
        for el in children:
            if isinstance(el, str):
                newChildren.extend(transformText(el))
            elif h.isElement(el):
                transformElement(el)
                newChildren.append(el)
        h.appendChild(parentEl, *newChildren, allowEmpty=True)

    def transformText(text: str) -> list[t.NodeT]:
        nodes: list[t.NodeT] = [text]
        if "css" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, propdescRe, propdescReplacer)
        if "dfn" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, dfnRe, dfnReplacer)
            nodes = config.processTextNodes(nodes, abstractRe, abstractReplacer)
        if "http" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, headerRe, headerReplacer)
        if "idl" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, idlRe, idlReplacer)
        if "markup" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, elementRe, elementReplacer)
        if "biblio" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, biblioRe, biblioReplacer)
            nodes = config.processTextNodes(nodes, sectionRe, sectionReplacer)
        if "algorithm" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, varRe, varReplacer)
        if "markdown" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, inlineLinkRe, inlineLinkReplacer)
            nodes = config.processTextNodes(nodes, strongRe, strongReplacer)
            nodes = config.processTextNodes(nodes, emRe, emReplacer)
            nodes = config.processTextNodes(nodes, escapedRe, escapedReplacer)
        for node in nodes:
            if h.isElement(node):
                addedNodes.append(node)
        return nodes

    transformElement(doc.document.getroot())
    for node in addedNodes:
        if h.isElement(node):
            addLineNumber(node)

    for el in h.findAll("var", doc):
        h.fixSurroundingTypography(el)


def transformShorthandElements(doc: t.SpecT) -> None:
    """
    The <l> element can contain any shorthand,
    and works inside of "opaque" elements too,
    unlike ordinary autolinking shorthands.
    """

    def replacer(reg: re.Pattern, rep: t.Callable[[re.Match], t.NodeT], el: t.ElementT, text: str) -> bool:
        match = reg.match(text)
        if match:
            result = rep(match)
            h.replaceNode(el, result)
            if isinstance(result, str):
                return True
            # Move the linking attributes from <l> to the <a>
            attrTarget: t.ElementT | None
            if result.tag == "a":
                h.transferAttributes(el, result)
            else:
                attrTarget = h.find("a", result)
                if attrTarget is not None:
                    h.transferAttributes(el, attrTarget)
            return True
        return False

    for el in h.findAll("l", doc):
        # Autolinks that aren't HTML-parsing-compatible
        # are already specially handled by fixAwkwardCSSShorthands().
        child = h.hasOnlyChild(el)
        if child is not None and child.get("bs-autolink-syntax") is not None:
            h.replaceNode(el, child)
            h.transferAttributes(el, child)
            continue

        text = h.textContent(el)
        if replacer(propdescRe, propdescReplacer, el, text):
            continue
        if replacer(dfnRe, dfnReplacer, el, text):
            continue
        if replacer(idlRe, idlReplacer, el, text):
            continue
        if replacer(elementRe, elementReplacer, el, text):
            continue
        if replacer(biblioRe, biblioReplacer, el, text):
            continue
        if replacer(sectionRe, sectionReplacer, el, text):
            continue
        if replacer(varRe, varReplacer, el, text):
            continue
        m.die(f"<l> element doesn't contain a recognized autolinking syntax:\n{h.outerHTML(el)}", el=el)
        el.tag = "span"


def transformProductionGrammars(doc: t.SpecT) -> None:
    # Link up the various grammar symbols in CSS grammars to their definitions.
    if "css" not in doc.md.markupShorthands:
        return

    hashMultRe = re.compile(r"#{\s*\d+(\s*,(\s*\d+)?)?\s*}")

    def hashMultReplacer(match: re.Match) -> t.ElementT:
        return h.E.a({"data-link-type": "grammar", "data-lt": "#", "for": ""}, match.group(0))

    multRe = re.compile(r"{\s*\d+\s*}")

    def multReplacer(match: re.Match) -> t.ElementT:
        return h.E.a({"data-link-type": "grammar", "data-lt": "{A}", "for": ""}, match.group(0))

    multRangeRe = re.compile(r"{\s*\d+\s*,(\s*\d+)?\s*}")

    def multRangeReplacer(match: re.Match) -> t.ElementT:
        return h.E.a({"data-link-type": "grammar", "data-lt": "{A,B}", "for": ""}, match.group(0))

    simpleRe = re.compile(r"(\?|!|#|\*|\+|\|\||\||&amp;&amp;|&&|,)(?!')")
    # Note the negative-lookahead, to avoid matching delim tokens.

    def simpleReplacer(match: re.Match) -> t.ElementT:
        return h.E.a(
            {"data-link-type": "grammar", "data-lt": match.group(0), "for": ""},
            match.group(0),
        )

    addedNodes = []

    def transformElement(parentEl: t.ElementT) -> None:
        children = h.childNodes(parentEl, clear=True)
        newChildren: list[t.NodesT] = []
        for el in children:
            if isinstance(el, str):
                newChildren.extend(transformText(el))
            elif h.isElement(el):
                if el.tag != "a":
                    # Transforms all add links, which aren't allowed in <a>...
                    transformElement(el)
                newChildren.append(el)
        h.appendChild(parentEl, *newChildren, allowEmpty=True)

    def transformText(text: str) -> t.NodesT:
        nodes: list[t.NodeT] = [text]
        nodes = config.processTextNodes(nodes, hashMultRe, hashMultReplacer)
        nodes = config.processTextNodes(nodes, multRe, multReplacer)
        nodes = config.processTextNodes(nodes, multRangeRe, multRangeReplacer)
        nodes = config.processTextNodes(nodes, simpleRe, simpleReplacer)
        for node in nodes:
            if h.isElement(node):
                addedNodes.append(node)
        return nodes

    for el in h.findAll(".prod", doc):
        transformElement(el)

    for node in addedNodes:
        if h.isElement(node):
            addLineNumber(node)


biblioRe = re.compile(
    r"""
                        (\\)?
                        \[\[
                        (!)?
                        ([\w.+-]+)
                        (\s+(?:current|snapshot|inline|index|direct|obsolete)\s*)*
                        (?:\|([^\]]+))?
                        \]\]""",
    re.X,
)


def biblioReplacer(match: re.Match) -> t.NodeT:
    # Allow escaping things that aren't actually biblio links, by preceding with a \
    escape, bang, term, modifiers, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if bang == "!":
        type = "normative"
    else:
        type = "informative"
    if linkText is None:
        linkText = f"[{term}]"
    attrs = {
        "data-lt": term,
        "data-link-type": "biblio",
        "data-biblio-type": type,
        "bs-autolink-syntax": match.group(0),
    }

    modifiers = re.split(r"\s+", modifiers.strip()) if modifiers is not None else []
    statusCurrent = "current" in modifiers
    statusSnapshot = "snapshot" in modifiers
    if statusCurrent and statusSnapshot:
        m.die(f"Biblio shorthand {match.group(0)} contains *both* 'current' and 'snapshot', please pick one.")
        return t.cast(str, match.group(0))
    elif statusCurrent or statusSnapshot:
        attrs["data-biblio-status"] = "current" if statusCurrent else "snapshot"

    displayInline = "inline" in modifiers
    displayIndex = "index" in modifiers
    displayDirect = "direct" in modifiers
    if (displayInline + displayIndex + displayDirect) > 1:
        m.die(
            f"Biblio shorthand {match.group(0)} contains more than one of 'inline', 'index' and 'direct', please pick one.",
        )
        return t.cast(str, match.group(0))
    elif displayInline:
        attrs["data-biblio-display"] = "inline"
    elif displayIndex:
        attrs["data-biblio-display"] = "index"
    elif displayDirect:
        attrs["data-biblio-display"] = "direct"

    if "obsolete" in modifiers:
        attrs["data-biblio-obsolete"] = ""

    return h.E.a(attrs, linkText)


sectionRe = re.compile(
    r"""
                        (\\)?
                        \[\[
                        ([\w.+-]+)?
                        (?:
                            ((?:\/[\w.+-]*)?(?:\#[\w.+-]+)) |
                            (\/[\w.+-]+)
                        )
                        (?:\|([^\]]+))?
                        \]\]""",
    re.X,
)


def sectionReplacer(match: re.Match) -> t.NodeT:
    escape, spec, section, justPage, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkText is None:
        linkText = ""

    if spec is None:
        # local section link
        return h.E.a(
            {"section": "", "href": section, "bs-autolink-syntax": match.group(0)},
            linkText,
        )
    elif justPage is not None:
        # foreign link, to an actual page from a multipage spec
        return h.E.span(
            {
                "spec-section": justPage + "#",
                "spec": spec,
                "bs-autolink-syntax": match.group(0),
            },
            linkText,
        )
    else:
        # foreign link
        return h.E.span(
            {
                "spec-section": section,
                "spec": spec,
                "bs-autolink-syntax": match.group(0),
            },
            linkText,
        )


propdescRe = re.compile(
    r"""
                        (\\)?
                        '
                        (?:([^\s'|]*)/)?
                        ([\w*-]+)
                        (?:!!([\w-]+))?
                        (?:\|([^']+))?
                        '""",
    re.X,
)


def propdescReplacer(match: re.Match) -> t.NodeT:
    escape, linkFor, lt, linkType, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkFor == "":
        linkFor = "/"
    if lt == "-":
        # Not a valid property actually.
        return "'-'"
    if linkType is None:
        if linkFor is None:
            linkType = "property"
        else:
            linkType = "propdesc"
    elif linkType in ("property", "descriptor"):
        pass
    else:
        m.die(
            f"Shorthand {match.group(0)} gives type as '{linkType}', but only 'property' and 'descriptor' are allowed.",
        )
        return h.E.span(match.group(0))
    if linkText is None:
        linkText = lt
    return h.E.a(
        {
            "data-link-type": linkType,
            "class": "property",
            "for": linkFor,
            "lt": lt,
            "bs-autolink-syntax": match.group(0),
        },
        linkText,
    )


idlRe = re.compile(
    r"""
                    (\\)?
                    {{
                    (?:([^}|]*)/)?
                    ([^}/|]+?)
                    (?:!!([\w-]+))?
                    (?:\|([^}]+))?
                    }}""",
    re.X,
)


def idlReplacer(match: re.Match) -> t.NodeT:
    escape, linkFor, lt, linkType, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkFor == "":
        linkFor = "/"
    if linkType is None:
        linkType = "idl"
    elif linkType in config.idlTypes:
        pass
    else:
        m.die(
            f"Shorthand {match.group(0)} gives type as '{linkType}', but only IDL types are allowed.",
        )
        return h.E.span(match.group(0))
    if linkText is None:
        if lt.startswith("constructor(") and linkFor and linkFor != "/":
            # make {{Foo/constructor()}} output as "Foo()" so you know what it's linking to.
            linkText = linkFor + lt[11:]
        else:
            linkText = lt
    return h.E.code(
        {"class": "idl", "nohighlight": ""},
        h.E.a(
            {
                "data-link-type": linkType,
                "for": linkFor,
                "lt": lt,
                "bs-autolink-syntax": match.group(0),
            },
            linkText,
        ),
    )


dfnRe = re.compile(
    r"""
                    (\\)?
                    \[=
                    (?!\s)(?:([^=|]*)/)?
                    ([^\"=]+?)
                    (?:\|([^\"=]+))?
                    =\]""",
    re.X,
)


def dfnReplacer(match: re.Match) -> t.NodeT:
    escape, linkFor, lt, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkFor == "":
        linkFor = "/"
    if linkText is None:
        linkText = lt
    return h.E.a(
        {
            "data-link-type": "dfn",
            "for": linkFor,
            "lt": lt,
            "bs-autolink-syntax": match.group(0),
        },
        linkText,
    )


abstractRe = re.compile(
    r"""
                        (\\)?
                        \[\$
                        (?!\s)(?:([^$|]*)/)?
                        ([^\"$]+?)
                        (?:\|([^\"$]+))?
                        \$\]""",
    re.X,
)


def abstractReplacer(match: re.Match) -> t.NodeT:
    escape, linkFor, lt, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkFor == "":
        linkFor = "/"
    if linkText is None:
        linkText = lt
    return h.E.a(
        {
            "data-link-type": "abstract-op",
            "for": linkFor,
            "lt": lt,
            "bs-autolink-syntax": match.group(0),
        },
        linkText,
    )


elementRe = re.compile(
    r"""
                        (?P<escape>\\)?
                        <{
                        (?P<element>[\w*-]+)
                        (?:/
                            (?P<attr>[\w*-]+)
                            (?:/(?P<value>[^}!|]+))?
                        )?
                        (?:!!(?P<linkType>[\w-]+))?
                        (?:\|(?P<linkText>[^}]+))?}>""",
    re.X,
)


def elementReplacer(match: re.Match) -> t.NodeT:
    groupdict = match.groupdict()
    if groupdict["escape"]:
        return t.cast(str, match.group(0))[1:]
    if groupdict["attr"] is None and groupdict["value"] is None:
        linkType = "element"
        linkFor = None
        lt = groupdict["element"]
    elif groupdict["value"] is None:
        linkType = "element-sub"
        linkFor = groupdict["element"]
        lt = groupdict["attr"]
    else:
        linkType = "attr-value"
        linkFor = groupdict["element"] + "/" + groupdict["attr"]
        lt = groupdict["value"]
    if groupdict["linkType"] is not None:
        linkType = groupdict["linkType"]
    if groupdict["linkText"] is not None:
        linkText = groupdict["linkText"]
    else:
        linkText = lt
    return h.E.code(
        {},
        h.E.a(
            {
                "data-link-type": linkType,
                "for": linkFor,
                "lt": lt,
                "bs-autolink-syntax": match.group(0),
            },
            linkText,
        ),
    )


varRe = re.compile(
    r"""
                    (\\)?
                    \|
                    (\w(?:[\w\s-]*\w)?)
                    \|""",
    re.X,
)


def varReplacer(match: re.Match) -> t.NodeT:
    escape, varText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    return h.E.var({"bs-autolink-syntax": match.group(0)}, varText)


inlineLinkRe = re.compile(
    r"""
                    (\\)?
                    \[([^\]]+)\]
                    \(\s*
                    (
                        (?:\\[()]|[^\s"()])*
                        (?:
                            # Optional top-level paren group
                            (?:\((?:\\[()]|[^\s"()])*\))
                            (?:\\[()]|[^\s"()])*
                        )*
                    )
                    \s*(?:"([^"]*)")?\s*
                    \)""",
    re.X,
)


def inlineLinkReplacer(match: re.Match) -> t.NodeT:
    _, text, href, title = match.groups()
    # Remove escapes from parens.
    href = re.sub(r"\\\(", "(", href)
    href = re.sub(r"\\\)", ")", href)
    if title:
        attrs = {"href": href, "title": title}
    else:
        attrs = {"href": href}
    attrs["bs-autolink-syntax"] = match.group(0)
    return h.E.a(attrs, text)


strongRe = re.compile(
    r"""
                    # **, not escaped, followed by non-space
                    (?<!\\)\*\*(?!\s)
                    # Escaped **, or not a ** at all
                    ((?:[^*]|\\\*\*|\s\*\*|\*[^*])+)
                    # **, not escaped, preceded by non-space
                    (?<!\s|\\)\*\*
                    """,
    re.X,
)


def strongReplacer(match: re.Match) -> t.NodeT:
    text = t.cast(str, match.group(1)).replace("\\**", "**")
    return h.E.strong({"bs-autolink-syntax": match.group(0)}, text)


emRe = re.compile(
    r"""
                    # *, not escaped, followed by non-space
                    (?<!\\)\*(?!\s)
                    # Escaped *, or not a * at all
                    ((?:[^*]|\\\*|\s\*)+)
                    # *, not escaped, preceded by non-space
                    (?<!\s|\\)\*
                    """,
    re.X,
)


def emReplacer(match: re.Match) -> t.NodeT:
    text = t.cast(str, match.group(1)).replace("\\*", "*")
    return h.E.em({"bs-autolink-syntax": match.group(0)}, text)


escapedRe = re.compile(r"\\\*")


def escapedReplacer(match: re.Match) -> t.NodeT:  # pylint: disable=unused-argument
    return "*"


headerRe = re.compile(
    r"""
                    (\\)?
                    \[:
                    (:?[^()<>@,;:\\"/\[\]?={}\s|]+)
                    (?:\|((?:(?!:\]).)+))?
                    :\]""",
    re.X,
)


def headerReplacer(match: re.Match) -> t.NodeT:
    escape, lt, linkText = match.groups()
    if escape:
        return t.cast(str, match.group(0))[1:]
    if linkText is None:
        linkText = lt
    attrs = {
        "data-link-type": "http-header",
        "for": "/",
        "lt": lt,
        "bs-autolink-syntax": match.group(0),
    }
    return h.E.span(
        {},
        "`",
        h.E.code({}, h.E.a(attrs, linkText)),
        "`",
    )


def addLineNumber(el: t.ElementT) -> None:
    if el.get("bs-line-number"):
        return
    line = h.approximateLineNumber(el)
    if line is not None:
        el.set("bs-line-number", line)
