import collections
import itertools
import re

from . import h, messages as m


def loadCSSLexer():
    from .lexers import CSSLexer

    return CSSLexer()


customLexers = {"css": loadCSSLexer}

ColoredText = collections.namedtuple("ColoredText", ["text", "color"])


def addSyntaxHighlighting(doc):
    if doc.md.slimBuildArtifact:
        return
    normalizeHighlightMarkers(doc)

    # Highlight all the appropriate elements
    highlightingOccurred = False
    lineWrappingOccurred = False
    lineHighlightingOccurred = False
    for el in h.findAll("xmp, pre, code", doc):
        # Find whether to highlight, and what the lang is
        lang = determineHighlightLang(doc, el)
        if lang is False:
            # Element was already highlighted, but needs styles
            highlightingOccurred = True
        elif lang:
            highlightEl(el, lang)
            highlightingOccurred = True
        # Find whether to add line numbers
        addLineNumbers, lineStart, lineHighlights = determineLineNumbers(doc, el)
        if addLineNumbers or lineHighlights:
            addLineWrappers(el, numbers=addLineNumbers, start=lineStart, highlights=lineHighlights)
            if addLineNumbers:
                lineWrappingOccurred = True
            if lineHighlights:
                lineHighlightingOccurred = True

    if highlightingOccurred:
        doc.extraStyles["style-syntax-highlighting"] += getHighlightStyles()
        doc.extraStyles["style-darkmode"] += getHighlightDarkmodeStyles()
    if lineWrappingOccurred:
        doc.extraStyles["style-line-numbers"] += getLineNumberStyles()
        doc.extraStyles["style-darkmode"] += getLineNumberDarkmodeStyles()
    if lineHighlightingOccurred:
        doc.extraStyles["style-line-highlighting"] += getLineHighlightingStyles()
        doc.extraStyles["style-darkmode"] += getLineHighlightingDarkmodeStyles()


def determineHighlightLang(doc, el):
    # Either returns a normalized highlight lang,
    # False indicating the element was already highlighted,
    # or None indicating the element shouldn't be highlighted.
    attr, lang = h.closestAttr(el, "nohighlight", "highlight")
    lang = normalizeLanguageName(lang)
    if lang == "webidl" and el.tag == "code" and h.parentElement(el).tag == "dfn":
        # No such thing as a dfn that needs to be WebIDL-highlighted.
        # This is probably happening from a <dfn idl-type> inside a <pre highlight=idl>.
        return None
    if attr == "nohighlight":
        return None
    if attr == "highlight":
        return lang
    # Highlight-by-default, if applicable.
    if el.tag in ["pre", "xmp"] and h.hasClass(el, "idl"):
        return "webidl"
    return doc.md.defaultHighlight


def determineLineNumbers(doc, el):
    lAttr, _ = h.closestAttr(el, "no-line-numbers", "line-numbers")
    if lAttr == "no-line-numbers" or el.tag == "code":
        addLineNumbers = False
    elif lAttr == "line-numbers":
        addLineNumbers = True
    else:
        addLineNumbers = doc.md.lineNumbers

    lineStart = el.get("line-start")
    if lineStart is None:
        lineStart = 1
    else:
        try:
            lineStart = int(lineStart)
        except ValueError:
            m.die(f"line-start attribute must have an integer value. Got '{lineStart}'.", el=el)
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
                    low = int(low)
                    high = int(high)
                except ValueError:
                    m.die(f"Error parsing line-highlight range '{item}' - must be `int-int`.", el=el)
                    continue
                if low >= high:
                    m.die(f"line-highlight ranges must be well-formed lo-hi - got '{item}'.", el=el)
                    continue
                lineHighlights.update(list(range(low, high + 1)))
            else:
                try:
                    item = int(item)
                except ValueError:
                    m.die(f"Error parsing line-highlight value '{item}' - must be integers.", el=el)
                    continue
                lineHighlights.add(item)

    return addLineNumbers, lineStart, lineHighlights


def highlightEl(el, lang):
    text = h.textContent(el)
    if lang == "webidl":
        coloredText = highlightWithWebIDL(text, el=el)
    else:
        coloredText = highlightWithPygments(text, lang, el=el)
    mergeHighlighting(el, coloredText)
    h.addClass(el, "highlight")


