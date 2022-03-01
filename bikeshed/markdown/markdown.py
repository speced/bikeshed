import functools
import re

from .. import Line, messages as m, h


def parse(
    lines,
    numSpacesForIndentation,
    features=None,
    opaqueElements=None,
    blockElements=None,
):
    fromStrings = False
    if any(isinstance(x, str) for x in lines):
        fromStrings = True
        lines = [Line.Line(-1, x) for x in lines]
    lines = Line.rectify(lines)
    tokens = tokenizeLines(
        lines,
        numSpacesForIndentation,
        features,
        opaqueElements=opaqueElements,
        blockElements=blockElements,
    )
    html = parseTokens(tokens, numSpacesForIndentation)
    if fromStrings:
        return [x.text for x in html]
    else:
        return html


def tokenizeLines(
    lines,
    numSpacesForIndentation,
    features=None,
    opaqueElements=None,
    blockElements=None,
):
    # Turns lines of text into block tokens,
    # which'll be turned into MD blocks later.
    # Every token *must* have 'type', 'raw', and 'prefix' keys.

    if features is None:
        features = {"headings"}

    # Inline elements that are allowed to start a "normal" line of text.
    # Any other element will instead be an HTML line and will close paragraphs, etc.
    inlineElements = {
        "a",
        "em",
        "strong",
        "small",
        "s",
        "cite",
        "q",
        "dfn",
        "abbr",
        "data",
        "time",
        "code",
        "var",
        "samp",
        "kbd",
        "sub",
        "sup",
        "i",
        "b",
        "u",
        "mark",
        "ruby",
        "bdi",
        "bdo",
        "span",
        "br",
        "wbr",
        "img",
        "meter",
        "progress",
        "css",
        "l",
    }

    if blockElements is None:
        blockElements = []
    # Custom elements are assumed to be inline in general,
    # (you have to pass the block-level custom elements as metadata),
    # but Bikeshed has some custom elements that it uses as block-level
    blockElements.append("if-wrapper")

    def inlineElementStart(line):
        # Whether or not the line starts with an inline element
        match = re.match(r"\s*</?([\w-]+)", line)
        if not match:
            return True
        tagname = match.group(1)
        if tagname in inlineElements:
            return True
        if "-" in tagname and tagname not in blockElements:
            # Assume custom elements are inline by default
            return True
        return False

    tokens = []
    rawStack = []
    if opaqueElements is None:
        opaqueElements = []
    opaqueElements += ["pre", "xmp", "script", "style"]
    rawElements = "|".join(re.escape(x) for x in opaqueElements)

    for i, line in enumerate(lines):

        # Three kinds of "raw" elements, which prevent markdown processing inside of them.
        # 1. <pre> and manual opaque elements, which can contain markup and so can nest.
        # 2. <xmp>, <script>, and <style>, which contain raw text, can't nest.
        # 3. Markdown code blocks, which contain raw text, can't nest.
        #
        # The rawStack holds tokens like
        # {"type":"fenced", "tag":"````", "nest":False}

        # TODO: when i pop the last rawstack, collect all the raw tokens in sequence and remove their indentation. gonna need to track the index explicitly, since a raw might end on one line and start on the next again, so i can't just walk backwards.
        if rawStack:
            # Inside at least one raw element that turns off markdown.
            # First see if this line will *end* the raw element.
            endTag = rawStack[-1]
            if lineEndsRawBlock(line, endTag):
                rawStack.pop()
                if endTag["type"] == "fenced":
                    stripCommonWsPrefix(tokens[endTag["start"] + 1 :])
                    line.text = "</xmp>"
                tokens.append({"type": "raw", "prefixlen": float("inf"), "line": line})
                continue
            elif not endTag["nest"]:
                # Just an internal line, but for the no-nesting elements,
                # so guaranteed no more work needs to be done.
                tokens.append({"type": "raw", "prefixlen": float("inf"), "line": line})
                continue

        # We're either in a nesting raw element or not in a raw element at all,
        # so check if the line starts a new element.
        match = re.match(r"(\s*)(`{3,}|~{3,})([^`]*)$", line.text)
        if match:
            ws, tag, infoString = match.groups()
            rawStack.append({"type": "fenced", "tag": tag, "nest": False, "start": i})
            infoString = infoString.strip()
            if infoString:
                # For now, I only care about lang
                lang = infoString.split(" ")[0]
                classAttr = f" class='language-{h.escapeAttr(lang)}'"
            else:
                classAttr = ""
            line.text = f"{ws}<xmp{classAttr}>"
            tokens.append(
                {
                    "type": "raw",
                    "prefixlen": prefixCount(ws, numSpacesForIndentation),
                    "line": line,
                }
            )
            continue
        match = re.match(rf"\s*<({rawElements})[ >]", line.text)
        if match:
            tokens.append(
                {
                    "type": "raw",
                    "prefixlen": prefixCount(line.text, numSpacesForIndentation),
                    "line": line,
                }
            )
            if re.search(r"</({})>".format(match.group(1)), line.text):
                # Element started and ended on same line, cool, don't need to do anything.
                pass
            else:
                nest = match.group(1) not in ["xmp", "script", "style"]
                rawStack.append(
                    {
                        "type": "element",
                        "tag": "</{}>".format(match.group(1)),
                        "nest": nest,
                    }
                )
            continue
        if rawStack:
            tokens.append({"type": "raw", "prefixlen": float("inf"), "line": line})
            continue

        lineText = line.text.strip()

        if lineText == "":
            token = {
                "type": "blank",
            }
        # FIXME: Detect the heading ID from heading lines
        elif "headings" in features and re.match(r"={3,}\s*$", lineText):
            # h1 underline
            match = re.match(r"={3,}\s$", lineText)
            token = {"type": "equals-line"}
        elif "headings" in features and re.match(r"-{3,}\s*$", lineText):
            # h2 underline
            match = re.match(r"-{3,}\s*$", lineText)
            token = {"type": "dash-line"}
        elif "headings" in features and re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", lineText):
            # single-line heading
            match = re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", lineText)
            level = len(match.group(1)) + 1
            token = {"type": "heading", "text": match.group(2).strip(), "level": level}
            match = re.search(r"\{#([^ }]+)\}\s*$", lineText)
            if match:
                token["id"] = match.group(1)
        elif re.match(r"((\*\s*){3,})$|((-\s*){3,})$|((_\s*){3,})$", lineText):
            token = {"type": "rule"}
        elif re.match(r"-?\d+\.\s", lineText):
            match = re.match(r"(-?\d+)\.\s+(.*)", lineText)
            token = {
                "type": "numbered",
                "text": match.group(2),
                "num": int(match.group(1)),
            }
        elif re.match(r"-?\d+\.$", lineText):
            token = {"type": "numbered", "text": "", "num": int(lineText[:-1])}
        elif re.match(r"[*+-]\s", lineText):
            match = re.match(r"[*+-]\s+(.*)", lineText)
            token = {"type": "bulleted", "text": match.group(1)}
        elif re.match(r"[*+-]$", lineText):
            token = {"type": "bulleted", "text": ""}
        elif re.match(r":{1,2}\s+", lineText):
            match = re.match(r"(:{1,2})\s+(.*)", lineText)
            type = "dt" if len(match.group(1)) == 1 else "dd"
            token = {"type": type, "text": match.group(2)}
        elif re.match(r":{1,2}$", lineText):
            match = re.match(r"(:{1,2})", lineText)
            type = "dt" if len(match.group(1)) == 1 else "dd"
            token = {"type": type, "text": ""}
        elif re.match(r">", lineText):
            match = re.match(r">\s?(.*)", lineText)
            token = {"type": "blockquote", "text": match.group(1)}
        elif re.match(r"<", lineText):
            if re.match(r"<<|<\{", lineText) or inlineElementStart(lineText):
                token = {"type": "text", "text": lineText}
            else:
                token = {"type": "htmlblock"}
        else:
            token = {"type": "text", "text": lineText}

        if token["type"] == "blank":
            token["prefixlen"] = float("inf")
        else:
            token["prefixlen"] = prefixCount(line.text, numSpacesForIndentation)
        token["line"] = line
        tokens.append(token)

    if False:  # pylint: disable=using-constant-test
        for i, token in enumerate(tokens):
            print(
                f"{' '*(2-len(str(i)))}{i} {' ' * (11 - len(token['type']))}{token['type']}: {token['line'].text.rstrip()}"
            )

    return tokens


