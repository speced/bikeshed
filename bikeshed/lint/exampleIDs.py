from ..h import *
from ..messages import *


def exampleIDs(doc):
    """
    Checks that every example in the document has an ID.
    """
    if not doc.md.complainAbout["missing-example-ids"]:
        return
    for el in findAll(".example:not([id])", doc):
        warn(f"Example needs ID:\n{outerHTML(el)[0:100]}", el=el)
