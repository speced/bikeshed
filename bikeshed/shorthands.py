# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from .messages import *
from .htmlhelpers import *


def transformProductionPlaceholders(doc):
    propdescRe = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")
    funcRe = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
    atruleRe = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
    typeRe = re.compile(r"^(?:(\S*)/)?(\S+)$")
    for el in findAll("fake-production-placeholder", doc):
        text = textContent(el)
        clearContents(el)
        match = propdescRe.match(text)
        if match:
            if match.group(3) is None:
                linkType = "propdesc"
            elif match.group(3) in ("property", "descriptor"):
                linkType = match.group(2)
            else:
                die("Shorthand <<{0}>> gives type as '{1}', but only 'property' and 'descriptor' are allowed.", match.group(0), match.group(3))
                el.tag = "span"
                el.text = "<‘" + text[1:-1] + "’>"
                continue
            el.tag = "a"
            el.set("data-link-type", linkType)
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<‘" + match.group(2) + "’>"
            continue
        match = funcRe.match(text)
        if match:
            el.tag = "a"
            el.set("data-link-type", "function")
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<" + match.group(2) + ">"
            continue
        match = atruleRe.match(text)
        if match:
            el.tag = "a"
            el.set("data-link-type", "at-rule")
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<" + match.group(2) + ">"
            continue
        match = typeRe.match(text)
        if match:
            el.tag = "a"
            el.set("data-link-type", "type")
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = "<" + match.group(2) + ">"
            continue
        die("Shorthand <<{0}>> does not match any recognized shorthand grammar.", text)
        continue


def transformMaybePlaceholders(doc):
    propRe = re.compile(r"^([\w-]+): .+")
    valRe = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")
    for el in findAll("fake-maybe-placeholder", doc):
        text = textContent(el)
        clearContents(el)
        match = propRe.match(text)
        if match:
            el.tag = "a"
            el.set("class", "css")
            el.set("data-link-type", "propdesc")
            el.set("data-lt", match.group(1))
            el.text = text
            continue
        match = valRe.match(text)
        if match:
            if match.group(3) is None:
                linkType = "maybe"
            elif match.group(3) in config.maybeTypes:
                linkType = match.group(3)
            else:
                die("Shorthand ''{0}'' gives type as '{1}', but only “maybe” types are allowed.", match.group(0), match.group(3))
                el.tag = "css"
                continue
            el.tag = "a"
            el.set("class", "css")
            el.set("data-link-type", linkType)
            el.set("data-lt", match.group(2))
            if match.group(1) is not None:
                el.set("for", match.group(1))
            el.text = match.group(2)
            continue
        el.tag = "css"
        el.text = text


