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

# When a ParserNode serializes as less or more lines than it was in the source,
# these are emitted to let the Markdown parser keep accurate track of what
# source line it's on.
incrementLineCountChar = "\uebbd"
decrementLineCountChar = "\uebbf"

# When I encounter a comment, it's retained in the source, but turned into a
# standardized char sequence so the Markdown parser can more easily ignore it.
bsComment = "<!--\uebbe-->"

# When I encounter a Markdown blockquote, these mark the beginning and end of
# a new blockquote (so the parser can expand them into <blockquote> and </blockquote>)
# and any middle lines. These also help me detect when a blockquote was
# incorrectly detected and the author meant to just close a tag.
bqChar = "\uebc0"


# TODO: remove. These *were* used to mark end tags auto-inserted by the parser,
# but I now handle that in SimpleParser instead.
virtualEndTag = "\uebc3"

# Marks what was originally a linebreak in the smuggled contents of a block, so that
# the element can be serialized on a single line hidden from Markdown, and
# afterwards I can restore the element's contents.
virtualLineBreak = "\uebc4"
