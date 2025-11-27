from __future__ import annotations

from .. import h, t
from .. import messages as m


def exampleIDs(doc: t.SpecT) -> None:
    """
    Checks that every example in the document has an ID.
    """
    if not doc.md.complainAbout["missing-example-ids"]:
        return
    for el in h.findAll(".example:not([id])", doc):
        m.lint("Example is missing an ID.", el=el)
