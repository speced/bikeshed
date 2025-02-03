from __future__ import annotations

import re

from .. import config, h, t


def transformMarkdownIB(doc: t.SpecT) -> None:
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


def addLineNumber(el: t.ElementT) -> None:
    if el.get("bs-line-number"):
        return
    line = h.approximateLineNumber(el)
    if line is not None:
        el.set("bs-line-number", line)
