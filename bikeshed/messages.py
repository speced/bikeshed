from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import sys
from collections import Counter

import lxml.html

from . import t

MESSAGE_LEVELS = {
    "everything": 0,
    "message": 1,
    "lint": 2,
    "warning": 3,
    "link-error": 4,
    "fatal": 5,
    "nothing": 6,
}

DEATH_TIMING = [
    "early",  # die as soon as the first disallowed error occurs
    "late",  # die at the end of processing
]

PRINT_MODES = [
    "plain",
    "console",
    "markup",
    "json",
]


@dataclasses.dataclass()
class MessagesState:
    # What message category (or higher) to stop processing on
    dieOn: str = "fatal"
    # When to stop processing when an error that trips failure happens
    dieWhen: str = "late"
    # What message category (or higher) to print
    printOn: str = "everything"
    # Suppress *all* categories, *plus* the final success/fail message
    silent: bool = False
    printMode: str = "console"
    asciiOnly: bool = False
    fh: io.TextIOWrapper = t.cast("io.TextIOWrapper", sys.stdout)  # noqa: RUF009
    seenMessages: set[str | tuple[str, str]] = dataclasses.field(default_factory=set)
    categoryCounts: Counter[str] = dataclasses.field(default_factory=Counter)

    def record(self, category: str, message: str | tuple[str, str]) -> None:
        self.categoryCounts[category] += 1
        self.seenMessages.add(message)

    def replace(self, **kwargs: t.Any) -> MessagesState:
        return dataclasses.replace(self, seenMessages=set(), categoryCounts=Counter(), **kwargs)

    def shouldDie(self, category: str, timing: str = "early") -> bool:
        if self.dieWhen == "never":
            return False
        if self.dieWhen == "late" and timing == "early":
            return False
        deathLevel = MESSAGE_LEVELS[self.dieOn]
        queriedLevel = MESSAGE_LEVELS[category]
        return queriedLevel >= deathLevel

    def shouldPrint(self, category: str) -> bool:
        if self.silent:
            return False
        if category in ("success", "failure"):
            return True
        printLevel = MESSAGE_LEVELS[self.printOn]
        queriedLevel = MESSAGE_LEVELS[category]
        return queriedLevel >= printLevel

    @staticmethod
    def categoryName(categoryNum: int) -> str:
        assert categoryNum >= 0
        if categoryNum >= len(MESSAGE_LEVELS):
            return "nothing"
        return list(MESSAGE_LEVELS.keys())[categoryNum]


state = MessagesState()


def p(msg: str | tuple[str, str], sep: str | None = None, end: str | None = None) -> None:
    if isinstance(msg, tuple):
        msg, ascii = msg
    else:
        ascii = msg.encode("ascii", "replace").decode()
    if state.asciiOnly:
        msg = ascii
    try:
        print(msg, sep=sep, end=end, file=state.fh)
    except UnicodeEncodeError:
        if ascii is not None:
            print(ascii, sep=sep, end=end, file=state.fh)
        else:
            warning = formatMessage(
                "warning",
                "Your console does not understand Unicode.\n  Messages may be slightly corrupted.",
            )
            if warning not in state.seenMessages:
                print(warning, file=state.fh)
                state.record("warning", warning)
            print(msg.encode("ascii", "xmlcharrefreplace"), sep=sep, end=end, file=state.fh)


def getLineNum(lineNum: str | int | None = None, el: t.ElementT | None = None) -> str | int | None:
    if lineNum is not None:
        return lineNum
    if el is not None and el.get("bs-line-number"):
        return el.get("bs-line-number", "")
    return None


