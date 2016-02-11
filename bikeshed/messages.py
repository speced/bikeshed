# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import sys

import config


messages = set()

def p(msg):
    try:
        print msg
    except UnicodeEncodeError:
        warning = "\033[1;33mWARNING:\033[0m Your console does not understand Unicode.\n  Messages may be slightly corrupted."
        if warning not in messages:
            print warning
            messages.add(warning)
        print msg.encode("ascii", "xmlcharrefreplace")


def die(msg, *formatArgs, **namedArgs):
    if config.quiet < 2:
        msg = "\033[1;31mFATAL ERROR:\033[0m "+msg.format(*formatArgs, **namedArgs)
        if msg not in messages:
            messages.add(msg)
            p(msg)
    if not config.force:
        sys.exit(1)

def warn(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        msg = "\033[1;33mWARNING:\033[0m "+msg.format(*formatArgs, **namedArgs)
        if msg not in messages:
            messages.add(msg)
            p(msg)

def say(msg, *formatArgs, **namedArgs):
    if config.quiet < 1:
        p(msg.format(*formatArgs, **namedArgs))

def resetSeenMessages():
    global messages
    messages = set()
