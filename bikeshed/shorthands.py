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

    biblioRe = re.compile(r"(\\)?\[\[(!)?([\w.-]+)((?: +current)|(?: +dated))?\]\]")

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
        return E.code({"class":"idl"},
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

    elementRe = re.compile(r"<{(?:([\w*-]+)/)?([\w*-]+)(?:!!([\w-]+))?(\|[^}]+)?}>")

    def elementReplacer(match):
        if match.group(1) == "":
            linkFor = "/"
        else:
            linkFor = match.group(1)
        if match.group(3) is not None:
            linkType = match.group(3)
        elif match.group(1) is None:
            linkType = "element"
        else:
            linkType = "element-sub"
        if match.group(4) is not None:
            linkText = match.group(4)[1:]
        else:
            linkText = match.group(2)
        return E.code({},
                      E.a({"data-link-type":linkType, "for": linkFor, "lt":match.group(2)}, linkText))

    varRe = re.compile(r"\|(\w(?:[\w\s-]*\w)?)\|")

    def varReplacer(match):
        return E.var(match.group(1))

    strongRe = re.compile(r"(?<!\\)([_*])\1(?!\s)([^\1]+)(?!\s)(?<!\\)\1\1")

    def strongReplacer(match):
        return E.strong(match.group(2))

    emRe = re.compile(r"(?<!\\)([_*])(?!\s)([^\1]+)(?!\s)(?<!\\)\1")

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
