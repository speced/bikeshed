"""Bikeshed inline autolink and variable shorthands (dfn, abstract-op, HTTP header, IDL, CDDL, markup, biblio/section, repo issue, and `|var|`)."""

from __future__ import annotations

import dataclasses
import re

from ... import config, t
from ... import messages as m
from .html import parseTagName
from .macros import replaceMacrosInText
from .nodes import EndTag, ParserNode, RawText, SafeText, StartTag, escapeAttr
from .preds import isDigit
from .result import Err, Ok, isErr
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import ResultT
    from .stream import ResultGeneratorFn

# Characters used by the [...]-type autolinks, inside of the bracket.
BRACKET_AUTOLINK_CHARS = "=$:[]^"

AUTOLINK_DFN_RE = re.compile(r".*?(?=\||=])", flags=re.DOTALL)
AUTOLINK_ABSTRACT_RE = re.compile(r".*?(?=\||\$])", flags=re.DOTALL)
AUTOLINK_HEADER_RE = re.compile(r":?.*?(?=\||:])", flags=re.DOTALL)
AUTOLINK_IDL_RE = re.compile(r".*?(?=\||}})", flags=re.DOTALL)
AUTOLINK_CDDL_RE = re.compile(r".*?(?=\||\^})", flags=re.DOTALL)
AUTOLINK_ELEMENT_RE = re.compile(r".*?(?=\||}>)", flags=re.DOTALL)
SHORTHAND_VARIABLE_RE = re.compile(r"\|(\w(?:[\w\s-]*\w)?)\|")

_LINK_HTML_ESCAPE_RE = re.compile(r"&[\w\d#]+;")
_LINK_WS_RE = re.compile(r"\s+")

AUTOLINK_BIBLIO_RE = re.compile(r"(!?)([\w.+-]+)((?:\s+\w+)*)(?=\||\]\])")
AUTOLINK_BIBLIO_KEYWORDS = ["current", "snapshot", "inline", "index", "direct", "obsolete"]
AUTOLINK_SECTION_RE = re.compile(
    r"""
    ([\w.+-]+)?                           # optional spec name
    (?:
        ((?:\/[\w.+-]*)?(?:\#[\w.+-]+)) | # /page#heading
        (\/[\w.+-]+)                      # /page only
    )
    (?=\||\]\])
    """,
    re.X,
)


@dataclasses.dataclass
class LinkData:
    """Parsed metadata (`lt`, optional `for`, optional `type`) from the target section of an autolink shorthand."""

    lt: str
    lfor: str | None = None
    ltype: str | None = None


def parseLinkInfo(
    s: Stream,
    innerStart: int,
    startSigil: str,
    endSigil: str,
    infoRe: t.Pattern,
) -> ResultT[LinkData]:
    """Parse the `for/lt!!type` target portion of an autolink shorthand up to `|` or `endSigil`."""
    start = innerStart - len(startSigil)
    match, innerEnd, _ = s.searchRe(innerStart, infoRe)
    if match is None or match[0].count("\n") > 1:
        m.die(
            f"{startSigil}...{endSigil} autolink was opened, but couldn't find {endSigil} or | on the same or next line. Either close your autolink, or escape the initial {startSigil[0]} as &bs{startSigil[0]};",
            lineNum=s.loc(start),
        )
        return Err(innerStart)

    innerText = match[0]
    if s.config.macrosInAutolinks:
        lt = replaceMacrosInText(
            text=innerText,
            macros=s.config.macros,
            s=s,
            start=innerStart,
            context=startSigil + innerText + endSigil,
        )
    else:
        lt = innerText

    if "&" in lt and _LINK_HTML_ESCAPE_RE.search(lt):
        m.die(
            "Saw an HTML escape in the link-data portion of an autolink. Use raw characters, or switch to the HTML syntax.",
            lineNum=s.loc(start),
        )
        # Okay to keep going, tho, it'll just fail to link.

    linkFor = None
    linkType = None
    if "/" in lt:
        linkFor, _, lt = lt.rpartition("/")
        if linkFor == "":
            linkFor = "/"
        linkFor = linkFor.strip()
        linkFor = _LINK_WS_RE.sub(" ", linkFor)
    if "!!" in lt:
        lt, _, linkType = lt.partition("!!")
        linkType = linkType.strip()
    lt = lt.strip()
    lt = _LINK_WS_RE.sub(" ", lt)

    # Even tho you no longer *need* to escape [[..]] in links
    # (used for WebIDL private slots), the parser still *allows*
    # it, and graciously/silently handles the unnecessary escape.
    # The one exception is if it's link details, since they're not
    # parsed normally, so we need to fix it right here.
    if linkFor and linkFor.startswith("\\[["):
        linkFor = linkFor[1:]
    if lt and lt.startswith("\\[["):
        lt = lt[1:]

    return Ok(LinkData(lt, linkFor, linkType), innerEnd)


