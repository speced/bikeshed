# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import collections
from . import config
from . import lexers
from .htmlhelpers import *
from .messages import *
from .widlparser.widlparser import parser
try:
    import pygments as pyg
    from pygments.lexers import get_lexer_by_name
    from pygments import formatters
except ImportError:
    die("Bikeshed now uses Pygments for syntax highlighting.\nPlease run `$ sudo pip install pygments` from your command line.")

customLexers = {
    "css": lexers.CSSLexer()
}

ColoredText = collections.namedtuple('ColoredText', ['text', 'color'])

class IDLUI(object):
    def warn(self, msg):
        die("{0}", msg.rstrip())


class HighlightMarker(object):
    # Just applies highlighting classes to IDL stuff.

    def markupTypeName(self, text, construct):
        return ('<span class=n>', '</span>')

    def markupName(self, text, construct):
        return ('<span class=nv>', '</span>')

    def markupKeyword(self, text, construct):
        return ('<span class=kt>', '</span>')

    def markupEnumValue(self, text, construct):
        return ('<span class=s>', '</span>')

def addSyntaxHighlighting(doc):
    highlightingOccurred = False

    if find("pre.idl, xmp.idl", doc) is not None:
        highlightingOccurred = True

    def translateLang(lang):
        # Translates some names to ones Pygment understands
        if lang == "aspnet":
            return "aspx-cs"
        if lang in ["markup", "svg"]:
            return "html"
        return lang

    # Translate Prism-style highlighting into Pygment-style
    for el in findAll("[class*=language-], [class*=lang-]", doc):
        match = re.search("(?:lang|language)-(\w+)", el.get("class"))
        if match:
            el.set("highlight", match.group(1))

    # Highlight all the appropriate elements
    for el in findAll("xmp, pre, code", doc):
        attr, lang = closestAttr(el, "nohighlight", "highlight")
        if attr == "nohighlight":
            continue
        if attr is None:
            if el.tag in ["pre", "xmp"] and hasClass(el, "idl"):
                if isNormative(el):
                    # Already processed/highlighted.
                    continue
                lang = "idl"
            elif doc.md.defaultHighlight is None:
                continue
            else:
                lang = doc.md.defaultHighlight
        highlightEl(el, translateLang(lang))
        highlightingOccurred = True

    if highlightingOccurred:
        # To regen the styles, edit and run the below
        #from pygments import token
        #from pygments import style
        #class PrismStyle(style.Style):
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
        #print formatters.HtmlFormatter(style=PrismStyle).get_style_defs('.highlight')
        doc.extraStyles['style-syntax-highlighting'] += '''
        .highlight:not(.idl) { background: hsl(24, 20%, 95%); }
        code.highlight { padding: .1em; border-radius: .3em; }
        pre.highlight, pre > code.highlight { display: block; padding: 1em; margin: .5em 0; overflow: auto; border-radius: 0; }
        .highlight .c { color: #708090 } /* Comment */
        .highlight .k { color: #990055 } /* Keyword */
        .highlight .l { color: #000000 } /* Literal */
        .highlight .n { color: #0077aa } /* Name */
        .highlight .o { color: #999999 } /* Operator */
        .highlight .p { color: #999999 } /* Punctuation */
        .highlight .cm { color: #708090 } /* Comment.Multiline */
        .highlight .cp { color: #708090 } /* Comment.Preproc */
        .highlight .c1 { color: #708090 } /* Comment.Single */
        .highlight .cs { color: #708090 } /* Comment.Special */
        .highlight .kc { color: #990055 } /* Keyword.Constant */
        .highlight .kd { color: #990055 } /* Keyword.Declaration */
        .highlight .kn { color: #990055 } /* Keyword.Namespace */
        .highlight .kp { color: #990055 } /* Keyword.Pseudo */
        .highlight .kr { color: #990055 } /* Keyword.Reserved */
        .highlight .kt { color: #990055 } /* Keyword.Type */
        .highlight .ld { color: #000000 } /* Literal.Date */
        .highlight .m { color: #000000 } /* Literal.Number */
        .highlight .s { color: #a67f59 } /* Literal.String */
        .highlight .na { color: #0077aa } /* Name.Attribute */
        .highlight .nc { color: #0077aa } /* Name.Class */
        .highlight .no { color: #0077aa } /* Name.Constant */
        .highlight .nd { color: #0077aa } /* Name.Decorator */
        .highlight .ni { color: #0077aa } /* Name.Entity */
        .highlight .ne { color: #0077aa } /* Name.Exception */
        .highlight .nf { color: #0077aa } /* Name.Function */
        .highlight .nl { color: #0077aa } /* Name.Label */
        .highlight .nn { color: #0077aa } /* Name.Namespace */
        .highlight .py { color: #0077aa } /* Name.Property */
        .highlight .nt { color: #669900 } /* Name.Tag */
        .highlight .nv { color: #222222 } /* Name.Variable */
        .highlight .ow { color: #999999 } /* Operator.Word */
        .highlight .mb { color: #000000 } /* Literal.Number.Bin */
        .highlight .mf { color: #000000 } /* Literal.Number.Float */
        .highlight .mh { color: #000000 } /* Literal.Number.Hex */
        .highlight .mi { color: #000000 } /* Literal.Number.Integer */
        .highlight .mo { color: #000000 } /* Literal.Number.Oct */
        .highlight .sb { color: #a67f59 } /* Literal.String.Backtick */
        .highlight .sc { color: #a67f59 } /* Literal.String.Char */
        .highlight .sd { color: #a67f59 } /* Literal.String.Doc */
        .highlight .s2 { color: #a67f59 } /* Literal.String.Double */
        .highlight .se { color: #a67f59 } /* Literal.String.Escape */
        .highlight .sh { color: #a67f59 } /* Literal.String.Heredoc */
        .highlight .si { color: #a67f59 } /* Literal.String.Interpol */
        .highlight .sx { color: #a67f59 } /* Literal.String.Other */
        .highlight .sr { color: #a67f59 } /* Literal.String.Regex */
        .highlight .s1 { color: #a67f59 } /* Literal.String.Single */
        .highlight .ss { color: #a67f59 } /* Literal.String.Symbol */
        .highlight .vc { color: #0077aa } /* Name.Variable.Class */
        .highlight .vg { color: #0077aa } /* Name.Variable.Global */
        .highlight .vi { color: #0077aa } /* Name.Variable.Instance */
        .highlight .il { color: #000000 } /* Literal.Number.Integer.Long */
        '''


