# pylint: disable=unused-argument

from __future__ import annotations

import dataclasses
import itertools
import re

from .. import h, t
from .. import messages as m
from . import legacy
from .grammarmanager import HighlightGrammarManager


def addSyntaxHighlighting(doc: t.SpecT) -> None:
    if doc.md.slimBuildArtifact:
        return
    normalizeHighlightMarkers(doc)

    usedGrammarLangs: set[str] = set()
    warnedLegacyLangs: set[str] = set()

    for gName, gPath in doc.md.highlightGrammars.items():
        doc.highlightGrammars.addGrammarPath(gName, gPath)

    for el in h.collectSyntaxHighlightables(doc.body):
        # Find whether to highlight, and what the lang is
        lang = determineHighlightLang(doc, el)
        if lang is False:
            # Element was already highlighted, but needs styles
            doc.extraJC.addLegacySyntaxHighlighting()
        elif lang:
            if doc.highlightGrammars.hasGrammar(lang):
                usedGrammarLangs.add(lang)
                el.set("highlight", lang)
                h.addClass(doc, el, "highlight")
            else:
                if lang not in doc.md.legacyHighlights and lang not in warnedLegacyLangs:
                    warnedLegacyLangs.add(lang)
                    m.warn(
                        f"Highlighting '{lang}' uses the legacy slow highlighter. Recommend finding a TextMate grammar and using it with 'Highlight Grammar', or filing an issue on Bikeshed; see https://speced.github.io/bikeshed/#missing-languages.",
                        el=el,
                    )
                legacy.highlightEl(doc, el, lang)
                doc.extraJC.addLegacySyntaxHighlighting()

        # Find whether to add line numbers
        ln = determineLineNumbers(doc, el)
        if ln.addNumbers or ln.highlights:
            addLineWrappers(doc, el, ln)
            if ln.addNumbers:
                doc.extraJC.addLineNumbers()
            if ln.highlights:
                doc.extraJC.addLineHighlighting()

    if usedGrammarLangs:
        neededGrammars = doc.highlightGrammars.getGrammarsForLanguages(usedGrammarLangs)
        theme = doc.md.highlightTheme
        doc.extraJC.addSyntaxHighlighting(theme=theme, grammars=neededGrammars)


def determineHighlightLang(doc: t.SpecT, el: t.ElementT) -> str | t.Literal[False] | None:
    # Either returns a normalized highlight lang,
    # False indicating the element was already highlighted,
    # or None indicating the element shouldn't be highlighted.
    attr, lang = h.closestAttr(el, "nohighlight", "highlight")
    lang = normalizeLanguageName(lang)
    if el.tag == "code":
        # If <pre> triggers highlighting, don't *also* trigger it
        # on the <pre><code> child.
        parent = h.parentElement(el)
        assert parent is not None
        if h.tagName(parent) == "pre" and determineHighlightLang(doc, parent):
            return None
    if lang == "webidl" and el.tag == "code" and h.tagName(h.parentElement(el)) == "dfn":
        # No such thing as a dfn that needs to be WebIDL-highlighted.
        # This is probably happening from a <dfn idl-type> inside a <pre highlight=idl>.
        return None
    if attr == "nohighlight":
        return None
    if attr == "highlight":
        return lang
    # Highlight-by-default, if applicable.
    if el.tag in ["pre", "xmp"]:
        if h.hasClass(doc, el, "idl"):
            return "webidl"
        if h.hasClass(doc, el, "cddl"):
            return "cddl"
    return doc.md.defaultHighlight


@dataclasses.dataclass
class LineNumberOptions:
    # Whether to add line numbers
    addNumbers: bool
    # What line number the snippet starts at
    startingLine: int
    # Which lines, if any, to specially highlight
    # (relative to the starting line)
    highlights: set[int]


