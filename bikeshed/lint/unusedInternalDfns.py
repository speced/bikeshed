from __future__ import annotations

from .. import config, h, t
from .. import messages as m


def unusedInternalDfns(doc: t.SpecT) -> None:
    """
    The export/noexport distinction assumes that noexport dfns are meant to be internal-only.
    If you don't actually *use* a noexport dfn, that's probably an error.
    In particular, this'll probably help find *untagged* dfns that are defaulting to noexport.
    """
    noexportDfns = [el for el in h.findAll(config.dfnElementsSelector, doc) if warnAboutUnused(el)]

    localHrefs = [el.get("href", "")[1:] for el in h.findAll("a", doc) if local(doc, el)]

    for el in noexportDfns:
        if el.get("id") not in localHrefs:
            m.lint(
                f"Unexported dfn for '{h.textContent(el)}' that's not referenced locally - did you mean to export it?",
                el=el,
            )


def warnAboutUnused(el: t.ElementT) -> bool:
    return el.get("data-noexport") == "by-default" and el.get("data-dfn-type") not in config.unexportedIgnorableTypes


def local(doc: t.SpecT, el: t.ElementT) -> bool:
    return (
        el.get("href") is not None
        and el.get("href", "").startswith("#")
        and not h.hasClass(doc, el, "self-link")
        and h.closestAncestor(el, lambda x: h.hasClass(doc, x, "index")) is None
    )
