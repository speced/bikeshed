# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import sys
from collections import Counter

import config


messages = set()
messageCounts = Counter()

def p(msg):
    try:
        print msg
    except UnicodeEncodeError:
        warning = formatMessage("warning", "Your console does not understand Unicode.\n  Messages may be slightly corrupted.")
        if warning not in messages:
            print warning
            messages.add(warning)
        print msg.encode("ascii", "xmlcharrefreplace")


def die(msg, *formatArgs, **namedArgs):
    messageCounts["fatal"] += 1
    if config.quiet < 2:
        msg = formatMessage("fatal", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)
    if not config.force:
        sys.exit(1)

def linkerror(msg, *formatArgs, **namedArgs):
    messageCounts["linkerror"] += 1
    if config.quiet < 1:
        msg = formatMessage("link", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)

def warn(msg, *formatArgs, **namedArgs):
    messageCounts["warning"] += 1
    if config.quiet < 1:
        msg = formatMessage("warning", msg.format(*formatArgs, **namedArgs))
        if msg not in messages:
            messages.add(msg)
            p(msg)

def say(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        p(msg.format(*formatArgs, **namedArgs))

def resetSeenMessages():
    global messages
    messages = set()
    global messageCounts
    messageCounts = Counter()

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

def formatMessage(type, text):
    if config.printMode == "markup":
        text = text.replace("<", "&lt;")
        if type == "fatal":
            return "<fatal>{0}</fatal>".format(text)
        elif type == "link":
            return "<linkerror>{0}</linkerror>".format(text)
        elif type == "warning":
            return "<warning>{0}</warning>".format(text)
        elif type == "message":
            return "<message>{0}</message>".format(text)
    else:
        if type == "message":
            return text
        if type == "fatal":
            headingText = "FATAL ERROR"
            color = "red"
        elif type == "link":
            headingText = "LINK ERROR"
            color = "yellow"
        elif type == "warning":
            headingText = "WARNING"
            color = "light cyan"
        x  = printColor(headingText + ":", color, "bold")
        x += " "
        x += text
        return x
