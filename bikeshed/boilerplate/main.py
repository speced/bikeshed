from __future__ import annotations

from .. import conditional, h, retrieve, t


# Fetches a given boilerplate, parses it, then inserts it into the boilerplate container.
# High-level simplistic action.
def loadBoilerplate(filename: str, tree: t.ElementT, doc: t.SpecT, bpname: str | None = None) -> None:
    if bpname is None:
        bpname = filename
    bpText = retrieve.retrieveBoilerplateFile(doc, filename)
    el = parseBoilerplate(bpText, context=f"{filename} boilerplate", doc=doc)
    fillWith(bpname, el, tree=tree, doc=doc)


# Takes already-processed elements, puts them into the boilerplate container with the given tag.
def fillWith(tag: str, newElements: t.NodesT, tree: t.ElementT, doc: t.SpecT) -> None:
    if (el := getFillContainer(tag, tree=tree, doc=doc)) is not None:
        h.replaceContents(el, newElements)
        return


# Gets the boilerplate container that *will* take some elements.
# Also serves as a check for whether to generate the elements at all.
def getFillContainer(tag: str, tree: t.ElementT, doc: t.SpecT, default: t.ElementT | None = None) -> t.ElementT | None:
    """
    Gets the element that should be filled with the stuff corresponding to tag.
    If it returns None, don't generate the section.

    If default=True,
    indicates that this is a "default on" section,
    and will be appended to <body> unless explicitly suppressed.
    Otherwise,
    it'll only be appended if explicitly requested with a data-fill-with attribute.
    """

    # If you've explicitly suppressed that section, don't do anything
    if tag not in doc.md.boilerplate:
        return None

    # If a fill-with is found, fill that

    if (fillEl := h.find(f"[data-fill-with='{tag}']", tree)) is not None:
        return fillEl

    # Otherwise, append to the end of the document,
    # unless you're in the byos group
    if doc.doctype.group.name == "BYOS":
        return None
    return default


# Takes html text, presumably from a boilerplate file, and processes it into elements.
# Boilerplates need to be processed in a few ways; *at least* conditionals but
# probably others that I'm not doing right now.
def parseBoilerplate(htmlString: str, context: str, doc: t.SpecT) -> t.NodesT:
    htmlString = h.parseText(htmlString, h.ParseConfig.fromSpec(doc, context=context), context=context)
    # FIXME: Here I'm having to pass a value that's already an EarlyParsedHtmlStr
    # (and thus should be safe for parsing into a doc) back thru h.safeHtml(),
    # because h.parseHTML() is still using the lxml parser, not my SimpleParser,
    # so the virtualLinebreak chars don't get handled unless I do it myself.
    bp = h.E.div({}, h.parseHTML(h.safeHtml(htmlString)))
    conditional.processConditionals(doc, bp)
    return h.childNodes(bp, clear=True)