def transformAutolinkShortcuts(doc):
    # Do the remaining textual replacements

    biblioRe = re.compile(r"(\\)?\[\[(!)?([\w.+-]+)((?: +current)|(?: +dated))?\]\]")

    def biblioReplacer(match):
        # Allow escaping things that aren't actually biblio links, by preceding with a \
        if match.group(1) is not None:
            return match.group(0)[1:]
        if match.group(2) == "!":
            type = "normative"
        else:
            type = "informative"
        term = match.group(3)
        attrs = {"data-lt":term, "data-link-type":"biblio", "data-biblio-type":type}
        if match.group(4) is not None:
            attrs['data-biblio-status'] = match.group(4).strip()
        return E.a(attrs,
                   "[",
                   term,
                   "]")

    sectionRe = re.compile(r"""
                            \[\[
                            ([\w-]+)?
                            (?:
                                ((?:\/[\w-]*)?(?:\#[\w-]+)) |
                                (\/[\w-]+)
                            )
                            (\|[^\]]+)?
                            \]\]""", re.X)

    def sectionReplacer(match):
        spec, section, justPage, linkText = match.groups()
        if linkText is None:
            linkText = ""
        else:
            linkText = linkText[1:]
        if spec is None:
            # local section link
            return E.a({"section":"", "href":section}, linkText)
        elif justPage is not None:
            # foreign link, to an actual page from a multipage spec
            return E.span({"spec-section":justPage + "#", "spec":spec}, linkText)
        else:
            # foreign link
            return E.span({"spec-section":section, "spec":spec}, linkText)

    propdescRe = re.compile(r"'(?:([^\s']*)/)?([\w*-]+)(?:!!([\w-]+))?(\|[^']+)?'")

    def propdescReplacer(match):
        if match.group(1) == "":
            linkFor = "/"
        else:
            linkFor = match.group(1)
        if match.group(2) == "-":
            return "'-'"
        if match.group(3) is None:
            linkType = "propdesc"
        elif match.group(3) in ("property", "descriptor"):
            linkType = match.group(3)
        else:
            die("Shorthand {0} gives type as '{1}', but only 'property' and 'descriptor' are allowed.", match.group(0), match.group(3))
            return E.span(match.group(0))
        if match.group(4) is not None:
            linkText = match.group(4)[1:]
        else:
            linkText = match.group(2)
        return E.a({"data-link-type":linkType, "class":"property", "for": linkFor, "lt": match.group(2)}, linkText)

    idlRe = re.compile(r"{{(?:([^}]*)/)?((?:[^}]|,\s)+?)(?:!!([\w-]+))?(\|[^}]+)?}}")

    def idlReplacer(match):
        if match.group(1) == "":
            linkFor = "/"
        else:
            linkFor = match.group(1)
        if match.group(3) is None:
            linkType = "idl"
        elif match.group(3) in config.idlTypes:
            linkType = match.group(3)
        else:
            die("Shorthand {0} gives type as '{1}', but only IDL types are allowed.", match.group(0), match.group(3))
            return E.span(match.group(0))
        if match.group(4) is not None:
            linkText = match.group(4)[1:]
        else:
            linkText = match.group(2)
        return E.code({"class":"idl", "nohighlight":""},
                      E.a({"data-link-type":linkType, "for": linkFor, "lt":match.group(2)}, linkText))

    dfnRe = re.compile(r"\[=(?!\s)(?:([^=]*)/)?([^\"=]+?)(\|[^\"=]+)?=\]")

    def dfnReplacer(match):
        if match.group(1) == "":
            linkFor = "/"
        else:
            linkFor = match.group(1)
        if match.group(3) is not None:
            linkText = match.group(3)[1:]
        else:
            linkText = match.group(2)
        return E.a({"data-link-type":"dfn", "for": linkFor, "lt":match.group(2)}, linkText)

    elementRe = re.compile(r"<{(?P<element>[\w*-]+)(?:/(?P<attr>[\w*-]+)(?:/(?P<value>[^}!|]+))?)?(?:!!(?P<linkType>[\w-]+))?(?:\|(?P<linkText>[^}]+))?}>")

    def elementReplacer(match):
        groupdict = match.groupdict()
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
        return E.code({},
                      E.a({"data-link-type":linkType, "for": linkFor, "lt": lt}, linkText))

    varRe = re.compile(r"\|(\w(?:[\w\s-]*\w)?)\|")

    def varReplacer(match):
        return E.var(match.group(1))

    inlineLinkRe = re.compile(r'\[([^\]]*)\]\(\s*([^\s)]*)\s*(?:"([^"]*)")?\s*\)')

    def inlineLinkReplacer(match):
        return (E.a({"href":match.group(2)}, match.group(1))
                if len(match.groups()) < 3
                else
                E.a({"href":match.group(2), "title":match.group(3)}, match.group(1))
                )

    strongRe = re.compile(r"(?<!\\)(\*\*)(?!\s)([^*]+)(?!\s)(?<!\\)\*\*")

    def strongReplacer(match):
        return E.strong(match.group(2))

    codeRe = re.compile(r"(?<!`)(\\?)(`+)(?!\s)(.*?[^`])(?!\s)(\\?)(\2)(?!`)")

    def codeReplacer(match):
        # This condition represents an escaped backtick. Substitute the string
        # without the escaping character.
        if match.group(1) != "":
            return match.expand("\\2\\3\\5")

        # From the CommonMark specification (version 0.27):
        #
        #  > The contents of the code span are the characters between the two
        #  > backtick strings, with leading and trailing spaces and line
        #  > endings removed, and whitespace collapsed to single spaces.
        import string
        normalized = escapeHTML(match.group(3)).strip(string.whitespace)
        normalized = re.sub("[" + string.whitespace + "]{2,}", " ", normalized)

        return E.code(normalized)

    emRe = re.compile(r"(?<!\\)(\*)(?!\s)([^*]+)(?!\s)(?<!\\)\*")

    def emReplacer(match):
        return E.em(match.group(2))

    escapedRe = re.compile(r"\\\*")

    def escapedReplacer(match):
        return "*"

    def transformElement(parentEl):
        processContents = isElement(parentEl) and not doc.isOpaqueElement(parentEl)
        if not processContents:
            return
        children = childNodes(parentEl, clear=True)
        newChildren = []
        for el in children:
            if isinstance(el, basestring):
                newChildren.extend(transformText(el))
            elif isElement(el):
                transformElement(el)
                newChildren.append(el)
        appendChild(parentEl, *newChildren)

    def transformText(text):
        nodes = [text]
        if "css" in doc.md.markupShorthands:
            config.processTextNodes(nodes, propdescRe, propdescReplacer)
        if "dfn" in doc.md.markupShorthands:
            config.processTextNodes(nodes, dfnRe, dfnReplacer)
        if "idl" in doc.md.markupShorthands:
            config.processTextNodes(nodes, idlRe, idlReplacer)
        if "markup" in doc.md.markupShorthands:
            config.processTextNodes(nodes, elementRe, elementReplacer)
        if "biblio" in doc.md.markupShorthands:
            config.processTextNodes(nodes, biblioRe, biblioReplacer)
            config.processTextNodes(nodes, sectionRe, sectionReplacer)
        if "algorithm" in doc.md.markupShorthands:
            config.processTextNodes(nodes, varRe, varReplacer)
        if "markdown" in doc.md.markupShorthands:
            config.processTextNodes(nodes, inlineLinkRe, inlineLinkReplacer)
            config.processTextNodes(nodes, codeRe, codeReplacer)
            config.processTextNodes(nodes, strongRe, strongReplacer)
            config.processTextNodes(nodes, emRe, emReplacer)
            config.processTextNodes(nodes, escapedRe, escapedReplacer)
        return nodes

    transformElement(doc.document.getroot())

    for el in findAll("var", doc):
        fixSurroundingTypography(el)


