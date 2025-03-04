from __future__ import annotations

import dataclasses
import os

from . import h, t


@dataclasses.dataclass
class OutlineEntry:
    text: str
    id: str | None
    level: int
    lineNum: int


def printOutline(doc: t.Spec) -> str:
    entries = generateOutline(doc)
    lineNumWidth = max(len(str(e.lineNum)) for e in entries)
    idWidth = max(len(str(e.id or "")) for e in entries)
    consoleWidth = os.get_terminal_size().columns
    lines = []
    for entry in entries:
        if entry.level == 2:
            prefix = ""
        else:
            prefix = " " * (entry.level - 2)
        line = f"{entry.lineNum:{lineNumWidth}} | #{entry.id:{idWidth}} | {prefix}{entry.text}"
        if len(line) > consoleWidth:
            line = line[: consoleWidth - 2] + "…"
        lines.append(line)
    return "\n".join(lines)


def generateOutline(doc: t.Spec) -> list[OutlineEntry]:
    entries = []
    for el in collectHeadings(doc):
        text = h.textContent(el).strip().replace("\n", "")
        id = el.get("id", None)
        level = int((h.tagName(el) or "h0")[1])
        try:
            lineNum = int(el.get("bs-line-number", ""))
        except:
            try:
                num, _, rest = el.get("bs-line-number", "").partition(":")
                lineNum = int(num)
                int(rest)
            except:  # noqa: S112
                continue
        entries.append(OutlineEntry(text, id, level, lineNum))
    return entries


def collectHeadings(
    doc: t.Spec,
    root: t.ElementT | None = None,
    headings: list[t.ElementT] | None = None,
) -> list[t.ElementT]:
    if headings is None:
        headings = []
    if root is None:
        root = doc.body
    for child in h.childElements(root):
        if h.tagName(child) in ("h1", "h2", "h3", "h4", "h5", "h6"):
            headings.append(child)
        collectHeadings(doc, child, headings)
    return headings