def parseLinkText(
    s: Stream,
    start: int,
    startingSigil: str,
    endingSigil: str,
    startTag: StartTag,
    *,
    generateResults: ResultGeneratorFn,
) -> ResultT[list[ParserNode]]:
    """Parse rich inline content inside an autolink up to `endingSigil` (within 3 lines), returning inner nodes + closing `EndTag`."""
    endingLength = len(endingSigil)
    content: list[ParserNode] = []
    s.observeShorthandOpen(startTag, (startingSigil, endingSigil))
    # generateResults() stops at every POSSIBLE_NODE_START_CHARS boundary, guaranteeing `endingSigil` lands on `i`.
    for res in generateResults(s, start):
        value, i, _ = res
        assert value is not None
        if isinstance(value, list):
            content.extend(value)
        else:
            content.append(value)
        if s.chars.count("\n", start, i) > 3:
            m.die(
                f"{startingSigil}...{endingSigil} autolink opened at {startTag.loc} wasn't closed within 3 lines. You might have forgotten to close it; if not, switch to the HTML syntax to spread your link across that many lines.",
                lineNum=startTag.loc,
            )
            s.observeShorthandClose(s, i, startTag, (startingSigil, endingSigil))
            return Err(start)
        if s.slice(i, i + endingLength) == endingSigil:
            endTag = EndTag.fromStream(s, i, i + endingLength, startTag)
            virtualEndTags = s.observeShorthandClose(s, i, startTag, (startingSigil, endingSigil))
            content.extend(virtualEndTags)
            content.append(endTag)
            return Ok(content, i + endingLength)
    m.die(
        f"{startingSigil}...{endingSigil} autolink was opened at {startTag.loc}, and used | to indicate it was providing explicit linktext, but never closed. Either close your autolink, or escape the initial characters that triggered autolink parsing.",
        lineNum=startTag.loc,
    )
    return Err(start)


