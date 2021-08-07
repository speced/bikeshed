from .stringEnum import StringEnum

dryRun = False
errorLevel = ["fatal"]
printMode = "console"
quiet = True
asciiOnly = False
refStatus = StringEnum("current", "snapshot")
biblioDisplay = StringEnum("index", "inline")
specClass = None
testAnnotationURL = "https://test.csswg.org/harness/annotate.js"
chroot = True
executeCode = False


def errorLevelAt(target):
    levels = {
        "nothing": 0,
        "fatal": 1,
        "link-error": 2,
        "warning": 3,
        "everything": 1000,
    }
    currentLevel = levels[errorLevel[0]]
    targetLevel = levels[target]
    return currentLevel >= targetLevel


def setErrorLevel(level=None):
    if level is None:
        level = "fatal"
    errorLevel[0] = level