def determineLineNumbers(doc: t.SpecT, el: t.ElementT) -> LineNumberOptions:
    lAttr, _ = h.closestAttr(el, "no-line-numbers", "line-numbers")
    if lAttr == "no-line-numbers" or el.tag == "code":
        addLineNumbers = False
    elif lAttr == "line-numbers":
        addLineNumbers = True
    else:
        addLineNumbers = doc.md.lineNumbers

    ls = el.get("line-start")
    if ls is None:
        lineStart = 1
    else:
        try:
            lineStart = int(ls)
        except ValueError:
            m.die(f"line-start attribute must have an integer value. Got '{ls}'.", el=el)
            lineStart = 1

    lh = el.get("line-highlight")
    lineHighlights = set()
    if lh is None:
        pass
    else:
        lh = re.sub(r"\s*", "", lh)
        for item in lh.split(","):
            if "-" in item:
                # Range, format of DDD-DDD
                low, _, high = item.partition("-")
                try:
                    lowVal = int(low)
                    highVal = int(high)
                except ValueError:
                    m.die(f"Error parsing line-highlight range '{item}' - must be `int-int`.", el=el)
                    continue
                if lowVal >= highVal:
                    m.die(f"line-highlight ranges must be well-formed lo-hi - got '{item}'.", el=el)
                    continue
                lineHighlights.update(list(range(lowVal, highVal + 1)))
            else:
                try:
                    itemVal = int(item)
                except ValueError:
                    m.die(f"Error parsing line-highlight value '{item}' - must be integers.", el=el)
                    continue
                lineHighlights.add(itemVal)

    return LineNumberOptions(addLineNumbers, lineStart, lineHighlights)


def normalizeLanguageName(lang: str | None) -> str | None:
    if lang is None:
        return None
    mgr = HighlightGrammarManager()
    return mgr.normalizeLanguage(lang)


def normalizeHighlightMarkers(doc: t.SpecT) -> None:
    # Translate Prism-style highlighting into Pygment-style
    for el in h.findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search(r"(?:lang|language)-(\w+)", el.get("class") or "")
        if match:
            el.set("highlight", match.group(1))


def addLineWrappers(doc: t.SpecT, el: t.ElementT, options: LineNumberOptions) -> t.ElementT:
    # Wrap everything between each top-level newline with a line tag.
    # Add an attr for the line number, and if needed, the end line.
    for nodes in splitNodesByLinebreaks(h.childNodes(el, clear=True)):
        h.appendChild(
            el,
            h.E.span({"class": "line-no"}),
            h.E.span({"class": "line"}, *nodes),
        )
    # Number the lines
    lineNumber = options.startingLine
    for lineNo, node in t.cast("tuple[t.ElementT, t.ElementT]", grouper(h.childNodes(el), 2)):
        if options.addNumbers or lineNumber in options.highlights:
            lineNo.set("data-line", str(lineNumber))
        if lineNumber in options.highlights:
            h.addClass(doc, node, "highlight-line")
            h.addClass(doc, lineNo, "highlight-line")
        internalNewlines = countInternalNewlines(node)
        if internalNewlines:
            for i in range(1, internalNewlines + 1):
                if (lineNumber + i) in options.highlights:
                    h.addClass(doc, lineNo, "highlight-line")
                    h.addClass(doc, node, "highlight-line")
                    lineNo.set("data-line", str(lineNumber))
            lineNumber += internalNewlines
            if options.addNumbers:
                lineNo.set("data-line-end", str(lineNumber))
        lineNumber += 1
    h.addClass(doc, el, "line-numbered")
    return el


def splitNodesByLinebreaks(nodes: t.NodeListT) -> t.Iterator[list[t.NodeT]]:
    line: list[t.NodeT] = []
    for node in nodes:
        if isinstance(node, str):
            while True:
                if "\n" in node:
                    pre, _, post = node.partition("\n")
                    line.append(pre)
                    yield line
                    line = []
                    node = post
                else:
                    line.append(node)
                    break
        else:
            line.append(node)
    if line:
        if len(line) == 1 and line[0] == "":
            # If the file ended with a newline,
            # the line array will just be a single empty string at this point;
            # don't emit that.
            return
        yield line


def countInternalNewlines(el: t.ElementT) -> int:
    count = 0
    for node in h.childNodes(el):
        if h.isElement(node):
            count += countInternalNewlines(node)
        else:
            assert isinstance(node, str)
            count += node.count("\n")
    return count


def grouper[T](
    iterable: t.Sequence[T],
    n: int,
    fillvalue: T | None = None,
) -> itertools.zip_longest[tuple[T | None, ...]]:
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)
