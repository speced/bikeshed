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

# When I encounter a Markdown blockquote, these mark the beginning and end of
# a new blockquote (so the parser can expand them into <blockquote> and </blockquote>)
# and any middle lines. These also help me detect when a blockquote was
# incorrectly detected and the author meant to just close a tag.
bqChar = "\uebc0"