def stripComments(lines):
    """
    Eagerly strip comments, because the serializer can't output them right now anyway,
    and they trigger some funky errors.
    """
    output = []
    inComment = False
    for line in lines:
        text, inComment = stripCommentsFromLine(line.text, inComment)
        if (line.text != text and text.strip() == "") or (line.text.strip() == "" and inComment):
            # First covers the entire line being stripped away by comment-removal.
            # Second covers an empty line that was fully inside a comment.
            # (If a comment started or ended on that line, it wouldn't start out empty.)
            # By removing these entirely, we avoid breaking Markdown constructs with their middles commented out or something.
            # (Rather than leaving them in as blank lines.)
            continue
        else:
            # Otherwise, just process whatever's left as normal.
            if line.text.endswith("\n") and not text.endswith("\n"):
                # Put back the newline, in case it got swallowed by an unclosed comment.
                text += "\n"
            line.text = text
            output.append(line)
    return output


def stripCommentsFromLine(line, inComment=False):
    # Removes HTML comments from the line.
    # Returns true if the comment wasn't closed by the end of the line
    if inComment:
        # The line starts out in a comment.
        pre, sep, post = line.partition("-->")
        if sep == "":
            # The entire line is a comment
            return "", True
        else:
            # Drop the comment part, see if there are any more
            return stripCommentsFromLine(post)
    else:
        # The line starts out as non-comment content.
        pre, sep, post = line.partition("<!--")
        if sep == "":
            # No comments in the line
            return pre, False
        else:
            # Keep the non-comment part, see if there's any more to do
            res, inComment = stripCommentsFromLine(post, inComment=True)
            return pre + res, inComment


