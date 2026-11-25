"""CSS autolink shorthand and production grammar parsers (`<<production>>`, `''maybe''`, `'propdesc'`, and `.prod` grammar symbols)."""

from __future__ import annotations

import re

from ... import config, t
from ... import messages as m
from .autolinks import parseLinkText
from .macros import replaceMacrosInText
from .nodes import EndTag, ParserNode, RawText, SafeText, StartTag, escapeAttr
from .result import Err, Ok, isOk
from .stream import Stream

if t.TYPE_CHECKING:
    from .result import ResultT
    from .stream import ExperimentalNodesFn, ResultGeneratorFn

PROD_PROPDESC_RE = re.compile(r"^'(?:(\S*)/)?([\w*-]+)(?:!!([\w-]+))?'$")
PROD_FUNC_RE = re.compile(r"^(?:(\S*)/)?([\w*-]+\(\))$")
PROD_ATRULE_RE = re.compile(r"^(?:(\S*)/)?(@[\w*-]+)$")
PROD_TYPE_RE = re.compile(
    r"""
    ^(?:(\S*)/)?
    (\S+)
    (?:\s+
        \[\s*
        (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;|&\#8734;))\s*
        ,\s*
        (-?(?:\d+[\w-]*|∞|[Ii]nfinity|&infin;|&\#8734;))\s*
        \]\s*
    )?$
    """,
    re.X,
)
TYPEWITHARGS_RE = re.compile(
    r"""
    ^(?:(\S*)/)?
    (\S+)
    \s*\[([^\]]*)\]\s*$
    """,
    re.X,
)

MAYBE_DECL_RE = re.compile(r"(@[\w-]+/)?([\w-]+)$")
MAYBE_VAL_RE = re.compile(r"^(?:(\S*)/)?(\S[^!]*)(?:!!([\w-]+))?$")

AUTOLINK_PROPDESC_RE = re.compile(
    r"""
    (?:(@[\w\[\]-]+|)/)?
    ([\w*\[\]-]+)
    (?:!!([\w\[\]-]+))?
    """,
    flags=re.X,
)

PROD_GRAMMAR_START_CHARS = "#{?!*+|&,"
PROD_GRAMMAR_START_SET = frozenset(PROD_GRAMMAR_START_CHARS)

_PROD_HASH_MULT_RE = re.compile(r"#\{\s*\d+(?:\s*,(?:\s*\d+)?)?\s*\}")
_PROD_MULT_RE = re.compile(r"\{\s*\d+\s*\}")
_PROD_MULT_RANGE_RE = re.compile(r"\{\s*\d+\s*,(?:\s*\d+)?\s*\}")
_PROD_DOUBLE_AMP_RE = re.compile(r"(?:&&|&amp;&amp;|&#38;&#38;|&#[xX]0*26;&#[xX]0*26;)(?!')")
_PROD_GRAMMAR_TEXT_RE = re.compile(
    r"#\{\s*\d+(?:\s*,(?:\s*\d+)?)?\s*\}|\{\s*\d+(?:\s*,(?:\s*\d+)?)?\s*\}|(?:&&|\|\||[?!#*+|,])(?!')",
)


