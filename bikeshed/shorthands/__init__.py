from __future__ import annotations

from . import oldShorthands

from .. import t


def run(doc: t.SpecT) -> None:
    oldShorthands.transformShorthandElements(doc)
    oldShorthands.transformProductionPlaceholders(doc)
    oldShorthands.transformMaybePlaceholders(doc)
    oldShorthands.transformAutolinkShortcuts(doc)
    oldShorthands.transformProductionGrammars(doc)