def prefixCount(text, numSpacesForIndentation):
    i = 0
    prefixLen = 0
    while i < len(text):
        if text[i] == "\t":
            i += 1
            prefixLen += 1
        elif text[i : i + numSpacesForIndentation] == " " * numSpacesForIndentation:
            i += numSpacesForIndentation
            prefixLen += 1
        else:
            break
    return prefixLen


def stripPrefix(token, numSpacesForIndentation, len):
    """Removes len number of prefix groups"""

    text = token["line"].text

    # Don't mess with "infinite" prefix lines
    if token["prefixlen"] == float("inf"):
        return text

    # Allow empty lines
    if text.strip() == "":
        return text

    offset = 0
    for _ in range(len):
        if text[offset] == "\t":
            offset += 1
        elif text[offset : offset + numSpacesForIndentation] == " " * numSpacesForIndentation:
            offset += numSpacesForIndentation
        else:
            m.die(
                f'Line {token["line"].i} isn\'t indented enough (needs {len} indent{"" if len == 1 else "s"}) to be valid Markdown:\n"{text[:-1]}"'
            )
    return text[offset:]


def lineEndsRawBlock(line, rawToken):
    return (rawToken["type"] == "element" and re.search(rawToken["tag"], line.text)) or (
        rawToken["type"] == "fenced"
        and re.match(r"\s*{}{}*\s*$".format(rawToken["tag"], rawToken["tag"][0]), line.text)
    )


def stripCommonWsPrefix(tokens):
    # Remove the longest common whitespace prefix from the lines.
    if not tokens:
        return tokens
    ws = [getWsPrefix(t["line"].text) for t in tokens]
    prefix = functools.reduce(commonPrefix, ws)
    prefixLen = len(prefix)
    for token in tokens:
        stripped = token["line"].text
        if len(token["line"].text) > prefixLen:
            # Don't remove from blank lines,
            # or else you'll eat the newline!
            stripped = token["line"].text[prefixLen:]
        token["line"].text = stripped
    return tokens


def commonPrefix(line1, line2):
    if line1 is None:
        return line2
    if line2 is None:
        return line1
    prefixSoFar = ""
    for i, char in enumerate(line1):
        if i == len(line2):
            break
        if char == line2[i]:
            prefixSoFar += char
        else:
            break
    return prefixSoFar