def parseAutolinkDfn(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[SafeText | list[ParserNode]]:
    """Parse a `[=dfn=]` or `[=dfn|text=]` definition autolink at `start`."""
    if s.slice(start, start + 2) != "[=":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "[=", "=]", AUTOLINK_DFN_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)

    lt, linkFor, linkType = dataclasses.astuple(data)
    if linkType == "dfn":
        pass
    elif linkType is None:
        linkType = "dfn"
    else:
        m.die(
            f"Autolink [={innerText}=] gave its type as '{linkType}', but only 'dfn' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "dfn"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": t.SafeAttrStr("dfn"),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[=" + innerText + "=]"),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "[=", "=]", startTag, generateResults=generateResults)
        if rest is not None:
            return Ok([startTag, *rest], nodeEnd)
        else:
            # Explicit link text never closed; stop right after `|` so the remaining text is parsed normally.
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Ok([startTag, middleText, endTag], nodeEnd)


def parseAutolinkAbstract(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[SafeText | list[ParserNode]]:
    """Parse a `[$op$]` or `[$op|text$]` abstract-operation autolink at `start`."""
    if s.slice(start, start + 2) != "[$":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "[$", "$]", AUTOLINK_ABSTRACT_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)
    lt, linkFor, linkType = dataclasses.astuple(data)

    if linkType == "abstract-op":
        pass
    elif linkType is None:
        linkType = "abstract-op"
    else:
        m.die(
            f"Autolink [${innerText}$] gave its type as '{linkType}', but only 'abstract-op' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "abstract-op"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": t.SafeAttrStr("abstract-op"),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[$" + innerText + "$]"),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "[$", "$]", startTag, generateResults=generateResults)
        if rest is not None:
            return Ok([startTag, *rest], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Ok([startTag, middleText, endTag], nodeEnd)


def parseAutolinkHeader(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[SafeText | list[ParserNode]]:
    """Parse a `[:Header:]` or `[:Header|text:]` HTTP header autolink, wrapped in backticks and `<code>`."""
    if s.slice(start, start + 2) != "[:":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "[:", ":]", AUTOLINK_HEADER_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)
    lt, linkFor, linkType = dataclasses.astuple(data)

    if linkType == "http-header":
        pass
    elif linkType is None:
        linkType = "http-header"
    else:
        m.die(
            f"Autolink [:{innerText}:] gave its type as '{linkType}', but only 'http-header' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "http-header"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 2,
        "a",
        {
            "data-link-type": t.SafeAttrStr("http-header"),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("[:" + innerText + ":]"),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    # HTTP specs format header names inside literal backticks around `<code><a>...</a></code>`.
    startTick = RawText.fromStream(s, start, start, "`")
    startCode = StartTag.fromStream(s, start, start, "code")

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "[:", ":]", startTag, generateResults=generateResults)
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            endTick = RawText.fromStream(s, nodeEnd, nodeEnd, "`")
            return Ok([startTick, startCode, startTag, *rest, endCode, endTick], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    endTick = RawText.fromStream(s, nodeEnd, nodeEnd, "`")
    return Ok([startTick, startCode, startTag, middleText, endTag, endCode, endTick], nodeEnd)


def parseAutolinkIdl(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a `{{Interface}}` or `{{Interface/member|text}}` WebIDL autolink wrapped in `<code class=idl>`."""
    if s.slice(start, start + 2) != "{{":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "{{", "}}", AUTOLINK_IDL_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)
    for badChar in ("{", "}"):
        if badChar in innerText:
            m.die(
                f"IDL autolink ({{{{...}}}}) contained a {badChar} in its data section, or meant to close itself and didn't do so correctly. If this was not meant to be an autolink, escape it or close it; if it was, switch to the manual <a> syntax to include this character.",
                lineNum=s.loc(start),
            )
            return Err(start)
    lt, linkFor, linkType = dataclasses.astuple(data)

    if linkType in config.idlTypes:
        pass
    elif linkType is None:
        linkType = "idl"
    else:
        m.die(
            f"IDL autolink {{{{{innerText}}}}} gave its type as '{linkType}', but only IDL types are allowed.",
            lineNum=s.loc(start),
        )
        linkType = "idl"

    if lt.startswith("constructor(") and linkFor and linkFor != "/":
        # make {{Foo/constructor()}} output as "Foo()" so you know what it's linking to.
        if "/" in linkFor:
            _, _, name = linkFor.rpartition("/")
        else:
            name = linkFor
        visibleText = name + lt[11:]
    else:
        visibleText = lt

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": escapeAttr(linkType),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s.slice(start, innerEnd + 2)),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startCode = StartTag.fromStream(
        s,
        start + 1,
        start + 1,
        "code",
        {"class": t.SafeAttrStr("idl"), "bs-nohighlight": ""},
    ).finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "{{", "}}", startTag, generateResults=generateResults)
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            return Ok([startCode, startTag, *rest, endCode], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, visibleText)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    return Ok([startCode, startTag, middleText, endTag, endCode], nodeEnd)


def parseAutolinkCddl(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a `{^type^}` or `{^type|text^}` CDDL autolink wrapped in `<code class=cddl>`."""
    if s.slice(start, start + 2) != "{^":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "{^", "^}", AUTOLINK_CDDL_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)
    lt, linkFor, linkType = dataclasses.astuple(data)

    if linkType in config.cddlTypes:
        pass
    elif linkType is None:
        linkType = "cddl"
    else:
        m.die(
            f"CDDL autolink {{^{innerText}^}} gave its type as '{linkType}', but only CDDL types are allowed.",
            lineNum=s.loc(start),
        )
        linkType = "cddl"

    visibleText = lt

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "a",
        {
            "data-link-type": t.SafeAttrStr(linkType),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr(s.slice(start, innerEnd + 2)),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    startCode = StartTag.fromStream(
        s,
        start + 1,
        start + 1,
        "code",
        {"class": t.SafeAttrStr("cddl"), "bs-nohighlight": ""},
    ).finalize()

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "{^", "^}", startTag, generateResults=generateResults)
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            return Ok([startCode, startTag, *rest, endCode], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, visibleText)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    return Ok([startCode, startTag, middleText, endTag, endCode], nodeEnd)


def parseAutolinkElement(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a `<{element}>`, `<{el/attr}>`, or `<{el/attr/val}>` markup autolink wrapped in `<code>`."""
    if s.slice(start, start + 2) != "<{":
        return Err(start)
    innerStart = start + 2

    data, innerEnd, _ = parseLinkInfo(s, innerStart, "<{", "}>", AUTOLINK_ELEMENT_RE)
    innerText = s.slice(innerStart, innerEnd)
    if data is None:
        return Err(start)
    lt, linkFor, linkType = dataclasses.astuple(data)

    if linkType is None:
        if linkFor is None:
            linkType = "element"
        elif "/" in linkFor:
            linkType = "attr-value"
        else:
            # either element-state or element-attr
            linkType = "element-sub"
    if linkType in config.markupTypes:
        pass
    else:
        m.die(
            f"Markup autolink <{{{innerText}}}> gave its type as '{linkType}', but only markup types are allowed.",
            lineNum=s.loc(start),
        )
        linkType = "element"

    startTag = StartTag.fromStream(
        s,
        start,
        start + 2,
        "a",
        {
            "data-link-type": t.SafeAttrStr(linkType),
            "bs-lt": escapeAttr(lt),
            "bs-autolink-syntax": escapeAttr("<{" + innerText + "}>"),
        },
    )
    if linkFor is not None:
        startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()
    startCode = StartTag.fromStream(s, start, start, "code", {"bs-nohighlight": ""})

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "<{", "}>", startTag, generateResults=generateResults)
        if rest is not None:
            endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
            return Ok([startCode, startTag, *rest, endCode], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = SafeText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    endCode = EndTag.fromStream(s, nodeEnd, nodeEnd, startCode)
    return Ok([startCode, startTag, middleText, endTag, endCode], nodeEnd)


def parseShorthandVariable(s: Stream, start: int) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse an algorithm variable shorthand (`|var|`) into `<var>var</var>`."""
    match, nodeEnd, _ = s.matchRe(start, SHORTHAND_VARIABLE_RE)
    if not match:
        return Err(start)

    startTag = StartTag.fromStream(
        s,
        start,
        start + 1,
        "var",
        {"bs-autolink-syntax": escapeAttr(match[0])},
    )
    contents = RawText.fromStream(s, start + 1, nodeEnd - 1)
    endTag = EndTag.fromStream(s, nodeEnd - 1, nodeEnd, startTag)
    return Ok([startTag, contents, endTag], nodeEnd)


def parseAutolinkBiblioSection(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a `[[SPEC]]` bibliography or `[[SPEC#sec]]` / `[[#sec]]` section autolink."""
    if s.slice(start, start + 2) != "[[":
        return Err(start)

    # A bunch of `[...]` autolink syntaxes can masquerade as biblio
    # when used in code-ish array access segments, like `foo[[=this=]].
    # So, look for one of the autolink characters, since they can't
    # be valid biblios anyway, and just fail silently.
    if s[start + 2] in BRACKET_AUTOLINK_CHARS:
        return Err(start)

    # Otherwise we're locked in, this opener is a very strong signal.
    innerStart = start + 2

    innerResult = parseBiblioInner(s, innerStart)
    if isErr(innerResult):
        innerResult = parseSectionInner(s, innerStart)
        if isErr(innerResult):
            m.die(
                "Saw a [[ opening a biblio or section autolink, but couldn't parse the following contents. If you didn't intend this to be a biblio autolink, escape the initial [ as &bs[;",
                lineNum=s.loc(start),
            )
            return Ok(
                RawText.fromStream(s, start, innerStart, "[["),
                innerStart,
            )
    parseOutcome, innerEnd, _ = innerResult
    assert parseOutcome is not None
    startTag, visibleText = parseOutcome

    if s[innerEnd] == "|":
        rest, nodeEnd, _ = parseLinkText(s, innerEnd + 1, "[[", "]]", startTag, generateResults=generateResults)
        if rest is not None:
            return Ok([startTag, *rest], nodeEnd)
        else:
            nodeEnd = innerEnd + 1
    else:
        nodeEnd = innerEnd + 2
    middleText = RawText.fromStream(s, innerStart, innerEnd, visibleText)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Ok([startTag, middleText, endTag], nodeEnd)


def parseBiblioInner(s: Stream, innerStart: int) -> ResultT[tuple[StartTag, str]]:
    """Parse the body of a `[[!SPEC modifiers]]` bibliography autolink, returning `(startTag, defaultVisibleText)`."""
    match, innerEnd, _ = s.matchRe(innerStart, AUTOLINK_BIBLIO_RE)
    if not match:
        return Err(innerStart)

    nodeStart = innerStart - 2
    normative = match[1] == "!"
    lt = match[2]
    modifierSequence = match[3].strip()
    attrs: t.SafeAttrDict = {
        "bs-lt": escapeAttr(lt),
        "data-link-type": t.SafeAttrStr("biblio"),
        "bs-biblio-type": t.SafeAttrStr("normative" if normative else "informative"),
        "bs-autolink-syntax": escapeAttr(s.slice(nodeStart, innerEnd) + "]]"),
    }

    failureStart = StartTag.fromStream(s, nodeStart, innerStart, "span")
    failureResult = Ok(
        (failureStart, f"&#91;{lt}]"),
        innerEnd,
    )

    if modifierSequence != "":
        for modifier in re.split(r"\s+", modifierSequence):
            if modifier in ("current", "snapshot"):
                if "bs-biblio-status" not in attrs:
                    attrs["bs-biblio-status"] = t.SafeAttrStr(modifier)
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple current/snapshot keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            elif modifier in ("inline", "index", "direct"):
                if "bs-biblio-display" not in attrs:
                    attrs["bs-biblio-display"] = t.SafeAttrStr(modifier)
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple inline/index/direct keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            elif modifier == "obsolete":
                if "bs-biblio-obsolete" not in attrs:
                    attrs["bs-biblio-obsolete"] = ""
                else:
                    m.die(
                        f"Biblio shorthand [{lt} ...] contains multiple 'obsolete' keywords. Please use only one.",
                        lineNum=s.loc(nodeStart),
                    )
                    return failureResult
            else:
                # Unknown modifier, that's just a failure.
                return Err(innerStart)

    startTag = StartTag.fromStream(s, nodeStart, innerStart, "a", attrs).finalize()
    return Ok(
        (startTag, f"&#91;{lt}]"),
        innerEnd,
    )


def parseSectionInner(s: Stream, innerStart: int) -> ResultT[tuple[StartTag, str]]:
    """Parse the body of a local (`[[#sec]]`) or foreign (`[[SPEC/page#sec]]`) section autolink."""
    nodeStart = innerStart - 2
    match, innerEnd, _ = s.matchRe(innerStart, AUTOLINK_SECTION_RE)
    if not match:
        return Err(innerStart)

    spec, section, justPage = match.groups()
    if spec is None:
        # local section link
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "a",
            {
                "bs-section": "",
                "href": escapeAttr(section),
                "bs-autolink-syntax": escapeAttr(f"[[{match[0]}]]"),
            },
        )
    elif justPage is not None:
        # foreign link, to an actual page from a multipage spec
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "span",
            {
                "bs-spec-section": escapeAttr(justPage + "#"),
                "bs-link-spec": escapeAttr(spec),
                "bs-autolink-syntax": escapeAttr(f"[[{match[0]}]]"),
            },
        )
    else:
        # foreign link
        startTag = StartTag.fromStream(
            s,
            nodeStart,
            innerStart,
            "span",
            {
                "bs-spec-section": escapeAttr(section),
                "bs-link-spec": escapeAttr(spec),
                "bs-autolink-syntax": escapeAttr(f"[[{match[0]}]]"),
            },
        )
    return Ok((startTag, ""), innerEnd)


def parseRepositoryLink(
    s: Stream,
    start: int,
    org: str | None = None,
    originalStart: int | None = None,
) -> ResultT[list[ParserNode]]:
    """Parse a repository issue link (`<#123>` or `<org/repo#123>`), optionally reusing `org` parsed by `parseStartTag()`."""
    repo: str | None
    if org is None:
        if s[start] != "<":
            return Err(start)
        i = start + 1
        repoStart, i, _ = parseRepositoryStart(s, i)
        if repoStart:
            org, repo = repoStart
        # failure is fine, just means it might be <#123>
    else:
        # Already parsed the `<org/` part...
        assert originalStart is not None
        repo, i, _ = parseTagName(s, start)
        # Since I'm already committed to org/repo, failure is failure.
        if not repo:
            return Err(start)
        start = originalStart
    if s[i] != "#":
        return Err(start)
    i += 1
    num, i, _ = parseDigits(s, i)
    if num is None:
        return Err(start)
    if s[i] != ">":
        return Err(start)
    i += 1

    if org:
        text = f"{org}/{repo} issue #{num}"
        issueID = f"{org}/{repo}#{num}"
    else:
        text = f"issue #{num}"
        issueID = f"#{num}"
    startTag = StartTag.fromStream(s, start, start + 1, "a", {"bs-remote-issue-id": escapeAttr(issueID)})
    return Ok(
        [startTag, SafeText.fromStream(s, start + 1, i - 1, text), EndTag.fromStream(s, i - 1, i, startTag)],
        i,
    )


def parseRepositoryStart(s: Stream, start: int) -> ResultT[tuple[str, str]]:
    """Parse the `org/repo` prefix of a repository issue link."""
    org, i, _ = parseTagName(s, start)
    if not org:
        return Err(start)
    if s[i] != "/":
        return Err(start)
    i += 1
    repo, i, _ = parseTagName(s, i)
    if not repo:
        return Err(start)
    return Ok((org, repo), i)


def parseDigits(s: Stream, start: int) -> ResultT[str]:
    """Parse 1 to 10 consecutive ASCII decimal digits starting at `start`."""
    i = start
    while not s.eof(i):
        if not isDigit(s[i]):
            break
        if i > (start + 10):
            return Err(start)
        i += 1
    if i == start:
        return Err(start)
    return Ok(s.slice(start, i), i)
