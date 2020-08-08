# -*- coding: utf-8 -*-

import re
from itertools import *

from .. import Line
from ..h import escapeAttr
from ..messages import *


def parse(lines, numSpacesForIndentation, features=None, opaqueElements=None, blockElements=None):
    fromStrings = False
    if any(isinstance(l, str) for l in lines):
        fromStrings = True
        lines = [Line.Line(-1, l) for l in lines]
    lines = Line.rectify(lines)
    tokens = tokenizeLines(lines, numSpacesForIndentation, features, opaqueElements=opaqueElements, blockElements=blockElements)
    html = parseTokens(tokens, numSpacesForIndentation)
    if fromStrings:
        return [l.text for l in html]
    else:
        return html


def tokenizeLines(lines, numSpacesForIndentation, features=None, opaqueElements=None, blockElements=None):
    # Turns lines of text into block tokens,
    # which'll be turned into MD blocks later.
    # Every token *must* have 'type', 'raw', and 'prefix' keys.

    if features is None:
        features = {"headings"}

    # Inline elements that are allowed to start a "normal" line of text.
    # Any other element will instead be an HTML line and will close paragraphs, etc.
    inlineElements = {"a", "em", "strong", "small", "s", "cite", "q", "dfn", "abbr", "data", "time", "code", "var", "samp", "kbd", "sub", "sup", "i", "b", "u", "mark", "ruby", "bdi", "bdo", "span", "br", "wbr", "img", "meter", "progress", "css", "l"}
    if blockElements is None:
        blockElements = []

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

    for l in lines:

        # Three kinds of "raw" elements, which prevent markdown processing inside of them.
        # 1. <pre> and manual opaque elements, which can contain markup and so can nest.
        # 2. <xmp>, <script>, and <style>, which contain raw text, can't nest.
        # 3. Markdown code blocks, which contain raw text, can't nest.
        #
        # The rawStack holds tokens like
        # {"type":"fenced", "tag":"````", "nest":False}

        if rawStack:
            # Inside at least one raw element that turns off markdown.
            # First see if this line will *end* the raw element.
            endTag = rawStack[-1]
            if endTag['type'] == "element" and re.search(endTag['tag'], l.text):
                rawStack.pop()
                tokens.append({'type':'raw', 'prefixlen':float('inf'), 'line':l})
                continue
            elif endTag['type'] == "fenced" and re.match(r"\s*{0}{1}*\s*$".format(endTag['tag'], endTag['tag'][0]), l.text):
                rawStack.pop()
                l.text = "</xmp>"
                tokens.append({'type':'raw', 'prefixlen':float('inf'), 'line':l})
                continue
            elif not endTag['nest']:
                # Just an internal line, but for the no-nesting elements,
                # so guaranteed no more work needs to be done.
                tokens.append({'type':'raw', 'prefixlen':float('inf'), 'line':l})
                continue

        # We're either in a nesting raw element or not in a raw element at all,
        # so check if the line starts a new element.
        match = re.match(r"(\s*)(`{3,}|~{3,})([^`]*)$", l.text)
        if match:
            ws,tag,infoString = match.groups()
            rawStack.append({"type":"fenced", "tag":tag, "nest":False})
            infoString = infoString.strip()
            if infoString:
                # For now, I only care about lang
                lang = infoString.split(" ")[0]
                classAttr = " class='language-{0}'".format(escapeAttr(lang))
            else:
                classAttr = ""
            l.text = '{0}<xmp{1}>'.format(ws, classAttr)
            tokens.append({'type':'raw', 'prefixlen':prefixLen(ws, numSpacesForIndentation), 'line':l})
            continue
        match = re.match(r"\s*<({0})[ >]".format(rawElements), l.text)
        if match:
            tokens.append({'type':'raw', 'prefixlen':prefixLen(l.text, numSpacesForIndentation), 'line':l})
            if re.search(r"</({0})>".format(match.group(1)), l.text):
                # Element started and ended on same line, cool, don't need to do anything.
                pass
            else:
                nest = match.group(1) not in ["xmp", "script", "style"]
                rawStack.append({'type':'element', 'tag':"</{0}>".format(match.group(1)), 'nest':nest})
            continue
        if rawStack:
            tokens.append({'type':'raw', 'prefixlen':float('inf'), 'line':l})
            continue

        line = l.text.strip()

        if line == "":
            token = {'type':'blank',}
        # FIXME: Detect the heading ID from heading lines
        elif "headings" in features and re.match(r"={3,}\s*$", line):
            # h1 underline
            match = re.match(r"={3,}\s$", line)
            token = {'type':'equals-line'}
        elif "headings" in features and re.match(r"-{3,}\s*$", line):
            # h2 underline
            match = re.match(r"-{3,}\s*$", line)
            token = {'type':'dash-line'}
        elif "headings" in features and re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", line):
            # single-line heading
            match = re.match(r"(#{1,5})\s+(.+?)(\1\s*\{#[^ }]+\})?\s*$", line)
            level = len(match.group(1)) + 1
            token = {'type':'heading', 'text': match.group(2).strip(), 'level': level}
            match = re.search(r"\{#([^ }]+)\}\s*$", line)
            if match:
                token['id'] = match.group(1)
        elif re.match(r"((\*\s*){3,})$|((-\s*){3,})$|((_\s*){3,})$", line):
            token = {'type':'rule'}
        elif re.match(r"-?\d+\.\s", line):
            match = re.match(r"(-?\d+)\.\s+(.*)", line)
            token = {'type':'numbered', 'text': match.group(2), 'num': int(match.group(1))}
        elif re.match(r"-?\d+\.$", line):
            token = {'type':'numbered', 'text': "", 'num': int(line[:-1])}
        elif re.match(r"[*+-]\s", line):
            match = re.match(r"[*+-]\s+(.*)", line)
            token = {'type':'bulleted', 'text': match.group(1)}
        elif re.match(r"[*+-]$", line):
            token = {'type':'bulleted', 'text': ""}
        elif re.match(r":{1,2}\s+", line):
            match = re.match(r"(:{1,2})\s+(.*)", line)
            type = 'dt' if len(match.group(1)) == 1 else 'dd'
            token = {'type':type, 'text': match.group(2)}
        elif re.match(r":{1,2}$", line):
            match = re.match(r"(:{1,2})", line)
            type = 'dt' if len(match.group(1)) == 1 else 'dd'
            token = {'type':type, 'text': ""}
        elif re.match(r">", line):
            match = re.match(r">\s?(.*)", line)
            token = {'type':'blockquote', 'text':match.group(1)}
        elif re.match(r"<", line):
            if re.match(r"<<|<\{", line) or inlineElementStart(line):
                token = {'type':'text', 'text': line}
            else:
                token = {'type':'htmlblock'}
        else:
            token = {'type':'text', 'text': line}

        if token['type'] == "blank":
            token['prefixlen'] = float('inf')
        else:
            token['prefixlen'] = prefixLen(l.text, numSpacesForIndentation)
        token['line'] = l
        tokens.append(token)

    #for token in tokens:
    #    print (" " * (11 - len(token['type']))) + token['type'] + ": " + token['line'].text.rstrip()

    return tokens