def getWsPrefix(line):
    if line.strip() == "":
        return None
    return re.match(r"(\s*)", line).group(1)


def parseTokens(tokens, numSpacesForIndentation):
    """
    Token types:
    eof
    blank
    equals-line
    dash-line
    heading
    rule
    numbered
    bulleted
    dt
    dd
    text
    htmlblock
    blockquote
    raw
    """
    stream = TokenStream(tokens, numSpacesForIndentation)
    lines = []

    while True:
        if stream.ended():
            break
        elif stream.currtype() in ("raw", "htmlblock"):
            lines.append(stream.currline())
            stream.advance()
        elif stream.currtype() == "heading":
            lines += parseSingleLineHeading(stream)
        elif stream.currtype() == "text" and stream.nexttype() in (
            "equals-line",
            "dash-line",
        ):
            lines += parseMultiLineHeading(stream)
        elif stream.currtype() == "text" and stream.prevtype() == "blank":
            lines += parseParagraph(stream)
        elif stream.currtype() == "rule" or stream.currtype() == "dash-line":
            lines += parseHorizontalRule(stream)
        elif stream.currtype() == "bulleted":
            lines += parseBulleted(stream)
        elif stream.currtype() == "numbered":
            lines += parseNumbered(stream, start=stream.currnum())
        elif stream.currtype() in ("dt", "dd"):
            lines += parseDl(stream)
        elif stream.currtype() == "blockquote":
            lines += parseBlockquote(stream)
        else:
            lines.append(stream.currline())
            stream.advance()

    # for line in lines:
    #    print f"«{line.text.rstrip()}»"

    return lines


def lineFromStream(stream, text):
    # Shortcut for when you're producing a new line from the currline in the stream,
    # with some modified text.
    return Line.Line(stream.currline().i, text)


# Each parser gets passed the stream
# and must return the lines it returns.
# The stream should be advanced to the *next* line,
# after the lines you've used up dealing with the construct.


def parseSingleLineHeading(stream):
    if "id" in stream.curr():
        idattr = f" id='{stream.currid()}'"
    else:
        idattr = ""
    lines = [
        lineFromStream(
            stream,
            "<h{level}{idattr} line-number={i}>{text}</h{level}>\n".format(
                idattr=idattr, i=stream.currline().i, **stream.curr()
            ),
        )
    ]
    stream.advance()
    return lines


def parseMultiLineHeading(stream):
    if stream.nexttype() == "equals-line":
        level = 2
    elif stream.nexttype() == "dash-line":
        level = 3
    else:
        m.die(
            "Markdown parser error: tried to parse a multiline heading from:\n"
            + stream.prevraw()
            + stream.currraw()
            + stream.nextraw()
        )
    match = re.search(r"(.*?)\s*\{\s*#([^ }]+)\s*\}\s*$", stream.currtext())
    if match:
        text = match.group(1)
        idattr = "id='{}'".format(match.group(2))
    else:
        text = stream.currtext()
        idattr = ""
    lines = [
        lineFromStream(
            stream,
            "<h{level} {idattr} line-number={i}>{htext}</h{level}>\n".format(
                idattr=idattr,
                level=level,
                htext=text,
                i=stream.currline().i,
                **stream.curr(),
            ),
        )
    ]
    stream.advance(2)
    return lines


def parseHorizontalRule(stream):
    lines = [lineFromStream(stream, "<hr>\n")]
    stream.advance()
    return lines


