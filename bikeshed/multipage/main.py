from __future__ import annotations

from .. import h, t
from .. import messages as m


def serializePages(doc: t.SpecT, mainFilename: str) -> dict[str, str]:
    main = h.find("main", doc)
    assert main is not None
    pages = collectIntoPages(list(h.childNodes(main, clear=True)), mainFilename)
    ret = {}
    serializer = h.Serializer(doc.md.opaqueElements, doc.md.blockElements)
    for filename, nodes in pages.items():
        h.childNodes(main, clear=True)
        h.appendChild(main, nodes)
        ret[filename] = serializer.serialize(doc.document)
    return ret


def collectIntoPages(nodes: list[t.NodeT], mainFilename: str) -> dict[str, list[t.NodeT]]:
    pages: dict[str, list[t.NodeT]] = {}
    filename = mainFilename
    pages[filename] = []
    for node in nodes:
        if h.isElement(node) and meaningfulHeading(node) and headingLevel(node) == 2:
            id = node.get("id")
            if not id:
                m.die("Heading doesn't have a useful ID, can't split on it.", el=node)
                return {}
            filename = id + ".html"
            pages[filename] = []
        pages[filename].append(node)
    return pages


def meaningfulHeading(el: t.ElementT) -> bool:
    if h.tagName(el) not in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return False
    lineNum = el.get("bs-line-number", "")
    if parsesAsInt(lineNum):
        return True
    else:
        num, _, rest = lineNum.partition(":")
        return parsesAsInt(num) and parsesAsInt(rest)


def parsesAsInt(s: str) -> bool:
    try:
        int(s)
        return True
    except:
        return False


def headingLevel(el: t.ElementT) -> int:
    tag = h.tagName(el)
    if tag not in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return 0
    return int(tag[1])
