# pylint: disable=unused-argument

from __future__ import annotations

import collections
import dataclasses
import itertools
import re

from .. import h, t
from .. import messages as m

if t.TYPE_CHECKING:
    import pygments

    from .. import lexers

    T = t.TypeVar("T")


def loadCSSLexer() -> lexers.CSSLexer:
    from ..lexers import CSSLexer

    return CSSLexer()


customLexers: dict[str, pygments.lexer.Lexer] = {"css": loadCSSLexer}


@dataclasses.dataclass
class ColoredText:
    text: str
    # None indicates uncolored text
    color: str | None


def addSyntaxHighlighting(doc: t.SpecT) -> None:
    if doc.md.slimBuildArtifact:
        return
    normalizeHighlightMarkers(doc)

    for el in h.findAll("xmp, pre, code", doc):
        # Find whether to highlight, and what the lang is
        lang = determineHighlightLang(doc, el)
        if lang is False:
            # Element was already highlighted, but needs styles
            doc.extraJC.addSyntaxHighlighting()
        elif lang:
            highlightEl(doc, el, lang)
            doc.extraJC.addSyntaxHighlighting()
        # Find whether to add line numbers
        ln = determineLineNumbers(doc, el)
        if ln.addNumbers or ln.highlights:
            addLineWrappers(doc, el, ln)
            if ln.addNumbers:
                doc.extraJC.addLineNumbers()
            if ln.highlights:
                doc.extraJC.addLineHighlighting()


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
        if h.tagName(parent) == "pre" and h.isOnlyChild(el) and determineHighlightLang(doc, parent):
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
    if el.tag in ["pre", "xmp"] and h.hasClass(doc, el, "idl"):
        return "webidl"
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


def highlightEl(doc: t.SpecT, el: t.ElementT, lang: str) -> None:
    text = h.textContent(el)
    coloredText: t.Deque[ColoredText] | None
    if lang == "webidl":
        coloredText = highlightWithWebIDL(text, el=el)
    else:
        coloredText = highlightWithPygments(text, lang, el=el)
    if coloredText is not None:
        mergeHighlighting(el, coloredText)
        h.addClass(doc, el, "highlight")


def highlightWithWebIDL(text: str, el: t.ElementT) -> t.Deque[ColoredText] | None:
    """
    Trick the widlparser emitter,
    which wants to output HTML via wrapping with start/end tags,
    into instead outputting a stack-based text format.
    A \1 indicates a new stack push;
    the text between the \1 and the \2 is the attr to be pushed.
    A \3 indicates a stack pop.
    All other text is colored with the attr currently on top of the stack.
    """
    import widlparser
    from widlparser import parser

    class IDLUI:
        def warn(self, msg: str) -> None:
            m.die(msg.rstrip())

        def note(self, msg: str) -> None:
            m.warn(msg.rstrip())

    class HighlightMarker:
        # Just applies highlighting classes to IDL stuff.

        def markup_type_name(
            self,
            text: str,
            construct: widlparser.constructs.Construct,
        ) -> tuple[str | None, str | None]:
            return ("\1n\2", "\3")

        def markup_name(self, text: str, construct: widlparser.constructs.Construct) -> tuple[str | None, str | None]:
            return ("\1g\2", "\3")

        def markup_keyword(
            self,
            text: str,
            construct: widlparser.constructs.Construct,
        ) -> tuple[str | None, str | None]:
            return ("\1b\2", "\3")

        def markup_enum_value(
            self,
            text: str,
            construct: widlparser.constructs.Construct,
        ) -> tuple[str | None, str | None]:
            return ("\1s\2", "\3")

    if "\1" in text or "\2" in text or "\3" in text:
        m.die(
            "WebIDL text contains some U+0001-0003 characters, which are used by the highlighter. This block can't be highlighted. :(",
            el=el,
        )
        return None

    widl = parser.Parser(text, IDLUI())
    return coloredTextFromWidlStack(str(widl.markup(t.cast(widlparser.protocols.Marker, HighlightMarker()))))


