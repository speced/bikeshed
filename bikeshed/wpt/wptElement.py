from __future__ import annotations

from .. import config, h, messages as m, t
from ..translate import _


def processWptElements(doc: t.SpecT) -> None:
    pathPrefix = doc.md.wptPathPrefix

    atLeastOneElement = False
    atLeastOneVisibleTest = False
    testData = None
    # <wpt> elements
    wptElements = h.findAll("wpt", doc)
    seenTestNames = set()
    prevEl = None
    for el in wptElements:
        if atLeastOneElement is False and el.get("hidden") is None:
            atLeastOneElement = True
        if testData is None:
            testData = loadTestData(doc)
        assert testData is not None
        testNames = testNamesFromEl(el, pathPrefix=pathPrefix)
        for testName in testNames:
            if testName not in testData:
                m.warn(f"Couldn't find WPT test '{testName}' - did you misspell something?", el=el)
                continue
            seenTestNames.add(testName)
            if atLeastOneVisibleTest is False and el.get("hidden") is None:
                atLeastOneVisibleTest = True
        testNames = [x for x in testNames if x in seenTestNames]
        if el.get("hidden") is not None:
            h.removeNode(el)
        else:
            title = el.get("title")
            titleLang = el.get("lang")
            titleDir = el.get("dir")
            if prevEl is not None and prevEl.getnext() is el and (prevEl.tail is None or prevEl.tail.strip() == ""):
                appendTestList(prevEl, testNames, testData, title, titleLang, titleDir)
                h.removeNode(el)
            else:
                createHTML(doc, el, testNames, testData, title, titleLang, titleDir)
                prevEl = el

    # <wpt-rest> elements
    wptRestElements = h.findAll("wpt-rest", doc)
    if wptRestElements:
        if testData is None:
            testData = loadTestData(doc)
        assert testData is not None
        if len(wptRestElements) > 1:
            m.die(f"Only one <wpt-rest> element allowed per document, you have {len(wptRestElements)}.")
            wptRestElements = wptRestElements[0:1]
        else:
            localPrefix = wptRestElements[0].get("pathprefix")
            if localPrefix is not None:
                pathPrefix = localPrefix
            if pathPrefix is None:
                m.die("Can't use <wpt-rest> without either a pathprefix='' attribute or a 'WPT Path Prefix' metadata.")
                return
            prefixedNames = [p for p in testData if prefixInPath(pathPrefix, p) and p not in seenTestNames]
            if len(prefixedNames) == 0:
                m.die(f"Couldn't find any tests with the path prefix '{pathPrefix}'.")
                return
            atLeastOneElement = True
            atLeastOneVisibleTest = True
            createHTML(doc, wptRestElements[0], prefixedNames, testData)
            m.warn(
                "<wpt-rest> is intended for debugging only. Move the tests to <wpt> elements next to what they're testing."
            )
    else:
        if pathPrefix:
            if testData is None:
                testData = loadTestData(doc)
            checkForOmittedTests(pathPrefix, testData, seenTestNames)

    if atLeastOneVisibleTest:
        if pathPrefix is None:
            pathPrefix = commonPathPrefix(seenTestNames)
        if pathPrefix and not pathPrefix.startswith("/"):
            pathPrefix = "/" + pathPrefix
        if pathPrefix != "/":
            doc.md.otherMetadata.setdefault(_("Test Suite"), []).append(
                h.E.dd(
                    {"class": "wpt-overview"},
                    h.E.a(
                        {"href": f"https://wpt.fyi/results{pathPrefix}"},
                        f"https://wpt.fyi/results{pathPrefix}",
                    ),
                )
            )

    if doc.md.wptDisplay != "none" and atLeastOneElement:
        # Empty <wpt> blocks still need styles
        doc.extraStyles["style-wpt"] = wptStyle
        if atLeastOneVisibleTest:
            # But I only need script if there's actually some tests.
            doc.extraScripts["script-wpt"] = getWptScript(pathPrefix)


def createHTML(
    doc: t.SpecT,
    blockEl: t.ElementT,
    testNames: list[str],
    testData: dict[str, str],
    title: str | None = None,
    titleLang: str | None = None,
    titleDir: str | None = None,
) -> None:
    if doc.md.wptDisplay == "none":
        h.removeNode(blockEl)
    elif doc.md.wptDisplay in ("inline", "open", "closed"):
        blockEl.tag = "details"
        h.addClass(doc, blockEl, "wpt-tests-block")
        h.removeAttr(blockEl, "pathprefix")
        h.removeAttr(blockEl, "title")
        blockEl.set("lang", "en")
        blockEl.set("dir", "ltr")
        if doc.md.wptDisplay in ("open", "inline"):
            blockEl.set("open", "")
        h.clearContents(blockEl)
        testSummaryEl = h.E.summary(_("Tests"))
        h.appendChild(blockEl, testSummaryEl)
        appendTestList(blockEl, testNames, testData, title, titleLang, titleDir)
    else:
        m.die("Programming error, uncaught WPT Display value in createHTML.")


