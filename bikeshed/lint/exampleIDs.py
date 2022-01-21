from .. import h, messages as m


def exampleIDs(doc):
    """
    Checks that every example in the document has an ID.
    """
    if not doc.md.complainAbout["missing-example-ids"]:
        return
    for el in h.findAll(".example:not([id])", doc):
        m.warn(f"Example needs ID:\n{h.outerHTML(el)[0:100]}", el=el)
