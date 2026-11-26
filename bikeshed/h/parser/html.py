"""HTML lexical and tag-level parsing: tags, attributes, shortcuts, char refs, comments, doctypes, raw elements, and datablocks."""

from __future__ import annotations

import re
from enum import Enum

from ... import config, t
from ... import messages as m
from .. import elements
from . import macros, preds
from .nodes import (
    Comment,
    Doctype,
    EndTag,
    ParserNode,
    RawElement,
    SafeText,
    SelfClosedTag,
    StartTag,
    escapeAttr,
    minimalEscapeAttr,
)
from .preds import charRefs
from .result import Err, Ok
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import OkT, ResultT


_DATABLOCK_CLASSES = frozenset(
    (
        "simpledef",
        "propdef",
        "descdef",
        "elementdef",
        "argumentdef",
        "railroad",
        "biblio",
        "anchors",
        "link-defaults",
        "ignored-specs",
        "info",
        "highlight-grammar",
        "include",
        "include-code",
        "include-raw",
    ),
)

ATTR_SHORTCUTS = {
    "export": "data-export",
    "noexport": "data-noexport",
    "link-spec": "bs-link-spec",
    "data-link-spec": "bs-link-spec",
    "spec": "bs-link-spec",
    "link-status": "bs-link-status",
    "data-link-status": "bs-link-status",
    "status": "bs-link-status",
    "dfn-for": "data-dfn-for",
    "link-for": "bs-link-for",
    "data-link-for": "bs-link-for",
    "link-for-hint": "bs-link-for-hint",
    "data-link-for-hint": "bs-link-for-hint",
    "dfn-type": "data-dfn-type",
    "dfn-force": "bs-dfn-force",
    "data-dfn-force": "bs-dfn-force",
    "force": "bs-dfn-force",
    "section": "bs-section",
    "data-section": "bs-section",
    "attribute-info": "bs-attribute-info",
    "data-attribute-info": "bs-attribute-info",
    "dict-member-info": "bs-dict-member-info",
    "data-dict-member-info": "bs-dict-member-info",
    "local-lt": "data-local-lt",
    "algorithm": "data-algorithm",
    "ignore": "bs-ignore",
    "data-var-ignore": "bs-ignore",
    "highlight": "bs-highlight",
    "nohighlight": "bs-nohighlight",
    "line-numbers": "bs-line-numbers",
    "no-line-numbers": "bs-no-line-numbers",
    "line-start": "bs-line-start",
    "line-highlight": "bs-line-highlight",
    "nocrossorigin": "bs-nocrossorigin",
    "data-opaque": "bs-opaque",
    "caniuse": "bs-caniuse",
    "no-autosize": "bs-no-autosize",
    "include-if": "bs-include-if",
    "exclude-if": "bs-exclude-if",
    "tracking-vector": "bs-tracking-vector",
    "heading": "bs-heading",
    "oldids": "bs-oldids",
    "assert": "bs-assert",
    "skip-existence-check": "bs-skip-existence-check",
    "pathprefix": "bs-pathprefix",
    "data-remote-issue-id": "bs-remote-issue-id",
    "data-no-self-link": "bs-no-self-link",
    "data-silently-dedup": "bs-silently-dedup",
    "data-okay-to-fail": "bs-okay-to-fail",
    "data-biblio-type": "bs-biblio-type",
    "data-biblio-status": "bs-biblio-status",
    "data-biblio-display": "bs-biblio-display",
    "data-biblio-obsolete": "bs-biblio-obsolete",
    "boilerplate": "bs-boilerplate",
    "data-no-idl": "bs-no-idl",
    "data-no-cddl": "bs-no-cddl",
    "data-cddl-module": "bs-cddl-module",
    "data-deco": "bs-deco",
}

