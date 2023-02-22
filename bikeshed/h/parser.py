# pylint: skip-file
from __future__ import annotations

import bisect
import enum
import io
import os
import re
import typing
from dataclasses import dataclass, field

from .. import messages as m, t
from . import dom


def test() -> None:
    nodes = []
    with io.open(os.path.abspath("tests/abstract001.html"), "r") as fh:
        i = 0
        s = Stream(fh.read())
        _, i = parseDoctype(s, i)
        while not s.eof(i):
            print(s.loc(i))
            text, i = s.skip(i, "<")
            if text:
                nodes.append(text)

            comment, i = parseComment(s, i)
            if comment is not Failure:
                nodes.append(comment)

            startTag, i = parseStartTag(s, i)
            if startTag is not Failure:
                nodes.append(startTag)
                if startTag.tag == "script":
                    text, i = parseScriptToEnd(s, i)
                    nodes.append(text)
                    nodes.append(EndTag(-1, "script"))
                elif startTag.tag == "style":
                    text, i = parseStyleToEnd(s, i)
                    nodes.append(text)
                    nodes.append(EndTag(-1, "style"))
                elif startTag.tag == "xmp":
                    text, i = parseXmpToEnd(s, i)
                    nodes.append(text)
                    nodes.append(EndTag(-1, "xmp"))

            endTag, i = parseEndTag(s, i)
            if endTag is not Failure:
                nodes.append(endTag)
        for node in nodes:
            print(node, end="")


#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#####################################
# Scaffolding
#####################################
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#


@dataclass
class Failure:
    pass


@dataclass
class ParseFailure(Failure):
    details: str
    s: Stream
    index: int

    def __str__(self) -> str:
        return f"{self.s.loc(self.index)} {self.details}"


@dataclass
class Result:
    value: t.Any
    end: int
    err: Failure | None = None

    @property
    def valid(self) -> bool:
        return self.err is None

    @staticmethod
    def fail(index: int) -> Result:
        return Result(None, index, Failure())

    @staticmethod
    def parseerror(s: Stream, index: int, details: str) -> Result:
        return Result(None, index, ParseFailure(details, s, index))

    def __iter__(self) -> t.Iterator[t.Any]:
        # By default, mask the error for simpler detection
        # via `is Failure`
        # (treating the class itself as a unique marker value)
        if self.err:
            value = Failure
        else:
            value = self.value
        return iter((value, self.end))

    def showErr(self) -> tuple[t.Any, int, Failure | None]:
        if self.err:
            value = Failure
        else:
            value = self.value
        return (value, self.end, self.err)


class Stream:
    _chars: str
    _lineBreaks: list[int]

    def __init__(self, chars: str):
        self._chars = chars
        self._lineBreaks = []
        for i, char in enumerate(chars):
            if char == "\n":
                self._lineBreaks.append(i)

    def __getitem__(self, key: int | slice) -> str:
        try:
            return self._chars[key]
        except IndexError:
            return ""

    def eof(self, index: int) -> bool:
        return index >= len(self._chars)

    def line(self, index: int) -> int:
        # Zero-based line index
        lineIndex = bisect.bisect_left(self._lineBreaks, index)
        return lineIndex + 1

    def col(self, index: int) -> int:
        lineIndex = bisect.bisect_left(self._lineBreaks, index)
        if lineIndex == 0:
            return index + 1
        startOfCol = self._lineBreaks[lineIndex - 1]
        return index - startOfCol

    def loc(self, index: int) -> str:
        return f"{self.line(index)}:{self.col(index)}"

    def skip(self, start: int, ch: str) -> Result:
        i = start
        chLen = len(ch)
        while self[i : i + chLen] != ch and not self.eof(i):
            i += 1
        return Result(self[start:i], i)

    def skipToNextLine(self, start: int) -> Result:
        lineIndex = bisect.bisect_left(self._lineBreaks, start)
        if lineIndex + 1 < len(self._lineBreaks):
            i = self._lineBreaks[lineIndex + 1] + 1
            return Result(self[start:i], i)
        else:
            return Result(self[start:], len(self._chars))


@dataclass
class StartTag:
    line: int
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        start = f"<{self.tag}:{self.line}"
        if self.attrs:
            attrs = " " + " ".join(f'{name}="{val}"' for name, val in self.attrs.items())
        else:
            attrs = ""
        return start + attrs + ">"


@dataclass
class EndTag:
    line: int
    tag: str

    def __str__(self) -> str:
        return f"</{self.tag}:{self.line}>"


@dataclass
class Comment:
    line: int
    data: str

    def __str__(self) -> str:
        return f"<!--{self.data}-->"


#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
##################################
# Parsing Funcs
##################################
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#


def parseStartTag(s: Stream, start: int) -> Result:
    if s[start] != "<":
        return Result.fail(start)
    else:
        i = start + 1

    tagname, i = parseTagName(s, i)
    if tagname is Failure:
        return Result.fail(start)

    # After this point we're committed to a start tag,
    # so failure will really be a parse error.

    tag = StartTag(s.line(start), tagname)

    while True:
        ws, i = parseWhitespace(s, i)
        if ws is Failure:
            break
        startAttr = i
        attr, i = parseAttribute(s, i)
        if attr is Failure:
            break
        attrName, attrValue = attr
        if attrName in tag.attrs:
            m.die(f"Attribute {attrName} appears twice in <{tagname}>.", lineNum=s.loc(startAttr))
            return Result.fail(start)
        tag.attrs[attrName] = attrValue

    _, i = parseWhitespace(s, i)

    if s[i] == "/":
        if s[i + 1] == ">" and tagname in ("br", "link", "meta"):
            return Result(tag, i + 2)
        else:
            m.die(f"Spurious / in <{tagname}>.", lineNum=s.loc(start))
            return Result.fail(start)

    if s[i] == ">":
        return Result(tag, i + 1)

    if s.eof(i):
        m.die(f"Tag <{tagname}> wasn't closed at end of file.", lineNum=s.loc(start))
        return Result.fail(start)

    m.die(f"Garbage at {s.loc(i)} in <{tagname}>.", lineNum=s.loc(start))
    return Result.fail(start)


def parseTagName(s: Stream, start: int) -> Result:
    if not isASCIIAlpha(s[start]):
        return Result.fail(start)
    end = start + 1
    while isTagnameChar(s[end]):
        end += 1
    return Result(s[start:end], end)


def parseAttribute(s: Stream, start: int) -> Result:
    i = start
    while isAttrNameChar(s[i]):
        i += 1
    if i == start:
        return Result.fail(start)

    # Committed to an attribute

    attrName = s[start:i]
    endOfName = i
    _, i = parseWhitespace(s, i)
    if s[i] == "=":
        i += 1
    else:
        return Result((attrName, ""), endOfName)

    # Now committed to a value too

    _, i = parseWhitespace(s, i)

    if s[i] == '"' or s[i] == "'":
        attrValue, i = parseQuotedAttrValue(s, i)
    else:
        attrValue, i = parseUnquotedAttrValue(s, i)
        if attrValue is Failure:
            m.die(f"Garbage after {attrName}=.", lineNum=s.loc(i))
            return Result.fail(start)

    return Result((attrName, attrValue), i)


def parseQuotedAttrValue(s: Stream, start: int) -> Result:
    endChar = s[start]
    i = start + 1

    # Could just append chars one-by-one,
    # but for efficiency track segments between char refs
    # and append the whole thing at once when I hit one.
    val = ""
    startSeg = i
    while s[i] != endChar:
        if s.eof(i):
            m.die("Quoted attribute was never closed", lineNum=s.loc(start))
            return Result.fail(start)
        if ord(s[i]) == 0:
            m.die("Unexpected U+0000 while parsing attribute value.", lineNum=s.loc(i))
            return Result.fail(start)
        if s[i] == "&":
            startRef = i
            ch, i = parseCharRef(s, i)
            if ch is Failure:
                i += 1
                continue
            val += s[startSeg:startRef] + ch
            startSeg = i
            continue
        i += 1
    val += s[startSeg:i]
    i += 1
    return Result(val, i)


def parseUnquotedAttrValue(s: Stream, start: int) -> Result:
    i = start
    val = ""
    startSeg = i
    while not s.eof(i):
        if s[i] == ">":
            break
        if isWhitespace(s[i]):
            break
        if s[i] in "\"'<=`":
            m.die(f"Character {s[i]} (at {s.loc(i)}) is invalid in unquoted attribute values.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i] == "&":
            startRef = i
            ch, i = parseCharRef(s, i)
            if ch is Failure:
                i += 1
                continue
            val += s[startSeg:startRef] + ch
            startSeg = i
            continue
        i += 1
    if i == start:
        m.die("Missing attribute value.", lineNum=s.loc(start))
        return Result.fail(start)
    val += s[startSeg:i]
    return Result(val, i)


def parseCharRef(s: Stream, start: int) -> Result:
    if s[start] != "&":
        return Result.fail(start)
    i = start + 1

    if isASCIIAlphanum(s[i]):
        i += 1
        while isASCIIAlphanum(s[i]):
            i += 1
        if s[i] != ";":
            m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
            return Result.fail(start)
        i += 1
        if s[start:i] not in charRefs:
            m.die(f"'{s[start:i]} isn't a valid character reference.", lineNum=s.loc(start))
            return Result.fail(start)
        return Result(charRefs[s[start:i]], i)
    elif s[i] == "#":
        i += 1
        if s[i] == "x" or s[i] == "X":
            i += 1
            numStart = i
            while isHexDigit(s[i]):
                i += 1
            if i == numStart:
                m.die(f"Malformed numeric character reference '{s[start:i]}'.", lineNum=s.loc(start))
                return Result.fail(start)
            if s[i] != ";":
                m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
                return Result.fail(start)
            cp = int(s[numStart:i], 16)
        else:
            numStart = i
            while isHexDigit(s[i]):
                i += 1
            if i == numStart:
                m.die(f"Malformed numeric character reference '{s[start:i]}'.", lineNum=s.loc(start))
                return Result.fail(start)
            if s[i] != ";":
                m.die(f"Character reference '{s[start:i]}' didn't end in ;.", lineNum=s.loc(start))
                return Result.fail(start)
            cp = int(s[numStart:i], 10)
        i += 1
        if cp == 0:
            m.die("Char refs can't resolve to null.", lineNum=s.loc(start))
            return Result.fail(start)
        if cp > 0x10FFFF:
            m.die(f"Char ref '{s[start:i]}' is outside of Unicode.", lineNum=s.loc(start))
            return Result.fail(start)
        if 0xD800 <= cp <= 0xDFFF:
            m.die(f"Char ref '{s[start:i]}' is a lone surrogate.", lineNum=s.loc(start))
            return Result.fail(start)
        if isNoncharacter(cp):
            m.die(f"Char ref '{s[start:i]}' is a non-character.", lineNum=s.loc(start))
            return Result.fail(start)
        if cp == 0xD or (isControl(cp) and not isWhitespace(cp)):
            m.die(f"Char ref '{s[start:i]}' is a control character.", lineNum=s.loc(start))
            return Result.fail(start)
        return Result(chr(cp), i)
    else:
        return Result.fail(start)


def parseWhitespace(s: Stream, start: int) -> Result:
    i = start
    while isWhitespace(s[i]):
        i += 1
    if i != start:
        return Result(True, i)
    else:
        return Result.fail(start)


def parseEndTag(s: Stream, start: int) -> Result:
    if s[start : start + 2] != "</":
        return Result.fail(start)
    i = start + 2

    # committed now

    if s[i] == ">":
        m.die("Missing end tag name. (Got </>.)", lineNum=s.loc(start))
        return Result.fail(start)
    if s.eof(i):
        m.die("Hit EOF in the middle of an end tag.", lineNum=s.loc(start))
        return Result.fail(start)
    tagname, i = parseTagName(s, i)
    if tagname is Failure:
        m.die("Garbage in an end tag.", lineNum=s.loc(start))
        return Result.fail(start)
    if s.eof(i):
        m.die(f"Hit EOF in the middle of an end tag </{tagname}>.", lineNum=s.loc(start))
        return Result.fail(start)
    if s[i] != ">":
        m.die(f"Garbage after the tagname in </{tagname}>.", lineNum=s.loc(start))
        return Result.fail(start)
    i += 1
    return Result(EndTag(s.line(start), tagname), i)


def parseComment(s: Stream, start: int) -> Result:
    if s[start : start + 2] != "<!":
        return Result.fail(start)
    i = start + 2

    # committed
    if s[i : i + 2] != "--":
        m.die(f"Malformed HTML comment '{s[start:start+10]}'.", lineNum=s.loc(start))
        return Result.fail(start)
    i += 2

    dataStart = i

    while True:
        while s[i] != "-" and not s.eof(i):
            i += 1
        if s[i : i + 3] == "-->":
            return Result(Comment(s.line(start), s[dataStart:i]), i + 3)
        if s[i : i + 4] == "--!>":
            m.die("Malformed comment - don't use a ! at the end.", lineNum=s.loc(start))
            return Result.fail(start)
        if s.eof(i):
            m.die("Hit EOF in the middle of a comment.", lineNum=s.loc(start))
            return Result.fail(start)
        i += 1
    assert False


def parseDoctype(s: Stream, start: int) -> Result:
    if s[start : start + 2] != "<!":
        return Result.fail(start)
    if s[start + 2 : start + 9].lower() != "doctype":
        return Result.fail(start)
    if s[start + 9 : start + 15].lower() != " html>":
        m.die("Unnecessarily complex doctype - use <!doctype html>.", lineNum=s.loc(start))
        return Result.fail(start)
    return Result(True, start + 15)


def parseScriptToEnd(s: Stream, start: int) -> Result:
    # Call with s[i] after the opening <script> tag.
    # Returns with s[i] after the </script> tag,
    # with text contents in the Result.

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of a <script>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 9] == "</script>":
            return Result(s[start:i], i + 9)
        i += 1
    assert False