def parseCSSProduction(s: Stream, start: int) -> ResultT[ParserNode | list[ParserNode]]:
    """Parse a CSS grammar production autolink (`<<type>>`, `<<'prop'>>`, `<<func()>>`, `<<@rule>>`, or ranged/parameterized types)."""
    if s.slice(start, start + 2) != "<<":
        return Err(start)
    textStart = start + 2

    text, textEnd, _ = s.skipTo(textStart, ">>")
    if text is None:
        m.die("Saw the start of a CSS production (like <<foo>>), but couldn't find the end.", lineNum=s.loc(start))
        failNode = SafeText.fromStream(s, start, start + 2)
        return Ok(failNode, start + 2)
    elif "\n" in text:
        m.die(
            "Saw the start of a CSS production (like <<foo>>), but couldn't find the end on the same line.",
            lineNum=s.loc(start),
        )
        failNode = SafeText.fromStream(s, start, start + 2)
        return Ok(failNode, start + 2)
    elif "<" in text or ">" in text:
        # Allow <<boolean [<<foo>>]>>
        if "[" in text:
            _, endOfArg, _ = s.skipTo(textEnd, "]")
            _, newTextEnd, _ = s.skipTo(endOfArg, ">>")
            if endOfArg == textEnd or newTextEnd == endOfArg:  # noqa: PLR1714
                m.die(
                    "It seems like you wrote a CSS production with an argument (like <<foo [<<bar>>]>>), but either included more [] in the argument, or otherwise messed up the syntax.",
                    lineNum=s.loc(start),
                )
                failNode = SafeText.fromStream(s, start, start + 2)
                return Ok(failNode, start + 2)
            textEnd = newTextEnd
            text = s.slice(textStart, textEnd)
        else:
            m.die(
                "It seems like you wrote a CSS production (like <<foo>>), but there's more markup inside of it, or you didn't close it properly.",
                lineNum=s.loc(start),
            )
            failNode = SafeText.fromStream(s, start, start + 2)
            return Ok(failNode, start + 2)
    nodeEnd = textEnd + 2

    attrs: t.SafeAttrDict = {
        "bs-autolink-syntax": escapeAttr(s.slice(start, nodeEnd)),
        "class": t.SafeAttrStr("production"),
        "bs-opaque": "",
    }
    # Single-iteration loop used as a breakable dispatch block; the `else:` runs if no grammar matches.
    for _ in [1]:
        match = PROD_PROPDESC_RE.match(text)
        if match:
            linkFor, lt, linkType = match.groups()
            if linkFor == "":
                linkFor = "/"
            if linkType is None:
                if linkFor is None:
                    linkType = "property"
                else:
                    linkType = "propdesc"
            elif linkType in ("property", "descriptor"):
                pass
            else:
                m.die(
                    f"Shorthand <<{match[0]}>> gives type as '{match[3]}', but only 'property' and 'descriptor' are allowed.",
                    lineNum=s.loc(start),
                )
                failNode = SafeText.fromStream(s, start, nodeEnd)
                return Ok(failNode, nodeEnd)
            attrs["data-link-type"] = escapeAttr(linkType)
            attrs["bs-lt"] = escapeAttr(lt)
            if linkFor is not None:
                attrs["bs-link-for"] = escapeAttr(linkFor)
            text = f"<'{lt}'>"
            break

        match = PROD_FUNC_RE.match(text)
        if match:
            attrs["data-link-type"] = t.SafeAttrStr("function")
            attrs["bs-lt"] = escapeAttr(match[2])
            if match[1] is not None:
                attrs["bs-link-for"] = escapeAttr(match[1])
            text = f"<{match[2]}>"
            break

        match = PROD_ATRULE_RE.match(text)
        if match:
            attrs["data-link-type"] = t.SafeAttrStr("at-rule")
            attrs["bs-lt"] = escapeAttr(match[2])
            if match[1] is not None:
                attrs["bs-link-for"] = escapeAttr(match[1])
            text = f"<{match[2]}>"
            break

        match = PROD_TYPE_RE.match(text)
        if match:
            for_, term, rangeStart, rangeEnd = match.groups()
            attrs["data-link-type"] = t.SafeAttrStr("type")
            attrs["bs-lt"] = escapeAttr(f"<{term}>")
            if for_ is not None:
                attrs["bs-link-for"] = escapeAttr(for_)
            if rangeStart is not None:
                formattedStart, numStart = parseRangeComponent(s, textStart + match.start(3), rangeStart)
                formattedEnd, numEnd = parseRangeComponent(s, textStart + match.start(4), rangeEnd)
                if formattedStart is None or formattedEnd is None:
                    m.die(f"Shorthand <<{text}>> has an invalid range.", lineNum=s.loc(start))
                    failNode = SafeText.fromStream(s, start, nodeEnd)
                    return Ok(failNode, nodeEnd)
                elif numStart >= numEnd:
                    m.die(
                        f"Shorthand <<{text}>> has a range whose start is equal or greater than its end.",
                        lineNum=s.loc(start),
                    )
                    # Getting this wrong is an error, but shouldn't stop
                    # the link from working, so continue on if you can.
                text = f"<{term} [{formattedStart},{formattedEnd}]>"
            else:
                text = f"<{term}>"
            break

        match = TYPEWITHARGS_RE.match(text)
        if match:
            for_, term, arg = match.groups()
            attrs["bs-lt"] = escapeAttr(f"<{term}>")
            attrs["data-link-type"] = t.SafeAttrStr("type")
            if for_ is not None:
                attrs["bs-link-for"] = escapeAttr(for_)
            if "<<" in arg:
                arg = arg.replace("<<", "<").replace(">>", ">")
            text = f"<{term}[{arg}]>"
            break

    else:
        m.die(f"Shorthand <<{text}>> does not match any recognized shorthand grammar.", lineNum=s.loc(start))
        failNode = SafeText.fromStream(s, start, nodeEnd)
        return Ok(failNode, nodeEnd)

    startTag = StartTag.fromStream(s, start, textStart, "a", attrs).finalize()
    contents = SafeText.fromStream(s, textStart, textEnd, text)
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Ok([startTag, contents, endTag], nodeEnd)


