# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import sys

import config


messages = set()

def p(msg):
    try:
        print msg
    except UnicodeEncodeError:
        warning = printHeading("WARNING", "light cyan", "Your console does not understand Unicode.\n  Messages may be slightly corrupted.")
        if warning not in messages:
            print warning
            messages.add(warning)
        print msg.encode("ascii", "xmlcharrefreplace")


def die(msg, *formatArgs, **namedArgs):
    if config.quiet < 2:
        msg = printHeading("FATAL ERROR", "red", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)
    if not config.force:
        sys.exit(1)

def linkerror(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        msg = printHeading("LINK ERROR", "yellow", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)

def warn(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        msg = printHeading("WARNING", "light cyan", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)

def say(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        p(msg.format(*formatArgs, **namedArgs))

def resetSeenMessages():
    global messages
    messages = set()

def printColor(text, color="white", *styles):
    if config.printMode == "plain":
        return text
    elif config.printMode == "console":
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
            "white": 97
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
            "hidden": 8
        }

        colorNum = colorsConverter[color.lower()]
        styleNum = ";".join(str(stylesConverter[style.lower()]) for style in styles)
        return "\033[{0};{1}m{text}\033[0m".format(styleNum, colorNum, text=text)

def printHeading(headingText, color, text):
    x  = printColor(headingText + ":", color, "bold")
    x += " "
    x += text
    return x