def highlightEl(el, lang):
    text = textContent(el)
    if lang in ["idl", "webidl"]:
        widl = parser.Parser(text, IDLUI())
        marker = HighlightMarker()
        nested = parseHTML(unicode(widl.markup(marker)))
        coloredText = collections.deque()
        for n in childNodes(flattenHighlighting(nested)):
            if isElement(n):
                coloredText.append(ColoredText(textContent(n), n.get('class')))
            else:
                coloredText.append(ColoredText(n, None))
    else:
        if lang in customLexers:
            lexer = customLexers[lang]
        else:
            try:
                lexer = get_lexer_by_name(lang, encoding="utf-8", stripAll=True)
            except pyg.util.ClassNotFound:
                die("'{0}' isn't a known syntax-highlighting language. See http://pygments.org/docs/lexers/. Seen on:\n{1}", lang, outerHTML(el), el=el)
                return
        coloredText = parsePygments(pyg.highlight(text, lexer, formatters.RawTokenFormatter()))
        # empty span at beginning
        # extra linebreak at the end
    mergeHighlighting(el, coloredText)
    addClass(el, "highlight")


def mergeHighlighting(el, coloredText):
    # Merges a tree of Pygment-highlighted HTML
    # into the original element's markup.
    # This works because Pygment effectively colors each character with a highlight class,
    # merging them together into runs of text for convenience/efficiency only;
    # the markup structure is a flat list of sibling elements containing raw text
    # (and maybe some un-highlighted raw text between them).
    def colorizeEl(el, coloredText):
        for node in childNodes(el, clear=True):
            if isElement(node):
                appendChild(el, colorizeEl(node, coloredText))
            else:
                appendChild(el, *colorizeText(node, coloredText))
        return el

    def colorizeText(text, coloredText):
        nodes = []
        while text and coloredText:
            nextColor = coloredText.popleft()
            if len(nextColor.text) <= len(text):
                if nextColor.color is None:
                    nodes.append(nextColor.text)
                else:
                    nodes.append(E.span({"class":nextColor.color}, nextColor.text))
                text = text[len(nextColor.text):]
            else:  # Need to use only part of the nextColor node
                if nextColor.color is None:
                    nodes.append(text)
                else:
                    nodes.append(E.span({"class":nextColor.color}, text))
                # Truncate the nextColor text to what's unconsumed,
                # and put it back into the deque
                nextColor = ColoredText(nextColor.text[len(text):], nextColor.color)
                coloredText.appendleft(nextColor)
                text = ''
        return nodes
    colorizeEl(el, coloredText)