def stripComments(lines):
    '''
    Eagerly strip comments, because the serializer can't output them right now anyway,
    and they trigger some funky errors.
    '''
    output = []
    inComment = False
    wholeCommentLines = 0
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
        pre,sep,post = line.partition("-->")
        if sep == "":
            # The entire line is a comment
            return "", True
        else:
            # Drop the comment part, see if there are any more
            return stripCommentsFromLine(post)
    else:
        # The line starts out as non-comment content.
        pre,sep,post = line.partition("<!--")
        if sep == "":
            # No comments in the line
            return pre, False
        else:
            # Keep the non-comment part, see if there's any more to do
            res,inComment = stripCommentsFromLine(post, inComment=True)
            return pre + res, inComment


def prefixLen(text, numSpacesForIndentation):
    i = 0
    prefixLen = 0
    while i < len(text):
        if text[i] == "\t":
            i += 1
            prefixLen += 1
        elif text[i:i + numSpacesForIndentation] == " " * numSpacesForIndentation:
            i += numSpacesForIndentation
            prefixLen += 1
        else:
            break
    return prefixLen


def stripPrefix(token, numSpacesForIndentation, len):
    '''Removes len number of prefix groups'''

    text = token['line'].text

    # Don't mess with "infinite" prefix lines
    if token['prefixlen'] == float('inf'):
        return text

    # Allow empty lines
    if text.strip() == "":
        return text

    offset = 0
    for x in range(len):
        if text[offset] == "\t":
            offset += 1
        elif text[offset:offset + numSpacesForIndentation] == " " * numSpacesForIndentation:
            offset += numSpacesForIndentation
        else:
            die("Line {i} isn't indented enough (needs {0} indent{plural}) to be valid Markdown:\n\"{1}\"", len, text[:-1], plural="" if len == 1 else "s", i=token['line'].i)
    return text[offset:]