def parseParagraph(stream):
    line = stream.currtext()
    i = stream.currline().i
    initialPrefixLen = stream.currprefixlen()
    endTag = "</p>"
    if re.match(r"note[:,]\s*", line, re.I):
        p = "<p class='replace-with-note-class'>"
        matchNote = re.match(r"(note[:,])(\s*)(.*)", line, re.I)
        if matchNote:
            line = matchNote.group(3)
            p += "<span>{note}</span>{ws}".format(note=matchNote.group(1), ws=matchNote.group(2))
    elif line.lower().startswith("issue:"):
        line = line[6:]
        p = f"<p line-number={i} class='replace-with-issue-class'>"
    elif line.lower().startswith("assert:"):
        p = f"<p line-number={i} class='replace-with-assertion-class'>"
    elif line.lower().startswith("advisement:"):
        line = line[11:]
        p = f"<p line-number={i}><strong class='replace-with-advisement-class'>"
        endTag = "</strong></p>"
    else:
        match = re.match(r"issue\(([^)]+)\):(.*)", line, re.I)
        if match:
            line = match.group(2)
            p = "<p line-number={} data-remote-issue-id='{}' class='replace-with-issue-class'>".format(
                i, match.group(1)
            )
        else:
            p = f"<p line-number={i}>"
    lines = [lineFromStream(stream, f"{p}{line}\n")]
    while True:
        stream.advance()
        if stream.currtype() not in ["text"] or stream.currprefixlen() < initialPrefixLen:
            lines[-1].text = lines[-1].text.rstrip() + endTag + "\n"
            return lines
        lines.append(stream.currline())


def parseBulleted(stream):
    prefixLen = stream.currprefixlen()
    numSpacesForIndentation = stream.numSpacesForIndentation
    ul_i = stream.currline().i

    def parseItem(stream):
        # Assumes it's being called with curr being a bulleted line.
        # Remove the bulleted part from the line
        firstLine = stream.currtext() + "\n"
        i = stream.currline().i
        lines = [lineFromStream(stream, firstLine)]
        while True:
            stream.advance()
            # All the conditions that indicate we're *past* the end of the item.
            if stream.currtype() == "bulleted" and stream.currprefixlen() == prefixLen:
                return lines, i
            if stream.currprefixlen() < prefixLen:
                return lines, i
            if stream.currtype() == "blank" and stream.nexttype() != "bulleted" and stream.nextprefixlen() <= prefixLen:
                return lines, i
            if stream.currtype() == "eof":
                return lines, i
            # Remove the prefix from each line before adding it.
            lines.append(
                lineFromStream(
                    stream,
                    stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1),
                )
            )

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == "eof":
                return
            if stream.currtype() == "blank" and stream.nexttype() != "bulleted" and stream.nextprefixlen() <= prefixLen:
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == "blank":
                stream.advance()
            yield parseItem(stream)

    lines = [Line.Line(-1, f"<ul data-md line-number={ul_i}>")]
    for li_lines, i in getItems(stream):
        lines.append(Line.Line(-1, f"<li data-md line-number={i}>"))
        lines.extend(parse(li_lines, numSpacesForIndentation))
        lines.append(Line.Line(-1, "</li>"))
    lines.append(Line.Line(-1, "</ul>"))
    return lines


def parseNumbered(stream, start=1):
    prefixLen = stream.currprefixlen()
    ol_i = stream.currline().i
    numSpacesForIndentation = stream.numSpacesForIndentation

    def parseItem(stream):
        # Assumes it's being called with curr being a numbered line.
        # Remove the numbered part from the line
        firstLine = stream.currtext() + "\n"
        i = stream.currline().i
        lines = [lineFromStream(stream, firstLine)]
        while True:
            stream.advance()
            # All the conditions that indicate we're *past* the end of the item.
            if stream.currtype() == "numbered" and stream.currprefixlen() == prefixLen:
                return lines, i
            if stream.currprefixlen() < prefixLen:
                return lines, i
            if stream.currtype() == "blank" and stream.nexttype() != "numbered" and stream.nextprefixlen() <= prefixLen:
                return lines, i
            if stream.currtype() == "eof":
                return lines, i
            # Remove the prefix from each line before adding it.
            lines.append(
                lineFromStream(
                    stream,
                    stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1),
                )
            )

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == "eof":
                return
            if stream.currtype() == "blank" and stream.nexttype() != "numbered" and stream.nextprefixlen() <= prefixLen:
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == "blank":
                stream.advance()
            yield parseItem(stream)

    if start == 1:
        lines = [Line.Line(-1, f"<ol data-md line-number={ol_i}>")]
    else:
        lines = [Line.Line(-1, f"<ol data-md start='{start}' line-number={ol_i}>")]
    for li_lines, i in getItems(stream):
        lines.append(Line.Line(-1, f"<li data-md line-number={i}>"))
        lines.extend(parse(li_lines, numSpacesForIndentation))
        lines.append(Line.Line(-1, "</li>"))
    lines.append(Line.Line(-1, "</ol>"))
    return lines