_ASCII_TAGNAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9._-]*")
_ASCII_ATTRNAME_RE = re.compile(r"[a-zA-Z0-9._:-]+")
_WHITESPACE_RE = re.compile(r"[\t\n\x0c ]+")
_UNQUOTED_ATTR_STOP_RE = re.compile(r"[\t\n\x0c >\"'<`&]")
_SVG_DOCTYPE_RE = re.compile(r"\s+svg(?![\w-])", re.I)
_DATABLOCK_PRE_STOP_RE = re.compile(r"</pre>|&")
_BS_MACRO_SCAN_RE = re.compile(r"<!--|<bs-macro(?=[\t\n\x0c />])|</bs-macro>", re.I)
metadataPreEndRe = re.compile(r"</pre>(.*)")
metadataXmpEndRe = re.compile(r"</xmp>(.*)")


def isDatablock(tag: StartTag, loc: str) -> str | None:
    """Return the single Bikeshed datablock class on `tag`, or `None` (logging an error if multiple match)."""
    tag.finalize()
    types = [x for x in tag.classes if isDatablockClass(x)]
    if len(types) == 0:
        return None
    elif len(types) == 1:
        return types[0]
    else:
        m.die(
            "Found {} classes on the <{}>, so can't tell which to process the block as. Please use only one.".format(
                config.englishFromList((f"'{x}'" for x in types), "and"),
                tag.tag,
            ),
            lineNum=loc,
        )
        return None


def isDatablockClass(text: str) -> bool:
    """Return True if `text` is a recognized Bikeshed datablock class name."""
    return text in _DATABLOCK_CLASSES


def parseStartTag(
    s: Stream,
    start: int,
    parseRepoLink: t.Callable[[Stream, int, str, int], ResultT[list[ParserNode]]] | None = None,
) -> ResultT[StartTag | SelfClosedTag | list[ParserNode]]:
    """Parse an HTML start tag (or void/self-closed tag, or `<org/repo#123>` repository link) at `start`."""
    if s[start] != "<":
        return Err(start)
    else:
        i = start + 1

    tagname, i, _ = parseTagName(s, i)
    if tagname is None:
        return Err(start)

    # At this point it might be an <org/repo#123> repo link,
    # so guard against that before going further.
    if s[i] == "/" and s.config.repositoryLinks and parseRepoLink is not None:
        repoLink, i, _ = parseRepoLink(s, i + 1, tagname, start)
        if repoLink:
            return Ok(repoLink, i)
        # If that failed, this'll just hit the "bad self-closing syntax" error path,
        # which is fine, so let it just run its course.

    # After this point we're committed to a start tag,
    # so failure will really be a parse error.

    attrs, i, _ = parseAttributeList(s, i)
    if attrs is None:
        return Err(start)

    safeAttrs: t.SafeAttrDict = {k: minimalEscapeAttr(v) for k, v in attrs.items()}

    _, i, _ = parseWhitespace(s, i)

    el: SelfClosedTag | StartTag
    if s[i] == "/":
        if s[i + 1] == ">" and (
            tagname in ("br", "link", "meta")
            or preds.isXMLishTagname(tagname)
            or (s.config.rawHtml and tagname in elements.VOID_ELEMENTS)
        ):
            el = SelfClosedTag.fromStream(s, start, i + 2, tagname, safeAttrs)
            return Ok(el if s.config.rawHtml else canonicalizeShortcuts(el), i + 2)
        elif tagname in elements.VOID_ELEMENTS:
            m.die(f"Void element (<{tagname}>) with a spurious trailing /.", lineNum=s.loc(start))
            i += 1
            # Skip past and handle it normally
        else:
            m.die(
                f"Invalid use of self-closing syntax (trailing / on start tag) on a non-XML element (<{tagname}>).",
                lineNum=s.loc(start),
            )
            i += 1
            # Again, just skip it and keep going.

    if s[i] == ">":
        if tagname in elements.VOID_ELEMENTS:
            el = SelfClosedTag.fromStream(s, start, i + 1, tagname, safeAttrs)
        else:
            el = StartTag.fromStream(s, start, i + 1, tagname, safeAttrs)
        return Ok(el if s.config.rawHtml else canonicalizeShortcuts(el), i + 1)

    if s.eof(i):
        m.die(f"Tag <{tagname}> wasn't closed at end of file.", lineNum=s.loc(start))
        return Err(start)

    # If I can, guess at what the 'garbage' is so I can display it.
    # Only look at next 20 chars, tho, so I don't spam the console.
    next20 = s.slice(i, i + 20)
    if ">" in next20 or " " in next20:
        garbageEnd = min(config.safeIndex(next20, ">", 20), config.safeIndex(next20, " ", 20))
        m.die(
            f"While trying to parse a <{tagname}> start tag, ran into some unparseable stuff ({next20[:garbageEnd]}).",
            lineNum=s.loc(i),
        )
    else:
        m.die(f"While trying to parse a <{tagname}> start tag, ran into some unparseable stuff.", lineNum=s.loc(i))
    return Err(start)