def parseTokens(tokens, numSpacesForIndentation):
    '''
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
    '''
    stream = TokenStream(tokens, numSpacesForIndentation)
    lines = []

    while True:
        if stream.ended():
            break
        elif stream.currtype() in ('raw', 'htmlblock'):
            lines.append(stream.currline())
            stream.advance()
        elif stream.currtype() == 'heading':
            lines += parseSingleLineHeading(stream)
        elif stream.currtype() == 'text' and stream.nexttype() in ('equals-line', 'dash-line'):
            lines += parseMultiLineHeading(stream)
        elif stream.currtype() == 'text' and stream.prevtype() == 'blank':
            lines += parseParagraph(stream)
        elif stream.currtype() == 'rule' or stream.currtype() == 'dash-line':
            lines += parseHorizontalRule(stream)
        elif stream.currtype() == 'bulleted':
            lines += parseBulleted(stream)
        elif stream.currtype() == 'numbered':
            lines += parseNumbered(stream, start=stream.currnum())
        elif stream.currtype() in ("dt", "dd"):
            lines += parseDl(stream)
        elif stream.currtype() == "blockquote":
            lines += parseBlockquote(stream)
        else:
            lines.append(stream.currline())
            stream.advance()

    #for line in lines:
    #    print "«{0}»".format(line.text.rstrip())

    return lines

def lineFromStream(stream, text):
    # Shortcut for when you're producing a new line from the currline in the stream,
    # with some modified text.
    return Line.Line(stream.currline().i,  text)

# Each parser gets passed the stream
# and must return the lines it returns.
# The stream should be advanced to the *next* line,
# after the lines you've used up dealing with the construct.


def parseSingleLineHeading(stream):
    if "id" in stream.curr():
        idattr = " id='{0}'".format(stream.currid())
    else:
        idattr = ""
    lines = [lineFromStream(stream, "<h{level}{idattr} line-number={i}>{text}</h{level}>\n".format(idattr=idattr, i=stream.currline().i, **stream.curr()))]
    stream.advance()
    return lines


def parseMultiLineHeading(stream):
    if stream.nexttype() == "equals-line":
        level = 2
    elif stream.nexttype() == "dash-line":
        level = 3
    else:
        die("Markdown parser error: tried to parse a multiline heading from:\n{0}{1}{2}", stream.prevraw(), stream.currraw(), stream.nextraw())
    match = re.search(r"(.*?)\s*\{\s*#([^ }]+)\s*\}\s*$", stream.currtext())
    if match:
        text = match.group(1)
        idattr = "id='{0}'".format(match.group(2))
    else:
        text = stream.currtext()
        idattr = ""
    lines = [lineFromStream(stream,  "<h{level} {idattr} line-number={i}>{htext}</h{level}>\n".format(idattr=idattr, level=level, htext=text, i=stream.currline().i, **stream.curr()))]
    stream.advance(2)
    return lines