def coloredTextFromWidlStack(widlText: str) -> t.Deque[ColoredText]:
    coloredTexts: t.Deque[ColoredText] = collections.deque()
    colors: list[str] = []
    currentText = ""
    mode = "text"
    for char in widlText:
        if mode == "text":
            if char == "\1":
                if colors:
                    coloredTexts.append(ColoredText(currentText, colors[-1]))
                else:
                    coloredTexts.append(ColoredText(currentText, None))
                currentText = ""
                mode = "color"
                continue
            if char == "\2":
                assert False, r"Encountered a \2 while in text mode"
                continue
            if char == "\3":
                assert colors, r"Encountered a \3 without any colors on stack."
                coloredTexts.append(ColoredText(currentText, colors.pop()))
                currentText = ""
                continue

            currentText += char
        elif mode == "color":
            if char == "\1":
                assert False, r"Encountered a \1 while in color mode."
                continue
            if char == "\2":
                colors.append(currentText)
                currentText = ""
                mode = "text"
                continue
            if char == "\3":
                assert False, r"Encountered a \3 while in color mode."
                continue
            currentText += char
            continue
    assert len(colors) == 0, r"Colors stack wasn't empty at end, \1 and \3s aren't balanced?"
    if currentText:
        coloredTexts.append(ColoredText(currentText, None))
    return coloredTexts


def highlightWithPygments(text: str, lang: str, el: t.ElementT) -> t.Deque[ColoredText] | None:
    import pygments  # pylint: disable=redefined-outer-name
    from pygments.formatters.other import RawTokenFormatter

    lexer = lexerFromLang(lang)
    if lexer is None:
        m.die(
            f"'{lang}' isn't a known syntax-highlighting language. See http://pygments.org/docs/lexers/. Seen on:\n"
            + h.outerHTML(el),
            el=el,
        )
        return None
    rawTokens = str(
        pygments.highlight(text, lexer, RawTokenFormatter()),
        encoding="utf-8",
    )
    coloredText = coloredTextFromRawTokens(rawTokens)
    return coloredText


def mergeHighlighting(el: t.ElementT, coloredText: t.Sequence[ColoredText]) -> None:
    # Merges a tree of Pygment-highlighted HTML
    # into the original element's markup.
    # This works because Pygment effectively colors each character with a highlight class,
    # merging them together into runs of text for convenience/efficiency only;
    # the markup structure is a flat list of sibling elements containing raw text
    # (and maybe some un-highlighted raw text between them).
    def createEl(color: str, text: str) -> t.ElementT:
        return h.createElement("c-", {color: ""}, text)

    def colorizeEl(el: t.ElementT, coloredText: t.Deque[ColoredText]) -> t.ElementT:
        for node in h.childNodes(el, clear=True):
            if h.isElement(node):
                h.appendChild(el, colorizeEl(node, coloredText))
            else:
                assert isinstance(node, str)
                h.appendChild(el, *colorizeText(node, coloredText), allowEmpty=True)
        return el

    def colorizeText(text: str, coloredText: t.Deque[ColoredText]) -> list[t.NodeT]:
        nodes: list[t.NodeT] = []
        while text and coloredText:
            nextColor = coloredText.popleft()
            if len(nextColor.text) <= len(text):
                if nextColor.color is None:
                    nodes.append(nextColor.text)
                else:
                    nodes.append(createEl(nextColor.color, nextColor.text))
                text = text[len(nextColor.text) :]
            else:  # Need to use only part of the nextColor node
                if nextColor.color is None:
                    nodes.append(text)
                else:
                    nodes.append(createEl(nextColor.color, text))
                # Truncate the nextColor text to what's unconsumed,
                # and put it back into the deque
                nextColor = ColoredText(nextColor.text[len(text) :], nextColor.color)
                coloredText.appendleft(nextColor)
                text = ""
        return nodes

    # Remove empty colored texts
    filtered = collections.deque(x for x in coloredText if x.text)
    colorizeEl(el, filtered)