def flattenHighlighting(el):
    # Given a highlighted chunk of markup that is "nested",
    # flattens it into a sequence of text and els with just text,
    # by merging classes upward.
    container = E.div()
    for node in childNodes(el):
        if not isElement(node):
            # raw text
            appendChild(container, node)
        elif not hasChildElements(node):
            # el with just text
            appendChild(container, node)
        else:
            # el with internal structure
            overclass = el.get("class", '') if isElement(el) else ""
            flattened = flattenHighlighting(node)
            for subnode in childNodes(flattened):
                if isElement(subnode):
                    addClass(subnode, overclass)
                    appendChild(container, subnode)
                else:
                    appendChild(container, E.span({"class":overclass},subnode))
    return container

def parsePygments(text):
    tokenClassFromName = {
        "Token.Comment": "c",
        "Token.Keyword": "k",
        "Token.Literal": "l",
        "Token.Name": "n",
        "Token.Operator": "o",
        "Token.Punctuation": "p",
        "Token.Comment.Multiline": "cm",
        "Token.Comment.Preproc": "cp",
        "Token.Comment.Single": "c1",
        "Token.Comment.Special": "cs",
        "Token.Keyword.Constant": "kc",
        "Token.Keyword.Declaration": "kd",
        "Token.Keyword.Namespace": "kn",
        "Token.Keyword.Pseudo": "kp",
        "Token.Keyword.Reserved": "kr",
        "Token.Keyword.Type": "kt",
        "Token.Literal.Date": "ld",
        "Token.Literal.Number": "m",
        "Token.Literal.String": "s",
        "Token.Name.Attribute": "na",
        "Token.Name.Class": "nc",
        "Token.Name.Constant": "no",
        "Token.Name.Decorator": "nd",
        "Token.Name.Entity": "ni",
        "Token.Name.Exception": "ne",
        "Token.Name.Function": "nf",
        "Token.Name.Label": "nl",
        "Token.Name.Namespace": "nn",
        "Token.Name.Property": "py",
        "Token.Name.Tag": "nt",
        "Token.Name.Variable": "nv",
        "Token.Operator.Word": "ow",
        "Token.Literal.Number.Bin": "mb",
        "Token.Literal.Number.Float": "mf",
        "Token.Literal.Number.Hex": "mh",
        "Token.Literal.Number.Integer": "mi",
        "Token.Literal.Number.Oct": "mo",
        "Token.Literal.String.Backtick": "sb",
        "Token.Literal.String.Char": "sc",
        "Token.Literal.String.Doc": "sd",
        "Token.Literal.String.Double": "s2",
        "Token.Literal.String.Escape": "se",
        "Token.Literal.String.Heredoc": "sh",
        "Token.Literal.String.Interpol": "si",
        "Token.Literal.String.Other": "sx",
        "Token.Literal.String.Regex": "sr",
        "Token.Literal.String.Single": "s1",
        "Token.Literal.String.Symbol": "ss",
        "Token.Name.Variable.Class": "vc",
        "Token.Name.Variable.Global": "vg",
        "Token.Name.Variable.Instance": "vi",
        "Token.Literal.Number.Integer.Long": "il"
    }
    coloredText = collections.deque()
    for line in text.split("\n"):
        if not line:
            continue
        tokenName,_,tokenTextRepr = line.partition("\t")
        tokenText = eval(tokenTextRepr)
        if not tokenText:
            continue
        if tokenName == "Token.Text":
            tokenClass = None
        else:
            tokenClass = tokenClassFromName.get(tokenName, None)
        coloredText.append(ColoredText(tokenText, tokenClass))
    return coloredText