def parseHorizontalRule(stream):
    lines = [lineFromStream(stream,  "<hr>\n")]
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
        p = "<p line-number={0} class='replace-with-issue-class'>".format(i)
    elif line.lower().startswith("assert:"):
        p = "<p line-number={0} class='replace-with-assertion-class'>".format(i)
    elif line.lower().startswith("advisement:"):
        line = line[11:]
        p = "<p line-number={0}><strong class='replace-with-advisement-class'>".format(i)
        endTag = "</strong></p>"
    else:
        match = re.match(r"issue\(([^)]+)\):(.*)", line, re.I)
        if match:
            line = match.group(2)
            p = "<p line-number={0} data-remote-issue-id='{1}' class='replace-with-issue-class'>".format(i, match.group(1))
        else:
            p = "<p line-number={0}>".format(i)
    lines = [lineFromStream(stream, "{0}{1}\n".format(p, line))]
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
        lines = [lineFromStream(stream,  firstLine)]
        while True:
            stream.advance()
            # All the conditions that indicate we're *past* the end of the item.
            if stream.currtype() == 'bulleted' and stream.currprefixlen() == prefixLen:
                return lines, i
            if stream.currprefixlen() < prefixLen:
                return lines, i
            if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted' and stream.nextprefixlen() <= prefixLen:
                return lines, i
            if stream.currtype() == 'eof':
                return lines, i
            # Remove the prefix from each line before adding it.
            lines.append(lineFromStream(stream,  stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1)))

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == 'eof':
                return
            if stream.currtype() == 'blank' and stream.nexttype() != 'bulleted' and stream.nextprefixlen() <= prefixLen:
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == 'blank':
                stream.advance()
            yield parseItem(stream)

    lines = [Line.Line(-1,  "<ul data-md line-number={0}>".format(ul_i))]
    for li_lines, i in getItems(stream):
        lines.append(Line.Line(-1, "<li data-md line-number={0}>".format(i)))
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
            if stream.currtype() == 'numbered' and stream.currprefixlen() == prefixLen:
                return lines,i
            if stream.currprefixlen() < prefixLen:
                return lines,i
            if stream.currtype() == 'blank' and stream.nexttype() != 'numbered' and stream.nextprefixlen() <= prefixLen:
                return lines,i
            if stream.currtype() == 'eof':
                return lines,i
            # Remove the prefix from each line before adding it.
            lines.append(lineFromStream(stream, stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1)))

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == 'eof':
                return
            if stream.currtype() == 'blank' and stream.nexttype() != 'numbered' and stream.nextprefixlen() <= prefixLen:
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == 'blank':
                stream.advance()
            yield parseItem(stream)

    if start == 1:
        lines = [Line.Line(-1, "<ol data-md line-number={0}>".format(ol_i))]
    else:
        lines = [Line.Line(-1, "<ol data-md start='{0}' line-number={1}>".format(start, ol_i))]
    for li_lines,i in getItems(stream):
        lines.append(Line.Line(-1, "<li data-md line-number={0}>".format(i)))
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
            if stream.currtype() in ('dt', 'dd') and stream.currprefixlen() == prefixLen:
                return type, lines, i
            if stream.currprefixlen() < prefixLen:
                return type, lines, i
            if stream.currtype() == 'blank' and stream.nexttype() not in ('dt', 'dd') and stream.nextprefixlen() <= prefixLen:
                return type, lines, i
            if stream.currtype() == 'eof':
                return type, lines, i
            # Remove the prefix from each line before adding it.
            lines.append(lineFromStream(stream, stripPrefix(stream.curr(), numSpacesForIndentation, prefixLen + 1)))

    def getItems(stream):
        while True:
            # The conditions that indicate we're past the end of the list itself
            if stream.currtype() == 'eof':
                return
            if stream.currtype() == 'blank' and stream.nexttype() not in ('dt', 'dd') and stream.nextprefixlen() <= prefixLen:
                return
            if stream.currprefixlen() < prefixLen:
                return
            if stream.currtype() == 'blank':
                stream.advance()
            yield parseItem(stream)

    lines = [Line.Line(-1, "<dl data-md line-number={0}>".format(dl_i))]
    for type, di_lines, i in getItems(stream):
        lines.append(Line.Line(-1, "<{0} data-md line-number={1}>".format(type, i)))
        lines.extend(parse(di_lines, numSpacesForIndentation))
        lines.append(Line.Line(-1, "</{0}>".format(type)))
    lines.append(Line.Line(-1, "</dl>"))
    return lines


def parseBlockquote(stream):
    prefixLen = stream.currprefixlen()
    i = stream.currline().i
    lines = [lineFromStream(stream, stream.currtext()+"\n")]
    while True:
        stream.advance()
        if stream.currprefixlen() < prefixLen:
            break
        if stream.currtype() in ["blockquote", "text"]:
            lines.append(lineFromStream(stream, stream.currtext()+"\n"))
        else:
            break
    return [Line.Line(-1, "<blockquote line-number={0}>\n".format(i))] + parse(lines, stream.numSpacesForIndentation) + [Line.Line(-1, "</blockquote>\n")]


class TokenStream:
    def __init__(self, tokens, numSpacesForIndentation, before={'type':'blank','prefixlen':0}, after={'type':'eof','prefixlen':0}):
        self.tokens = tokens
        self.i = 0
        self.numSpacesForIndentation = numSpacesForIndentation
        self.before = before
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
                else:
                    raise AttributeError(attrName)
                    return tok['raw']
            return _missing