def canonicalizeShortcuts(el: StartTag | SelfClosedTag) -> StartTag | SelfClosedTag:
    """Rewrite Bikeshed shorthand attributes (like `export`, `for`, `lt`, and boolean dfn/link types) to canonical `bs-*`/`data-*` names."""
    attrs = el.attrs
    if not attrs:
        return el
    for oldAttr in tuple(attrs):
        if newAttr := ATTR_SHORTCUTS.get(oldAttr):
            attrs[newAttr] = attrs.pop(oldAttr)

    # Some of these attrs conflict with existing real attributes on some elements.
    # Instead, limit the search/transforms to the relevant elements.
    tag = el.tag
    if tag in ("dfn", "h2", "h3", "h4", "h5", "h6"):
        for dfnType, val in attrs.items():
            if dfnType in config.dfnTypes:
                if val == "":
                    del attrs[dfnType]
                    attrs["data-dfn-type"] = escapeAttr(dfnType)
                    break
                elif dfnType == "type" and val in config.dfnTypes:
                    m.die(
                        f"You used type={val}, which isn't valid. Instead use just {val} as a boolean attribute, or dfn-type={val}.",
                        lineNum=el.loc,
                    )
                    del attrs["type"]
                    break

    if tag in ("a", "l"):
        for linkType in attrs:
            if linkType in config.linkTypes:
                del attrs[linkType]
                attrs["data-link-type"] = escapeAttr(linkType)
                break

    if tag in ("a", "l", "bs-link"):
        if "link-type" in attrs:
            attrs["data-link-type"] = attrs.pop("link-type")
    else:
        if "link-type" in attrs:
            attrs["bs-link-type"] = attrs.pop("link-type")
        if "data-link-type" in attrs:
            attrs["bs-link-type"] = attrs.pop("data-link-type")

    if tag in config.dfnElements:
        if "lt" in attrs:
            attrs["data-lt"] = attrs.pop("lt")
    else:
        if "lt" in attrs:
            attrs["bs-lt"] = attrs.pop("lt")
        if "data-lt" in attrs:
            attrs["bs-lt"] = attrs.pop("data-lt")

    if tag in ("a", "l") and "for" in attrs:
        attrs["bs-link-for"] = attrs.pop("for")

    if (
        (tag == "dfn" and "bs-ignore" not in attrs)
        or (tag in ("h2", "h3", "h4", "h5", "h6") and "data-dfn-type" in attrs)
    ) and "for" in attrs:
        attrs["data-dfn-for"] = attrs.pop("for")

    if tag == "span" and ("bs-attribute-info" in attrs or "bs-dict-member-info" in attrs) and "for" in attrs:
        attrs["bs-for"] = attrs.pop("for")

    return el


def parseTagName(s: Stream, start: int) -> ResultT[str]:
    """Parse an HTML/XML tag name at `start` and return it lowercased."""
    match = _ASCII_TAGNAME_RE.match(s.chars, start)
    if not match:
        return Err(start)
    end = match.end()
    while preds.isTagnameChar(s[end]):
        end += 1
    return Ok(s.chars[start:end].lower(), end)