def parseRangeComponent(s: Stream, i: int, val: str) -> tuple[str | None, float | int]:
    """Parse one bound of a CSS range notation (`[min, max]`), returning `(formatted_str, numeric_val)`."""
    sign = ""
    signVal = 1
    num: float | int
    val = val.strip()
    if val[0] in ["-", "−"]:
        sign = "-"
        signVal = -1
        val = val[1:]

    if val.lower() == "infinity":
        val = "∞"
    if val.lower() in ("&infin;", "&#8734;"):
        m.warn(
            f"Infinite ranges should be written as 'infinity' or '∞', not an HTML entity. (Got {val})",
            lineNum=s.loc(i),
        )
        val = "∞"
    if val == "∞":
        return sign + val, signVal * float("inf")

    match = re.match(r"(\d+)([\w-]*)", val)
    if match is None:
        return None, 0
    digits, unit = match.groups()
    num = int(digits) * signVal
    val = str(num)

    return val + unit, num


def parseCSSMaybe(
    s: Stream,
    start: int,
    generateResults: ResultGeneratorFn,
    generateExperimentalNodes: ExperimentalNodesFn,
) -> ResultT[list[ParserNode]]:
    """Parse a `''...''` CSS maybe shorthand, trying a `prop: value` declaration first and then a value."""
    if s.slice(start, start + 2) != "''":
        return Err(start)
    textStart = start + 2

    res = parseMaybeDecl(s, textStart, generateResults)
    if isOk(res):
        return res

    res = parseMaybeValue(s, textStart, generateExperimentalNodes)
    if isOk(res):
        return res

    return Err(start)


def parseMaybeDecl(
    s: Stream,
    textStart: int,
    generateResults: ResultGeneratorFn,
) -> ResultT[list[ParserNode]]:
    """Parse a `''prop: value''` CSS declaration shorthand starting right after the opening `''`."""
    rawText, colonStart, _ = s.skipToSameLine(textStart, ":")
    if not rawText:
        return Err(textStart)
    if "'" in rawText:
        return Err(textStart)
    if not s[colonStart + 1].isspace():
        return Err(textStart)
    colonEnd = colonStart + 1

    if s.config.macrosInAutolinks:
        text = replaceMacrosInText(
            text=rawText,
            macros=s.config.macros,
            s=s,
            start=textStart,
            context=f"''{rawText}: ...''",
        )
    else:
        text = rawText
    match = MAYBE_DECL_RE.match(text)
    if not match:
        return Err(textStart)

    for_, propdescname = match.groups()

    autolinkSyntax = f"''{rawText}: ...''"
    if rawText != text:
        autolinkSyntax += f" (expands to ''{text}: ...'')"

    startTag = StartTag.fromStream(
        s,
        textStart - 2,
        textStart,
        "a",
        {
            "bs-autolink-syntax": escapeAttr(autolinkSyntax),
            "class": t.SafeAttrStr("css"),
            "data-link-type": t.SafeAttrStr("propdesc"),
            "bs-lt": escapeAttr(propdescname),
        },
    )
    if for_:
        startTag.attrs["bs-link-for"] = escapeAttr(for_)
        startTag.attrs["data-link-type"] = t.SafeAttrStr("descriptor")
    startTag.finalize()

    declStart = RawText.fromStream(s, textStart, colonEnd, propdescname + ":")

    rest, nodeEnd, _ = parseLinkText(s, colonEnd, "''", "''", startTag, generateResults=generateResults)
    if rest is None:
        return Err(textStart)
    return Ok([startTag, declStart, *rest], nodeEnd)