def highlightWithWebIDL(text, el):
    """
    Trick the widlparser emitter,
    which wants to output HTML via wrapping with start/end tags,
    into instead outputting a stack-based text format.
    A \1 indicates a new stack push;
    the text between the \1 and the \2 is the attr to be pushed.
    A \3 indicates a stack pop.
    All other text is colored with the attr currently on top of the stack.
    """
    from widlparser import parser

    class IDLUI:
        def warn(self, msg):
            m.die(msg.rstrip())

    class HighlightMarker:
        # Just applies highlighting classes to IDL stuff.
        def markup_type_name(self, text, construct):  # pylint: disable=unused-argument
            return ("\1n\2", "\3")

        def markup_name(self, text, construct):  # pylint: disable=unused-argument
            return ("\1g\2", "\3")

        def markup_keyword(self, text, construct):  # pylint: disable=unused-argument
            return ("\1b\2", "\3")

        def markup_enum_value(self, text, construct):  # pylint: disable=unused-argument
            return ("\1s\2", "\3")

    if "\1" in text or "\2" in text or "\3" in text:
        m.die(
            "WebIDL text contains some U+0001-0003 characters, which are used by the highlighter. This block can't be highlighted. :(",
            el=el,
        )
        return

    widl = parser.Parser(text, IDLUI())
    return coloredTextFromWidlStack(str(widl.markup(HighlightMarker())))


def coloredTextFromWidlStack(widlText):
    coloredTexts = collections.deque()
    colors = []
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


def highlightWithPygments(text, lang, el):
    import pygments
    from pygments.formatters.other import RawTokenFormatter

    lexer = lexerFromLang(lang)
    if lexer is None:
        m.die(
            f"'{lang}' isn't a known syntax-highlighting language. See http://pygments.org/docs/lexers/. Seen on:\n"
            + h.outerHTML(el),
            el=el,
        )
        return
    rawTokens = str(
        pygments.highlight(text, lexer, RawTokenFormatter()),
        encoding="utf-8",
    )
    coloredText = coloredTextFromRawTokens(rawTokens)
    return coloredText


def mergeHighlighting(el, coloredText):
    # Merges a tree of Pygment-highlighted HTML
    # into the original element's markup.
    # This works because Pygment effectively colors each character with a highlight class,
    # merging them together into runs of text for convenience/efficiency only;
    # the markup structure is a flat list of sibling elements containing raw text
    # (and maybe some un-highlighted raw text between them).
    def createEl(color, text):
        return h.createElement("c-", {color: ""}, text)

    def colorizeEl(el, coloredText):
        for node in h.childNodes(el, clear=True):
            if h.isElement(node):
                h.appendChild(el, colorizeEl(node, coloredText))
            else:
                h.appendChild(el, *colorizeText(node, coloredText), allowEmpty=True)
        return el

    def colorizeText(text, coloredText):
        nodes = []
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
    coloredText = collections.deque(x for x in coloredText if x.text)
    colorizeEl(el, coloredText)


def coloredTextFromRawTokens(text):
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

    def addCtToList(list, ct):
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

    textList = collections.deque()
    currentCT = None
    for line in text.split("\n"):
        if not line:
            continue
        tokenName, _, tokenTextRepr = line.partition("\t")
        color = colorFromName.get(tokenName, None)
        text = eval(tokenTextRepr)
        if not text:
            continue
        if not currentCT:
            currentCT = ColoredText(text, color)
        elif currentCT.color == color:
            # Repeated color, merge into current
            currentCT = currentCT._replace(text=currentCT.text + text)
        else:
            addCtToList(textList, currentCT)
            currentCT = ColoredText(text, color)
    if currentCT:
        addCtToList(textList, currentCT)
    return textList


def normalizeLanguageName(lang):
    # Translates some names to ones Pygment understands
    if lang == "aspnet":
        return "aspx-cs"
    if lang in ["markup", "svg"]:
        return "html"
    if lang == "idl":
        return "webidl"
    return lang


def normalizeHighlightMarkers(doc):
    # Translate Prism-style highlighting into Pygment-style
    for el in h.findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search(r"(?:lang|language)-(\w+)", el.get("class"))
        if match:
            el.set("highlight", match.group(1))


def lexerFromLang(lang):
    if lang in customLexers:
        return customLexers[lang]()
    try:
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        return get_lexer_by_name(lang, encoding="utf-8", stripAll=True)
    except ClassNotFound:
        return None