def parseDl(stream):
    prefixLen = stream.currprefixlen()
    dl_i = stream.currline().i
    numSpacesForIndentation = stream.numSpacesForIndentation

    def parseItem(stream):
        # Assumes it's being called with curr being a :/:: prefixed line.
        firstLine = stream.currtext() + "\n"
        i = stream.currline().i
        type = stream.currtype()
        lines = [lineFromStream(stream, firstLine)]
        while True:
            stream.advance()
            # All the conditions that indicate we're *past* the end of the item.
            if stream.currtype() in ("dt", "dd") and stream.currprefixlen() == prefixLen:
                return type, lines, i
            if stream.currprefixlen() < prefixLen:
                return type, lines, i
            if (
                stream.currtype() == "blank"
                and stream.nexttype() not in ("dt", "dd")
                and stream.nextprefixlen() <= prefixLen
            ):
                return type, lines, i
            if stream.currtype() == "eof":
                return type, lines, i
            # Remove the prefix from each line before adding it.
            lines.append(
                lineFromStream(
                    stream,
                    stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1),
                )
            )

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == "eof":
                return
            if (
                stream.currtype() == "blank"
                and stream.nexttype() not in ("dt", "dd")
                and stream.nextprefixlen() <= prefixLen
            ):
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == "blank":
                stream.advance()
            yield parseItem(stream)

    lines = [Line.Line(-1, f"<dl data-md line-number={dl_i}>")]
    for type, di_lines, i in getItems(stream):
        lines.append(Line.Line(-1, f"<{type} data-md line-number={i}>"))
        lines.extend(parse(di_lines, numSpacesForIndentation))
        lines.append(Line.Line(-1, f"</{type}>"))
    lines.append(Line.Line(-1, "</dl>"))
    return lines


def parseBlockquote(stream):
    prefixLen = stream.currprefixlen()
    i = stream.currline().i
    lines = [lineFromStream(stream, stream.currtext() + "\n")]
    while True:
        stream.advance()
        if stream.currprefixlen() < prefixLen:
            break
        if stream.currtype() in ["blockquote", "text"]:
            lines.append(lineFromStream(stream, stream.currtext() + "\n"))
        else:
            break
    return (
        [Line.Line(-1, f"<blockquote line-number={i}>\n")]
        + parse(lines, stream.numSpacesForIndentation)
        + [Line.Line(-1, "</blockquote>\n")]
    )


class TokenStream:
    def __init__(
        self,
        tokens,
        numSpacesForIndentation,
        before=None,
        after=None,
    ):
        self.tokens = tokens
        self.i = 0
        self.numSpacesForIndentation = numSpacesForIndentation
        if before is None:
            self.before = {"type": "blank", "prefixlen": 0}
        else:
            self.before = before
        if after is None:
            self.after = {"type": "eof", "prefixlen": 0}
        else:
            self.after = after

    def __len__(self):
        return len(self.tokens)

    def ended(self):
        return self.i >= len(self)

    def nth(self, i):
        if i < 0:
            return self.before
        elif i >= len(self):
            return self.after
        else:
            return self.tokens[i]

    def prev(self, i=1):
        return self.nth(self.i - i)

    def curr(self):
        return self.nth(self.i)

    def next(self, i=1):
        return self.nth(self.i + i)

    def advance(self, i=1):
        self.i += i
        return self.curr()

    def __getattr__(self, name):
        if len(name) >= 5 and name[0:4] in ("prev", "curr", "next"):
            tokenDir = name[0:4]
            attrName = name[4:]

            def _missing(i=1):
                if tokenDir == "prev":
                    tok = self.prev(i)
                elif tokenDir == "next":
                    tok = self.next(i)
                else:
                    tok = self.curr()
                if attrName in tok:
                    return tok[attrName]

                raise AttributeError(attrName)

            return _missing
