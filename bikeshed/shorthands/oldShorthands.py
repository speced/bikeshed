from __future__ import annotations

import re

from .. import config, h, t
from .. import messages as m


def transformAutolinkShortcuts(doc: t.SpecT) -> None:
    # Do the remaining textual replacements

    addedNodes = []

    if "markdown" not in doc.md.markupShorthands:
        return

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
        if "markdown" in doc.md.markupShorthands:
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
        # The shorthands that get handled in the parser just need
        # their attributes moved over. (Eventually this'll be all
        # of them).
        alreadyDone = h.find("[bs-autolink-syntax]", el)
        if alreadyDone is not None:
            h.transferAttributes(el, alreadyDone)
            h.replaceWithContents(el)
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