def addLineWrappers(el, numbers=True, start=1, highlights=None):
    # Wrap everything between each top-level newline with a line tag.
    # Add an attr for the line number, and if needed, the end line.
    if highlights is None:
        highlights = set()
    lineWrapper = h.E.span({"class": "line"})
    for node in h.childNodes(el, clear=True):
        if h.isElement(node):
            h.appendChild(lineWrapper, node)
        else:
            while True:
                if "\n" in node:
                    pre, _, post = node.partition("\n")
                    h.appendChild(lineWrapper, pre)
                    h.appendChild(el, h.E.span({"class": "line-no"}))
                    h.appendChild(el, lineWrapper)
                    lineWrapper = h.E.span({"class": "line"})
                    node = post
                else:
                    h.appendChild(lineWrapper, node)
                    break
    if len(lineWrapper) > 0:
        h.appendChild(el, h.E.span({"class": "line-no"}))
        h.appendChild(el, lineWrapper)
    # Number the lines
    lineNumber = start
    for lineNo, node in grouper(h.childNodes(el), 2):
        if numbers or lineNumber in highlights:
            lineNo.set("data-line", str(lineNumber))
        if lineNumber in highlights:
            h.addClass(node, "highlight-line")
            h.addClass(lineNo, "highlight-line")
        internalNewlines = countInternalNewlines(node)
        if internalNewlines:
            for i in range(1, internalNewlines + 1):
                if (lineNumber + i) in highlights:
                    h.addClass(lineNo, "highlight-line")
                    h.addClass(node, "highlight-line")
                    lineNo.set("data-line", str(lineNumber))
            lineNumber += internalNewlines
            if numbers:
                lineNo.set("data-line-end", str(lineNumber))
        lineNumber += 1
    h.addClass(el, "line-numbered")
    return el


def countInternalNewlines(el):
    count = 0
    for node in h.childNodes(el):
        if h.isElement(node):
            count += countInternalNewlines(node)
        else:
            count += node.count("\n")
    return count


def getHighlightStyles():
    # To regen the styles, edit and run the below
    # from pygments import token
    # from pygments import style
    # class PrismStyle(style.Style):
    #    default_style = "#000000"
    #    styles = {
    #        token.Name: "#0077aa",
    #        token.Name.Tag: "#669900",
    #        token.Name.Builtin: "noinherit",
    #        token.Name.Variable: "#222222",
    #        token.Name.Other: "noinherit",
    #        token.Operator: "#999999",
    #        token.Punctuation: "#999999",
    #        token.Keyword: "#990055",
    #        token.Literal: "#000000",
    #        token.Literal.Number: "#000000",
    #        token.Literal.String: "#a67f59",
    #        token.Comment: "#708090"
    #    }
    # print formatters.HtmlFormatter(style=PrismStyle).get_style_defs('.highlight')
    return """
code.highlight { padding: .1em; border-radius: .3em; }
pre.highlight, pre > code.highlight { display: block; padding: 1em; margin: .5em 0; overflow: auto; border-radius: 0; }

.highlight:not(.idl) { background: rgba(0, 0, 0, .03); }
c-[a] { color: #990055 } /* Keyword.Declaration */
c-[b] { color: #990055 } /* Keyword.Type */
c-[c] { color: #708090 } /* Comment */
c-[d] { color: #708090 } /* Comment.Multiline */
c-[e] { color: #0077aa } /* Name.Attribute */
c-[f] { color: #669900 } /* Name.Tag */
c-[g] { color: #222222 } /* Name.Variable */
c-[k] { color: #990055 } /* Keyword */
c-[l] { color: #000000 } /* Literal */
c-[m] { color: #000000 } /* Literal.Number */
c-[n] { color: #0077aa } /* Name */
c-[o] { color: #999999 } /* Operator */
c-[p] { color: #999999 } /* Punctuation */
c-[s] { color: #a67f59 } /* Literal.String */
c-[t] { color: #a67f59 } /* Literal.String.Single */
c-[u] { color: #a67f59 } /* Literal.String.Double */
c-[cp] { color: #708090 } /* Comment.Preproc */
c-[c1] { color: #708090 } /* Comment.Single */
c-[cs] { color: #708090 } /* Comment.Special */
c-[kc] { color: #990055 } /* Keyword.Constant */
c-[kn] { color: #990055 } /* Keyword.Namespace */
c-[kp] { color: #990055 } /* Keyword.Pseudo */
c-[kr] { color: #990055 } /* Keyword.Reserved */
c-[ld] { color: #000000 } /* Literal.Date */
c-[nc] { color: #0077aa } /* Name.Class */
c-[no] { color: #0077aa } /* Name.Constant */
c-[nd] { color: #0077aa } /* Name.Decorator */
c-[ni] { color: #0077aa } /* Name.Entity */
c-[ne] { color: #0077aa } /* Name.Exception */
c-[nf] { color: #0077aa } /* Name.Function */
c-[nl] { color: #0077aa } /* Name.Label */
c-[nn] { color: #0077aa } /* Name.Namespace */
c-[py] { color: #0077aa } /* Name.Property */
c-[ow] { color: #999999 } /* Operator.Word */
c-[mb] { color: #000000 } /* Literal.Number.Bin */
c-[mf] { color: #000000 } /* Literal.Number.Float */
c-[mh] { color: #000000 } /* Literal.Number.Hex */
c-[mi] { color: #000000 } /* Literal.Number.Integer */
c-[mo] { color: #000000 } /* Literal.Number.Oct */
c-[sb] { color: #a67f59 } /* Literal.String.Backtick */
c-[sc] { color: #a67f59 } /* Literal.String.Char */
c-[sd] { color: #a67f59 } /* Literal.String.Doc */
c-[se] { color: #a67f59 } /* Literal.String.Escape */
c-[sh] { color: #a67f59 } /* Literal.String.Heredoc */
c-[si] { color: #a67f59 } /* Literal.String.Interpol */
c-[sx] { color: #a67f59 } /* Literal.String.Other */
c-[sr] { color: #a67f59 } /* Literal.String.Regex */
c-[ss] { color: #a67f59 } /* Literal.String.Symbol */
c-[vc] { color: #0077aa } /* Name.Variable.Class */
c-[vg] { color: #0077aa } /* Name.Variable.Global */
c-[vi] { color: #0077aa } /* Name.Variable.Instance */
c-[il] { color: #000000 } /* Literal.Number.Integer.Long */
"""