def parseAttributeList(s: Stream, start: int) -> ResultT[dict[str, str]]:
    """Parse zero or more HTML attributes (and attribute-list macros) inside a start tag."""
    _, i, _ = parseWhitespace(s, start)
    attrs: dict[str, str] = {}
    while True:
        if s.eof(i):
            break
        startAttr = i

        # Macros are allowed in attr list context, *if* they expand to an attribute list.
        if not s.config.rawHtml and s[i] == "[":
            macroAttrs, i, _ = macros.parseMacroToAttrs(s, i, parseAttributeList, parseWhitespace)
            if macroAttrs is None:
                break
            macroName = s.slice(startAttr, i)
            for k, v in macroAttrs.items():
                if k in attrs:
                    m.die(
                        f"Attribute '{k}', coming from the {macroName} macro, already exists on the element.",
                        lineNum=s.loc(startAttr),
                    )
                    continue
                attrs[k] = v
        elif preds.isAttrNameChar(s[i]):
            attr, i, _ = parseAttribute(s, i)
            if attr is None:
                break
            attrName, attrValue = attr
            if attrName in attrs:
                if s.config.rawHtml:
                    ws, i, _ = parseWhitespace(s, i)
                    if ws is None:
                        break
                    continue
                m.die(f"Attribute '{attrName}' appears twice in the tag.", lineNum=s.loc(startAttr))
                return Err(start)
            if not s.config.rawHtml and "[" in attrValue:
                attrValue = macros.replaceMacrosInText(
                    text=attrValue,
                    macros=s.config.macros,
                    s=s,
                    start=i,
                    context=f"attribute {attrName}='...'",
                )
            attrs[attrName] = attrValue
        else:
            break

        ws, i, _ = parseWhitespace(s, i)
        if ws is None:
            # We're definitely done, just see if it should be an error or not.
            if s.eof(i):
                # At the end of a macro, most likely
                # (or the doc ended with an unclosed tag, so I'll catch that later)
                break
            if s[i] in ("/", ">"):
                # End of a tag
                break
            m.die(
                f"Expected whitespace between attributes. ({s.slice(startAttr, i+5)}...)",
                lineNum=s.loc(i),
            )
            break
    return Ok(attrs, i)


def parseAttribute(s: Stream, start: int) -> ResultT[tuple[str, str]]:
    """Parse a single HTML attribute (`name` or `name=value`) at `start`."""
    match = _ASCII_ATTRNAME_RE.match(s.chars, start)
    i = match.end() if match else start
    while preds.isAttrNameChar(s[i]):
        i += 1
    if i == start:
        return Err(start)

    # Committed to an attribute

    attrName = s.slice(start, i)
    endOfName = i
    _, i, _ = parseWhitespace(s, i)
    if s[i] == "=":
        i += 1
    else:
        return Ok((attrName, ""), endOfName)

    # Now committed to a value too

    _, i, _ = parseWhitespace(s, i)

    if s[i] == '"' or s[i] == "'":
        attrValue, i, _ = parseQuotedAttrValue(s, i)
    else:
        attrValue, i, _ = parseUnquotedAttrValue(s, i)
    if attrValue is None:
        m.die(f"Garbage after {attrName}=.", lineNum=s.loc(i))
        return Err(start)

    return Ok((attrName, attrValue), i)


def parseQuotedAttrValue(s: Stream, start: int) -> ResultT[str]:
    """Parse a single- or double-quoted HTML attribute value, normalizing character references."""
    endChar = s[start]
    i = start + 1
    val = ""
    while True:
        endIndex = s.chars.find(endChar, i)
        if endIndex == -1:
            m.die("Quoted attribute was never closed", lineNum=s.loc(start))
            return Err(start)
        ampIndex = s.chars.find("&", i, endIndex)
        if ampIndex == -1:
            val += s.chars[i:endIndex]
            return Ok(val, endIndex + 1)
        val += s.chars[i:ampIndex]
        ch, i, _ = parseCharRef(s, ampIndex, context=CharRefContext.Attr)
        if ch is None:
            val += "&"
            i = ampIndex + 1
        else:
            val += printChAsCharRef(ch)


