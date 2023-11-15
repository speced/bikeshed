from __future__ import annotations

from .stringEnum import StringEnum

dryRun: bool = False
refStatus: StringEnum = StringEnum("current", "snapshot")
biblioDisplay: StringEnum = StringEnum("index", "inline", "direct")
chroot: bool = True
executeCode: bool = False

macroStartChar = "\uebbb"
macroEndChar = "\uebbc"
incrementLineCountChar = "\uebbd"
decrementLineCountChar = "\uebbf"
bsComment = "<!--\uebbe-->"
