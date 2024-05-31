from __future__ import annotations

from collections import Counter

from .. import h, t
from .. import messages as m
from ..translate import _t


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
            if el.get("skip-existence-check") is None:
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
                "<wpt-rest> is intended for debugging only. Move the tests to <wpt> elements next to what they're testing.",
            )
    else:
        if pathPrefix:
            if testData is None:
                testData = loadTestData(doc)
            checkForOmittedTests(pathPrefix, testData, seenTestNames)

    if atLeastOneVisibleTest:
        if pathPrefix and pathPrefix.startswith("https:"):
            dataPaths = [pathPrefix]
        else:
            dataPaths = commonPathPrefixes(seenTestNames)

        testSuiteUrl = None
        if pathPrefix and not pathPrefix.startswith("https:"):
            pathPrefix = "/" + pathPrefix.strip("/") + "/"
            testSuiteUrl = f"https://wpt.fyi/results{pathPrefix}"
        elif not pathPrefix:
            testSuiteUrl = guessTestSuiteUrl(seenTestNames)
        if testSuiteUrl:
            doc.md.otherMetadata.setdefault(_t("Test Suite"), []).append(
                h.E.dd(
                    {"class": "wpt-overview"},
                    h.E.a(
                        {"href": testSuiteUrl},
                        testSuiteUrl,
                    ),
                ),
            )

    if doc.md.wptDisplay != "none":
        if atLeastOneElement:
            # Empty <wpt> blocks still need styles
            doc.extraJC.addWptCSS()
        if atLeastOneVisibleTest:
            # But I only need script if there's actually some tests.
            doc.extraJC.addWpt(dataPaths)


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
        testSummaryEl = h.E.summary(_t("Tests"))
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
            if testName.startswith("https:"):
                # Assume it's a custom URL, just link to it.
                singleTestEl = h.E.li(
                    {"class": "wpt-test"},
                    h.E.a(
                        {
                            "href": testName,
                            "class": "wpt-name",
                            # Since the name is a URL and might be long,
                            # let it break freely.
                            "style": "word-break: break-all",
                        },
                        testName,
                    ),
                )
                h.appendChild(testListEl, singleTestEl)
                continue
            else:
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
                    h.E.small(_t("(live test)")),
                ),
                " ",
                h.E.a(
                    {
                        "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                        "class": "wpt-source",
                    },
                    h.E.small(_t("(source)")),
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
                    h.E.small(_t("(source)")),
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
                    h.E.small(_t("(source)")),
                ),
            )
        else:
            m.warn(
                f"Programming error, the test {testName} is of type {testType}, which I don't know how to render. Please report this!",
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
def normalizePathSegment(pathSeg: str) -> str: ...


@t.overload
def normalizePathSegment(pathSeg: None) -> None: ...


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
    for testPath in testData:
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


def commonPathPrefixes(paths: t.Iterable[str]) -> list[str]:
    # Split the paths into segments, and drop the filename
    splitPaths = [x.strip("/").split("/")[:-1] for x in paths]
    # Only record the first two segments, that's good enough
    # for limiting the data slurped.
    oneSegs = set()
    twoSegs = set()
    for pathSegs in splitPaths:
        prefix = pathSegs[0:2]
        if len(prefix) == 1:
            oneSegs.add("/" + prefix[0] + "/")
        else:
            twoSegs.add("/" + "/".join(prefix) + "/")
    # Filter out any 2-length segments already covered by a 1-length seg
    for short in oneSegs:
        twoSegs = {x for x in twoSegs if not x.startswith(short)}
    return list(oneSegs) + list(twoSegs)


def guessTestSuiteUrl(paths: t.Iterable[str]) -> str:
    # Do the same transforms as commonPathPrefixes, but then
    # just count the number of paths under each,
    # and return the one that wins.
    splitPaths = [x.strip("/").split("/")[:-1] for x in paths]
    prefixCounter: Counter[str] = Counter()
    for pathSegs in splitPaths:
        prefix = "/" + "/".join(pathSegs[0:2]) + "/"
        prefixCounter[prefix] += 1
    bestGuess = prefixCounter.most_common(1)[0][0]
    return f"https://wpt.fyi/results{bestGuess}"