def parseUnquotedAttrValue(s: Stream, start: int) -> ResultT[str]:
    """Parse an unquoted HTML attribute value up to whitespace or `>`, normalizing character references."""
    i = start
    val = ""
    while match := _UNQUOTED_ATTR_STOP_RE.search(s.chars, i):
        stopIndex = match.start()
        ch = s.chars[stopIndex]
        if ch == ">" or ch in preds.WHITESPACE_CHARS:
            val += s.chars[i:stopIndex]
            i = stopIndex
            break
        if ch in "\"'<`":
            m.die(
                f"Character {ch} (at {s.loc(stopIndex)}) is invalid in unquoted attribute values.",
                lineNum=s.loc(start),
            )
            return Err(start)
        # Otherwise ch == "&"
        val += s.chars[i:stopIndex]
        ref, i, _ = parseCharRef(s, stopIndex, context=CharRefContext.Attr)
        if ref is None:
            val += "&"
            i = stopIndex + 1
        else:
            val += printChAsCharRef(ref)
    else:
        val += s.chars[i:]
        i = s.length
    if i == start:
        m.die("Missing attribute value.", lineNum=s.loc(start))
        return Err(start)
    return Ok(val, i)


def printChAsCharRef(ch: str | SafeText) -> str:
    """
    * If passed a str (which should have been the value of a char ref),
        prints it back into char refs for normalization purposes.
        (Sometimes more than one, as some char refs are multi-char.)
    * If passed a SafeText (which should have been the result of a *failed*
        char ref parsing, giving some portion of the bad char ref),
        just stringifies it, since that'll give an escaped & at least.
    """
    if isinstance(ch, str):
        return "".join(f"&#{ord(x)};" for x in ch)
    else:
        return str(ch)


class CharRefContext(Enum):
    """Parsing context controlling whether `&name=` is left unparsed as a query parameter."""

    Attr = "Attr"
    NonAttr = "NonAttr"
    DatablockPre = "DatablockPre"


