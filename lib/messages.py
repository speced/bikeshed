import sys
from lib.fuckunicode import u
import lib.config as config

def die(msg, *formatArgs):
    print u"\033[1;31mFATAL ERROR:\033[0m "+u(msg).format(*map(u, formatArgs))
    if not config.debug:
        sys.exit(1)

def warn(msg, *formatArgs):
    if not config.debugQuiet:
        print u"\033[1;34mWARNING:\033[0m "+u(msg).format(*map(u, formatArgs))

def say(msg, *formatArgs):
    if not config.debugQuiet:
        print u(msg).format(*map(u, formatArgs))

def progress(msg, val, total):
    if config.debugQuiet:
        return
    barSize = 20
    fractionDone = val / total
    hashes = "#" * int(fractionDone*barSize)
    spaces = " " * (barSize - int(fractionDone*barSize))
    print "\r{0} [{1}{2}] {3}%".format(msg, hashes, spaces, int(fractionDone*100)),
    if val == total:
        print
    sys.stdout.flush()