def getHighlightDarkmodeStyles():
    return """
@media (prefers-color-scheme: dark) {
    .highlight:not(.idl) { background: rgba(255, 255, 255, .05); }

    c-[a] { color: #d33682 } /* Keyword.Declaration */
    c-[b] { color: #d33682 } /* Keyword.Type */
    c-[c] { color: #2aa198 } /* Comment */
    c-[d] { color: #2aa198 } /* Comment.Multiline */
    c-[e] { color: #268bd2 } /* Name.Attribute */
    c-[f] { color: #b58900 } /* Name.Tag */
    c-[g] { color: #cb4b16 } /* Name.Variable */
    c-[k] { color: #d33682 } /* Keyword */
    c-[l] { color: #657b83 } /* Literal */
    c-[m] { color: #657b83 } /* Literal.Number */
    c-[n] { color: #268bd2 } /* Name */
    c-[o] { color: #657b83 } /* Operator */
    c-[p] { color: #657b83 } /* Punctuation */
    c-[s] { color: #6c71c4 } /* Literal.String */
    c-[t] { color: #6c71c4 } /* Literal.String.Single */
    c-[u] { color: #6c71c4 } /* Literal.String.Double */
    c-[ch] { color: #2aa198 } /* Comment.Hashbang */
    c-[cp] { color: #2aa198 } /* Comment.Preproc */
    c-[cpf] { color: #2aa198 } /* Comment.PreprocFile */
    c-[c1] { color: #2aa198 } /* Comment.Single */
    c-[cs] { color: #2aa198 } /* Comment.Special */
    c-[kc] { color: #d33682 } /* Keyword.Constant */
    c-[kn] { color: #d33682 } /* Keyword.Namespace */
    c-[kp] { color: #d33682 } /* Keyword.Pseudo */
    c-[kr] { color: #d33682 } /* Keyword.Reserved */
    c-[ld] { color: #657b83 } /* Literal.Date */
    c-[nc] { color: #268bd2 } /* Name.Class */
    c-[no] { color: #268bd2 } /* Name.Constant */
    c-[nd] { color: #268bd2 } /* Name.Decorator */
    c-[ni] { color: #268bd2 } /* Name.Entity */
    c-[ne] { color: #268bd2 } /* Name.Exception */
    c-[nf] { color: #268bd2 } /* Name.Function */
    c-[nl] { color: #268bd2 } /* Name.Label */
    c-[nn] { color: #268bd2 } /* Name.Namespace */
    c-[py] { color: #268bd2 } /* Name.Property */
    c-[ow] { color: #657b83 } /* Operator.Word */
    c-[mb] { color: #657b83 } /* Literal.Number.Bin */
    c-[mf] { color: #657b83 } /* Literal.Number.Float */
    c-[mh] { color: #657b83 } /* Literal.Number.Hex */
    c-[mi] { color: #657b83 } /* Literal.Number.Integer */
    c-[mo] { color: #657b83 } /* Literal.Number.Oct */
    c-[sa] { color: #6c71c4 } /* Literal.String.Affix */
    c-[sb] { color: #6c71c4 } /* Literal.String.Backtick */
    c-[sc] { color: #6c71c4 } /* Literal.String.Char */
    c-[dl] { color: #6c71c4 } /* Literal.String.Delimiter */
    c-[sd] { color: #6c71c4 } /* Literal.String.Doc */
    c-[se] { color: #6c71c4 } /* Literal.String.Escape */
    c-[sh] { color: #6c71c4 } /* Literal.String.Heredoc */
    c-[si] { color: #6c71c4 } /* Literal.String.Interpol */
    c-[sx] { color: #6c71c4 } /* Literal.String.Other */
    c-[sr] { color: #6c71c4 } /* Literal.String.Regex */
    c-[ss] { color: #6c71c4 } /* Literal.String.Symbol */
    c-[fm] { color: #268bd2 } /* Name.Function.Magic */
    c-[vc] { color: #cb4b16 } /* Name.Variable.Class */
    c-[vg] { color: #cb4b16 } /* Name.Variable.Global */
    c-[vi] { color: #cb4b16 } /* Name.Variable.Instance */
    c-[vm] { color: #cb4b16 } /* Name.Variable.Magic */
    c-[il] { color: #657b83 } /* Literal.Number.Integer.Long */
}
"""