def parseStyleToEnd(s: Stream, start: int) -> Result:
    # Identical to parseScriptToEnd

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of a <style>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 8] == "</style>":
            return Result(s[start:i], i + 8)
        i += 1
    assert False


def parseXmpToEnd(s: Stream, start: int) -> Result:
    # Identical to parseScriptToEnd

    i = start
    while True:
        while s[i] != "<" and not s.eof(i):
            i += 1
        if s.eof(i):
            m.die("Hit EOF in the middle of an <xmp>.", lineNum=s.loc(start))
            return Result.fail(start)
        if s[i : i + 6] == "</xmp>":
            return Result(s[start:i], i + 6)
        i += 1
    assert False


#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
######################################
# Predicates
######################################
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#


def isTagnameChar(ch: str) -> bool:
    if len(ch) != 1:
        return False
    if ch in "-.0123456789_" or isASCIIAlpha(ch):
        return True
    cp = ord(ch)
    if cp == 0xB7:
        return True
    if 0xC0 <= cp <= 0x1FFF:
        if cp in (0xD7, 0xF7, 0x37E):
            return False
        return True
    if cp in (0x200C, 0x200D, 0x203F, 0x2040):
        return True
    if 0x2070 <= cp <= 0x218F:
        return True
    if 0x2C00 <= cp <= 0x2FEF:
        return True
    if 0x3001 <= cp <= 0xD7FF:
        return True
    if 0xF900 <= cp <= 0xFDCF:
        return True
    if 0xFDF0 <= cp <= 0xFFFD:
        return True
    if 0x10000 <= cp <= 0xEFFFF:
        return True
    return False


def isAttrNameChar(ch: str) -> bool:
    if len(ch) != 1:
        return False
    if isWhitespace(ch) or ch in "/<>=\"'" or ord(ch) == 0:
        return False
    return True