def appendTestList(
    blockEl: t.ElementT,
    testNames: list[str],
    testData: dict[str, str],
    title: str | None = None,
    titleLang: str | None = None,
    titleDir: str | None = None,
) -> None:
    if title:
        titleEl = h.E.p(
            {
                "lang": titleLang,
                "dir": titleDir,
            },
            h.parseHTML(title),
        )
        h.appendChild(blockEl, titleEl)
    testListEl = h.E.ul({"class": "wpt-tests-list"})
    h.appendChild(blockEl, testListEl)
    for testName in testNames:
        if testName not in testData:
            m.warn(f"Cannot find '{testName}' in the test data.")
            continue
        if ".https." in testName or ".serviceworker." in testName:
            liveTestScheme = "https"
        else:
            liveTestScheme = "http"
        unused1, unused2, lastNameFragment = testName.rpartition("/")  # pylint: disable=unused-variable
        testType = testData[testName]
        if testType in ["crashtest", "print-reftest", "reftest", "testharness"]:
            singleTestEl = h.E.li(
                {"class": "wpt-test"},
                h.E.a(
                    {
                        "title": testName,
                        "href": "https://wpt.fyi/results/" + testName,
                        "class": "wpt-name",
                    },
                    lastNameFragment,
                ),
                " ",
                h.E.a(
                    {
                        "href": f"{liveTestScheme}://wpt.live/{testName}",
                        "class": "wpt-live",
                    },
                    h.E.small(_("(live test)")),
                ),
                " ",
                h.E.a(
                    {
                        "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                        "class": "wpt-source",
                    },
                    h.E.small(_("(source)")),
                ),
            )
        elif testType in ["manual", "visual"]:
            singleTestEl = h.E.li(
                {"class": "wpt-test"},
                h.E.span({"class": "wpt-name"}, lastNameFragment, f" ({testType} test) "),
                h.E.a(
                    {
                        "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                        "class": "wpt-source",
                    },
                    h.E.small(_("(source)")),
                ),
            )
        elif testType in ["wdspec"]:
            singleTestEl = h.E.li(
                {"class": "wpt-test"},
                h.E.a(
                    {
                        "href": "https://wpt.fyi/results/" + testName,
                        "class": "wpt-name",
                    },
                    lastNameFragment,
                ),
                " ",
                h.E.a(
                    {
                        "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                        "class": "wpt-source",
                    },
                    h.E.small(_("(source)")),
                ),
            )
        else:
            m.warn(
                f"Programming error, the test {testName} is of type {testType}, which I don't know how to render. Please report this!"
            )
            continue
        h.appendChild(testListEl, singleTestEl)
    if title:
        h.appendChild(blockEl, h.E.hr())


def testNamesFromEl(el: t.ElementT, pathPrefix: str | None = None) -> list[str]:
    testNames = []
    localPrefix = el.get("pathprefix")
    if localPrefix is not None:
        pathPrefix = localPrefix
    for name in [x.strip() for x in h.textContent(el).split("\n")]:
        if name == "":
            continue
        testName = prefixPlusPath(pathPrefix, name)
        testNames.append(testName)
    return testNames


def prefixPlusPath(prefix: str | None, path: str) -> str:
    # Join prefix to path, normalizing slashes
    if path.startswith("/"):
        return path[1:]
    prefix = normalizePathSegment(prefix)
    if prefix is None:
        return path
    return prefix + path


def prefixInPath(prefix: str | None, path: str) -> bool:
    if prefix is None:
        return False
    return path.startswith(normalizePathSegment(prefix))


@t.overload
def normalizePathSegment(pathSeg: str) -> str:
    ...


@t.overload
def normalizePathSegment(pathSeg: None) -> None:
    ...


def normalizePathSegment(pathSeg: str | None) -> str | None:
    # No slash at front, yes slash at end
    if pathSeg is None:
        return None
    if pathSeg.startswith("/"):
        pathSeg = pathSeg[1:]
    if not pathSeg.endswith("/"):
        pathSeg += "/"
    return pathSeg


def checkForOmittedTests(pathPrefix: str, testData: dict[str, str], seenTestNames: set[str]) -> None:
    unseenTests = []
    for testPath in testData.keys():
        if ".tentative." in testPath:
            continue
        if prefixInPath(pathPrefix, testPath):
            if testPath not in seenTestNames:
                unseenTests.append(testPath)
    if unseenTests:
        numTests = len(unseenTests)
        m.warn(
            f"There are {numTests} WPT tests underneath your path prefix '{pathPrefix}' that aren't in your document and must be added. (Use a <wpt hidden> if you don't actually want them in your document.)\n"
            + "\n".join("  " + path for path in sorted(unseenTests)),
        )


def loadTestData(doc: t.SpecT) -> dict[str, str]:
    paths = {}
    for line in doc.dataFile.fetch("wpt-tests.txt", str=True).split("\n")[1:]:
        testType, _, testPath = line.strip().partition(" ")
        paths[testPath] = testType
    return paths


def xor(a: t.Any, b: t.Any) -> bool:
    return bool(a) != bool(b)


