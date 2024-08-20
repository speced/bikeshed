from __future__ import annotations

from . import config, h, t
from . import messages as m


def processHeadings(doc: t.SpecT, scope: str = "doc") -> None:
    # scope arg can be "doc" or "all"
    # "doc" ignores things that are part of boilerplate
    for el in h.findAll("h2, h3, h4, h5, h6", doc):
        h.addClass(doc, el, "heading")
    headings = []
    for el in h.findAll(".heading:not(.settled)", doc):
        if scope == "doc" and h.treeAttr(el, "boilerplate"):
            continue
        headings.append(el)
    resetHeadings(headings)
    determineHeadingLevels(doc, headings)
    addHeadingIds(doc, headings)
    addHeadingAlgorithms(headings)
    h.fixupIDs(doc, headings)
    addHeadingBonuses(headings)
    for el in headings:
        h.addClass(doc, el, "settled")
    if scope == "all" and doc.doctype.group.privSec:
        checkPrivacySecurityHeadings(doc, h.findAll(".heading", doc))


def resetHeadings(headings: list[t.ElementT]) -> None:
    for header in headings:
        content = h.E.span({"class": "content"})
        h.moveContents(content, header)
        h.appendChild(header, content)


def addHeadingIds(doc: t.SpecT, headings: list[t.ElementT]) -> None:
    neededIds = set()
    for header in headings:
        if header.get("id") is None:
            if header.get("data-dfn-type") is None:
                # dfn headings will get their IDs assigned by the dfn code
                neededIds.add(header)
                contentEl = t.cast("t.ElementT", h.find(".content", header))
                id = config.simplifyText(h.textContent(contentEl))
                header.set("id", h.safeID(doc, id))
    h.addOldIDs(headings)
    if len(neededIds) == 0:
        pass
    elif 1 <= len(neededIds) <= 5:
        for el in h.sortElements(neededIds):
            m.warn(f"The heading '{h.textContent(el)}' needs a manually-specified ID.", el=el)
    else:
        m.warn(
            "You should manually provide IDs for your headings:\n"
            + "\n".join("  " + h.textContent(el) for el in h.sortElements(neededIds)),
        )


def checkPrivacySecurityHeadings(doc: t.SpecT, headings: list[t.ElementT]) -> None:
    security = False
    privacy = False
    for header in headings:
        contentEl = t.cast("t.ElementT", h.find(".content", header))
        text = h.textContent(contentEl).lower()
        if "security" in text and "considerations" in text:
            security = True
        if "privacy" in text and "considerations" in text:
            privacy = True
        if "security" in text and "privacy" in text and "considerations" in text and doc.doctype.org.name == "W3C":
            m.warn(
                "W3C policy requires Privacy Considerations and Security Considerations to be separate sections, but you appear to have them combined into one.",
                el=header,
            )
        if security and privacy:
            return
    if not security and not privacy:
        m.warn(
            "This specification has neither a 'Security Considerations' nor a 'Privacy Considerations' section. Please consider adding both, see https://w3ctag.github.io/security-questionnaire/.",
        )
    elif not security:
        m.warn(
            "This specification does not have a 'Security Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/.",
        )
    elif not privacy:
        m.warn(
            "This specification does not have a 'Privacy Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/.",
        )


def addHeadingAlgorithms(headings: list[t.ElementT]) -> None:
    for header in headings:
        if header.get("data-algorithm") == "":
            header.set("data-algorithm", h.textContent(header).strip())


def determineHeadingLevels(doc: t.SpecT, headings: list[t.ElementT]) -> None:
    headerLevel = [0, 0, 0, 0, 0]

    def incrementLevel(level: int) -> None:
        headerLevel[level - 2] += 1
        for i in range(level - 1, 5):
            headerLevel[i] = 0

    def printLevel() -> str:
        return ".".join(str(x) for x in headerLevel if x > 0)

    skipLevel = float("inf")
    for header in headings:
        # Add the heading number.
        level = int(header.tag[-1])

        # Reset, if this is a re-run.
        if header.get("data-level"):
            del header.attrib["data-level"]

        # If we encounter a no-num or an appendix, don't number it or any in the same section.
        if h.hasClass(doc, header, "no-num") or h.textContent(header).lstrip()[0:9].lower() == "appendix ":
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue

        skipLevel = float("inf")

        incrementLevel(level)
        header.set("data-level", printLevel())


def addHeadingBonuses(headings: list[t.ElementT]) -> None:
    for header in headings:
        level = header.get("data-level")
        if level is not None:
            secno = h.E.span({"class": "secno"}, level + ". ")
            header.insert(0, secno)