def parseMaybeValue(
    s: Stream,
    textStart: int,
    generateExperimentalNodes: ExperimentalNodesFn,
) -> ResultT[list[ParserNode]]:
    """Parse a `''value''` CSS maybe autolink (or inline CSS snippet), distinguishing explicit autolinks from rich content."""
    start = textStart - 2

    # Ugh, "maybe" autolinks might be text *or* html; we can't tell until we examine them.
    # So, do a real (but experimental) parse to the next '', holding onto the results.
    # Do some analysis on the *text* in those bounds,
    # and then, only if it looks like we need to, process the parse results.

    nodes: list[ParserNode] = []
    for i in generateExperimentalNodes(s, textStart, nodes):
        if s.chars.count("\n", start, i) > 3:
            m.die(
                "CSS-maybe autolink (''foo'') was opened, but no closing '' was found within a few lines. Either close your autolink, switch to the <css></css> element if you need the contents to stretch across that many lines, or escape the initial '' as &bs';&bs'; if it wasn't intended at all.",
                lineNum=s.loc(textStart),
            )
            return Err(textStart)
        if s.slice(i, i + 2) == "''":
            textEnd = i
            nodeEnd = i + 2
            break
    else:
        m.die(
            "CSS-maybe autolink (''foo'') was opened, but no closing '' was found within a few lines. Either close your autolink, switch to the <css></css> element if you need the contents to stretch across that many lines, or escape the initial '' as &bs';&bs'; if it wasn't intended at all.",
            lineNum=s.loc(textStart),
        )
        return Err(textStart)

    rawText = s.slice(textStart, textEnd)
    if s.config.macrosInAutolinks:
        text = replaceMacrosInText(
            text=rawText,
            macros=s.config.macros,
            s=s,
            start=textStart,
            context=f"''{rawText}''",
        )
    else:
        text = rawText
    # Do some text-based analysis of the contents first.

    match = MAYBE_VAL_RE.match(text)
    if match:
        for_, valueName, linkType = match.groups()
        probablyAutolink = (for_ is not None and not for_.endswith("<")) or match[3] is not None
    else:
        for_ = None
        valueName = text
        linkType = None
        probablyAutolink = False

    if linkType is None:
        linkType = "maybe"
    elif linkType in config.maybeTypes:
        pass
    else:
        # Looks like a maybe shorthand, just with an illegal type,
        # so format it nicely and leave it alone.
        m.die(
            f"Shorthand ''{rawText}'' gives type as '{linkType}', but only “maybe” sub-types are allowed: {config.englishFromList(config.maybeTypes)}.",
            lineNum=s.loc(start),
        )
        return Ok(
            [
                StartTag.fromStream(s, start, textStart, "css"),
                SafeText.fromStream(s, textStart, textEnd, valueName),
                EndTag.fromStream(s, textEnd, nodeEnd, "css"),
            ],
            nodeEnd,
        )

    # If the text looked sufficiently like an autolink,
    # (has a for value (that doesn't look like it's from an end tag) and/or a manual type),
    # act as if the text was autolinking literal the whole time,
    # and format it nicely (just give it the valueName as contents).
    # Otherwise, use the parsed nodes as contents,
    # but set it up for autolinking based on the text,
    # and tell it what to replace itself with if it *does* succeed at linking.
    startTag = StartTag.fromStream(
        s,
        start,
        textStart,
        "bs-link",
        {
            "class": t.SafeAttrStr("css"),
            "bs-autolink-syntax": escapeAttr(s.slice(start, nodeEnd)),
            "data-link-type": escapeAttr(linkType),
            "bs-lt": escapeAttr(valueName),
        },
    )
    if probablyAutolink:
        if "&lt" in text or "&gt" in text:
            m.die(
                f"The autolink {s.slice(start, nodeEnd)} is using an escaped < or > in its value; you probably just want to use a literal < and >.",
                lineNum=s.loc(start),
            )
            m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
        elif "<<" in text:
            m.die(
                f"The autolink {s.slice(start, nodeEnd)} is using << in its value; you probably just want to use a single < and >.",
                lineNum=s.loc(start),
            )
            m.say("(See https://speced.github.io/bikeshed/#autolink-limits )")
        if for_:
            startTag.attrs["bs-link-for"] = escapeAttr(for_)
    startTag.finalize()

    s.observeShorthandOpen(startTag, ("''", "''"))
    if probablyAutolink:
        # Nothing to observe, this is just text.
        nodes = [SafeText.fromStream(s, textStart, textEnd, safeFromDoubleAngles(t.cast(str, valueName)))]
    else:
        startTag.attrs["bs-replace-text-on-link-success"] = escapeAttr(safeFromDoubleAngles(text))
        s.observeNodes(nodes)
    virtualEndTags = s.observeShorthandClose(s, textEnd, startTag, ("''", "''"))
    endTag = EndTag.fromStream(s, textEnd, nodeEnd, startTag)
    return Ok([startTag, *nodes, *virtualEndTags, endTag], nodeEnd)


