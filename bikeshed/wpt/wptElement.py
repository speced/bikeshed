from ..h import (
    E,
    addClass,
    appendChild,
    clearContents,
    findAll,
    removeNode,
    textContent,
)
from ..messages import *


def processWptElements(doc):
    pathPrefix = doc.md.wptPathPrefix

    atLeastOneElement = False
    testData = None
    # <wpt> elements
    wptElements = findAll("wpt", doc)
    seenTestNames = set()
    for el in wptElements:
        atLeastOneElement = True
        if testData is None:
            testData = loadTestData(doc)
        testNames = testNamesFromEl(el, pathPrefix=pathPrefix)
        for testName in testNames:
            if testName not in testData:
                die(
                    "Couldn't find WPT test '{0}' - did you misspell something?",
                    testName,
                    el=el,
                )
                continue
            seenTestNames.add(testName)
        createHTML(doc, el, testNames, testData)

    # <wpt-rest> elements
    wptRestElements = findAll("wpt-rest", doc)
    if wptRestElements and testData is None:
        testData = loadTestData(doc)
    if len(wptRestElements) > 1:
        die(
            "Only one <wpt-rest> element allowed per document, you have {0}.",
            len(wptRestElements),
        )
        wptRestElements = wptRestElements[0:1]
    elif len(wptRestElements) == 1:
        localPrefix = wptRestElements[0].get("pathprefix")
        if localPrefix is not None:
            pathPrefix = localPrefix
        if pathPrefix is None:
            die(
                "Can't use <wpt-rest> without either a pathprefix="
                " attribute or a 'WPT Path Prefix' metadata."
            )
            return
        atLeastOneElement = True
        prefixedNames = [
            p
            for p in testData
            if prefixInPath(pathPrefix, p) and p not in seenTestNames
        ]
        if len(prefixedNames) == 0:
            die("Couldn't find any tests with the path prefix '{0}'.", pathPrefix)
            return
        createHTML(doc, wptRestElements[0], prefixedNames, testData)
        warn(
            "<wpt-rest> is intended for debugging only. Move the tests to <wpt> elements next to what they're testing."
        )
    else:
        if pathPrefix:
            if testData is None:
                testData = loadTestData(doc)
            checkForOmittedTests(pathPrefix, testData, seenTestNames)

    if atLeastOneElement:
        doc.extraStyles["style-wpt"] = wptStyle


def createHTML(doc, blockEl, testNames, testData):
    if doc.md.wptDisplay == "none":
        removeNode(blockEl)
    elif doc.md.wptDisplay == "inline":
        blockEl.tag = "ul"
        addClass(blockEl, "wpt-tests-block")
        clearContents(blockEl)
        for testName in testNames:
            if testName not in testData:
                warn(f"Cannot find '{testName}' in the test data.")
                continue
            if ".https." in testName or ".serviceworker." in testName:
                liveTestScheme = "https"
            else:
                liveTestScheme = "http"
            _, _, lastNameFragment = testName.rpartition("/")
            testType = testData[testName]
            if testType in ["crashtest", "print-reftest", "reftest", "testharness"]:
                singleTestEl = E.li(
                    {"class": "wpt-test"},
                    E.a(
                        {
                            "href": "https://wpt.fyi/results/" + testName,
                            "class": "wpt-name",
                        },
                        lastNameFragment,
                    ),
                    " ",
                    E.a(
                        {
                            "title": testName,
                            "href": f"{liveTestScheme}://wpt.live/{testName}",
                            "class": "wpt-live",
                        },
                        E.small("(live test)"),
                    ),
                    " ",
                    E.a(
                        {
                            "href": "https://github.com/web-platform-tests/wpt/blob/master/"
                            + testName,
                            "class": "wpt-source",
                        },
                        E.small("(source)"),
                    ),
                )
            elif testType in ["manual", "visual"]:
                singleTestEl = E.li(
                    {"class": "wpt-test"},
                    E.span(
                        {"class": "wpt-name"}, lastNameFragment, f" ({testType} test) "
                    ),
                    E.a(
                        {
                            "href": "https://github.com/web-platform-tests/wpt/blob/master/"
                            + testName,
                            "class": "wpt-source",
                        },
                        E.small("(source)"),
                    ),
                )
            elif testType in ["wdspec"]:
                singleTestEl = E.li(
                    {"class": "wpt-test"},
                    E.a(
                        {
                            "href": "https://wpt.fyi/results/" + testName,
                            "class": "wpt-name",
                        },
                        lastNameFragment,
                    ),
                    " ",
                    E.a(
                        {
                            "href": "https://github.com/web-platform-tests/wpt/blob/master/"
                            + testName,
                            "class": "wpt-source",
                        },
                        E.small("(source)"),
                    ),
                )
            else:
                warn(
                    f"Programming error, the test {testName} is of type {testType}, which I don't know how to render. Please report this!"
                )
                continue

            appendChild(blockEl, singleTestEl)
    else:
        die("Programming error, uncaught WPT Display value in createHTML.")


