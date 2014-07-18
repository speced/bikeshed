# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import sys

from . import config


messages = set()

def die(msg, *formatArgs, **namedArgs):
    msg = "\033[1;31mFATAL ERROR:\033[0m "+msg.format(*formatArgs, **namedArgs)
    if msg not in messages:
        messages.add(msg)
        print msg
    if not config.debug:
        sys.exit(1)

def warn(msg, *formatArgs, **namedArgs):
    if not config.quiet:
        msg = "\033[1;33mWARNING:\033[0m "+msg.format(*formatArgs, **namedArgs)
        if msg not in messages:
            messages.add(msg)
            print msg

def say(msg, *formatArgs, **namedArgs):
    if not config.quiet:
        print msg.format(*formatArgs, **namedArgs)

def progress(msg, val, total):
    if config.quiet:
        return
    barSize = 20
    fractionDone = val / total
    hashes = "#" * int(fractionDone*barSize)
    spaces = " " * (barSize - int(fractionDone*barSize))
    print "\r{0} [{1}{2}] {3}%".format(msg, hashes, spaces, int(fractionDone*100)),
    if val == total:
        print
    sys.stdout.flush()