def transformProductionGrammars(doc):
    # Link up the various grammar symbols in CSS grammars to their definitions.
    if "css" not in doc.md.markupShorthands:
        return

    hashMultRe = re.compile(r"#{\s*\d+(\s*,(\s*\d+)?)?\s*}")

    def hashMultReplacer(match):
        return E.a({"data-link-type":"grammar", "data-lt": "#", "for":""}, match.group(0))

    multRe = re.compile(r"{\s*\d+\s*}")

    def multReplacer(match):
        return E.a({"data-link-type":"grammar", "data-lt": "{A}", "for":""}, match.group(0))

    multRangeRe = re.compile(r"{\s*\d+\s*,(\s*\d+)?\s*}")

    def multRangeReplacer(match):
        return E.a({"data-link-type":"grammar", "data-lt": "{A,B}", "for":""}, match.group(0))

    simpleRe = re.compile(r"(\?|!|#|\*|\+|\|\||\||&amp;&amp;|&&|,)(?!')")
    # Note the negative-lookahead, to avoid matching delim tokens.

    def simpleReplacer(match):
        return E.a({"data-link-type":"grammar", "data-lt": match.group(0), "for":""}, match.group(0))

    def transformElement(parentEl):
        children = childNodes(parentEl, clear=True)
        newChildren = []
        for el in children:
            if isinstance(el, basestring):
                newChildren.extend(transformText(el))
            elif isElement(el):
                transformElement(el)
                newChildren.append(el)
        appendChild(parentEl, *newChildren)

    def transformText(text):
        nodes = [text]
        config.processTextNodes(nodes, hashMultRe, hashMultReplacer)
        config.processTextNodes(nodes, multRe, multReplacer)
        config.processTextNodes(nodes, multRangeRe, multRangeReplacer)
        config.processTextNodes(nodes, simpleRe, simpleReplacer)
        return nodes

    for el in findAll(".prod", doc):
        transformElement(el)