def getLineNumberStyles():
    return """
:root {
    --highlight-hover-bg: rgba(0, 0, 0, .05);
}
.line-numbered {
    display: grid !important;
    grid-template-columns: min-content 1fr;
    grid-auto-flow: row;
}
.line-numbered > *,
.line-numbered::before,
.line-numbered::after {
    grid-column: 1/-1;
}
.line-no {
    grid-column: 1;
    color: gray;
}
.line {
    grid-column: 2;
}
.line:hover {
    background: var(--highlight-hover-bg);
}
.line-no[data-line]::before {
    padding: 0 .5em 0 .1em;
    content: attr(data-line);
}
.line-no[data-line-end]::after {
    padding: 0 .5em 0 .1em;
    content: attr(data-line-end);
}
"""


def getLineNumberDarkmodeStyles():
    return """
@media (prefers-color-scheme: dark) {
    :root {
        --highlight-hover-bg: rgba(255, 255, 255, .05);
    }
}
"""


def getLineHighlightingStyles():
    return """
:root {
    --highlight-hover-bg: rgba(0, 0, 0, .05);
}
.line-numbered {
    display: grid !important;
    grid-template-columns: min-content 1fr;
    grid-auto-flow: rows;
}
.line-numbered > *,
.line-numbered::before,
.line-numbered::after {
    grid-column: 1/-1;
}
.line-no {
    grid-column: 1;
    color: gray;
}
.line {
    grid-column: 2;
}
.line.highlight-line {
    background: var(--highlight-hover-bg);
}
.line-no.highlight-line {
    background: var(--highlight-hover-bg);
    color: #444;
    font-weight: bold;
}
.line-no.highlight-line[data-line]::before {
    padding: 0 .5em 0 .1em;
    content: attr(data-line);
}
.line-no.highlight-line[data-line-end]::after {
    padding: 0 .5em 0 .1em;
    content: attr(data-line-end);
}
"""


def getLineHighlightingDarkmodeStyles():
    return """
@media (prefers-color-scheme: dark) {
    :root {
        --highlight-hover-bg: rgba(255, 255, 255, .05);
    }
}
"""


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.zip_longest(fillvalue=fillvalue, *args)
