import sys
from lib.fuckunicode import u
import lib.config as config

def die(msg, *formatArgs):
    if not config.quiet:
        print u"\033[1;31mFATAL ERROR:\033[0m "+u(msg).format(*map(u, formatArgs))
    if not config.debug:
        sys.exit(1)

def warn(msg, *formatArgs):
    if not config.quiet:
        print u"\033[1;33mWARNING:\033[0m "+u(msg).format(*map(u, formatArgs))

def say(msg, *formatArgs):
    if not config.quiet:
        print u(msg).format(*map(u, formatArgs))

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