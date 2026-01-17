from __future__ import annotations

import copy
import dataclasses

from .. import h, t
from .. import messages as m
from ..translate import _t
from . import main


def addTOCSection(doc: t.SpecT, body: t.ElementT) -> None:
    tocContainer = main.getFillContainer("table-of-contents", doc=doc, tree=body)
    if tocContainer is None:
        return
    h.appendChild(
        tocContainer,
        h.E.h2(
            {"class": "no-num no-toc no-ref", "id": h.safeID(doc, "contents")},
            _t("Table of Contents"),
        ),
        buildTOCLevel(doc.tocEntries),
    )


def addTOCInner(doc: t.SpecT, body: t.ElementT) -> None:
    # *Just* the nested list of links, in case you want to customize the surrounding content.
    tocContainer = main.getFillContainer("toc-links", doc=doc, tree=body)
    if tocContainer is None:
        return
    h.appendChild(
        tocContainer,
        buildTOCLevel(doc.tocEntries),
    )


def buildTOCLevel(entries: list[TOCEntry]) -> t.ElementT:
    ol = h.E.ol({"class": "toc"})
    for entry in entries:
        h.appendChild(
            ol,
            h.E.li(
                h.E.a(
                    {"href": "#" + entry.id},
                    h.E.span({"class": "secno"}, entry.level),
                    " ",
                    copy.deepcopy(entry.content),
                ),
                buildTOCLevel(entry.children) if entry.children else [],
            ),
        )
    return ol


@dataclasses.dataclass
class TOCEntry:
    level: str
    id: str
    content: t.NodesT
    children: list[TOCEntry] = dataclasses.field(default_factory=list)


def buildTOCGraph(doc: t.SpecT, body: t.ElementT) -> list[TOCEntry]:
    # I use entries 2-6, corresponding to header levels.
    # 0 and 1 are just there to make the indexes work,
    root = TOCEntry("", "", [])
    containers: list[TOCEntry | None] = [None] * 7
    containers[1] = root
    prevLevel = 1
    for header in h.findAll("h2, h3, h4, h5, h6", body):
        level = int(header.tag[-1])
        container = containers[level - 1]
        if prevLevel == 1 and level > 2:
            # Saw a low-level heading without first seeing a higher heading.
            m.die(f"First heading in your content is <h{level}>, expected an <h2>.", el=header)
            return root.children
        if level > prevLevel + 1:
            # Jumping two+ levels is a no-no.
            m.die(f"Heading level jumps <h{prevLevel}> to <h{level}>.", el=header)
            return root.children

        if (
            h.hasClass(doc, header, "no-toc")
            or container is None
            or (doc.md.maxToCDepth and (level - 1) > doc.md.maxToCDepth)
        ):
            containers[level] = None
        else:
            content = copy.deepcopy(h.find(".content", header))
            assert content is not None
            entry = TOCEntry(header.get("data-level", ""), header.get("id", ""), cleanContent(content))
            container.children.append(entry)
            containers[level] = entry
        prevLevel = level
    return root.children


def cleanContent(content: t.ElementT) -> t.ElementT:
    for el in h.findAll("a, dfn", content):
        el.tag = "span"
        h.removeAttr(el, "href")
    for el in h.findAll("[id]", content):
        h.removeAttr(el, "id")
    return content
