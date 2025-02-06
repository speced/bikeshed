from __future__ import annotations

from .. import t
from . import oldShorthands


def run(doc: t.SpecT) -> None:
    oldShorthands.transformMarkdownIB(doc)
    oldShorthands.transformProductionGrammars(doc)
