from __future__ import annotations

from .. import t


def annotateDfns(doc: t.SpecT) -> None:
    from . import attributeInfo

    attributeInfo.addAttributeInfoSpans(doc)
    attributeInfo.fillAttributeInfoSpans(doc)