def isASCII(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return cp <= 127


def isASCIIAlphanum(ch: str) -> bool:
    return isASCIIAlpha(ch) or isDigit(ch)


def isASCIIAlpha(ch: str) -> bool:
    return isASCIILowerAlpha(ch) or isASCIIUpperAlpha(ch)


def isASCIILowerAlpha(ch: str) -> bool:
    if len(ch) != 1:
        return False
    return ch in "abcdefghijklmnopqrstuvwxyz"


def isASCIIUpperAlpha(ch: str) -> bool:
    if len(ch) != 1:
        return False
    return ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def isDigit(ch: str) -> bool:
    if len(ch) != 1:
        return False
    return ch in "0123456789"


def isHexDigit(ch: str) -> bool:
    if len(ch) != 1:
        return False
    return ch in "0123456789abcdefABCDEF"


def isWhitespace(ch: str | int) -> bool:
    if isinstance(ch, str):
        if len(ch) != 1:
            return False
        cp = ord(ch)
    else:
        cp = ch
    return cp in (0x9, 0xA, 0xC, 0x20)


def isControl(ch: str | int) -> bool:
    if isinstance(ch, str):
        if len(ch) != 1:
            return False
        cp = ord(ch)
    else:
        cp = ch
    return (0 <= cp <= 0x1F) or (0x7F <= cp <= 0x9F)


def isNoncharacter(ch: str | int) -> bool:
    if isinstance(ch, str):
        if len(ch) != 1:
            return False
        cp = ord(ch)
    else:
        cp = ch
    return 0xFDD0 <= cp <= 0xFDEF or cp in (
        0xFFFE,
        0xFFFF,
        0x1FFFE,
        0x1FFF,
        0x2FFFE,
        0x2FFFF,
        0x3FFFE,
        0x3FFFF,
        0x4FFFE,
        0x4FFFF,
        0x5FFFE,
        0x5FFFF,
        0x6FFFE,
        0x6FFFF,
        0x7FFFE,
        0x7FFFF,
        0x8FFFE,
        0x8FFFF,
        0x9FFFE,
        0x9FFFF,
        0xAFFFE,
        0xAFFFF,
        0xBFFFE,
        0xBFFFF,
        0xCFFFE,
        0xCFFFF,
        0xDFFFE,
        0xDFFFF,
        0xEFFFE,
        0xEFFFF,
        0xFFFFE,
        0xFFFFF,
        0x10FFFE,
        0x10FFFF,
    )


charRefs = {
    "&AElig": "\u00C6",
    "&AElig;": "\u00C6",
    "&AMP": "\u0026",
    "&AMP;": "\u0026",
    "&Aacute": "\u00C1",
    "&Aacute;": "\u00C1",
    "&Abreve;": "\u0102",
    "&Acirc": "\u00C2",
    "&Acirc;": "\u00C2",
    "&Acy;": "\u0410",
    "&Afr;": "\uD835\uDD04",
    "&Agrave": "\u00C0",
    "&Agrave;": "\u00C0",
    "&Alpha;": "\u0391",
    "&Amacr;": "\u0100",
    "&And;": "\u2A53",
    "&Aogon;": "\u0104",
    "&Aopf;": "\uD835\uDD38",
    "&ApplyFunction;": "\u2061",
    "&Aring": "\u00C5",
    "&Aring;": "\u00C5",
    "&Ascr;": "\uD835\uDC9C",
    "&Assign;": "\u2254",
    "&Atilde": "\u00C3",
    "&Atilde;": "\u00C3",
    "&Auml": "\u00C4",
    "&Auml;": "\u00C4",
    "&Backslash;": "\u2216",
    "&Barv;": "\u2AE7",
    "&Barwed;": "\u2306",
    "&Bcy;": "\u0411",
    "&Because;": "\u2235",
    "&Bernoullis;": "\u212C",
    "&Beta;": "\u0392",
    "&Bfr;": "\uD835\uDD05",
    "&Bopf;": "\uD835\uDD39",
    "&Breve;": "\u02D8",
    "&Bscr;": "\u212C",
    "&Bumpeq;": "\u224E",
    "&CHcy;": "\u0427",
    "&COPY": "\u00A9",
    "&COPY;": "\u00A9",
    "&Cacute;": "\u0106",
    "&Cap;": "\u22D2",
    "&CapitalDifferentialD;": "\u2145",
    "&Cayleys;": "\u212D",
    "&Ccaron;": "\u010C",
    "&Ccedil": "\u00C7",
    "&Ccedil;": "\u00C7",
    "&Ccirc;": "\u0108",
    "&Cconint;": "\u2230",
    "&Cdot;": "\u010A",
    "&Cedilla;": "\u00B8",
    "&CenterDot;": "\u00B7",
    "&Cfr;": "\u212D",
    "&Chi;": "\u03A7",
    "&CircleDot;": "\u2299",
    "&CircleMinus;": "\u2296",
    "&CirclePlus;": "\u2295",
    "&CircleTimes;": "\u2297",
    "&ClockwiseContourIntegral;": "\u2232",
    "&CloseCurlyDoubleQuote;": "\u201D",
    "&CloseCurlyQuote;": "\u2019",
    "&Colon;": "\u2237",
    "&Colone;": "\u2A74",
    "&Congruent;": "\u2261",
    "&Conint;": "\u222F",
    "&ContourIntegral;": "\u222E",
    "&Copf;": "\u2102",
    "&Coproduct;": "\u2210",
    "&CounterClockwiseContourIntegral;": "\u2233",
    "&Cross;": "\u2A2F",
    "&Cscr;": "\uD835\uDC9E",
    "&Cup;": "\u22D3",
    "&CupCap;": "\u224D",
    "&DD;": "\u2145",
    "&DDotrahd;": "\u2911",
    "&DJcy;": "\u0402",
    "&DScy;": "\u0405",
    "&DZcy;": "\u040F",
    "&Dagger;": "\u2021",
    "&Darr;": "\u21A1",
    "&Dashv;": "\u2AE4",
    "&Dcaron;": "\u010E",
    "&Dcy;": "\u0414",
    "&Del;": "\u2207",
    "&Delta;": "\u0394",
    "&Dfr;": "\uD835\uDD07",
    "&DiacriticalAcute;": "\u00B4",
    "&DiacriticalDot;": "\u02D9",
    "&DiacriticalDoubleAcute;": "\u02DD",
    "&DiacriticalGrave;": "\u0060",
    "&DiacriticalTilde;": "\u02DC",
    "&Diamond;": "\u22C4",
    "&DifferentialD;": "\u2146",
    "&Dopf;": "\uD835\uDD3B",
    "&Dot;": "\u00A8",
    "&DotDot;": "\u20DC",
    "&DotEqual;": "\u2250",
    "&DoubleContourIntegral;": "\u222F",
    "&DoubleDot;": "\u00A8",
    "&DoubleDownArrow;": "\u21D3",
    "&DoubleLeftArrow;": "\u21D0",
    "&DoubleLeftRightArrow;": "\u21D4",
    "&DoubleLeftTee;": "\u2AE4",
    "&DoubleLongLeftArrow;": "\u27F8",
    "&DoubleLongLeftRightArrow;": "\u27FA",
    "&DoubleLongRightArrow;": "\u27F9",
    "&DoubleRightArrow;": "\u21D2",
    "&DoubleRightTee;": "\u22A8",
    "&DoubleUpArrow;": "\u21D1",
    "&DoubleUpDownArrow;": "\u21D5",
    "&DoubleVerticalBar;": "\u2225",
    "&DownArrow;": "\u2193",
    "&DownArrowBar;": "\u2913",
    "&DownArrowUpArrow;": "\u21F5",
    "&DownBreve;": "\u0311",
    "&DownLeftRightVector;": "\u2950",
    "&DownLeftTeeVector;": "\u295E",
    "&DownLeftVector;": "\u21BD",
    "&DownLeftVectorBar;": "\u2956",
    "&DownRightTeeVector;": "\u295F",
    "&DownRightVector;": "\u21C1",
    "&DownRightVectorBar;": "\u2957",
    "&DownTee;": "\u22A4",
    "&DownTeeArrow;": "\u21A7",
    "&Downarrow;": "\u21D3",
    "&Dscr;": "\uD835\uDC9F",
    "&Dstrok;": "\u0110",
    "&ENG;": "\u014A",
    "&ETH": "\u00D0",
    "&ETH;": "\u00D0",
    "&Eacute": "\u00C9",
    "&Eacute;": "\u00C9",
    "&Ecaron;": "\u011A",
    "&Ecirc": "\u00CA",
    "&Ecirc;": "\u00CA",
    "&Ecy;": "\u042D",
    "&Edot;": "\u0116",
    "&Efr;": "\uD835\uDD08",
    "&Egrave": "\u00C8",
    "&Egrave;": "\u00C8",
    "&Element;": "\u2208",
    "&Emacr;": "\u0112",
    "&EmptySmallSquare;": "\u25FB",
    "&EmptyVerySmallSquare;": "\u25AB",
    "&Eogon;": "\u0118",
    "&Eopf;": "\uD835\uDD3C",
    "&Epsilon;": "\u0395",
    "&Equal;": "\u2A75",
    "&EqualTilde;": "\u2242",
    "&Equilibrium;": "\u21CC",
    "&Escr;": "\u2130",
    "&Esim;": "\u2A73",
    "&Eta;": "\u0397",
    "&Euml": "\u00CB",
    "&Euml;": "\u00CB",
    "&Exists;": "\u2203",
    "&ExponentialE;": "\u2147",
    "&Fcy;": "\u0424",
    "&Ffr;": "\uD835\uDD09",
    "&FilledSmallSquare;": "\u25FC",
    "&FilledVerySmallSquare;": "\u25AA",
    "&Fopf;": "\uD835\uDD3D",
    "&ForAll;": "\u2200",
    "&Fouriertrf;": "\u2131",
    "&Fscr;": "\u2131",
    "&GJcy;": "\u0403",
    "&GT": "\u003E",
    "&GT;": "\u003E",
    "&Gamma;": "\u0393",
    "&Gammad;": "\u03DC",
    "&Gbreve;": "\u011E",
    "&Gcedil;": "\u0122",
    "&Gcirc;": "\u011C",
    "&Gcy;": "\u0413",
    "&Gdot;": "\u0120",
    "&Gfr;": "\uD835\uDD0A",
    "&Gg;": "\u22D9",
    "&Gopf;": "\uD835\uDD3E",
    "&GreaterEqual;": "\u2265",
    "&GreaterEqualLess;": "\u22DB",
    "&GreaterFullEqual;": "\u2267",
    "&GreaterGreater;": "\u2AA2",
    "&GreaterLess;": "\u2277",
    "&GreaterSlantEqual;": "\u2A7E",
    "&GreaterTilde;": "\u2273",
    "&Gscr;": "\uD835\uDCA2",
    "&Gt;": "\u226B",
    "&HARDcy;": "\u042A",
    "&Hacek;": "\u02C7",
    "&Hat;": "\u005E",
    "&Hcirc;": "\u0124",
    "&Hfr;": "\u210C",
    "&HilbertSpace;": "\u210B",
    "&Hopf;": "\u210D",
    "&HorizontalLine;": "\u2500",
    "&Hscr;": "\u210B",
    "&Hstrok;": "\u0126",
    "&HumpDownHump;": "\u224E",
    "&HumpEqual;": "\u224F",
    "&IEcy;": "\u0415",
    "&IJlig;": "\u0132",
    "&IOcy;": "\u0401",
    "&Iacute": "\u00CD",
    "&Iacute;": "\u00CD",
    "&Icirc": "\u00CE",
    "&Icirc;": "\u00CE",
    "&Icy;": "\u0418",
    "&Idot;": "\u0130",
    "&Ifr;": "\u2111",
    "&Igrave": "\u00CC",
    "&Igrave;": "\u00CC",
    "&Im;": "\u2111",
    "&Imacr;": "\u012A",
    "&ImaginaryI;": "\u2148",
    "&Implies;": "\u21D2",
    "&Int;": "\u222C",
    "&Integral;": "\u222B",
    "&Intersection;": "\u22C2",
    "&InvisibleComma;": "\u2063",
    "&InvisibleTimes;": "\u2062",
    "&Iogon;": "\u012E",
    "&Iopf;": "\uD835\uDD40",
    "&Iota;": "\u0399",
    "&Iscr;": "\u2110",
    "&Itilde;": "\u0128",
    "&Iukcy;": "\u0406",
    "&Iuml": "\u00CF",
    "&Iuml;": "\u00CF",
    "&Jcirc;": "\u0134",
    "&Jcy;": "\u0419",
    "&Jfr;": "\uD835\uDD0D",
    "&Jopf;": "\uD835\uDD41",
    "&Jscr;": "\uD835\uDCA5",
    "&Jsercy;": "\u0408",
    "&Jukcy;": "\u0404",
    "&KHcy;": "\u0425",
    "&KJcy;": "\u040C",
    "&Kappa;": "\u039A",
    "&Kcedil;": "\u0136",
    "&Kcy;": "\u041A",
    "&Kfr;": "\uD835\uDD0E",
    "&Kopf;": "\uD835\uDD42",
    "&Kscr;": "\uD835\uDCA6",
    "&LJcy;": "\u0409",
    "&LT": "\u003C",
    "&LT;": "\u003C",
    "&Lacute;": "\u0139",
    "&Lambda;": "\u039B",
    "&Lang;": "\u27EA",
    "&Laplacetrf;": "\u2112",
    "&Larr;": "\u219E",
    "&Lcaron;": "\u013D",
    "&Lcedil;": "\u013B",
    "&Lcy;": "\u041B",
    "&LeftAngleBracket;": "\u27E8",
    "&LeftArrow;": "\u2190",
    "&LeftArrowBar;": "\u21E4",
    "&LeftArrowRightArrow;": "\u21C6",
    "&LeftCeiling;": "\u2308",
    "&LeftDoubleBracket;": "\u27E6",
    "&LeftDownTeeVector;": "\u2961",
    "&LeftDownVector;": "\u21C3",
    "&LeftDownVectorBar;": "\u2959",
    "&LeftFloor;": "\u230A",
    "&LeftRightArrow;": "\u2194",
    "&LeftRightVector;": "\u294E",
    "&LeftTee;": "\u22A3",
    "&LeftTeeArrow;": "\u21A4",
    "&LeftTeeVector;": "\u295A",
    "&LeftTriangle;": "\u22B2",
    "&LeftTriangleBar;": "\u29CF",
    "&LeftTriangleEqual;": "\u22B4",
    "&LeftUpDownVector;": "\u2951",
    "&LeftUpTeeVector;": "\u2960",
    "&LeftUpVector;": "\u21BF",
    "&LeftUpVectorBar;": "\u2958",
    "&LeftVector;": "\u21BC",
    "&LeftVectorBar;": "\u2952",
    "&Leftarrow;": "\u21D0",
    "&Leftrightarrow;": "\u21D4",
    "&LessEqualGreater;": "\u22DA",
    "&LessFullEqual;": "\u2266",
    "&LessGreater;": "\u2276",
    "&LessLess;": "\u2AA1",
    "&LessSlantEqual;": "\u2A7D",
    "&LessTilde;": "\u2272",
    "&Lfr;": "\uD835\uDD0F",
    "&Ll;": "\u22D8",
    "&Lleftarrow;": "\u21DA",
    "&Lmidot;": "\u013F",
    "&LongLeftArrow;": "\u27F5",
    "&LongLeftRightArrow;": "\u27F7",
    "&LongRightArrow;": "\u27F6",
    "&Longleftarrow;": "\u27F8",
    "&Longleftrightarrow;": "\u27FA",
    "&Longrightarrow;": "\u27F9",
    "&Lopf;": "\uD835\uDD43",
    "&LowerLeftArrow;": "\u2199",
    "&LowerRightArrow;": "\u2198",
    "&Lscr;": "\u2112",
    "&Lsh;": "\u21B0",
    "&Lstrok;": "\u0141",
    "&Lt;": "\u226A",
    "&Map;": "\u2905",
    "&Mcy;": "\u041C",
    "&MediumSpace;": "\u205F",
    "&Mellintrf;": "\u2133",
    "&Mfr;": "\uD835\uDD10",
    "&MinusPlus;": "\u2213",
    "&Mopf;": "\uD835\uDD44",
    "&Mscr;": "\u2133",
    "&Mu;": "\u039C",
    "&NJcy;": "\u040A",
    "&Nacute;": "\u0143",
    "&Ncaron;": "\u0147",
    "&Ncedil;": "\u0145",
    "&Ncy;": "\u041D",
    "&NegativeMediumSpace;": "\u200B",
    "&NegativeThickSpace;": "\u200B",
    "&NegativeThinSpace;": "\u200B",
    "&NegativeVeryThinSpace;": "\u200B",
    "&NestedGreaterGreater;": "\u226B",
    "&NestedLessLess;": "\u226A",
    "&NewLine;": "\u000A",
    "&Nfr;": "\uD835\uDD11",
    "&NoBreak;": "\u2060",
    "&NonBreakingSpace;": "\u00A0",
    "&Nopf;": "\u2115",
    "&Not;": "\u2AEC",
    "&NotCongruent;": "\u2262",
    "&NotCupCap;": "\u226D",
    "&NotDoubleVerticalBar;": "\u2226",
    "&NotElement;": "\u2209",
    "&NotEqual;": "\u2260",
    "&NotEqualTilde;": "\u2242\u0338",
    "&NotExists;": "\u2204",
    "&NotGreater;": "\u226F",
    "&NotGreaterEqual;": "\u2271",
    "&NotGreaterFullEqual;": "\u2267\u0338",
    "&NotGreaterGreater;": "\u226B\u0338",
    "&NotGreaterLess;": "\u2279",
    "&NotGreaterSlantEqual;": "\u2A7E\u0338",
    "&NotGreaterTilde;": "\u2275",
    "&NotHumpDownHump;": "\u224E\u0338",
    "&NotHumpEqual;": "\u224F\u0338",
    "&NotLeftTriangle;": "\u22EA",
    "&NotLeftTriangleBar;": "\u29CF\u0338",
    "&NotLeftTriangleEqual;": "\u22EC",
    "&NotLess;": "\u226E",
    "&NotLessEqual;": "\u2270",
    "&NotLessGreater;": "\u2278",
    "&NotLessLess;": "\u226A\u0338",
    "&NotLessSlantEqual;": "\u2A7D\u0338",
    "&NotLessTilde;": "\u2274",
    "&NotNestedGreaterGreater;": "\u2AA2\u0338",
    "&NotNestedLessLess;": "\u2AA1\u0338",
    "&NotPrecedes;": "\u2280",
    "&NotPrecedesEqual;": "\u2AAF\u0338",
    "&NotPrecedesSlantEqual;": "\u22E0",
    "&NotReverseElement;": "\u220C",
    "&NotRightTriangle;": "\u22EB",
    "&NotRightTriangleBar;": "\u29D0\u0338",
    "&NotRightTriangleEqual;": "\u22ED",
    "&NotSquareSubset;": "\u228F\u0338",
    "&NotSquareSubsetEqual;": "\u22E2",
    "&NotSquareSuperset;": "\u2290\u0338",
    "&NotSquareSupersetEqual;": "\u22E3",
    "&NotSubset;": "\u2282\u20D2",
    "&NotSubsetEqual;": "\u2288",
    "&NotSucceeds;": "\u2281",
    "&NotSucceedsEqual;": "\u2AB0\u0338",
    "&NotSucceedsSlantEqual;": "\u22E1",
    "&NotSucceedsTilde;": "\u227F\u0338",
    "&NotSuperset;": "\u2283\u20D2",
    "&NotSupersetEqual;": "\u2289",
    "&NotTilde;": "\u2241",
    "&NotTildeEqual;": "\u2244",
    "&NotTildeFullEqual;": "\u2247",
    "&NotTildeTilde;": "\u2249",
    "&NotVerticalBar;": "\u2224",
    "&Nscr;": "\uD835\uDCA9",
    "&Ntilde": "\u00D1",
    "&Ntilde;": "\u00D1",
    "&Nu;": "\u039D",
    "&OElig;": "\u0152",
    "&Oacute": "\u00D3",
    "&Oacute;": "\u00D3",
    "&Ocirc": "\u00D4",
    "&Ocirc;": "\u00D4",
    "&Ocy;": "\u041E",
    "&Odblac;": "\u0150",
    "&Ofr;": "\uD835\uDD12",
    "&Ograve": "\u00D2",
    "&Ograve;": "\u00D2",
    "&Omacr;": "\u014C",
    "&Omega;": "\u03A9",
    "&Omicron;": "\u039F",
    "&Oopf;": "\uD835\uDD46",
    "&OpenCurlyDoubleQuote;": "\u201C",
    "&OpenCurlyQuote;": "\u2018",
    "&Or;": "\u2A54",
    "&Oscr;": "\uD835\uDCAA",
    "&Oslash": "\u00D8",
    "&Oslash;": "\u00D8",
    "&Otilde": "\u00D5",
    "&Otilde;": "\u00D5",
    "&Otimes;": "\u2A37",
    "&Ouml": "\u00D6",
    "&Ouml;": "\u00D6",
    "&OverBar;": "\u203E",
    "&OverBrace;": "\u23DE",
    "&OverBracket;": "\u23B4",
    "&OverParenthesis;": "\u23DC",
    "&PartialD;": "\u2202",
    "&Pcy;": "\u041F",
    "&Pfr;": "\uD835\uDD13",
    "&Phi;": "\u03A6",
    "&Pi;": "\u03A0",
    "&PlusMinus;": "\u00B1",
    "&Poincareplane;": "\u210C",
    "&Popf;": "\u2119",
    "&Pr;": "\u2ABB",
    "&Precedes;": "\u227A",
    "&PrecedesEqual;": "\u2AAF",
    "&PrecedesSlantEqual;": "\u227C",
    "&PrecedesTilde;": "\u227E",
    "&Prime;": "\u2033",
    "&Product;": "\u220F",
    "&Proportion;": "\u2237",
    "&Proportional;": "\u221D",
    "&Pscr;": "\uD835\uDCAB",
    "&Psi;": "\u03A8",
    "&QUOT": "\u0022",
    "&QUOT;": "\u0022",
    "&Qfr;": "\uD835\uDD14",
    "&Qopf;": "\u211A",
    "&Qscr;": "\uD835\uDCAC",
    "&RBarr;": "\u2910",
    "&REG": "\u00AE",
    "&REG;": "\u00AE",
    "&Racute;": "\u0154",
    "&Rang;": "\u27EB",
    "&Rarr;": "\u21A0",
    "&Rarrtl;": "\u2916",
    "&Rcaron;": "\u0158",
    "&Rcedil;": "\u0156",
    "&Rcy;": "\u0420",
    "&Re;": "\u211C",
    "&ReverseElement;": "\u220B",
    "&ReverseEquilibrium;": "\u21CB",
    "&ReverseUpEquilibrium;": "\u296F",
    "&Rfr;": "\u211C",
    "&Rho;": "\u03A1",
    "&RightAngleBracket;": "\u27E9",
    "&RightArrow;": "\u2192",
    "&RightArrowBar;": "\u21E5",
    "&RightArrowLeftArrow;": "\u21C4",
    "&RightCeiling;": "\u2309",
    "&RightDoubleBracket;": "\u27E7",
    "&RightDownTeeVector;": "\u295D",
    "&RightDownVector;": "\u21C2",
    "&RightDownVectorBar;": "\u2955",
    "&RightFloor;": "\u230B",
    "&RightTee;": "\u22A2",
    "&RightTeeArrow;": "\u21A6",
    "&RightTeeVector;": "\u295B",
    "&RightTriangle;": "\u22B3",
    "&RightTriangleBar;": "\u29D0",
    "&RightTriangleEqual;": "\u22B5",
    "&RightUpDownVector;": "\u294F",
    "&RightUpTeeVector;": "\u295C",
    "&RightUpVector;": "\u21BE",
    "&RightUpVectorBar;": "\u2954",
    "&RightVector;": "\u21C0",
    "&RightVectorBar;": "\u2953",
    "&Rightarrow;": "\u21D2",
    "&Ropf;": "\u211D",
    "&RoundImplies;": "\u2970",
    "&Rrightarrow;": "\u21DB",
    "&Rscr;": "\u211B",
    "&Rsh;": "\u21B1",
    "&RuleDelayed;": "\u29F4",
    "&SHCHcy;": "\u0429",
    "&SHcy;": "\u0428",
    "&SOFTcy;": "\u042C",
    "&Sacute;": "\u015A",
    "&Sc;": "\u2ABC",
    "&Scaron;": "\u0160",
    "&Scedil;": "\u015E",
    "&Scirc;": "\u015C",
    "&Scy;": "\u0421",
    "&Sfr;": "\uD835\uDD16",
    "&ShortDownArrow;": "\u2193",
    "&ShortLeftArrow;": "\u2190",
    "&ShortRightArrow;": "\u2192",
    "&ShortUpArrow;": "\u2191",
    "&Sigma;": "\u03A3",
    "&SmallCircle;": "\u2218",
    "&Sopf;": "\uD835\uDD4A",
    "&Sqrt;": "\u221A",
    "&Square;": "\u25A1",
    "&SquareIntersection;": "\u2293",
    "&SquareSubset;": "\u228F",
    "&SquareSubsetEqual;": "\u2291",
    "&SquareSuperset;": "\u2290",
    "&SquareSupersetEqual;": "\u2292",
    "&SquareUnion;": "\u2294",
    "&Sscr;": "\uD835\uDCAE",
    "&Star;": "\u22C6",
    "&Sub;": "\u22D0",
    "&Subset;": "\u22D0",
    "&SubsetEqual;": "\u2286",
    "&Succeeds;": "\u227B",
    "&SucceedsEqual;": "\u2AB0",
    "&SucceedsSlantEqual;": "\u227D",
    "&SucceedsTilde;": "\u227F",
    "&SuchThat;": "\u220B",
    "&Sum;": "\u2211",
    "&Sup;": "\u22D1",
    "&Superset;": "\u2283",
    "&SupersetEqual;": "\u2287",
    "&Supset;": "\u22D1",
    "&THORN": "\u00DE",
    "&THORN;": "\u00DE",
    "&TRADE;": "\u2122",
    "&TSHcy;": "\u040B",
    "&TScy;": "\u0426",
    "&Tab;": "\u0009",
    "&Tau;": "\u03A4",
    "&Tcaron;": "\u0164",
    "&Tcedil;": "\u0162",
    "&Tcy;": "\u0422",
    "&Tfr;": "\uD835\uDD17",
    "&Therefore;": "\u2234",
    "&Theta;": "\u0398",
    "&ThickSpace;": "\u205F\u200A",
    "&ThinSpace;": "\u2009",
    "&Tilde;": "\u223C",
    "&TildeEqual;": "\u2243",
    "&TildeFullEqual;": "\u2245",
    "&TildeTilde;": "\u2248",
    "&Topf;": "\uD835\uDD4B",
    "&TripleDot;": "\u20DB",
    "&Tscr;": "\uD835\uDCAF",
    "&Tstrok;": "\u0166",
    "&Uacute": "\u00DA",
    "&Uacute;": "\u00DA",
    "&Uarr;": "\u219F",
    "&Uarrocir;": "\u2949",
    "&Ubrcy;": "\u040E",
    "&Ubreve;": "\u016C",
    "&Ucirc": "\u00DB",
    "&Ucirc;": "\u00DB",
    "&Ucy;": "\u0423",
    "&Udblac;": "\u0170",
    "&Ufr;": "\uD835\uDD18",
    "&Ugrave": "\u00D9",
    "&Ugrave;": "\u00D9",
    "&Umacr;": "\u016A",
    "&UnderBar;": "\u005F",
    "&UnderBrace;": "\u23DF",
    "&UnderBracket;": "\u23B5",
    "&UnderParenthesis;": "\u23DD",
    "&Union;": "\u22C3",
    "&UnionPlus;": "\u228E",
    "&Uogon;": "\u0172",
    "&Uopf;": "\uD835\uDD4C",
    "&UpArrow;": "\u2191",
    "&UpArrowBar;": "\u2912",
    "&UpArrowDownArrow;": "\u21C5",
    "&UpDownArrow;": "\u2195",
    "&UpEquilibrium;": "\u296E",
    "&UpTee;": "\u22A5",
    "&UpTeeArrow;": "\u21A5",
    "&Uparrow;": "\u21D1",
    "&Updownarrow;": "\u21D5",
    "&UpperLeftArrow;": "\u2196",
    "&UpperRightArrow;": "\u2197",
    "&Upsi;": "\u03D2",
    "&Upsilon;": "\u03A5",
    "&Uring;": "\u016E",
    "&Uscr;": "\uD835\uDCB0",
    "&Utilde;": "\u0168",
    "&Uuml": "\u00DC",
    "&Uuml;": "\u00DC",
    "&VDash;": "\u22AB",
    "&Vbar;": "\u2AEB",
    "&Vcy;": "\u0412",
    "&Vdash;": "\u22A9",
    "&Vdashl;": "\u2AE6",
    "&Vee;": "\u22C1",
    "&Verbar;": "\u2016",
    "&Vert;": "\u2016",
    "&VerticalBar;": "\u2223",
    "&VerticalLine;": "\u007C",
    "&VerticalSeparator;": "\u2758",
    "&VerticalTilde;": "\u2240",
    "&VeryThinSpace;": "\u200A",
    "&Vfr;": "\uD835\uDD19",
    "&Vopf;": "\uD835\uDD4D",
    "&Vscr;": "\uD835\uDCB1",
    "&Vvdash;": "\u22AA",
    "&Wcirc;": "\u0174",
    "&Wedge;": "\u22C0",
    "&Wfr;": "\uD835\uDD1A",
    "&Wopf;": "\uD835\uDD4E",
    "&Wscr;": "\uD835\uDCB2",
    "&Xfr;": "\uD835\uDD1B",
    "&Xi;": "\u039E",
    "&Xopf;": "\uD835\uDD4F",
    "&Xscr;": "\uD835\uDCB3",
    "&YAcy;": "\u042F",
    "&YIcy;": "\u0407",
    "&YUcy;": "\u042E",
    "&Yacute": "\u00DD",
    "&Yacute;": "\u00DD",
    "&Ycirc;": "\u0176",
    "&Ycy;": "\u042B",
    "&Yfr;": "\uD835\uDD1C",
    "&Yopf;": "\uD835\uDD50",
    "&Yscr;": "\uD835\uDCB4",
    "&Yuml;": "\u0178",
    "&ZHcy;": "\u0416",
    "&Zacute;": "\u0179",
    "&Zcaron;": "\u017D",
    "&Zcy;": "\u0417",
    "&Zdot;": "\u017B",
    "&ZeroWidthSpace;": "\u200B",
    "&Zeta;": "\u0396",
    "&Zfr;": "\u2128",
    "&Zopf;": "\u2124",
    "&Zscr;": "\uD835\uDCB5",
    "&aacute": "\u00E1",
    "&aacute;": "\u00E1",
    "&abreve;": "\u0103",
    "&ac;": "\u223E",
    "&acE;": "\u223E\u0333",
    "&acd;": "\u223F",
    "&acirc": "\u00E2",
    "&acirc;": "\u00E2",
    "&acute": "\u00B4",
    "&acute;": "\u00B4",
    "&acy;": "\u0430",
    "&aelig": "\u00E6",
    "&aelig;": "\u00E6",
    "&af;": "\u2061",
    "&afr;": "\uD835\uDD1E",
    "&agrave": "\u00E0",
    "&agrave;": "\u00E0",
    "&alefsym;": "\u2135",
    "&aleph;": "\u2135",
    "&alpha;": "\u03B1",
    "&amacr;": "\u0101",
    "&amalg;": "\u2A3F",
    "&amp": "\u0026",
    "&amp;": "\u0026",
    "&and;": "\u2227",
    "&andand;": "\u2A55",
    "&andd;": "\u2A5C",
    "&andslope;": "\u2A58",
    "&andv;": "\u2A5A",
    "&ang;": "\u2220",
    "&ange;": "\u29A4",
    "&angle;": "\u2220",
    "&angmsd;": "\u2221",
    "&angmsdaa;": "\u29A8",
    "&angmsdab;": "\u29A9",
    "&angmsdac;": "\u29AA",
    "&angmsdad;": "\u29AB",
    "&angmsdae;": "\u29AC",
    "&angmsdaf;": "\u29AD",
    "&angmsdag;": "\u29AE",
    "&angmsdah;": "\u29AF",
    "&angrt;": "\u221F",
    "&angrtvb;": "\u22BE",
    "&angrtvbd;": "\u299D",
    "&angsph;": "\u2222",
    "&angst;": "\u00C5",
    "&angzarr;": "\u237C",
    "&aogon;": "\u0105",
    "&aopf;": "\uD835\uDD52",
    "&ap;": "\u2248",
    "&apE;": "\u2A70",
    "&apacir;": "\u2A6F",
    "&ape;": "\u224A",
    "&apid;": "\u224B",
    "&apos;": "\u0027",
    "&approx;": "\u2248",
    "&approxeq;": "\u224A",
    "&aring": "\u00E5",
    "&aring;": "\u00E5",
    "&ascr;": "\uD835\uDCB6",
    "&ast;": "\u002A",
    "&asymp;": "\u2248",
    "&asympeq;": "\u224D",
    "&atilde": "\u00E3",
    "&atilde;": "\u00E3",
    "&auml": "\u00E4",
    "&auml;": "\u00E4",
    "&awconint;": "\u2233",
    "&awint;": "\u2A11",
    "&bNot;": "\u2AED",
    "&backcong;": "\u224C",
    "&backepsilon;": "\u03F6",
    "&backprime;": "\u2035",
    "&backsim;": "\u223D",
    "&backsimeq;": "\u22CD",
    "&barvee;": "\u22BD",
    "&barwed;": "\u2305",
    "&barwedge;": "\u2305",
    "&bbrk;": "\u23B5",
    "&bbrktbrk;": "\u23B6",
    "&bcong;": "\u224C",
    "&bcy;": "\u0431",
    "&bdquo;": "\u201E",
    "&becaus;": "\u2235",
    "&because;": "\u2235",
    "&bemptyv;": "\u29B0",
    "&bepsi;": "\u03F6",
    "&bernou;": "\u212C",
    "&beta;": "\u03B2",
    "&beth;": "\u2136",
    "&between;": "\u226C",
    "&bfr;": "\uD835\uDD1F",
    "&bigcap;": "\u22C2",
    "&bigcirc;": "\u25EF",
    "&bigcup;": "\u22C3",
    "&bigodot;": "\u2A00",
    "&bigoplus;": "\u2A01",
    "&bigotimes;": "\u2A02",
    "&bigsqcup;": "\u2A06",
    "&bigstar;": "\u2605",
    "&bigtriangledown;": "\u25BD",
    "&bigtriangleup;": "\u25B3",
    "&biguplus;": "\u2A04",
    "&bigvee;": "\u22C1",
    "&bigwedge;": "\u22C0",
    "&bkarow;": "\u290D",
    "&blacklozenge;": "\u29EB",
    "&blacksquare;": "\u25AA",
    "&blacktriangle;": "\u25B4",
    "&blacktriangledown;": "\u25BE",
    "&blacktriangleleft;": "\u25C2",
    "&blacktriangleright;": "\u25B8",
    "&blank;": "\u2423",
    "&blk12;": "\u2592",
    "&blk14;": "\u2591",
    "&blk34;": "\u2593",
    "&block;": "\u2588",
    "&bne;": "\u003D\u20E5",
    "&bnequiv;": "\u2261\u20E5",
    "&bnot;": "\u2310",
    "&bopf;": "\uD835\uDD53",
    "&bot;": "\u22A5",
    "&bottom;": "\u22A5",
    "&bowtie;": "\u22C8",
    "&boxDL;": "\u2557",
    "&boxDR;": "\u2554",
    "&boxDl;": "\u2556",
    "&boxDr;": "\u2553",
    "&boxH;": "\u2550",
    "&boxHD;": "\u2566",
    "&boxHU;": "\u2569",
    "&boxHd;": "\u2564",
    "&boxHu;": "\u2567",
    "&boxUL;": "\u255D",
    "&boxUR;": "\u255A",
    "&boxUl;": "\u255C",
    "&boxUr;": "\u2559",
    "&boxV;": "\u2551",
    "&boxVH;": "\u256C",
    "&boxVL;": "\u2563",
    "&boxVR;": "\u2560",
    "&boxVh;": "\u256B",
    "&boxVl;": "\u2562",
    "&boxVr;": "\u255F",
    "&boxbox;": "\u29C9",
    "&boxdL;": "\u2555",
    "&boxdR;": "\u2552",
    "&boxdl;": "\u2510",
    "&boxdr;": "\u250C",
    "&boxh;": "\u2500",
    "&boxhD;": "\u2565",
    "&boxhU;": "\u2568",
    "&boxhd;": "\u252C",
    "&boxhu;": "\u2534",
    "&boxminus;": "\u229F",
    "&boxplus;": "\u229E",
    "&boxtimes;": "\u22A0",
    "&boxuL;": "\u255B",
    "&boxuR;": "\u2558",
    "&boxul;": "\u2518",
    "&boxur;": "\u2514",
    "&boxv;": "\u2502",
    "&boxvH;": "\u256A",
    "&boxvL;": "\u2561",
    "&boxvR;": "\u255E",
    "&boxvh;": "\u253C",
    "&boxvl;": "\u2524",
    "&boxvr;": "\u251C",
    "&bprime;": "\u2035",
    "&breve;": "\u02D8",
    "&brvbar": "\u00A6",
    "&brvbar;": "\u00A6",
    "&bscr;": "\uD835\uDCB7",
    "&bsemi;": "\u204F",
    "&bsim;": "\u223D",
    "&bsime;": "\u22CD",
    "&bsol;": "\u005C",
    "&bsolb;": "\u29C5",
    "&bsolhsub;": "\u27C8",
    "&bull;": "\u2022",
    "&bullet;": "\u2022",
    "&bump;": "\u224E",
    "&bumpE;": "\u2AAE",
    "&bumpe;": "\u224F",
    "&bumpeq;": "\u224F",
    "&cacute;": "\u0107",
    "&cap;": "\u2229",
    "&capand;": "\u2A44",
    "&capbrcup;": "\u2A49",
    "&capcap;": "\u2A4B",
    "&capcup;": "\u2A47",
    "&capdot;": "\u2A40",
    "&caps;": "\u2229\uFE00",
    "&caret;": "\u2041",
    "&caron;": "\u02C7",
    "&ccaps;": "\u2A4D",
    "&ccaron;": "\u010D",
    "&ccedil": "\u00E7",
    "&ccedil;": "\u00E7",
    "&ccirc;": "\u0109",
    "&ccups;": "\u2A4C",
    "&ccupssm;": "\u2A50",
    "&cdot;": "\u010B",
    "&cedil": "\u00B8",
    "&cedil;": "\u00B8",
    "&cemptyv;": "\u29B2",
    "&cent": "\u00A2",
    "&cent;": "\u00A2",
    "&centerdot;": "\u00B7",
    "&cfr;": "\uD835\uDD20",
    "&chcy;": "\u0447",
    "&check;": "\u2713",
    "&checkmark;": "\u2713",
    "&chi;": "\u03C7",
    "&cir;": "\u25CB",
    "&cirE;": "\u29C3",
    "&circ;": "\u02C6",
    "&circeq;": "\u2257",
    "&circlearrowleft;": "\u21BA",
    "&circlearrowright;": "\u21BB",
    "&circledR;": "\u00AE",
    "&circledS;": "\u24C8",
    "&circledast;": "\u229B",
    "&circledcirc;": "\u229A",
    "&circleddash;": "\u229D",
    "&cire;": "\u2257",
    "&cirfnint;": "\u2A10",
    "&cirmid;": "\u2AEF",
    "&cirscir;": "\u29C2",
    "&clubs;": "\u2663",
    "&clubsuit;": "\u2663",
    "&colon;": "\u003A",
    "&colone;": "\u2254",
    "&coloneq;": "\u2254",
    "&comma;": "\u002C",
    "&commat;": "\u0040",
    "&comp;": "\u2201",
    "&compfn;": "\u2218",
    "&complement;": "\u2201",
    "&complexes;": "\u2102",
    "&cong;": "\u2245",
    "&congdot;": "\u2A6D",
    "&conint;": "\u222E",
    "&copf;": "\uD835\uDD54",
    "&coprod;": "\u2210",
    "&copy": "\u00A9",
    "&copy;": "\u00A9",
    "&copysr;": "\u2117",
    "&crarr;": "\u21B5",
    "&cross;": "\u2717",
    "&cscr;": "\uD835\uDCB8",
    "&csub;": "\u2ACF",
    "&csube;": "\u2AD1",
    "&csup;": "\u2AD0",
    "&csupe;": "\u2AD2",
    "&ctdot;": "\u22EF",
    "&cudarrl;": "\u2938",
    "&cudarrr;": "\u2935",
    "&cuepr;": "\u22DE",
    "&cuesc;": "\u22DF",
    "&cularr;": "\u21B6",
    "&cularrp;": "\u293D",
    "&cup;": "\u222A",
    "&cupbrcap;": "\u2A48",
    "&cupcap;": "\u2A46",
    "&cupcup;": "\u2A4A",
    "&cupdot;": "\u228D",
    "&cupor;": "\u2A45",
    "&cups;": "\u222A\uFE00",
    "&curarr;": "\u21B7",
    "&curarrm;": "\u293C",
    "&curlyeqprec;": "\u22DE",
    "&curlyeqsucc;": "\u22DF",
    "&curlyvee;": "\u22CE",
    "&curlywedge;": "\u22CF",
    "&curren": "\u00A4",
    "&curren;": "\u00A4",
    "&curvearrowleft;": "\u21B6",
    "&curvearrowright;": "\u21B7",
    "&cuvee;": "\u22CE",
    "&cuwed;": "\u22CF",
    "&cwconint;": "\u2232",
    "&cwint;": "\u2231",
    "&cylcty;": "\u232D",
    "&dArr;": "\u21D3",
    "&dHar;": "\u2965",
    "&dagger;": "\u2020",
    "&daleth;": "\u2138",
    "&darr;": "\u2193",
    "&dash;": "\u2010",
    "&dashv;": "\u22A3",
    "&dbkarow;": "\u290F",
    "&dblac;": "\u02DD",
    "&dcaron;": "\u010F",
    "&dcy;": "\u0434",
    "&dd;": "\u2146",
    "&ddagger;": "\u2021",
    "&ddarr;": "\u21CA",
    "&ddotseq;": "\u2A77",
    "&deg": "\u00B0",
    "&deg;": "\u00B0",
    "&delta;": "\u03B4",
    "&demptyv;": "\u29B1",
    "&dfisht;": "\u297F",
    "&dfr;": "\uD835\uDD21",
    "&dharl;": "\u21C3",
    "&dharr;": "\u21C2",
    "&diam;": "\u22C4",
    "&diamond;": "\u22C4",
    "&diamondsuit;": "\u2666",
    "&diams;": "\u2666",
    "&die;": "\u00A8",
    "&digamma;": "\u03DD",
    "&disin;": "\u22F2",
    "&div;": "\u00F7",
    "&divide": "\u00F7",
    "&divide;": "\u00F7",
    "&divideontimes;": "\u22C7",
    "&divonx;": "\u22C7",
    "&djcy;": "\u0452",
    "&dlcorn;": "\u231E",
    "&dlcrop;": "\u230D",
    "&dollar;": "\u0024",
    "&dopf;": "\uD835\uDD55",
    "&dot;": "\u02D9",
    "&doteq;": "\u2250",
    "&doteqdot;": "\u2251",
    "&dotminus;": "\u2238",
    "&dotplus;": "\u2214",
    "&dotsquare;": "\u22A1",
    "&doublebarwedge;": "\u2306",
    "&downarrow;": "\u2193",
    "&downdownarrows;": "\u21CA",
    "&downharpoonleft;": "\u21C3",
    "&downharpoonright;": "\u21C2",
    "&drbkarow;": "\u2910",
    "&drcorn;": "\u231F",
    "&drcrop;": "\u230C",
    "&dscr;": "\uD835\uDCB9",
    "&dscy;": "\u0455",
    "&dsol;": "\u29F6",
    "&dstrok;": "\u0111",
    "&dtdot;": "\u22F1",
    "&dtri;": "\u25BF",
    "&dtrif;": "\u25BE",
    "&duarr;": "\u21F5",
    "&duhar;": "\u296F",
    "&dwangle;": "\u29A6",
    "&dzcy;": "\u045F",
    "&dzigrarr;": "\u27FF",
    "&eDDot;": "\u2A77",
    "&eDot;": "\u2251",
    "&eacute": "\u00E9",
    "&eacute;": "\u00E9",
    "&easter;": "\u2A6E",
    "&ecaron;": "\u011B",
    "&ecir;": "\u2256",
    "&ecirc": "\u00EA",
    "&ecirc;": "\u00EA",
    "&ecolon;": "\u2255",
    "&ecy;": "\u044D",
    "&edot;": "\u0117",
    "&ee;": "\u2147",
    "&efDot;": "\u2252",
    "&efr;": "\uD835\uDD22",
    "&eg;": "\u2A9A",
    "&egrave": "\u00E8",
    "&egrave;": "\u00E8",
    "&egs;": "\u2A96",
    "&egsdot;": "\u2A98",
    "&el;": "\u2A99",
    "&elinters;": "\u23E7",
    "&ell;": "\u2113",
    "&els;": "\u2A95",
    "&elsdot;": "\u2A97",
    "&emacr;": "\u0113",
    "&empty;": "\u2205",
    "&emptyset;": "\u2205",
    "&emptyv;": "\u2205",
    "&emsp13;": "\u2004",
    "&emsp14;": "\u2005",
    "&emsp;": "\u2003",
    "&eng;": "\u014B",
    "&ensp;": "\u2002",
    "&eogon;": "\u0119",
    "&eopf;": "\uD835\uDD56",
    "&epar;": "\u22D5",
    "&eparsl;": "\u29E3",
    "&eplus;": "\u2A71",
    "&epsi;": "\u03B5",
    "&epsilon;": "\u03B5",
    "&epsiv;": "\u03F5",
    "&eqcirc;": "\u2256",
    "&eqcolon;": "\u2255",
    "&eqsim;": "\u2242",
    "&eqslantgtr;": "\u2A96",
    "&eqslantless;": "\u2A95",
    "&equals;": "\u003D",
    "&equest;": "\u225F",
    "&equiv;": "\u2261",
    "&equivDD;": "\u2A78",
    "&eqvparsl;": "\u29E5",
    "&erDot;": "\u2253",
    "&erarr;": "\u2971",
    "&escr;": "\u212F",
    "&esdot;": "\u2250",
    "&esim;": "\u2242",
    "&eta;": "\u03B7",
    "&eth": "\u00F0",
    "&eth;": "\u00F0",
    "&euml": "\u00EB",
    "&euml;": "\u00EB",
    "&euro;": "\u20AC",
    "&excl;": "\u0021",
    "&exist;": "\u2203",
    "&expectation;": "\u2130",
    "&exponentiale;": "\u2147",
    "&fallingdotseq;": "\u2252",
    "&fcy;": "\u0444",
    "&female;": "\u2640",
    "&ffilig;": "\uFB03",
    "&fflig;": "\uFB00",
    "&ffllig;": "\uFB04",
    "&ffr;": "\uD835\uDD23",
    "&filig;": "\uFB01",
    "&fjlig;": "\u0066\u006A",
    "&flat;": "\u266D",
    "&fllig;": "\uFB02",
    "&fltns;": "\u25B1",
    "&fnof;": "\u0192",
    "&fopf;": "\uD835\uDD57",
    "&forall;": "\u2200",
    "&fork;": "\u22D4",
    "&forkv;": "\u2AD9",
    "&fpartint;": "\u2A0D",
    "&frac12": "\u00BD",
    "&frac12;": "\u00BD",
    "&frac13;": "\u2153",
    "&frac14": "\u00BC",
    "&frac14;": "\u00BC",
    "&frac15;": "\u2155",
    "&frac16;": "\u2159",
    "&frac18;": "\u215B",
    "&frac23;": "\u2154",
    "&frac25;": "\u2156",
    "&frac34": "\u00BE",
    "&frac34;": "\u00BE",
    "&frac35;": "\u2157",
    "&frac38;": "\u215C",
    "&frac45;": "\u2158",
    "&frac56;": "\u215A",
    "&frac58;": "\u215D",
    "&frac78;": "\u215E",
    "&frasl;": "\u2044",
    "&frown;": "\u2322",
    "&fscr;": "\uD835\uDCBB",
    "&gE;": "\u2267",
    "&gEl;": "\u2A8C",
    "&gacute;": "\u01F5",
    "&gamma;": "\u03B3",
    "&gammad;": "\u03DD",
    "&gap;": "\u2A86",
    "&gbreve;": "\u011F",
    "&gcirc;": "\u011D",
    "&gcy;": "\u0433",
    "&gdot;": "\u0121",
    "&ge;": "\u2265",
    "&gel;": "\u22DB",
    "&geq;": "\u2265",
    "&geqq;": "\u2267",
    "&geqslant;": "\u2A7E",
    "&ges;": "\u2A7E",
    "&gescc;": "\u2AA9",
    "&gesdot;": "\u2A80",
    "&gesdoto;": "\u2A82",
    "&gesdotol;": "\u2A84",
    "&gesl;": "\u22DB\uFE00",
    "&gesles;": "\u2A94",
    "&gfr;": "\uD835\uDD24",
    "&gg;": "\u226B",
    "&ggg;": "\u22D9",
    "&gimel;": "\u2137",
    "&gjcy;": "\u0453",
    "&gl;": "\u2277",
    "&glE;": "\u2A92",
    "&gla;": "\u2AA5",
    "&glj;": "\u2AA4",
    "&gnE;": "\u2269",
    "&gnap;": "\u2A8A",
    "&gnapprox;": "\u2A8A",
    "&gne;": "\u2A88",
    "&gneq;": "\u2A88",
    "&gneqq;": "\u2269",
    "&gnsim;": "\u22E7",
    "&gopf;": "\uD835\uDD58",
    "&grave;": "\u0060",
    "&gscr;": "\u210A",
    "&gsim;": "\u2273",
    "&gsime;": "\u2A8E",
    "&gsiml;": "\u2A90",
    "&gt": "\u003E",
    "&gt;": "\u003E",
    "&gtcc;": "\u2AA7",
    "&gtcir;": "\u2A7A",
    "&gtdot;": "\u22D7",
    "&gtlPar;": "\u2995",
    "&gtquest;": "\u2A7C",
    "&gtrapprox;": "\u2A86",
    "&gtrarr;": "\u2978",
    "&gtrdot;": "\u22D7",
    "&gtreqless;": "\u22DB",
    "&gtreqqless;": "\u2A8C",
    "&gtrless;": "\u2277",
    "&gtrsim;": "\u2273",
    "&gvertneqq;": "\u2269\uFE00",
    "&gvnE;": "\u2269\uFE00",
    "&hArr;": "\u21D4",
    "&hairsp;": "\u200A",
    "&half;": "\u00BD",
    "&hamilt;": "\u210B",
    "&hardcy;": "\u044A",
    "&harr;": "\u2194",
    "&harrcir;": "\u2948",
    "&harrw;": "\u21AD",
    "&hbar;": "\u210F",
    "&hcirc;": "\u0125",
    "&hearts;": "\u2665",
    "&heartsuit;": "\u2665",
    "&hellip;": "\u2026",
    "&hercon;": "\u22B9",
    "&hfr;": "\uD835\uDD25",
    "&hksearow;": "\u2925",
    "&hkswarow;": "\u2926",
    "&hoarr;": "\u21FF",
    "&homtht;": "\u223B",
    "&hookleftarrow;": "\u21A9",
    "&hookrightarrow;": "\u21AA",
    "&hopf;": "\uD835\uDD59",
    "&horbar;": "\u2015",
    "&hscr;": "\uD835\uDCBD",
    "&hslash;": "\u210F",
    "&hstrok;": "\u0127",
    "&hybull;": "\u2043",
    "&hyphen;": "\u2010",
    "&iacute": "\u00ED",
    "&iacute;": "\u00ED",
    "&ic;": "\u2063",
    "&icirc": "\u00EE",
    "&icirc;": "\u00EE",
    "&icy;": "\u0438",
    "&iecy;": "\u0435",
    "&iexcl": "\u00A1",
    "&iexcl;": "\u00A1",
    "&iff;": "\u21D4",
    "&ifr;": "\uD835\uDD26",
    "&igrave": "\u00EC",
    "&igrave;": "\u00EC",
    "&ii;": "\u2148",
    "&iiiint;": "\u2A0C",
    "&iiint;": "\u222D",
    "&iinfin;": "\u29DC",
    "&iiota;": "\u2129",
    "&ijlig;": "\u0133",
    "&imacr;": "\u012B",
    "&image;": "\u2111",
    "&imagline;": "\u2110",
    "&imagpart;": "\u2111",
    "&imath;": "\u0131",
    "&imof;": "\u22B7",
    "&imped;": "\u01B5",
    "&in;": "\u2208",
    "&incare;": "\u2105",
    "&infin;": "\u221E",
    "&infintie;": "\u29DD",
    "&inodot;": "\u0131",
    "&int;": "\u222B",
    "&intcal;": "\u22BA",
    "&integers;": "\u2124",
    "&intercal;": "\u22BA",
    "&intlarhk;": "\u2A17",
    "&intprod;": "\u2A3C",
    "&iocy;": "\u0451",
    "&iogon;": "\u012F",
    "&iopf;": "\uD835\uDD5A",
    "&iota;": "\u03B9",
    "&iprod;": "\u2A3C",
    "&iquest": "\u00BF",
    "&iquest;": "\u00BF",
    "&iscr;": "\uD835\uDCBE",
    "&isin;": "\u2208",
    "&isinE;": "\u22F9",
    "&isindot;": "\u22F5",
    "&isins;": "\u22F4",
    "&isinsv;": "\u22F3",
    "&isinv;": "\u2208",
    "&it;": "\u2062",
    "&itilde;": "\u0129",
    "&iukcy;": "\u0456",
    "&iuml": "\u00EF",
    "&iuml;": "\u00EF",
    "&jcirc;": "\u0135",
    "&jcy;": "\u0439",
    "&jfr;": "\uD835\uDD27",
    "&jmath;": "\u0237",
    "&jopf;": "\uD835\uDD5B",
    "&jscr;": "\uD835\uDCBF",
    "&jsercy;": "\u0458",
    "&jukcy;": "\u0454",
    "&kappa;": "\u03BA",
    "&kappav;": "\u03F0",
    "&kcedil;": "\u0137",
    "&kcy;": "\u043A",
    "&kfr;": "\uD835\uDD28",
    "&kgreen;": "\u0138",
    "&khcy;": "\u0445",
    "&kjcy;": "\u045C",
    "&kopf;": "\uD835\uDD5C",
    "&kscr;": "\uD835\uDCC0",
    "&lAarr;": "\u21DA",
    "&lArr;": "\u21D0",
    "&lAtail;": "\u291B",
    "&lBarr;": "\u290E",
    "&lE;": "\u2266",
    "&lEg;": "\u2A8B",
    "&lHar;": "\u2962",
    "&lacute;": "\u013A",
    "&laemptyv;": "\u29B4",
    "&lagran;": "\u2112",
    "&lambda;": "\u03BB",
    "&lang;": "\u27E8",
    "&langd;": "\u2991",
    "&langle;": "\u27E8",
    "&lap;": "\u2A85",
    "&laquo": "\u00AB",
    "&laquo;": "\u00AB",
    "&larr;": "\u2190",
    "&larrb;": "\u21E4",
    "&larrbfs;": "\u291F",
    "&larrfs;": "\u291D",
    "&larrhk;": "\u21A9",
    "&larrlp;": "\u21AB",
    "&larrpl;": "\u2939",
    "&larrsim;": "\u2973",
    "&larrtl;": "\u21A2",
    "&lat;": "\u2AAB",
    "&latail;": "\u2919",
    "&late;": "\u2AAD",
    "&lates;": "\u2AAD\uFE00",
    "&lbarr;": "\u290C",
    "&lbbrk;": "\u2772",
    "&lbrace;": "\u007B",
    "&lbrack;": "\u005B",
    "&lbrke;": "\u298B",
    "&lbrksld;": "\u298F",
    "&lbrkslu;": "\u298D",
    "&lcaron;": "\u013E",
    "&lcedil;": "\u013C",
    "&lceil;": "\u2308",
    "&lcub;": "\u007B",
    "&lcy;": "\u043B",
    "&ldca;": "\u2936",
    "&ldquo;": "\u201C",
    "&ldquor;": "\u201E",
    "&ldrdhar;": "\u2967",
    "&ldrushar;": "\u294B",
    "&ldsh;": "\u21B2",
    "&le;": "\u2264",
    "&leftarrow;": "\u2190",
    "&leftarrowtail;": "\u21A2",
    "&leftharpoondown;": "\u21BD",
    "&leftharpoonup;": "\u21BC",
    "&leftleftarrows;": "\u21C7",
    "&leftrightarrow;": "\u2194",
    "&leftrightarrows;": "\u21C6",
    "&leftrightharpoons;": "\u21CB",
    "&leftrightsquigarrow;": "\u21AD",
    "&leftthreetimes;": "\u22CB",
    "&leg;": "\u22DA",
    "&leq;": "\u2264",
    "&leqq;": "\u2266",
    "&leqslant;": "\u2A7D",
    "&les;": "\u2A7D",
    "&lescc;": "\u2AA8",
    "&lesdot;": "\u2A7F",
    "&lesdoto;": "\u2A81",
    "&lesdotor;": "\u2A83",
    "&lesg;": "\u22DA\uFE00",
    "&lesges;": "\u2A93",
    "&lessapprox;": "\u2A85",
    "&lessdot;": "\u22D6",
    "&lesseqgtr;": "\u22DA",
    "&lesseqqgtr;": "\u2A8B",
    "&lessgtr;": "\u2276",
    "&lesssim;": "\u2272",
    "&lfisht;": "\u297C",
    "&lfloor;": "\u230A",
    "&lfr;": "\uD835\uDD29",
    "&lg;": "\u2276",
    "&lgE;": "\u2A91",
    "&lhard;": "\u21BD",
    "&lharu;": "\u21BC",
    "&lharul;": "\u296A",
    "&lhblk;": "\u2584",
    "&ljcy;": "\u0459",
    "&ll;": "\u226A",
    "&llarr;": "\u21C7",
    "&llcorner;": "\u231E",
    "&llhard;": "\u296B",
    "&lltri;": "\u25FA",
    "&lmidot;": "\u0140",
    "&lmoust;": "\u23B0",
    "&lmoustache;": "\u23B0",
    "&lnE;": "\u2268",
    "&lnap;": "\u2A89",
    "&lnapprox;": "\u2A89",
    "&lne;": "\u2A87",
    "&lneq;": "\u2A87",
    "&lneqq;": "\u2268",
    "&lnsim;": "\u22E6",
    "&loang;": "\u27EC",
    "&loarr;": "\u21FD",
    "&lobrk;": "\u27E6",
    "&longleftarrow;": "\u27F5",
    "&longleftrightarrow;": "\u27F7",
    "&longmapsto;": "\u27FC",
    "&longrightarrow;": "\u27F6",
    "&looparrowleft;": "\u21AB",
    "&looparrowright;": "\u21AC",
    "&lopar;": "\u2985",
    "&lopf;": "\uD835\uDD5D",
    "&loplus;": "\u2A2D",
    "&lotimes;": "\u2A34",
    "&lowast;": "\u2217",
    "&lowbar;": "\u005F",
    "&loz;": "\u25CA",
    "&lozenge;": "\u25CA",
    "&lozf;": "\u29EB",
    "&lpar;": "\u0028",
    "&lparlt;": "\u2993",
    "&lrarr;": "\u21C6",
    "&lrcorner;": "\u231F",
    "&lrhar;": "\u21CB",
    "&lrhard;": "\u296D",
    "&lrm;": "\u200E",
    "&lrtri;": "\u22BF",
    "&lsaquo;": "\u2039",
    "&lscr;": "\uD835\uDCC1",
    "&lsh;": "\u21B0",
    "&lsim;": "\u2272",
    "&lsime;": "\u2A8D",
    "&lsimg;": "\u2A8F",
    "&lsqb;": "\u005B",
    "&lsquo;": "\u2018",
    "&lsquor;": "\u201A",
    "&lstrok;": "\u0142",
    "&lt": "\u003C",
    "&lt;": "\u003C",
    "&ltcc;": "\u2AA6",
    "&ltcir;": "\u2A79",
    "&ltdot;": "\u22D6",
    "&lthree;": "\u22CB",
    "&ltimes;": "\u22C9",
    "&ltlarr;": "\u2976",
    "&ltquest;": "\u2A7B",
    "&ltrPar;": "\u2996",
    "&ltri;": "\u25C3",
    "&ltrie;": "\u22B4",
    "&ltrif;": "\u25C2",
    "&lurdshar;": "\u294A",
    "&luruhar;": "\u2966",
    "&lvertneqq;": "\u2268\uFE00",
    "&lvnE;": "\u2268\uFE00",
    "&mDDot;": "\u223A",
    "&macr": "\u00AF",
    "&macr;": "\u00AF",
    "&male;": "\u2642",
    "&malt;": "\u2720",
    "&maltese;": "\u2720",
    "&map;": "\u21A6",
    "&mapsto;": "\u21A6",
    "&mapstodown;": "\u21A7",
    "&mapstoleft;": "\u21A4",
    "&mapstoup;": "\u21A5",
    "&marker;": "\u25AE",
    "&mcomma;": "\u2A29",
    "&mcy;": "\u043C",
    "&mdash;": "\u2014",
    "&measuredangle;": "\u2221",
    "&mfr;": "\uD835\uDD2A",
    "&mho;": "\u2127",
    "&micro": "\u00B5",
    "&micro;": "\u00B5",
    "&mid;": "\u2223",
    "&midast;": "\u002A",
    "&midcir;": "\u2AF0",
    "&middot": "\u00B7",
    "&middot;": "\u00B7",
    "&minus;": "\u2212",
    "&minusb;": "\u229F",
    "&minusd;": "\u2238",
    "&minusdu;": "\u2A2A",
    "&mlcp;": "\u2ADB",
    "&mldr;": "\u2026",
    "&mnplus;": "\u2213",
    "&models;": "\u22A7",
    "&mopf;": "\uD835\uDD5E",
    "&mp;": "\u2213",
    "&mscr;": "\uD835\uDCC2",
    "&mstpos;": "\u223E",
    "&mu;": "\u03BC",
    "&multimap;": "\u22B8",
    "&mumap;": "\u22B8",
    "&nGg;": "\u22D9\u0338",
    "&nGt;": "\u226B\u20D2",
    "&nGtv;": "\u226B\u0338",
    "&nLeftarrow;": "\u21CD",
    "&nLeftrightarrow;": "\u21CE",
    "&nLl;": "\u22D8\u0338",
    "&nLt;": "\u226A\u20D2",
    "&nLtv;": "\u226A\u0338",
    "&nRightarrow;": "\u21CF",
    "&nVDash;": "\u22AF",
    "&nVdash;": "\u22AE",
    "&nabla;": "\u2207",
    "&nacute;": "\u0144",
    "&nang;": "\u2220\u20D2",
    "&nap;": "\u2249",
    "&napE;": "\u2A70\u0338",
    "&napid;": "\u224B\u0338",
    "&napos;": "\u0149",
    "&napprox;": "\u2249",
    "&natur;": "\u266E",
    "&natural;": "\u266E",
    "&naturals;": "\u2115",
    "&nbsp": "\u00A0",
    "&nbsp;": "\u00A0",
    "&nbump;": "\u224E\u0338",
    "&nbumpe;": "\u224F\u0338",
    "&ncap;": "\u2A43",
    "&ncaron;": "\u0148",
    "&ncedil;": "\u0146",
    "&ncong;": "\u2247",
    "&ncongdot;": "\u2A6D\u0338",
    "&ncup;": "\u2A42",
    "&ncy;": "\u043D",
    "&ndash;": "\u2013",
    "&ne;": "\u2260",
    "&neArr;": "\u21D7",
    "&nearhk;": "\u2924",
    "&nearr;": "\u2197",
    "&nearrow;": "\u2197",
    "&nedot;": "\u2250\u0338",
    "&nequiv;": "\u2262",
    "&nesear;": "\u2928",
    "&nesim;": "\u2242\u0338",
    "&nexist;": "\u2204",
    "&nexists;": "\u2204",
    "&nfr;": "\uD835\uDD2B",
    "&ngE;": "\u2267\u0338",
    "&nge;": "\u2271",
    "&ngeq;": "\u2271",
    "&ngeqq;": "\u2267\u0338",
    "&ngeqslant;": "\u2A7E\u0338",
    "&nges;": "\u2A7E\u0338",
    "&ngsim;": "\u2275",
    "&ngt;": "\u226F",
    "&ngtr;": "\u226F",
    "&nhArr;": "\u21CE",
    "&nharr;": "\u21AE",
    "&nhpar;": "\u2AF2",
    "&ni;": "\u220B",
    "&nis;": "\u22FC",
    "&nisd;": "\u22FA",
    "&niv;": "\u220B",
    "&njcy;": "\u045A",
    "&nlArr;": "\u21CD",
    "&nlE;": "\u2266\u0338",
    "&nlarr;": "\u219A",
    "&nldr;": "\u2025",
    "&nle;": "\u2270",
    "&nleftarrow;": "\u219A",
    "&nleftrightarrow;": "\u21AE",
    "&nleq;": "\u2270",
    "&nleqq;": "\u2266\u0338",
    "&nleqslant;": "\u2A7D\u0338",
    "&nles;": "\u2A7D\u0338",
    "&nless;": "\u226E",
    "&nlsim;": "\u2274",
    "&nlt;": "\u226E",
    "&nltri;": "\u22EA",
    "&nltrie;": "\u22EC",
    "&nmid;": "\u2224",
    "&nopf;": "\uD835\uDD5F",
    "&not": "\u00AC",
    "&not;": "\u00AC",
    "&notin;": "\u2209",
    "&notinE;": "\u22F9\u0338",
    "&notindot;": "\u22F5\u0338",
    "&notinva;": "\u2209",
    "&notinvb;": "\u22F7",
    "&notinvc;": "\u22F6",
    "&notni;": "\u220C",
    "&notniva;": "\u220C",
    "&notnivb;": "\u22FE",
    "&notnivc;": "\u22FD",
    "&npar;": "\u2226",
    "&nparallel;": "\u2226",
    "&nparsl;": "\u2AFD\u20E5",
    "&npart;": "\u2202\u0338",
    "&npolint;": "\u2A14",
    "&npr;": "\u2280",
    "&nprcue;": "\u22E0",
    "&npre;": "\u2AAF\u0338",
    "&nprec;": "\u2280",
    "&npreceq;": "\u2AAF\u0338",
    "&nrArr;": "\u21CF",
    "&nrarr;": "\u219B",
    "&nrarrc;": "\u2933\u0338",
    "&nrarrw;": "\u219D\u0338",
    "&nrightarrow;": "\u219B",
    "&nrtri;": "\u22EB",
    "&nrtrie;": "\u22ED",
    "&nsc;": "\u2281",
    "&nsccue;": "\u22E1",
    "&nsce;": "\u2AB0\u0338",
    "&nscr;": "\uD835\uDCC3",
    "&nshortmid;": "\u2224",
    "&nshortparallel;": "\u2226",
    "&nsim;": "\u2241",
    "&nsime;": "\u2244",
    "&nsimeq;": "\u2244",
    "&nsmid;": "\u2224",
    "&nspar;": "\u2226",
    "&nsqsube;": "\u22E2",
    "&nsqsupe;": "\u22E3",
    "&nsub;": "\u2284",
    "&nsubE;": "\u2AC5\u0338",
    "&nsube;": "\u2288",
    "&nsubset;": "\u2282\u20D2",
    "&nsubseteq;": "\u2288",
    "&nsubseteqq;": "\u2AC5\u0338",
    "&nsucc;": "\u2281",
    "&nsucceq;": "\u2AB0\u0338",
    "&nsup;": "\u2285",
    "&nsupE;": "\u2AC6\u0338",
    "&nsupe;": "\u2289",
    "&nsupset;": "\u2283\u20D2",
    "&nsupseteq;": "\u2289",
    "&nsupseteqq;": "\u2AC6\u0338",
    "&ntgl;": "\u2279",
    "&ntilde": "\u00F1",
    "&ntilde;": "\u00F1",
    "&ntlg;": "\u2278",
    "&ntriangleleft;": "\u22EA",
    "&ntrianglelefteq;": "\u22EC",
    "&ntriangleright;": "\u22EB",
    "&ntrianglerighteq;": "\u22ED",
    "&nu;": "\u03BD",
    "&num;": "\u0023",
    "&numero;": "\u2116",
    "&numsp;": "\u2007",
    "&nvDash;": "\u22AD",
    "&nvHarr;": "\u2904",
    "&nvap;": "\u224D\u20D2",
    "&nvdash;": "\u22AC",
    "&nvge;": "\u2265\u20D2",
    "&nvgt;": "\u003E\u20D2",
    "&nvinfin;": "\u29DE",
    "&nvlArr;": "\u2902",
    "&nvle;": "\u2264\u20D2",
    "&nvlt;": "\u003C\u20D2",
    "&nvltrie;": "\u22B4\u20D2",
    "&nvrArr;": "\u2903",
    "&nvrtrie;": "\u22B5\u20D2",
    "&nvsim;": "\u223C\u20D2",
    "&nwArr;": "\u21D6",
    "&nwarhk;": "\u2923",
    "&nwarr;": "\u2196",
    "&nwarrow;": "\u2196",
    "&nwnear;": "\u2927",
    "&oS;": "\u24C8",
    "&oacute": "\u00F3",
    "&oacute;": "\u00F3",
    "&oast;": "\u229B",
    "&ocir;": "\u229A",
    "&ocirc": "\u00F4",
    "&ocirc;": "\u00F4",
    "&ocy;": "\u043E",
    "&odash;": "\u229D",
    "&odblac;": "\u0151",
    "&odiv;": "\u2A38",
    "&odot;": "\u2299",
    "&odsold;": "\u29BC",
    "&oelig;": "\u0153",
    "&ofcir;": "\u29BF",
    "&ofr;": "\uD835\uDD2C",
    "&ogon;": "\u02DB",
    "&ograve": "\u00F2",
    "&ograve;": "\u00F2",
    "&ogt;": "\u29C1",
    "&ohbar;": "\u29B5",
    "&ohm;": "\u03A9",
    "&oint;": "\u222E",
    "&olarr;": "\u21BA",
    "&olcir;": "\u29BE",
    "&olcross;": "\u29BB",
    "&oline;": "\u203E",
    "&olt;": "\u29C0",
    "&omacr;": "\u014D",
    "&omega;": "\u03C9",
    "&omicron;": "\u03BF",
    "&omid;": "\u29B6",
    "&ominus;": "\u2296",
    "&oopf;": "\uD835\uDD60",
    "&opar;": "\u29B7",
    "&operp;": "\u29B9",
    "&oplus;": "\u2295",
    "&or;": "\u2228",
    "&orarr;": "\u21BB",
    "&ord;": "\u2A5D",
    "&order;": "\u2134",
    "&orderof;": "\u2134",
    "&ordf": "\u00AA",
    "&ordf;": "\u00AA",
    "&ordm": "\u00BA",
    "&ordm;": "\u00BA",
    "&origof;": "\u22B6",
    "&oror;": "\u2A56",
    "&orslope;": "\u2A57",
    "&orv;": "\u2A5B",
    "&oscr;": "\u2134",
    "&oslash": "\u00F8",
    "&oslash;": "\u00F8",
    "&osol;": "\u2298",
    "&otilde": "\u00F5",
    "&otilde;": "\u00F5",
    "&otimes;": "\u2297",
    "&otimesas;": "\u2A36",
    "&ouml": "\u00F6",
    "&ouml;": "\u00F6",
    "&ovbar;": "\u233D",
    "&par;": "\u2225",
    "&para": "\u00B6",
    "&para;": "\u00B6",
    "&parallel;": "\u2225",
    "&parsim;": "\u2AF3",
    "&parsl;": "\u2AFD",
    "&part;": "\u2202",
    "&pcy;": "\u043F",
    "&percnt;": "\u0025",
    "&period;": "\u002E",
    "&permil;": "\u2030",
    "&perp;": "\u22A5",
    "&pertenk;": "\u2031",
    "&pfr;": "\uD835\uDD2D",
    "&phi;": "\u03C6",
    "&phiv;": "\u03D5",
    "&phmmat;": "\u2133",
    "&phone;": "\u260E",
    "&pi;": "\u03C0",
    "&pitchfork;": "\u22D4",
    "&piv;": "\u03D6",
    "&planck;": "\u210F",
    "&planckh;": "\u210E",
    "&plankv;": "\u210F",
    "&plus;": "\u002B",
    "&plusacir;": "\u2A23",
    "&plusb;": "\u229E",
    "&pluscir;": "\u2A22",
    "&plusdo;": "\u2214",
    "&plusdu;": "\u2A25",
    "&pluse;": "\u2A72",
    "&plusmn": "\u00B1",
    "&plusmn;": "\u00B1",
    "&plussim;": "\u2A26",
    "&plustwo;": "\u2A27",
    "&pm;": "\u00B1",
    "&pointint;": "\u2A15",
    "&popf;": "\uD835\uDD61",
    "&pound": "\u00A3",
    "&pound;": "\u00A3",
    "&pr;": "\u227A",
    "&prE;": "\u2AB3",
    "&prap;": "\u2AB7",
    "&prcue;": "\u227C",
    "&pre;": "\u2AAF",
    "&prec;": "\u227A",
    "&precapprox;": "\u2AB7",
    "&preccurlyeq;": "\u227C",
    "&preceq;": "\u2AAF",
    "&precnapprox;": "\u2AB9",
    "&precneqq;": "\u2AB5",
    "&precnsim;": "\u22E8",
    "&precsim;": "\u227E",
    "&prime;": "\u2032",
    "&primes;": "\u2119",
    "&prnE;": "\u2AB5",
    "&prnap;": "\u2AB9",
    "&prnsim;": "\u22E8",
    "&prod;": "\u220F",
    "&profalar;": "\u232E",
    "&profline;": "\u2312",
    "&profsurf;": "\u2313",
    "&prop;": "\u221D",
    "&propto;": "\u221D",
    "&prsim;": "\u227E",
    "&prurel;": "\u22B0",
    "&pscr;": "\uD835\uDCC5",
    "&psi;": "\u03C8",
    "&puncsp;": "\u2008",
    "&qfr;": "\uD835\uDD2E",
    "&qint;": "\u2A0C",
    "&qopf;": "\uD835\uDD62",
    "&qprime;": "\u2057",
    "&qscr;": "\uD835\uDCC6",
    "&quaternions;": "\u210D",
    "&quatint;": "\u2A16",
    "&quest;": "\u003F",
    "&questeq;": "\u225F",
    "&quot": "\u0022",
    "&quot;": "\u0022",
    "&rAarr;": "\u21DB",
    "&rArr;": "\u21D2",
    "&rAtail;": "\u291C",
    "&rBarr;": "\u290F",
    "&rHar;": "\u2964",
    "&race;": "\u223D\u0331",
    "&racute;": "\u0155",
    "&radic;": "\u221A",
    "&raemptyv;": "\u29B3",
    "&rang;": "\u27E9",
    "&rangd;": "\u2992",
    "&range;": "\u29A5",
    "&rangle;": "\u27E9",
    "&raquo": "\u00BB",
    "&raquo;": "\u00BB",
    "&rarr;": "\u2192",
    "&rarrap;": "\u2975",
    "&rarrb;": "\u21E5",
    "&rarrbfs;": "\u2920",
    "&rarrc;": "\u2933",
    "&rarrfs;": "\u291E",
    "&rarrhk;": "\u21AA",
    "&rarrlp;": "\u21AC",
    "&rarrpl;": "\u2945",
    "&rarrsim;": "\u2974",
    "&rarrtl;": "\u21A3",
    "&rarrw;": "\u219D",
    "&ratail;": "\u291A",
    "&ratio;": "\u2236",
    "&rationals;": "\u211A",
    "&rbarr;": "\u290D",
    "&rbbrk;": "\u2773",
    "&rbrace;": "\u007D",
    "&rbrack;": "\u005D",
    "&rbrke;": "\u298C",
    "&rbrksld;": "\u298E",
    "&rbrkslu;": "\u2990",
    "&rcaron;": "\u0159",
    "&rcedil;": "\u0157",
    "&rceil;": "\u2309",
    "&rcub;": "\u007D",
    "&rcy;": "\u0440",
    "&rdca;": "\u2937",
    "&rdldhar;": "\u2969",
    "&rdquo;": "\u201D",
    "&rdquor;": "\u201D",
    "&rdsh;": "\u21B3",
    "&real;": "\u211C",
    "&realine;": "\u211B",
    "&realpart;": "\u211C",
    "&reals;": "\u211D",
    "&rect;": "\u25AD",
    "&reg": "\u00AE",
    "&reg;": "\u00AE",
    "&rfisht;": "\u297D",
    "&rfloor;": "\u230B",
    "&rfr;": "\uD835\uDD2F",
    "&rhard;": "\u21C1",
    "&rharu;": "\u21C0",
    "&rharul;": "\u296C",
    "&rho;": "\u03C1",
    "&rhov;": "\u03F1",
    "&rightarrow;": "\u2192",
    "&rightarrowtail;": "\u21A3",
    "&rightharpoondown;": "\u21C1",
    "&rightharpoonup;": "\u21C0",
    "&rightleftarrows;": "\u21C4",
    "&rightleftharpoons;": "\u21CC",
    "&rightrightarrows;": "\u21C9",
    "&rightsquigarrow;": "\u219D",
    "&rightthreetimes;": "\u22CC",
    "&ring;": "\u02DA",
    "&risingdotseq;": "\u2253",
    "&rlarr;": "\u21C4",
    "&rlhar;": "\u21CC",
    "&rlm;": "\u200F",
    "&rmoust;": "\u23B1",
    "&rmoustache;": "\u23B1",
    "&rnmid;": "\u2AEE",
    "&roang;": "\u27ED",
    "&roarr;": "\u21FE",
    "&robrk;": "\u27E7",
    "&ropar;": "\u2986",
    "&ropf;": "\uD835\uDD63",
    "&roplus;": "\u2A2E",
    "&rotimes;": "\u2A35",
    "&rpar;": "\u0029",
    "&rpargt;": "\u2994",
    "&rppolint;": "\u2A12",
    "&rrarr;": "\u21C9",
    "&rsaquo;": "\u203A",
    "&rscr;": "\uD835\uDCC7",
    "&rsh;": "\u21B1",
    "&rsqb;": "\u005D",
    "&rsquo;": "\u2019",
    "&rsquor;": "\u2019",
    "&rthree;": "\u22CC",
    "&rtimes;": "\u22CA",
    "&rtri;": "\u25B9",
    "&rtrie;": "\u22B5",
    "&rtrif;": "\u25B8",
    "&rtriltri;": "\u29CE",
    "&ruluhar;": "\u2968",
    "&rx;": "\u211E",
    "&sacute;": "\u015B",
    "&sbquo;": "\u201A",
    "&sc;": "\u227B",
    "&scE;": "\u2AB4",
    "&scap;": "\u2AB8",
    "&scaron;": "\u0161",
    "&sccue;": "\u227D",
    "&sce;": "\u2AB0",
    "&scedil;": "\u015F",
    "&scirc;": "\u015D",
    "&scnE;": "\u2AB6",
    "&scnap;": "\u2ABA",
    "&scnsim;": "\u22E9",
    "&scpolint;": "\u2A13",
    "&scsim;": "\u227F",
    "&scy;": "\u0441",
    "&sdot;": "\u22C5",
    "&sdotb;": "\u22A1",
    "&sdote;": "\u2A66",
    "&seArr;": "\u21D8",
    "&searhk;": "\u2925",
    "&searr;": "\u2198",
    "&searrow;": "\u2198",
    "&sect": "\u00A7",
    "&sect;": "\u00A7",
    "&semi;": "\u003B",
    "&seswar;": "\u2929",
    "&setminus;": "\u2216",
    "&setmn;": "\u2216",
    "&sext;": "\u2736",
    "&sfr;": "\uD835\uDD30",
    "&sfrown;": "\u2322",
    "&sharp;": "\u266F",
    "&shchcy;": "\u0449",
    "&shcy;": "\u0448",
    "&shortmid;": "\u2223",
    "&shortparallel;": "\u2225",
    "&shy": "\u00AD",
    "&shy;": "\u00AD",
    "&sigma;": "\u03C3",
    "&sigmaf;": "\u03C2",
    "&sigmav;": "\u03C2",
    "&sim;": "\u223C",
    "&simdot;": "\u2A6A",
    "&sime;": "\u2243",
    "&simeq;": "\u2243",
    "&simg;": "\u2A9E",
    "&simgE;": "\u2AA0",
    "&siml;": "\u2A9D",
    "&simlE;": "\u2A9F",
    "&simne;": "\u2246",
    "&simplus;": "\u2A24",
    "&simrarr;": "\u2972",
    "&slarr;": "\u2190",
    "&smallsetminus;": "\u2216",
    "&smashp;": "\u2A33",
    "&smeparsl;": "\u29E4",
    "&smid;": "\u2223",
    "&smile;": "\u2323",
    "&smt;": "\u2AAA",
    "&smte;": "\u2AAC",
    "&smtes;": "\u2AAC\uFE00",
    "&softcy;": "\u044C",
    "&sol;": "\u002F",
    "&solb;": "\u29C4",
    "&solbar;": "\u233F",
    "&sopf;": "\uD835\uDD64",
    "&spades;": "\u2660",
    "&spadesuit;": "\u2660",
    "&spar;": "\u2225",
    "&sqcap;": "\u2293",
    "&sqcaps;": "\u2293\uFE00",
    "&sqcup;": "\u2294",
    "&sqcups;": "\u2294\uFE00",
    "&sqsub;": "\u228F",
    "&sqsube;": "\u2291",
    "&sqsubset;": "\u228F",
    "&sqsubseteq;": "\u2291",
    "&sqsup;": "\u2290",
    "&sqsupe;": "\u2292",
    "&sqsupset;": "\u2290",
    "&sqsupseteq;": "\u2292",
    "&squ;": "\u25A1",
    "&square;": "\u25A1",
    "&squarf;": "\u25AA",
    "&squf;": "\u25AA",
    "&srarr;": "\u2192",
    "&sscr;": "\uD835\uDCC8",
    "&ssetmn;": "\u2216",
    "&ssmile;": "\u2323",
    "&sstarf;": "\u22C6",
    "&star;": "\u2606",
    "&starf;": "\u2605",
    "&straightepsilon;": "\u03F5",
    "&straightphi;": "\u03D5",
    "&strns;": "\u00AF",
    "&sub;": "\u2282",
    "&subE;": "\u2AC5",
    "&subdot;": "\u2ABD",
    "&sube;": "\u2286",
    "&subedot;": "\u2AC3",
    "&submult;": "\u2AC1",
    "&subnE;": "\u2ACB",
    "&subne;": "\u228A",
    "&subplus;": "\u2ABF",
    "&subrarr;": "\u2979",
    "&subset;": "\u2282",
    "&subseteq;": "\u2286",
    "&subseteqq;": "\u2AC5",
    "&subsetneq;": "\u228A",
    "&subsetneqq;": "\u2ACB",
    "&subsim;": "\u2AC7",
    "&subsub;": "\u2AD5",
    "&subsup;": "\u2AD3",
    "&succ;": "\u227B",
    "&succapprox;": "\u2AB8",
    "&succcurlyeq;": "\u227D",
    "&succeq;": "\u2AB0",
    "&succnapprox;": "\u2ABA",
    "&succneqq;": "\u2AB6",
    "&succnsim;": "\u22E9",
    "&succsim;": "\u227F",
    "&sum;": "\u2211",
    "&sung;": "\u266A",
    "&sup1": "\u00B9",
    "&sup1;": "\u00B9",
    "&sup2": "\u00B2",
    "&sup2;": "\u00B2",
    "&sup3": "\u00B3",
    "&sup3;": "\u00B3",
    "&sup;": "\u2283",
    "&supE;": "\u2AC6",
    "&supdot;": "\u2ABE",
    "&supdsub;": "\u2AD8",
    "&supe;": "\u2287",
    "&supedot;": "\u2AC4",
    "&suphsol;": "\u27C9",
    "&suphsub;": "\u2AD7",
    "&suplarr;": "\u297B",
    "&supmult;": "\u2AC2",
    "&supnE;": "\u2ACC",
    "&supne;": "\u228B",
    "&supplus;": "\u2AC0",
    "&supset;": "\u2283",
    "&supseteq;": "\u2287",
    "&supseteqq;": "\u2AC6",
    "&supsetneq;": "\u228B",
    "&supsetneqq;": "\u2ACC",
    "&supsim;": "\u2AC8",
    "&supsub;": "\u2AD4",
    "&supsup;": "\u2AD6",
    "&swArr;": "\u21D9",
    "&swarhk;": "\u2926",
    "&swarr;": "\u2199",
    "&swarrow;": "\u2199",
    "&swnwar;": "\u292A",
    "&szlig": "\u00DF",
    "&szlig;": "\u00DF",
    "&target;": "\u2316",
    "&tau;": "\u03C4",
    "&tbrk;": "\u23B4",
    "&tcaron;": "\u0165",
    "&tcedil;": "\u0163",
    "&tcy;": "\u0442",
    "&tdot;": "\u20DB",
    "&telrec;": "\u2315",
    "&tfr;": "\uD835\uDD31",
    "&there4;": "\u2234",
    "&therefore;": "\u2234",
    "&theta;": "\u03B8",
    "&thetasym;": "\u03D1",
    "&thetav;": "\u03D1",
    "&thickapprox;": "\u2248",
    "&thicksim;": "\u223C",
    "&thinsp;": "\u2009",
    "&thkap;": "\u2248",
    "&thksim;": "\u223C",
    "&thorn": "\u00FE",
    "&thorn;": "\u00FE",
    "&tilde;": "\u02DC",
    "&times": "\u00D7",
    "&times;": "\u00D7",
    "&timesb;": "\u22A0",
    "&timesbar;": "\u2A31",
    "&timesd;": "\u2A30",
    "&tint;": "\u222D",
    "&toea;": "\u2928",
    "&top;": "\u22A4",
    "&topbot;": "\u2336",
    "&topcir;": "\u2AF1",
    "&topf;": "\uD835\uDD65",
    "&topfork;": "\u2ADA",
    "&tosa;": "\u2929",
    "&tprime;": "\u2034",
    "&trade;": "\u2122",
    "&triangle;": "\u25B5",
    "&triangledown;": "\u25BF",
    "&triangleleft;": "\u25C3",
    "&trianglelefteq;": "\u22B4",
    "&triangleq;": "\u225C",
    "&triangleright;": "\u25B9",
    "&trianglerighteq;": "\u22B5",
    "&tridot;": "\u25EC",
    "&trie;": "\u225C",
    "&triminus;": "\u2A3A",
    "&triplus;": "\u2A39",
    "&trisb;": "\u29CD",
    "&tritime;": "\u2A3B",
    "&trpezium;": "\u23E2",
    "&tscr;": "\uD835\uDCC9",
    "&tscy;": "\u0446",
    "&tshcy;": "\u045B",
    "&tstrok;": "\u0167",
    "&twixt;": "\u226C",
    "&twoheadleftarrow;": "\u219E",
    "&twoheadrightarrow;": "\u21A0",
    "&uArr;": "\u21D1",
    "&uHar;": "\u2963",
    "&uacute": "\u00FA",
    "&uacute;": "\u00FA",
    "&uarr;": "\u2191",
    "&ubrcy;": "\u045E",
    "&ubreve;": "\u016D",
    "&ucirc": "\u00FB",
    "&ucirc;": "\u00FB",
    "&ucy;": "\u0443",
    "&udarr;": "\u21C5",
    "&udblac;": "\u0171",
    "&udhar;": "\u296E",
    "&ufisht;": "\u297E",
    "&ufr;": "\uD835\uDD32",
    "&ugrave": "\u00F9",
    "&ugrave;": "\u00F9",
    "&uharl;": "\u21BF",
    "&uharr;": "\u21BE",
    "&uhblk;": "\u2580",
    "&ulcorn;": "\u231C",
    "&ulcorner;": "\u231C",
    "&ulcrop;": "\u230F",
    "&ultri;": "\u25F8",
    "&umacr;": "\u016B",
    "&uml": "\u00A8",
    "&uml;": "\u00A8",
    "&uogon;": "\u0173",
    "&uopf;": "\uD835\uDD66",
    "&uparrow;": "\u2191",
    "&updownarrow;": "\u2195",
    "&upharpoonleft;": "\u21BF",
    "&upharpoonright;": "\u21BE",
    "&uplus;": "\u228E",
    "&upsi;": "\u03C5",
    "&upsih;": "\u03D2",
    "&upsilon;": "\u03C5",
    "&upuparrows;": "\u21C8",
    "&urcorn;": "\u231D",
    "&urcorner;": "\u231D",
    "&urcrop;": "\u230E",
    "&uring;": "\u016F",
    "&urtri;": "\u25F9",
    "&uscr;": "\uD835\uDCCA",
    "&utdot;": "\u22F0",
    "&utilde;": "\u0169",
    "&utri;": "\u25B5",
    "&utrif;": "\u25B4",
    "&uuarr;": "\u21C8",
    "&uuml": "\u00FC",
    "&uuml;": "\u00FC",
    "&uwangle;": "\u29A7",
    "&vArr;": "\u21D5",
    "&vBar;": "\u2AE8",
    "&vBarv;": "\u2AE9",
    "&vDash;": "\u22A8",
    "&vangrt;": "\u299C",
    "&varepsilon;": "\u03F5",
    "&varkappa;": "\u03F0",
    "&varnothing;": "\u2205",
    "&varphi;": "\u03D5",
    "&varpi;": "\u03D6",
    "&varpropto;": "\u221D",
    "&varr;": "\u2195",
    "&varrho;": "\u03F1",
    "&varsigma;": "\u03C2",
    "&varsubsetneq;": "\u228A\uFE00",
    "&varsubsetneqq;": "\u2ACB\uFE00",
    "&varsupsetneq;": "\u228B\uFE00",
    "&varsupsetneqq;": "\u2ACC\uFE00",
    "&vartheta;": "\u03D1",
    "&vartriangleleft;": "\u22B2",
    "&vartriangleright;": "\u22B3",
    "&vcy;": "\u0432",
    "&vdash;": "\u22A2",
    "&vee;": "\u2228",
    "&veebar;": "\u22BB",
    "&veeeq;": "\u225A",
    "&vellip;": "\u22EE",
    "&verbar;": "\u007C",
    "&vert;": "\u007C",
    "&vfr;": "\uD835\uDD33",
    "&vltri;": "\u22B2",
    "&vnsub;": "\u2282\u20D2",
    "&vnsup;": "\u2283\u20D2",
    "&vopf;": "\uD835\uDD67",
    "&vprop;": "\u221D",
    "&vrtri;": "\u22B3",
    "&vscr;": "\uD835\uDCCB",
    "&vsubnE;": "\u2ACB\uFE00",
    "&vsubne;": "\u228A\uFE00",
    "&vsupnE;": "\u2ACC\uFE00",
    "&vsupne;": "\u228B\uFE00",
    "&vzigzag;": "\u299A",
    "&wcirc;": "\u0175",
    "&wedbar;": "\u2A5F",
    "&wedge;": "\u2227",
    "&wedgeq;": "\u2259",
    "&weierp;": "\u2118",
    "&wfr;": "\uD835\uDD34",
    "&wopf;": "\uD835\uDD68",
    "&wp;": "\u2118",
    "&wr;": "\u2240",
    "&wreath;": "\u2240",
    "&wscr;": "\uD835\uDCCC",
    "&xcap;": "\u22C2",
    "&xcirc;": "\u25EF",
    "&xcup;": "\u22C3",
    "&xdtri;": "\u25BD",
    "&xfr;": "\uD835\uDD35",
    "&xhArr;": "\u27FA",
    "&xharr;": "\u27F7",
    "&xi;": "\u03BE",
    "&xlArr;": "\u27F8",
    "&xlarr;": "\u27F5",
    "&xmap;": "\u27FC",
    "&xnis;": "\u22FB",
    "&xodot;": "\u2A00",
    "&xopf;": "\uD835\uDD69",
    "&xoplus;": "\u2A01",
    "&xotime;": "\u2A02",
    "&xrArr;": "\u27F9",
    "&xrarr;": "\u27F6",
    "&xscr;": "\uD835\uDCCD",
    "&xsqcup;": "\u2A06",
    "&xuplus;": "\u2A04",
    "&xutri;": "\u25B3",
    "&xvee;": "\u22C1",
    "&xwedge;": "\u22C0",
    "&yacute": "\u00FD",
    "&yacute;": "\u00FD",
    "&yacy;": "\u044F",
    "&ycirc;": "\u0177",
    "&ycy;": "\u044B",
    "&yen": "\u00A5",
    "&yen;": "\u00A5",
    "&yfr;": "\uD835\uDD36",
    "&yicy;": "\u0457",
    "&yopf;": "\uD835\uDD6A",
    "&yscr;": "\uD835\uDCCE",
    "&yucy;": "\u044E",
    "&yuml": "\u00FF",
    "&yuml;": "\u00FF",
    "&zacute;": "\u017A",
    "&zcaron;": "\u017E",
    "&zcy;": "\u0437",
    "&zdot;": "\u017C",
    "&zeetrf;": "\u2128",
    "&zeta;": "\u03B6",
    "&zfr;": "\uD835\uDD37",
    "&zhcy;": "\u0436",
    "&zigrarr;": "\u21DD",
    "&zopf;": "\uD835\uDD6B",
    "&zscr;": "\uD835\uDCCF",
    "&zwj;": "\u200D",
    "&zwnj;": "\u200C",
}
