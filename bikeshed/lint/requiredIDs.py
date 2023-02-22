from __future__ import annotations

from .. import h, messages as m, t


def requiredIDs(doc: t.SpecT) -> None:
    if not doc.md.requiredIDs:
        return
    doc_ids = {e.get("id") for e in h.findAll("[id]", doc)}
    for id in doc.md.requiredIDs:
        if id.startswith("#"):
            id = id[1:]
        if id not in doc_ids:
            m.die(f"Required ID '{id}' was not found in the document.")