def testNamesFromEl(el, pathPrefix=None):
    testNames = []
    localPrefix = el.get("pathprefix")
    if localPrefix is not None:
        pathPrefix = localPrefix
    for name in [x.strip() for x in textContent(el).split("\n")]:
        if name == "":
            continue
        testName = prefixPlusPath(pathPrefix, name)
        testNames.append(testName)
    return testNames


def prefixPlusPath(prefix, path):
    # Join prefix to path, normalizing slashes
    if path.startswith("/"):
        return path[1:]
    prefix = normalizePathSegment(prefix)
    if prefix is None:
        return path
    return prefix + path


def prefixInPath(prefix, path):
    if prefix is None:
        return False
    return path.startswith(normalizePathSegment(prefix))


def normalizePathSegment(pathSeg):
    # No slash at front, yes slash at end
    if pathSeg is None:
        return None
    if pathSeg.startswith("/"):
        pathSeg = pathSeg[1:]
    if not pathSeg.endswith("/"):
        pathSeg += "/"
    return pathSeg


def checkForOmittedTests(pathPrefix, testData, seenTestNames):
    unseenTests = []
    for testPath in testData.keys():
        if ".tentative." in testPath:
            continue
        if prefixInPath(pathPrefix, testPath):
            if testPath not in seenTestNames:
                unseenTests.append(testPath)
    if unseenTests:
        numTests = len(unseenTests)
        if numTests < 10:
            warn(
                "There are {} WPT tests underneath your path prefix '{}' that aren't in your document and must be added:\n{}",
                numTests,
                pathPrefix,
                "\n".join("  " + path for path in sorted(unseenTests)),
            )
        else:
            warn(
                f"There are {numTests} WPT tests (too many to display individually) underneath your path prefix '{pathPrefix}' that aren't in your document."
            )


def loadTestData(doc):
    paths = {}
    for line in doc.dataFile.fetch("wpt-tests.txt", str=True).split("\n")[1:]:
        testType, _, testPath = line.strip().partition(" ")
        paths[testPath] = testType
    return paths


def xor(a, b):
    return bool(a) != bool(b)


wptStyle = """
:root {
    --wpt-border: hsl(290, 70%, 60%);
    --wpt-bg: hsl(290, 70%, 95%);
    --wpt-text: var(--text);
    --wptheading-text: hsl(290, 70%, 30%);
}
@media (prefers-color-scheme: dark) {
    :root {
        --wpt-border: hsl(290, 70%, 30%);
        --wpt-bg: var(--borderedblock-bg);
        --wpt-text: var(--text);
        --wptheading-text: hsl(290, 70%, 60%);
    }
}
.wpt-tests-block {
    list-style: none;
    border-left: .5em solid var(--wpt-border);
    background: var(--wpt-bg);
    color: var(--wpt-text);
    margin: 1em auto;
    padding: .5em;
    display: grid;
    grid-template-columns: 1fr auto auto;
    grid-column-gap: .5em;
}
.wpt-tests-block::before {
    content: "Tests";
    grid-column: 1/-1;
    color: var(--wptheading-text);
    text-transform: uppercase;
}
.wpt-test {
    display: contents;
}
.wpt-test > a {
    text-decoration: underline;
    border: none;
}
.wpt-test > .wpt-name { grid-column: 1; }
.wpt-test > .wpt-live { grid-column: 2; }
.wpt-test > .wpt-source { grid-column: 3; }
"""
