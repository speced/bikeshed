from __future__ import annotations

from .stringEnum import StringEnum

dryRun: bool = False
refStatus: StringEnum = StringEnum("current", "snapshot")
biblioDisplay: StringEnum = StringEnum("index", "inline", "direct")
chroot: bool = True
executeCode: bool = False

# Mark the start and end of macro expansions, so adjacent expansions
# can't each accidentally supply half of a macro.
macroStartChar = "\uebbb"
macroEndChar = "\uebbc"