def commonPathPrefix(paths: t.Iterable[str]) -> str | None:
    splitPaths = [x.split("/")[:-1] for x in paths]
    commonPrefix = splitPaths[0]
    for pathSegs in splitPaths[1:]:
        # can't have a common prefix longer than the shortest path
        if len(pathSegs) < len(commonPrefix):
            commonPrefix = commonPrefix[: len(pathSegs)]
        # now compare the remaining segments
        for i in range(0, min(len(commonPrefix), len(pathSegs))):
            if pathSegs[i] != commonPrefix[i]:
                commonPrefix = commonPrefix[:i]
                break
    if len(commonPrefix) >= 1:
        return "/" + "/".join(commonPrefix) + "/"
    return None


wptStyle = """
:root {
    --wpt-border: hsl(0, 0%, 60%);
    --wpt-bg: hsl(0, 0%, 95%);
    --wpt-text: var(--text);
    --wptheading-text: hsl(0, 0%, 30%);
}
@media (prefers-color-scheme: dark) {
    :root {
        --wpt-border: hsl(0, 0%, 30%);
        --wpt-bg: var(--borderedblock-bg);
        --wpt-text: var(--text);
        --wptheading-text: hsl(0, 0%, 60%);
    }
}
.wpt-tests-block {
    list-style: none;
    border-left: .5em solid var(--wpt-border);
    background: var(--wpt-bg);
    color: var(--wpt-text);
    margin: 1em auto;
    padding: .5em;
}
.wpt-tests-block summary {
    color: var(--wptheading-text);
    font-weight: normal;
    text-transform: uppercase;
}
.wpt-tests-block summary::marker{
    color: var(--wpt-border);
}
.wpt-tests-block summary:hover::marker{
    color: var(--wpt-text);
}
/*
   The only content  of a wpt test block in its closed state is the <summary>,
   which contains the word TESTS,
   and that is absolutely positioned.
   In that closed state, wpt test blocks are styled
   to have a top margin whose height is exactly equal
   to the height of the absolutely positioned <summary>,
   and no other background/padding/margin/border.
   The wpt test block elements will therefore allow the maring
   of the previous/next block elements
   to collapse through them;
   if this combined margin would be larger than its own top margin,
   it stays as is,
   and therefore the pre-existing vertical rhythm of the document is undisturbed.
   If that combined margin would be smaller, it is grown to that size.
   This means that the wpt test block ensures
   that there's always enough vertical space to insert the summary,
   without adding more than is needed.
*/
.wpt-tests-block:not([open]){
    padding: 0;
    border: none;
    background: none;
    font-size: 0.75em;
    line-height: 1;
    position: relative;
    margin: 1em 0 0;
}
.wpt-tests-block:not([open]) summary {
    position: absolute;
    right: 0;
    bottom: 0;
}
/*
   It is possible that both the last child of a block element
   and the block element itself
   would be annotated with a <wpt> block each.
   If the block element has a padding or a border,
   that's fine, but otherwise
   the bottom margin of the block and of its last child would collapse
   and both <wpt> elements would overlap, being both placed there.
   To avoid that, add 1px of padding to the <wpt> element annotating the last child
   to prevent the bottom margin of the block and of its last child from collapsing
   (and as much negative margin,
   as wel only want to prevent margin collapsing,
   but are not trying to actually take more space).
*/
.wpt-tests-block:not([open]):last-child {
    padding-bottom: 1px;
    margin-bottom: -1px;
}
/*
   Exception to the previous rule:
   don't do that in non-last list items,
   because it's not necessary,
   and would therefore consume more space than strictly needed.
   Lists must have list items as children, not <wpt> elements,
   so a <wpt> element cannot be a sibling of a list item,
   and the collision that the previous rule avoids cannot happen.
*/
li:not(:last-child) > .wpt-tests-block:not([open]):last-child,
dd:not(:last-child) > .wpt-tests-block:not([open]):last-child {
    padding-bottom: 0;
    margin-bottom: 0;
}
.wpt-tests-block:not([open]):not(:hover){
    opacity: 0.5;
}
.wpt-tests-list {
    list-style: none;
    display: grid;
    margin: 0;
    padding: 0;
    grid-template-columns: 1fr max-content auto auto;
    grid-column-gap: .5em;
}
.wpt-tests-block hr:last-child {
    display: none;
}
.wpt-test {
    display: contents;
}
.wpt-test > a {
    text-decoration: underline;
    border: none;
}
.wpt-test > .wpt-name { grid-column: 1; }
.wpt-test > .wpt-results { grid-column: 2; }
.wpt-test > .wpt-live { grid-column: 3; }
.wpt-test > .wpt-source { grid-column: 4; }

.wpt-test > .wpt-results {
    display: flex;
    gap: .1em;
}
.wpt-test .wpt-result {
    display: inline-block;
    height: 1em;
    width: 1em;
    border-radius: 50%;
    position: relative;
}
"""


def getWptScript(path: str | None) -> str:
    if path is None:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"
    script = f'let wptPath = "{path}";\n'
    with open(config.scriptPath("wpt", "wptScript.js"), "r", encoding="utf-8") as fh:
        script += fh.read()
    return script
