debug = False
debugQuiet = False

def die(msg, *formatArgs):
    global debug
    print u"FATAL ERROR: "+u(msg).format(*map(u, formatArgs))
    if not debug:
        sys.exit(1)

def warn(msg, *formatArgs):
    global debugQuiet
    if not debugQuiet:
        print u"WARNING: "+u(msg).format(*map(u, formatArgs))

def say(msg, *formatArgs):
    global debugQuiet
    if not debugQuiet:
        print u(msg).format(*map(u, formatArgs))

def progress(msg, val, total):
    global debugQuiet
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