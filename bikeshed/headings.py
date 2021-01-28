from . import config
from .config import simplifyText
from .h import *
from .messages import *


def processHeadings(doc, scope="doc"):
    # scope arg can be "doc" or "all"
    # "doc" ignores things that are part of boilerplate
    for el in findAll("h2, h3, h4, h5, h6", doc):
        addClass(el, "heading")
    headings = []
    for el in findAll(".heading:not(.settled)", doc):
        if scope == "doc" and treeAttr(el, "boilerplate"):
            continue
        headings.append(el)
    resetHeadings(headings)
    determineHeadingLevels(headings)
    addHeadingIds(doc, headings)
    addHeadingAlgorithms(headings)
    fixupIDs(doc, headings)
    addHeadingBonuses(headings)
    for el in headings:
        addClass(el, "settled")
    if scope == "all" and doc.md.group in config.megaGroups["priv-sec"]:
        checkPrivacySecurityHeadings(findAll(".heading", doc))


def resetHeadings(headings):
    for header in headings:
        # Reset to base, if this is a re-run
        if find(".content", header) is not None:
            content = find(".content", header)
            moveContents(header, content)

        # Insert current header contents into a <span class='content'>
        content = E.span({"class": "content"})
        moveContents(content, header)
        appendChild(header, content)


def addHeadingIds(doc, headings):
    neededIds = set()
    for header in headings:
        if header.get("id") is None:
            if header.get("data-dfn-type") is None:
                # dfn headings will get their IDs assigned by the dfn code
                neededIds.add(header)
                id = simplifyText(textContent(find(".content", header)))
                header.set("id", safeID(doc, id))
    addOldIDs(headings)
    if len(neededIds) > 0:
        warn(
            "You should manually provide IDs for your headings:\n{0}",
            "\n".join("  " + outerHTML(el) for el in neededIds),
        )


def checkPrivacySecurityHeadings(headings):
    security = False
    privacy = False
    for header in headings:
        text = textContent(find(".content", header)).lower()
        if "security" in text and "considerations" in text:
            security = True
        if "privacy" in text and "considerations" in text:
            privacy = True
        if security and privacy:
            # No need to look any further!
            return
    if not security and not privacy:
        warn(
            "This specification has neither a 'Security Considerations' nor a 'Privacy Considerations' section. Please consider adding both, see https://w3ctag.github.io/security-questionnaire/."
        )
    elif not security:
        warn(
            "This specification does not have a 'Security Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/."
        )
    elif not privacy:
        warn(
            "This specification does not have a 'Privacy Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/."
        )


def addHeadingAlgorithms(headings):
    for header in headings:
        if header.get("data-algorithm") == "":
            header.set("data-algorithm", textContent(header).strip())


def determineHeadingLevels(headings):
    headerLevel = [0, 0, 0, 0, 0]

    def incrementLevel(level):
        headerLevel[level - 2] += 1
        for i in range(level - 1, 5):
            headerLevel[i] = 0

    def printLevel():
        return ".".join(str(x) for x in headerLevel if x > 0)

    skipLevel = float("inf")
    for header in headings:
        # Add the heading number.
        level = int(header.tag[-1])

        # Reset, if this is a re-run.
        if header.get("data-level"):
            del header.attrib["data-level"]

        # If we encounter a no-num or an appendix, don't number it or any in the same section.
        if (
            hasClass(header, "no-num")
            or textContent(header).lstrip()[0:9].lower() == "appendix "
        ):
            skipLevel = min(level, skipLevel)
            continue
        if skipLevel < level:
            continue

        skipLevel = float("inf")

        incrementLevel(level)
        header.set("data-level", printLevel())


def addHeadingBonuses(headings):
    for header in headings:
        if header.get("data-level") is not None:
            secno = E.span({"class": "secno"}, header.get("data-level") + ". ")
            header.insert(0, secno)