def parseCharRef(s: Stream, start: int, context: CharRefContext) -> ResultT[str | SafeText]:
    """Parse an HTML named/numeric or Bikeshed `&bs...;` character reference at `start`."""
    if s[start] != "&":
        return Err(start)
    i = start + 1

    if s.slice(i, i + 2) == "bs":
        bsEscape, i, _ = s.skipToSameLine(i, ";")
        i += 1
        if bsEscape is None:
            m.die(
                "Saw the start of an &bs...; escape, but couldn't find the ending semicolon. If this wasn't intended, escape the & with &amp;",
                lineNum=s.loc(start),
            )
            return Ok(SafeText.fromStream(s, start, i), i)
        if len(bsEscape) == 3 and bsEscape[2] in "`~!@#$%^&*()-_=+[]{}\\|:'\"<>,./?":
            return Ok(bsEscape[2], i)
        elif len(bsEscape) == 2 and s.slice(start, start + 5) == "&bs;;":
            # handling &bs;; to escape a semicolon...
            return Ok(";", i + 1)
        elif bsEscape == "bs<<":
            return Ok("«", i)
        elif bsEscape == "bs>>":
            return Ok("»", i)
        elif bsEscape == "bs->":
            return Ok("→", i)
        else:
            m.die(
                f"&{bsEscape}; isn't a valid Bikeshed character reference. See <https://speced.github.io/bikeshed/#bs-charref>.",
                lineNum=s.loc(start),
            )
            return Ok(SafeText.fromStream(s, start, i), i)
    elif preds.isASCIIAlphanum(s[i]):
        i += 1
        while preds.isASCIIAlphanum(s[i]):
            i += 1
        if s[i] == "=":
            if context is CharRefContext.Attr or context is CharRefContext.DatablockPre:
                # HTML allows you to write <a href="?foo&bar=baz">
                # without escaping the ampersand, even if it matches
                # a named charRef so long as there's an `=` after it.
                return Err(start)
            elif context is CharRefContext.NonAttr:
                pass
            else:
                t.assert_never(context)
        if s[i] != ";":
            m.die(f"Character reference '{s.slice(start, i)}' didn't end in ;.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        i += 1
        if s.slice(start, i) not in charRefs:
            m.die(f"'{s.slice(start, i)} isn't a valid character reference.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        return Ok(charRefs[s.slice(start, i)], i)
    elif s[i] == "#":
        i += 1
        isHex = s[i] in ("x", "X")
        if isHex:
            i += 1
        numStart = i
        digitPred = preds.isHexDigit if isHex else preds.isDigit
        while digitPred(s[i]):
            i += 1
        if i == numStart:
            kind = "hex" if isHex else "decimal"
            m.die(
                f"Saw the start of a {kind} char ref ({s.slice(start, i)}), but no hex digits follow it.",
                lineNum=s.loc(start),
            )
            return Ok(SafeText.fromStream(s, start, i), i)
        if s[i] != ";":
            m.die(f"Char ref '{s.slice(start, i)}' didn't end in ;.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        cp = int(s.slice(numStart, i), 16 if isHex else 10)
        i += 1
        if cp == 0:
            m.die("Char refs can't resolve to U+0000 NULL.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        if cp > 0x10FFFF:
            m.die(f"Char ref '{s.slice(start, i)}' is outside of Unicode.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        if 0xD800 <= cp <= 0xDFFF:
            m.die(f"Char ref '{s.slice(start, i)}' is a lone surrogate.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        if preds.isNoncharacter(cp):
            m.die(f"Char ref '{s.slice(start, i)}' is a non-character.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        if cp == 0xD or (preds.isControl(cp) and not preds.isWhitespace(cp)):
            m.die(f"Char ref '{s.slice(start, i)}' is a control character.", lineNum=s.loc(start))
            return Ok(SafeText.fromStream(s, start, i), i)
        return Ok(chr(cp), i)
    else:
        return Err(start)


def parseWhitespace(s: Stream, start: int) -> ResultT[bool]:
    """Consume one or more HTML ASCII whitespace characters at `start`."""
    if start >= s.length or s.chars[start] not in preds.WHITESPACE_CHARS:
        return Err(start)
    match = _WHITESPACE_RE.match(s.chars, start)
    assert match is not None
    return Ok(True, match.end())


def parseEndTag(s: Stream, start: int) -> ResultT[EndTag]:
    """Parse an HTML closing tag (`</tag>`) at `start`."""
    if s.slice(start, start + 2) != "</":
        return Err(start)
    i = start + 2

    # committed now

    if s[i] == ">":
        m.die("Missing end tag name. (Got </>.)", lineNum=s.loc(start))
        return Err(start)
    if s.eof(i):
        m.die("Hit EOF in the middle of an end tag.", lineNum=s.loc(start))
        return Err(start)
    tagname, i, _ = parseTagName(s, i)
    if tagname is None:
        m.die("Garbage in an end tag.", lineNum=s.loc(start))
        return Err(start)
    if tagname in elements.VOID_ELEMENTS:
        m.die(f"Saw an end tag </{tagname}> for a void element.", lineNum=s.loc(start))
        return Err(start)
    if s.eof(i):
        m.die(f"Hit EOF in the middle of an end tag </{tagname}>.", lineNum=s.loc(start))
        return Err(start)
    if s.config.rawHtml:
        _, i, _ = parseWhitespace(s, i)
    if s[i] != ">":
        m.die(f"Garbage after the tagname in </{tagname}>.", lineNum=s.loc(start))
        return Err(start)
    i += 1
    return Ok(EndTag.fromStream(s, start, i, tagname), i)


def parseComment(s: Stream, start: int) -> ResultT[Comment]:
    """Parse an HTML `<!-- ... -->` comment at `start`."""
    if s.slice(start, start + 2) != "<!":
        return Err(start)
    i = start + 2

    # committed
    if s.slice(i, i + 2) != "--":
        m.die(f"Malformed HTML comment '{s.slice(start, start+10)}'.", lineNum=s.loc(start))
        return Err(start)
    i += 2

    dataStart = i

    while True:
        dashIndex = s.chars.find("--", i)
        if dashIndex == -1:
            m.die("Hit EOF in the middle of a comment.", lineNum=s.loc(start))
            return Err(start)
        i = dashIndex
        if s.slice(i, i + 3) == "-->":
            return Ok(
                Comment.fromStream(s, start, i + 3, s.slice(dataStart, i)),
                i + 3,
            )
        if s.slice(i, i + 4) == "--!>":
            m.die("Malformed comment - don't use a ! at the end.", lineNum=s.loc(start))
            return Err(start)
        i += 1


def parseDoctype(s: Stream, start: int) -> ResultT[Doctype]:
    """Parse an HTML `<!doctype ...>` declaration, rejecting non-leading doctypes in Bikeshed markup."""
    if s.slice(start, start + 2) != "<!":
        return Err(start)
    if s.slice(start + 2, start + 9).lower() != "doctype":
        return Err(start)
    endIndex = s.chars.find(">", start + 9)
    if endIndex == -1:
        m.die("Hit EOF in the middle of a doctype.", lineNum=s.loc(start))
        end = len(s)
    else:
        end = endIndex + 1
        if start != 0 or s.startLine != 1 or s.colOffset(0) != 0:
            if _SVG_DOCTYPE_RE.match(s.slice(start + 9, endIndex)):
                m.die(
                    "Inline SVG fragments must not include a doctype or processing instruction.",
                    lineNum=s.loc(start),
                )
            else:
                m.die("Bikeshed markup does not use a doctype.", lineNum=s.loc(start))
    node = Doctype.fromStream(s, start, end, s.slice(start, end))
    return Ok(node, end)


def parseRawElementToEnd(s: Stream, start: int, tag: str) -> OkT[str]:
    """Read raw `<script>`, `<style>`, or `<xmp>` contents from `start` through `</tag>` (or EOF)."""
    endTag = f"</{tag}>"
    i = s.chars.find(endTag, start)
    if i == -1:
        article = "an" if tag == "xmp" else "a"
        m.die(f"Hit EOF in the middle of {article} <{tag}>.", lineNum=s.loc(start))
        return Ok(s.slice(start, None), len(s))
    return Ok(s.slice(start, i), i + len(endTag))


def parseBsMacroToEnd(s: Stream, start: int, startTag: StartTag) -> ResultT[str]:
    """Read a `<bs-macro>` body from `start` through its matching `</bs-macro>`, tracking nested `<bs-macro>` tags."""
    chars = s.chars
    length = s.length
    depth = 1
    pos = start
    while True:
        match = _BS_MACRO_SCAN_RE.search(chars, pos)
        if match is None:
            m.die("<bs-macro> element was never closed.", lineNum=startTag.loc)
            return Err(start)
        tok = match.group(0).lower()
        if tok == "<!--":
            endComment = chars.find("-->", match.end())
            if endComment == -1:
                m.die("<bs-macro> element was never closed.", lineNum=startTag.loc)
                return Err(start)
            pos = endComment + 3
        elif tok == "</bs-macro>":
            depth -= 1
            if depth == 0:
                return Ok(s.slice(start, match.start()), match.end())
            pos = match.end()
        else:
            depth += 1
            qPos = match.end()
            quote: str | None = None
            while qPos < length:
                ch = chars[qPos]
                if quote is not None:
                    if ch == quote:
                        quote = None
                elif ch in ('"', "'"):
                    quote = ch
                elif ch == ">":
                    qPos += 1
                    break
                qPos += 1
            pos = qPos


def parseTitleToEnd(s: Stream, start: int) -> ResultT[str]:
    """Read `<title>` contents through `</title>`, normalizing HTML character references and expanding text macros."""
    i = start
    val = ""
    startSeg = i
    while True:
        if s.eof(i):
            m.die("Hit EOF while the document's <title> was still open.", lineNum=s.loc(start))
            return Err(start)
        elif s.slice(i, i + 8) == "</title>":
            val += s.slice(startSeg, i)
            break
        elif s[i] == "&":
            startRef = i
            ch, i, _ = parseCharRef(s, i, context=CharRefContext.NonAttr)
            if ch is None:
                i += 1
                continue
            val += s.slice(startSeg, startRef) + printChAsCharRef(ch)
            startSeg = i
            continue
        elif s[i] == "[":
            startMacro = i
            text, i, _ = macros.parseMacroToText(s, i)
            if text is None:
                i += 1
                continue
            val += s.slice(startSeg, startMacro) + text
            startSeg = i
            continue
        else:
            i += 1
    return Ok(val, i + 8)


def parseDatablockPreToEnd(s: Stream, start: int) -> ResultT[str]:
    """Read a datablock `<pre>` body through `</pre>`, normalizing named HTML entities to numeric ones for LXML."""
    i = start
    val = ""
    startSeg = i
    while True:
        match = _DATABLOCK_PRE_STOP_RE.search(s.chars, i)
        if match is None:
            m.die("Hit EOF in the middle of a <pre> datablock.", lineNum=s.loc(start))
            return Err(start)
        i = match.start()
        if match.group(0) == "</pre>":
            val += s.slice(startSeg, i)
            return Ok(val, i + 6)
        startRef = i
        ch, i, _ = parseCharRef(s, i, context=CharRefContext.DatablockPre)
        if ch is None:
            i += 1
            continue
        val += s.slice(startSeg, startRef) + printChAsCharRef(ch)
        startSeg = i


def isMetadataBlock(startTag: StartTag) -> bool:
    """Return True if `startTag` is a `<pre class=metadata>` or `<xmp class=metadata>` opener."""
    if startTag.tag not in ("pre", "xmp"):
        return False
    startTag.finalize()
    return "metadata" in startTag.classes


def parseMetadataBlockToEnd(s: Stream, start: int, startTag: StartTag, i: int) -> ResultT[RawElement]:
    """Consume an unindented `<pre/xmp class=metadata>` block through its closing tag."""
    if start != s.currentLineStart(start) or s.col(start) != 1:
        # Metadata blocks must have their start/end tags
        # on the left margin, completely unindented.
        return Err(start)
    line, i, _ = s.skipToNextLine(i)
    assert line is not None
    if line.strip() != "":
        m.die("Significant text on the same line as the metadata start tag isn't allowed.", lineNum=s.loc(start))
    contents = line
    endPattern = metadataPreEndRe if startTag.tag == "pre" else metadataXmpEndRe
    while True:
        if s.eof(i):
            m.die("Hit EOF while trying to parse a metadata block.", lineNum=s.loc(start))
            break
        line, i, _ = s.skipToNextLine(i)
        assert line is not None
        match = endPattern.match(line)
        if not match:
            contents += line
            continue
        # Hit the end tag
        # Back up one char so we're actually ending at the end
        # of the construct, rather than on the next line.
        if line.endswith("\n"):
            i -= 1
        if match.group(1).strip() != "":
            m.die("Significant text on the same line as the metadata end tag isn't allowed.", lineNum=s.loc(i))
        break

    el = RawElement.fromStream(s, start, i, startTag, contents)
    return Ok(el, i)
