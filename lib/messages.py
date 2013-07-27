from fuckunicode import u
import sys

debug = False
debugQuiet = False

def die(msg, *formatArgs):
    print u"FATAL ERROR: "+u(msg).format(*map(u, formatArgs))
    if not debug:
        sys.exit(1)

def warn(msg, *formatArgs):
    if not debugQuiet:
        print u"WARNING: "+u(msg).format(*map(u, formatArgs))

def say(msg, *formatArgs):
    if not debugQuiet:
        print u(msg).format(*map(u, formatArgs))

def progress(msg, val, total):
    if debugQuiet:
        return
    barSize = 20
    fractionDone = val / total
    hashes = "#" * int(fractionDone*barSize)
    spaces = " " * (barSize - int(fractionDone*barSize))
    print "\r{0} [{1}{2}] {3}%".format(msg, hashes, spaces, int(fractionDone*100)),
    if val == total:
        print
    sys.stdout.flush()