def die(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    lineNum = getLineNum(lineNum, el)
    formattedMsg = formatMessage("fatal", msg, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("fatal", formattedMsg)
        if state.shouldPrint("fatal"):
            p(formattedMsg)
    if state.shouldDie("fatal"):
        errorAndExit()


def linkerror(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    lineNum = getLineNum(lineNum, el)
    suffix = ""
    if el is not None:
        if el.get("bs-autolink-syntax"):
            suffix = "\n" + t.cast(str, el.get("bs-autolink-syntax"))
        else:
            suffix = "\n" + lxml.html.tostring(el, with_tail=False, encoding="unicode")
    formattedMsg = formatMessage("link", msg + suffix, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("link-error", formattedMsg)
        if state.shouldPrint("link-error"):
            p(formattedMsg)
    if state.shouldDie("link-error"):
        errorAndExit()


def lint(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    lineNum = getLineNum(lineNum, el)
    suffix = ""
    if el is not None:
        if el.get("bs-autolink-syntax"):
            suffix = "\n" + t.cast(str, el.get("bs-autolink-syntax"))
        else:
            suffix = "\n" + lxml.html.tostring(el, with_tail=False, encoding="unicode")
    formattedMsg = formatMessage("lint", msg + suffix, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("lint", formattedMsg)
        if state.shouldPrint("lint"):
            p(formattedMsg)
    if state.shouldDie("lint"):
        errorAndExit()


def warn(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    if lineNum is None and el is not None and el.get("bs-line-number"):
        lineNum = el.get("bs-line-number")
    formattedMsg = formatMessage("warning", msg, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("warning", formattedMsg)
        if state.shouldPrint("warning"):
            p(formattedMsg)
    if state.shouldDie("warning"):
        errorAndExit()


def say(msg: str) -> None:
    if state.shouldPrint("message"):
        p(formatMessage("message", msg))


def success(msg: str) -> None:
    if state.shouldPrint("success"):
        p(formatMessage("success", msg))


def failure(msg: str) -> None:
    if state.shouldPrint("failure"):
        p(formatMessage("failure", msg))


def retroactivelyCheckErrorLevel(level: str | None = None, timing: str = "early") -> bool:
    if level is None:
        level = state.dieOn
    for levelName, msgCount in state.categoryCounts.items():
        if msgCount > 0 and state.shouldDie(levelName, timing):
            errorAndExit()
    return True


def printColor(text: str, color: str = "white", *styles: str) -> str:
    if state.printMode == "console":
        colorsConverter = {
            "black": 30,
            "red": 31,
            "green": 32,
            "yellow": 33,
            "blue": 34,
            "magenta": 35,
            "cyan": 36,
            "light gray": 37,
            "dark gray": 90,
            "light red": 91,
            "light green": 92,
            "light yellow": 93,
            "light blue": 94,
            "light magenta": 95,
            "light cyan": 96,
            "white": 97,
        }
        stylesConverter = {
            "normal": 0,
            "bold": 1,
            "bright": 1,
            "dim": 2,
            "underline": 4,
            "underlined": 4,
            "blink": 5,
            "reverse": 7,
            "invert": 7,
            "hidden": 8,
        }

        colorNum = colorsConverter[color.lower()]
        styleNum = ";".join(str(stylesConverter[style.lower()]) for style in styles)
        return f"\033[{styleNum};{colorNum}m{text}\033[0m"
    return text


def formatMessage(type: str, text: str, lineNum: str | int | None = None) -> str | tuple[str, str]:
    if state.printMode == "markup":
        text = text.replace("<", "&lt;")
        if type == "fatal":
            return f"<fatal>{text}</fatal>"
        if type == "link":
            return f"<linkerror>{text}</linkerror>"
        if type == "lint":
            return f"<lint>{text}</lint>"
        if type == "warning":
            return f"<warning>{text}</warning>"
        if type == "message":
            return f"<message>{text}</message>"
        if type == "success":
            return f"<final-success>{text}</final-success>"
        if type == "failure":
            return f"<final-failure>{text}</final-failure>"
    elif state.printMode == "json":
        if not state.seenMessages:
            jsonText = "[\n"
        else:
            jsonText = ""
        msg = {"lineNum": lineNum, "messageType": type, "text": text}
        jsonText += "  " + json.dumps(msg)
        if type in ("success", "failure"):
            jsonText += "\n]"
        else:
            jsonText += ", "
        return jsonText

    if type == "message":
        return text
    if type == "success":
        return (
            printColor(" ✔ ", "green", "invert") + " " + text,
            printColor("YAY", "green", "invert") + " " + text,
        )
    if type == "failure":
        return (
            printColor(" ✘ ", "red", "invert") + " " + text,
            printColor("ERR", "red", "invert") + " " + text,
        )
    if type == "fatal":
        headingText = "FATAL ERROR"
        color = "red"
    elif type == "link":
        headingText = "LINK ERROR"
        color = "yellow"
    elif type == "lint":
        headingText = "LINT"
        color = "yellow"
    elif type == "warning":
        headingText = "WARNING"
        color = "light cyan"
    if lineNum is not None:
        headingText = f"LINE {lineNum}"
    return printColor(headingText + ":", color, "bold") + " " + text


def errorAndExit() -> None:
    failure("Did not generate, due to errors exceeding the allowed error level.")
    sys.exit(2)


@contextlib.contextmanager
def withMessageState(
    fh: str | io.TextIOWrapper,
    **kwargs: t.Any,
) -> t.Generator[io.TextIOWrapper, None, None]:
    if isinstance(fh, str):
        fhIsTemporary = True
        fh = open(fh, "w", encoding="utf-8")
        assert isinstance(fh, io.TextIOWrapper)
    else:
        fhIsTemporary = False
    global state
    oldState = state
    state = oldState.replace(fh=fh, **kwargs)
    try:
        yield fh
    finally:
        state = oldState
        if fhIsTemporary:
            fh.close()


@contextlib.contextmanager
def messagesSilent() -> t.Generator[io.TextIOWrapper, None, None]:
    import os

    fh = open(os.devnull, "w", encoding="utf-8")
    global state
    oldState = state
    state = oldState.replace(fh=fh)
    try:
        yield fh
    finally:
        state = oldState
        fh.close()
