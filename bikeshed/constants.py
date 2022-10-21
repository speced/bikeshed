from __future__ import annotations
from .stringEnum import StringEnum

dryRun: bool = False
errorLevel: list[str] = ["fatal"]
printMode: str = "console"
quiet: float = 0
asciiOnly: bool = False
refStatus: StringEnum = StringEnum("current", "snapshot")
biblioDisplay: StringEnum = StringEnum("index", "inline", "direct")
testAnnotationURL: str = "https://test.csswg.org/harness/annotate.js"
chroot: bool = True
executeCode: bool = False


def errorLevelAt(target: str) -> bool:
    levels = {
        "nothing": 0,
        "fatal": 1,
        "link-error": 2,
        "warning": 3,
        "lint": 4,
        "everything": 1000,
    }
    currentLevel = levels[errorLevel[0]]
    targetLevel = levels[target]
    return currentLevel >= targetLevel


def setErrorLevel(level: str | None = None) -> None:
    if level is None:
        level = "fatal"
    errorLevel[0] = level