def rawFromDoubleAngles(text: str) -> str:
    """Convert `<<` and `>>` in CSS maybe text into HTML-escaped `&lt;` and `>`."""
    text = re.sub(r"<<", "&lt;", text)
    text = re.sub(r">>", ">", text)
    return text


def safeFromDoubleAngles(text: str) -> str:
    """Convert `<<` and `>>` in CSS maybe text into literal `<` and `>` (for `SafeText` or attribute escaping)."""
    text = re.sub(r"<<", "<", text)
    text = re.sub(r">>", ">", text)
    return text


def parseCSSPropdesc(s: Stream, start: int) -> ResultT[SafeText | list[ParserNode]]:
    """Parse a single-quoted CSS property/descriptor autolink (`'prop'`, `'@rule/desc'`, `'--custom'`)."""
    if s[start] != "'":
        return Err(start)
    if s.slice(start, start + 3) == "'-'":
        return Err(start)

    innerStart = start + 1

    match, innerEnd, _ = s.matchRe(start + 1, AUTOLINK_PROPDESC_RE)
    if match is None:
        return Err(start)

    if s.config.macrosInAutolinks and "[" in match[0]:
        innerText = replaceMacrosInText(
            text=match[0],
            macros=s.config.macros,
            s=s,
            start=innerStart,
            context=f"'{match[0]}'",
        )
        match = AUTOLINK_PROPDESC_RE.match(innerText)
        if match:
            innerText = match[0]
        else:
            m.die(
                f"After macro replacement, couldn't parse a CSS property/descriptor autolink.\n  Original: '{s.slice(innerStart, innerEnd)}'\n  After macros: '{innerText}'",
                lineNum=s.loc(start),
            )
            return Err(start)
    else:
        innerText = match[0]
    linkFor, lt, linkType = match.groups()

    if s[innerEnd] != "'":
        # If you provided a for or type, you almost certainly *meant*
        # this to be a propdesc, and just left off the closing '.
        if linkFor is not None or linkType is not None:
            m.die(
                f"It appears that you meant to write a property/descriptor autolink ({s.slice(start, innerEnd)}), but didn't finish it. Close it with a final ', or escape the initial ' character.",
                lineNum=s.loc(start),
            )
            return Ok(
                SafeText.fromStream(s, start, innerEnd),
                innerEnd,
            )
        else:
            # Otherwise this is likely just an innocent apostrophe
            # used for other purposes, and should just fail to parse.
            return Err(start)

    if linkType is None:
        if linkFor is None:
            linkType = "property"
        else:
            linkType = "propdesc"
    elif linkType in ("property", "descriptor"):
        pass
    else:
        m.die(
            f"Propdesc link '{innerText}' gave its type as '{linkType}', but only 'property' or 'descriptor' is allowed.",
            lineNum=s.loc(start),
        )
        linkType = "propdesc"

    if "*" in lt or lt.startswith("--"):
        startTag = StartTag.fromStream(
            s,
            start,
            start + 1,
            "css",
            {
                "bs-autolink-syntax": escapeAttr("'" + innerText + "'"),
            },
        )
    else:
        startTag = StartTag.fromStream(
            s,
            start,
            start + 1,
            "a",
            {
                "class": t.SafeAttrStr("property"),
                "data-link-type": escapeAttr(linkType),
                "bs-lt": escapeAttr(lt),
                "bs-autolink-syntax": escapeAttr("'" + innerText + "'"),
            },
        )
        if linkFor is not None:
            startTag.attrs["bs-link-for"] = escapeAttr(linkFor)
    startTag = startTag.finalize()

    nodeEnd = innerEnd + 1
    middleText = SafeText.fromStream(s, innerStart, innerEnd, lt)
    endTag = EndTag.fromStream(s, innerEnd, nodeEnd, startTag)
    return Ok([startTag, middleText, endTag], nodeEnd)


