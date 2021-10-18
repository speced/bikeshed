from . import oldShorthands


def run(doc):
    oldShorthands.transformShorthandElements(doc)
    oldShorthands.transformProductionPlaceholders(doc)
    oldShorthands.transformMaybePlaceholders(doc)
    oldShorthands.transformAutolinkShortcuts(doc)
    oldShorthands.transformProductionGrammars(doc)
