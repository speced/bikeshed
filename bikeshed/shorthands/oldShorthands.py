from __future__ import annotations

import re

from .. import config, h, t


def transformMarkdownIB(doc: t.SpecT) -> None:
    # Do the remaining textual replacements

    addedNodes = []

    if "markdown-inline" not in doc.md.markupShorthands:
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
        if "markdown-inline" in doc.md.markupShorthands:
            nodes = config.processTextNodes(nodes, strongRe, strongReplacer)
            nodes = config.processTextNodes(nodes, emRe, emReplacer)
            nodes = config.processTextNodes(nodes, escapedRe, escapedReplacer)
        for node in nodes:
            if h.isElement(node):
                addedNodes.append(node)
        return nodes

    transformElement(doc.document)
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


def strongReplacer(match: t.Match) -> t.NodeT:
    text = match.group(1).replace("\\**", "**")
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


def emReplacer(match: t.Match) -> t.NodeT:
    text = match.group(1).replace("\\*", "*")
    return h.E.em({"bs-autolink-syntax": match.group(0)}, text)


escapedRe = re.compile(r"\\\*")


def escapedReplacer(match: t.Match) -> t.NodeT:  # pylint: disable=unused-argument
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