def _makeGrammarLink(s: Stream, start: int, end: int, lt: str, text: str) -> list[ParserNode]:
    """Build `[StartTag('a'), SafeText, EndTag('a')]` for a CSS production grammar symbol link."""
    startTag = StartTag.fromStream(
        s,
        start,
        start,
        "a",
        {
            "data-link-type": t.SafeAttrStr("grammar"),
            "bs-lt": escapeAttr(lt),
            "bs-link-for": t.SafeAttrStr(""),
        },
    )
    content = SafeText.fromStream(s, start, end, text)
    endTag = EndTag.fromStream(s, end, end, startTag)
    return [startTag, content, endTag]


def parseCSSProductionGrammar(s: Stream, start: int) -> ResultT[list[ParserNode]]:
    """Parse a CSS production grammar combinator or multiplier at `start` (`?`, `!`, `#`, `*`, `+`, `|`, `||`, `&&`, `,`, `{A}`, `{A,B}`, `#{...}`)."""
    ch = s[start]
    if ch == "#":
        match, end, _ = s.matchRe(start, _PROD_HASH_MULT_RE)
        if match is not None:
            return Ok(_makeGrammarLink(s, start, end, "#", match.group(0)), end)
        if s[start + 1] != "'":
            return Ok(_makeGrammarLink(s, start, start + 1, "#", "#"), start + 1)
        return Err(start)
    if ch == "{":
        match, end, _ = s.matchRe(start, _PROD_MULT_RE)
        if match is not None:
            return Ok(_makeGrammarLink(s, start, end, "{A}", match.group(0)), end)
        match, end, _ = s.matchRe(start, _PROD_MULT_RANGE_RE)
        if match is not None:
            return Ok(_makeGrammarLink(s, start, end, "{A,B}", match.group(0)), end)
        return Err(start)
    if ch == "|":
        if s.slice(start, start + 2) == "||" and s[start + 2] != "'":
            return Ok(_makeGrammarLink(s, start, start + 2, "||", "||"), start + 2)
        if s[start + 1] != "'":
            return Ok(_makeGrammarLink(s, start, start + 1, "|", "|"), start + 1)
        return Err(start)
    if ch == "&":
        match, end, _ = s.matchRe(start, _PROD_DOUBLE_AMP_RE)
        if match is not None:
            return Ok(_makeGrammarLink(s, start, end, "&&", "&&"), end)
        return Err(start)
    if ch in ("?", "!", "*", "+", ","):
        if s[start + 1] != "'":
            return Ok(_makeGrammarLink(s, start, start + 1, ch, ch), start + 1)
        return Err(start)
    return Err(start)


def parseCSSProductionGrammarInText(
    s: Stream,
    baseOffset: int,
    text: str,
    *,
    exactOffsets: bool = True,
) -> list[ParserNode]:
    """Split raw `<xmp class=prod>` or fenced `prod` body text into `SafeText` and CSS grammar link nodes."""
    nodes: list[ParserNode] = []
    pos = 0
    for match in _PROD_GRAMMAR_TEXT_RE.finditer(text):
        mStart, mEnd = match.span()
        if mStart > pos:
            segStart = baseOffset + pos if exactOffsets else baseOffset
            segEnd = baseOffset + mStart if exactOffsets else baseOffset
            nodes.append(SafeText.fromStream(s, segStart, segEnd, text[pos:mStart]))
        tok = match.group(0)
        if tok.startswith("#{"):
            lt = "#"
        elif tok.startswith("{"):
            lt = "{A,B}" if "," in tok else "{A}"
        else:
            lt = tok
        tokStart = baseOffset + mStart if exactOffsets else baseOffset
        tokEnd = baseOffset + mEnd if exactOffsets else baseOffset
        nodes.extend(_makeGrammarLink(s, tokStart, tokEnd, lt, tok))
        pos = mEnd
    if pos < len(text):
        segStart = baseOffset + pos if exactOffsets else baseOffset
        segEnd = baseOffset + len(text) if exactOffsets else baseOffset
        nodes.append(SafeText.fromStream(s, segStart, segEnd, text[pos:]))
    return nodes