def coloredTextFromRawTokens(text: str) -> t.Deque[ColoredText]:
    colorFromName = {
        "Token.Comment": "c",
        "Token.Keyword": "k",
        "Token.Literal": "l",
        "Token.Name": "n",
        "Token.Operator": "o",
        "Token.Punctuation": "p",
        "Token.Comment.Multiline": "d",
        "Token.Comment.Preproc": "cp",
        "Token.Comment.Single": "c1",
        "Token.Comment.Special": "cs",
        "Token.Keyword.Constant": "kc",
        "Token.Keyword.Declaration": "a",
        "Token.Keyword.Namespace": "kn",
        "Token.Keyword.Pseudo": "kp",
        "Token.Keyword.Reserved": "kr",
        "Token.Keyword.Type": "b",
        "Token.Literal.Date": "ld",
        "Token.Literal.Number": "m",
        "Token.Literal.String": "s",
        "Token.Name.Attribute": "e",
        "Token.Name.Class": "nc",
        "Token.Name.Constant": "no",
        "Token.Name.Decorator": "nd",
        "Token.Name.Entity": "ni",
        "Token.Name.Exception": "ne",
        "Token.Name.Function": "nf",
        "Token.Name.Label": "nl",
        "Token.Name.Namespace": "nn",
        "Token.Name.Property": "py",
        "Token.Name.Tag": "f",
        "Token.Name.Variable": "g",
        "Token.Operator.Word": "ow",
        "Token.Literal.Number.Bin": "mb",
        "Token.Literal.Number.Float": "mf",
        "Token.Literal.Number.Hex": "mh",
        "Token.Literal.Number.Integer": "mi",
        "Token.Literal.Number.Oct": "mo",
        "Token.Literal.String.Backtick": "sb",
        "Token.Literal.String.Char": "sc",
        "Token.Literal.String.Doc": "sd",
        "Token.Literal.String.Double": "u",
        "Token.Literal.String.Escape": "se",
        "Token.Literal.String.Heredoc": "sh",
        "Token.Literal.String.Interpol": "si",
        "Token.Literal.String.Other": "sx",
        "Token.Literal.String.Regex": "sr",
        "Token.Literal.String.Single": "t",
        "Token.Literal.String.Symbol": "ss",
        "Token.Name.Variable.Class": "vc",
        "Token.Name.Variable.Global": "vg",
        "Token.Name.Variable.Instance": "vi",
        "Token.Literal.Number.Integer.Long": "il",
    }

    def addCtToList(list: t.Deque[ColoredText], ct: ColoredText) -> None:
        if "\n" in ct.text:
            # Break apart the formatting so that the \n is plain text,
            # so it works better with line numbers.
            textBits = ct.text.split("\n")
            list.append(ColoredText(textBits[0], ct.color))
            for bit in textBits[1:]:
                list.append(ColoredText("\n", None))
                list.append(ColoredText(bit, ct.color))
        else:
            list.append(ct)

    textList: t.Deque[ColoredText] = collections.deque()
    currentCT: ColoredText | None = None
    for line in text.split("\n"):
        if not line:
            continue
        tokenName, _, tokenTextRepr = line.partition("\t")
        color = colorFromName.get(tokenName)
        text = eval(tokenTextRepr)  # noqa: S307
        if not text:
            continue
        if not currentCT:
            currentCT = ColoredText(text, color)
        elif currentCT.color == color:
            # Repeated color, merge into current
            currentCT.text += text
        else:
            addCtToList(textList, currentCT)
            currentCT = ColoredText(text, color)
    if currentCT:
        addCtToList(textList, currentCT)
    return textList


def normalizeLanguageName(lang: str | None) -> str | None:
    # Translates some names to ones Pygment understands
    if lang == "aspnet":
        return "aspx-cs"
    if lang in ["markup", "svg"]:
        return "html"
    if lang == "idl":
        return "webidl"
    return lang


def normalizeHighlightMarkers(doc: t.SpecT) -> None:
    # Translate Prism-style highlighting into Pygment-style
    for el in h.findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search(r"(?:lang|language)-(\w+)", el.get("class") or "")
        if match:
            el.set("highlight", match.group(1))


def lexerFromLang(lang: str) -> pygments.lexer.Lexer | None:
    if lang in customLexers:
        return customLexers[lang]()
    try:
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        return get_lexer_by_name(lang, encoding="utf-8", stripnl=False)
    except ClassNotFound:
        return None


def addLineWrappers(doc: t.SpecT, el: t.ElementT, options: LineNumberOptions) -> t.ElementT:
    # Wrap everything between each top-level newline with a line tag.
    # Add an attr for the line number, and if needed, the end line.
    for nodes in splitNodesByLinebreaks(h.childNodes(el, clear=True)):
        h.appendChild(
            el,
            h.E.span({"class": "line-no"}),
            h.E.span({"class": "line"}, nodes),
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


def splitNodesByLinebreaks(nodes: t.NodesT) -> t.Generator[list[t.NodesT], None, None]:
    line: list[t.NodesT] = []
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


def grouper(iterable: t.Sequence[T], n: int, fillvalue: T | None = None) -> itertools.zip_longest[tuple[T | None, ...]]:
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)
