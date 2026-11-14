from __future__ import annotations

import collections
import dataclasses
import re

import pygments
from pygments.lexers import get_lexer_by_name

from .. import h, t
from .. import messages as m


@dataclasses.dataclass
class ColoredText:
    text: str
    # None indicates uncolored text
    color: str | None


def highlightEl(doc: t.SpecT, el: t.ElementT, lang: str) -> None:
    text = h.textContent(el)
    coloredText = highlightWithPygments(text, lang, el=el)
    if coloredText is not None:
        coloredText = mergeColors(coloredText)
        readdWhitespacePrefix(text, coloredText)
        mergeHighlighting(el, coloredText)
        h.addClass(doc, el, "highlight")


def mergeColors(coloredText: t.Deque[ColoredText]) -> t.Deque[ColoredText]:
    """
    Some highlighters gratuitously emit multiple tokens in a row with the same color,
    which makes other modifications I perform annoying.
    This does a pass to merge those together.
    """
    ret: t.Deque[ColoredText] = collections.deque()
    for token in coloredText:
        if not ret:
            ret.append(token)
            continue
        if ret[-1].color == token.color:
            ret[-1].text += token.text
            continue
        ret.append(token)
    return ret


def readdWhitespacePrefix(rawText: str, coloredText: t.Deque[ColoredText]) -> t.Deque[ColoredText]:
    """
    If the raw text starts with whitespace, Pygments auto-strips it >:(
    So, we need to add it back in, as an uncolored chunk of text.
    But also, it doesn't... always strip whitespace. So check for that.
    """
    if not coloredText:
        # Empty colored text, nothing to do
        return coloredText
    coloredMatch = re.match(r"\s+", coloredText[0].text)
    if coloredMatch:
        # whitespace was kept by the formatter, so nothing to do
        return coloredText
    textMatch = re.match(r"\s+", rawText)
    if not textMatch:
        # No whitespace on the text, nothing to do
        return coloredText
    prefix = ColoredText(textMatch[0], None)
    coloredText.appendleft(prefix)
    return coloredText


def highlightWithPygments(text: str, lang: str, el: t.ElementT) -> t.Deque[ColoredText] | None:
    lexer = lexerFromLang(lang)
    if lexer is None:
        m.die(
            f"'{lang}' isn't a known syntax-highlighting language. See http://pygments.org/docs/lexers/. Seen on:\n"
            + h.outerHTML(el),
            el=el,
        )
        return None
    rawTokens = [(str(ttype), val) for (ttype, val) in pygments.lex(text, lexer)]
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
        newChildren: list[t.NodeT] = []
        for node in h.childNodes(el, clear=True):
            if h.isElement(node):
                newChildren.append(colorizeEl(node, coloredText))
            else:
                assert isinstance(node, str)
                newChildren.extend(colorizeText(node, coloredText))
        if newChildren:
            h.appendChild(el, *newChildren)
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


def coloredTextFromRawTokens(rawTokens: t.Sequence[tuple[str, str]]) -> t.Deque[ColoredText]:
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

    def addCtToList(targetList: t.Deque[ColoredText], ct: ColoredText) -> None:
        if "\n" in ct.text:
            # Break apart the formatting so that the \n is plain text,
            # so it works better with line numbers.
            textBits = ct.text.split("\n")
            targetList.append(ColoredText(textBits[0], ct.color))
            for bit in textBits[1:]:
                targetList.append(ColoredText("\n", None))
                targetList.append(ColoredText(bit, ct.color))
        else:
            targetList.append(ct)

    textList: t.Deque[ColoredText] = collections.deque()
    currentCT: ColoredText | None = None
    for tokenName, text in rawTokens:
        color = colorFromName.get(tokenName)
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


def lexerFromLang(lang: str) -> pygments.lexer.Lexer | None:
    try:
        return get_lexer_by_name(lang, encoding="utf-8", stripnl=False)
    except pygments.util.ClassNotFound:
        return None
