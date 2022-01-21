from . import config, h, messages as m


def processHeadings(doc, scope="doc"):
    # scope arg can be "doc" or "all"
    # "doc" ignores things that are part of boilerplate
    for el in h.findAll("h2, h3, h4, h5, h6", doc):
        h.addClass(el, "heading")
    headings = []
    for el in h.findAll(".heading:not(.settled)", doc):
        if scope == "doc" and h.treeAttr(el, "boilerplate"):
            continue
        headings.append(el)
    resetHeadings(headings)
    determineHeadingLevels(headings)
    addHeadingIds(doc, headings)
    addHeadingAlgorithms(headings)
    h.fixupIDs(doc, headings)
    addHeadingBonuses(headings)
    for el in headings:
        h.addClass(el, "settled")
    if scope == "all" and doc.md.group in config.megaGroups["priv-sec"]:
        checkPrivacySecurityHeadings(h.findAll(".heading", doc))


def resetHeadings(headings):
    for header in headings:
        # Reset to base, if this is a re-run
        if h.find(".content", header) is not None:
            content = h.find(".content", header)
            h.moveContents(header, content)

        # Insert current header contents into a <span class='content'>
        content = h.E.span({"class": "content"})
        h.moveContents(content, header)
        h.appendChild(header, content)


def addHeadingIds(doc, headings):
    neededIds = set()
    for header in headings:
        if header.get("id") is None:
            if header.get("data-dfn-type") is None:
                # dfn headings will get their IDs assigned by the dfn code
                neededIds.add(header)
                id = config.simplifyText(h.textContent(h.find(".content", header)))
                header.set("id", h.safeID(doc, id))
    h.addOldIDs(headings)
    if len(neededIds) == 0:
        pass
    elif 1 <= len(neededIds) <= 5:
        for el in neededIds:
            m.warn(f"The heading '{h.textContent(el)}' needs a manually-specified ID.", el=el)
    else:
        m.warn(
            "You should manually provide IDs for your headings:\n"
            + "\n".join("  " + h.textContent(el) for el in neededIds)
        )


def checkPrivacySecurityHeadings(headings):
    security = False
    privacy = False
    for header in headings:
        text = h.textContent(h.find(".content", header)).lower()
        if "security" in text and "considerations" in text:
            security = True
        if "privacy" in text and "considerations" in text:
            privacy = True
        if "security" in text and "privacy" in text and "considerations" in text:
            m.warn(
                "W3C policy requires Privacy Considerations and Security Considerations to be separate sections, but you appear to have them combined into one.",
                el=header,
            )
        if security and privacy:
            return
    if not security and not privacy:
        m.warn(
            "This specification has neither a 'Security Considerations' nor a 'Privacy Considerations' section. Please consider adding both, see https://w3ctag.github.io/security-questionnaire/."
        )
    elif not security:
        m.warn(
            "This specification does not have a 'Security Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/."
        )
    elif not privacy:
        m.warn(
            "This specification does not have a 'Privacy Considerations' section. Please consider adding one, see https://w3ctag.github.io/security-questionnaire/."
        )


def addHeadingAlgorithms(headings):
    for header in headings:
        if header.get("data-algorithm") == "":
            header.set("data-algorithm", h.textContent(header).strip())


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
        if h.hasClass(header, "no-num") or h.textContent(header).lstrip()[0:9].lower() == "appendix ":
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
            secno = h.E.span({"class": "secno"}, header.get("data-level") + ". ")
            header.insert(0, secno)
