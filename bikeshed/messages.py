from __future__ import annotations

import contextlib
import dataclasses
import io
import sys
from collections import Counter

import lxml.html

from . import t

@dataclasses.dataclass
class MessagesState:
    dieOn: str = "fatal"
    printMode: str = "console"
    asciiOnly: bool = False
    quiet: float = 0
    fh: io.TextIOWrapper = t.cast("io.TextIOWrapper", sys.stdout)
    seenMessages: set[str | tuple[str, str]] = dataclasses.field(default_factory=set)
    categoryCounts: Counter[str] = dataclasses.field(default_factory=Counter)

    def record(self, category: str, message: str | tuple[str, str]) -> None:
        self.categoryCounts[category] += 1
        self.seenMessages.add(message)

    def replace(self, **kwargs: t.Any) -> MessagesState:
        return dataclasses.replace(self, seenMessages=set(), categoryCounts=Counter(), **kwargs)

    def shouldDieFrom(self, category: str) -> bool:
        levels = {
            "nothing": 0,
            "fatal": 1,
            "link-error": 2,
            "warning": 3,
            "lint": 4,
            "everything": 1000,
        }
        currentLevel = levels[self.dieOn]
        queriedLevel = levels[category]
        return currentLevel >= queriedLevel


state = MessagesState()


def p(msg: str | tuple[str, str], sep: str | None = None, end: str | None = None) -> None:
    if state.quiet == float("infinity"):
        return
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


def die(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    if lineNum is None and el is not None and el.get("bs-line-number"):
        lineNum = el.get("bs-line-number")
    formattedMsg = formatMessage("fatal", msg, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.categoryCounts["fatal"] += 1
        state.seenMessages.add(formattedMsg)
        if state.quiet < 3:
            p(formattedMsg)
    if state.shouldDieFrom("fatal"):
        errorAndExit()


def linkerror(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    if lineNum is None and el is not None and el.get("bs-line-number"):
        lineNum = el.get("bs-line-number")
    suffix = ""
    if el is not None:
        if el.get("bs-autolink-syntax"):
            suffix = "\n" + t.cast(str, el.get("bs-autolink-syntax"))
        else:
            suffix = "\n" + lxml.html.tostring(el, with_tail=False, encoding="unicode")
    formattedMsg = formatMessage("link", msg + suffix, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("link-error", formattedMsg)
        if state.quiet < 2:
            p(formattedMsg)
    if state.shouldDieFrom("link-error"):
        errorAndExit()


def lint(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    if lineNum is None and el is not None and el.get("bs-line-number"):
        lineNum = el.get("bs-line-number")
    suffix = ""
    if el is not None:
        if el.get("bs-autolink-syntax"):
            suffix = "\n" + t.cast(str, el.get("bs-autolink-syntax"))
        else:
            suffix = "\n" + lxml.html.tostring(el, with_tail=False, encoding="unicode")
    formattedMsg = formatMessage("lint", msg + suffix, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("lint", formattedMsg)
        if state.quiet < 1:
            p(formattedMsg)
    if state.shouldDieFrom("lint"):
        errorAndExit()


def warn(msg: str, el: t.ElementT | None = None, lineNum: str | int | None = None) -> None:
    if lineNum is None and el is not None and el.get("bs-line-number"):
        lineNum = el.get("bs-line-number")
    formattedMsg = formatMessage("warning", msg, lineNum=lineNum)
    if formattedMsg not in state.seenMessages:
        state.record("warning", formattedMsg)
        if state.quiet < 1:
            p(formattedMsg)
    if state.shouldDieFrom("warning"):
        errorAndExit()


def say(msg: str) -> None:
    if state.quiet < 1:
        p(formatMessage("message", msg))


def success(msg: str) -> None:
    if state.quiet < 4:
        p(formatMessage("success", msg))


def failure(msg: str) -> None:
    if state.quiet < 4:
        p(formatMessage("failure", msg))


def retroactivelyCheckErrorLevel(level: str | None = None) -> bool:
    if level is None:
        level = state.dieOn
    for levelName, msgCount in state.categoryCounts.items():
        if msgCount > 0 and state.shouldDieFrom(levelName):
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
