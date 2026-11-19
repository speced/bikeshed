from __future__ import annotations

from collections import Counter

from .. import h, t
from .. import messages as m
from ..translate import _t


def processWptElements(doc: t.SpecT) -> None:
    pathPrefix = doc.md.wptPathPrefix

    atLeastOneElement = False
    atLeastOneVisibleTest = False
    testData = loadTestData(doc)
    prefixPreloaded = False
    # <wpt> elements
    wptElements = h.findAll("wpt", doc)
    seenTestNames: set[str] = set()
    prevEl = None
    for el in wptElements:
        isHidden = el.get("hidden") is not None
        if not atLeastOneElement and not isHidden:
            atLeastOneElement = True
        testNames = testNamesFromEl(el, pathPrefix=pathPrefix)
        validTestNames = []
        if testNames:
            if not prefixPreloaded and pathPrefix and not pathPrefix.startswith("https:"):
                testData.testsForPrefix(normalizePathSegment(pathPrefix))
                prefixPreloaded = True
            skipExistenceCheck = el.get("bs-skip-existence-check") is not None
            for testName in testNames:
                if not skipExistenceCheck and testData.get(testName) is None:
                    m.warn(f"Couldn't find WPT test '{testName}' - did you misspell something?", el=el)
                    continue
                seenTestNames.add(testName)
                validTestNames.append(testName)
                if not atLeastOneVisibleTest and not isHidden:
                    atLeastOneVisibleTest = True
        if isHidden or doc.md.wptDisplay == "none":
            h.removeNode(el)
        else:
            title = el.get("title")
            titleLang = el.get("lang")
            titleDir = el.get("dir")
            if prevEl is not None and prevEl.getnext() is el and (prevEl.tail is None or prevEl.tail.strip() == ""):
                appendTestList(
                    prevEl,
                    testNames=validTestNames,
                    testData=testData,
                    title=title,
                    titleLang=titleLang,
                    titleDir=titleDir,
                )
                h.removeNode(el)
            else:
                createHTML(
                    doc,
                    el,
                    testNames=validTestNames,
                    testData=testData,
                    title=title,
                    titleLang=titleLang,
                    titleDir=titleDir,
                )
                prevEl = el

    # <wpt-rest> elements
    wptRestElements = h.findAll("wpt-rest", doc)
    if wptRestElements:
        if len(wptRestElements) > 1:
            m.die(f"Only one <wpt-rest> element allowed per document, you have {len(wptRestElements)}.")
            wptRestElements = wptRestElements[0:1]
        else:
            localPrefix = wptRestElements[0].get("bs-pathprefix")
            if localPrefix is not None:
                pathPrefix = localPrefix
            if pathPrefix is None:
                m.die("Can't use <wpt-rest> without either a pathprefix='' attribute or a 'WPT Path Prefix' metadata.")
                return
            normalizedPrefix = normalizePathSegment(pathPrefix)
            prefixedNames = [p for p in testData.testsForPrefix(normalizedPrefix) if p not in seenTestNames]
            if len(prefixedNames) == 0:
                m.die(f"Couldn't find any tests with the path prefix '{pathPrefix}'.")
                return
            atLeastOneElement = True
            atLeastOneVisibleTest = True
            createHTML(doc, wptRestElements[0], testNames=prefixedNames, testData=testData)
            m.warn(
                "<wpt-rest> is intended for debugging only. Move the tests to <wpt> elements next to what they're testing.",
            )
    else:
        if pathPrefix:
            checkForOmittedTests(pathPrefix, testData, seenTestNames, doc)

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
    *,
    testNames: list[str],
    testData: WptData,
    title: str | None = None,
    titleLang: str | None = None,
    titleDir: str | None = None,
) -> None:
    if doc.md.wptDisplay == "none":
        h.removeNode(blockEl)
    elif doc.md.wptDisplay in ("inline", "open", "closed"):
        blockEl.tag = "details"
        h.addClass(doc, blockEl, "wpt-tests-block")
        h.removeAttr(blockEl, "title")
        blockEl.set("lang", "en")
        blockEl.set("dir", "ltr")
        if doc.md.wptDisplay in ("open", "inline"):
            blockEl.set("open", "")
        h.clearContents(blockEl)
        h.appendChild(blockEl, h.E.summary(_t("Tests")))
        appendTestList(
            blockEl,
            testNames=testNames,
            testData=testData,
            title=title,
            titleLang=titleLang,
            titleDir=titleDir,
        )
    else:
        m.die("Programming error, uncaught WPT Display value in createHTML.")


def appendTestList(
    blockEl: t.ElementT,
    *,
    testNames: list[str],
    testData: WptData,
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
            *h.parseHTML(h.safeHtml(title, context="<wpt title>")),
        )
        h.appendChild(blockEl, titleEl)
    testListEl = h.E.ul({"class": "wpt-tests-list"})
    h.appendChild(blockEl, testListEl)
    if testNames:
        liveTestLabel = _t("(live test)")
        sourceLabel = _t("(source)")
        for testName in testNames:
            testType = testData.get(testName)
            if testType is None:
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
            _, _, lastNameFragment = testName.rpartition("/")
            if testType in ("crashtest", "print-reftest", "reftest", "testharness"):
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
                        h.E.small(liveTestLabel),
                    ),
                    " ",
                    h.E.a(
                        {
                            "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                            "class": "wpt-source",
                        },
                        h.E.small(sourceLabel),
                    ),
                )
            elif testType in ("manual", "visual"):
                singleTestEl = h.E.li(
                    {"class": "wpt-test"},
                    h.E.span(
                        {"class": "wpt-name"},
                        f"{lastNameFragment} ({testType} test) ",
                    ),
                    h.E.a(
                        {
                            "href": "https://github.com/web-platform-tests/wpt/blob/master/" + testName,
                            "class": "wpt-source",
                        },
                        h.E.small(sourceLabel),
                    ),
                )
            elif testType == "wdspec":
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
                        h.E.small(sourceLabel),
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
    text = h.textContent(el)
    if not text:
        return []
    testNames = []
    localPrefix = el.get("bs-pathprefix")
    if localPrefix is not None:
        pathPrefix = localPrefix
    pathPrefix = normalizePathSegment(pathPrefix)
    for line in text.split("\n"):
        name = line.strip()
        if name == "":
            continue
        if name.startswith("/"):
            testNames.append(name[1:])
        elif pathPrefix is None:
            testNames.append(name)
        else:
            testNames.append(pathPrefix + name)
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


def checkForOmittedTests(pathPrefix: str, testData: WptData, seenTestNames: set[str], doc: t.SpecT) -> None:
    normalizedPrefix = normalizePathSegment(pathPrefix)
    unseenTests = [
        testPath
        for testPath in testData.testsForPrefix(normalizedPrefix)
        if ".tentative." not in testPath and testPath not in seenTestNames
    ]
    if unseenTests:
        numTests = len(unseenTests)
        if doc.md.wptErrors == "verbose":
            m.warn(
                f"There are {numTests} WPT tests underneath your path prefix '{pathPrefix}' that aren't in your document and must be added. (Use a <wpt hidden> if you don't actually want them in your document.)\n"
                + "\n".join("  " + path for path in sorted(unseenTests)),
            )
        elif doc.md.wptErrors == "minimal":
            m.warn(
                f"There are {numTests} WPT tests underneath your path prefix that aren't in your document. (Use `WPT Errors: verbose` to see more details.)",
            )


TEST_TYPES = ("crashtest", "manual", "print-reftest", "reftest", "testharness", "visual", "wdspec")
LOOKUP_TEST_TYPES = ("testharness", "reftest", "manual", "visual", "crashtest", "wdspec", "print-reftest")


class WptData:
    __slots__ = ["_initialized", "_prefixCache", "_raw", "_testCache", "_typeBounds", "dataFile"]

    def __init__(self, dataFile: t.DataFileRequester) -> None:
        self.dataFile = dataFile
        self._initialized = False
        self._raw = ""
        self._testCache: dict[str, str | None] = {}
        self._prefixCache: dict[str, dict[str, str]] = {}
        self._typeBounds: dict[str, tuple[int, int]] = {}

    def _ensureLoaded(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        raw = self.dataFile.fetch("wpt-tests.txt", str=True)
        if not raw:
            return
        if not raw.endswith("\n") or raw.endswith("\n\n"):
            raw = raw.rstrip("\n") + "\n"
        self._raw = raw
        firstNl = raw.find("\n")
        if firstNl == -1:
            return
        n = len(raw) - 1
        pos = firstNl
        for testType in TEST_TYPES:
            if not raw.startswith(f"\n{testType} ", pos):
                pos = self._bisect(pos, n, f"\n{testType} ")
            end = self._bisect(pos, n, f"\n{testType}!")
            if pos < end:
                self._typeBounds[testType] = (pos, end)
            pos = end

    def _bisect(self, lo: int, hi: int, target: str) -> int:
        raw = self._raw
        while lo < hi:
            mid = (lo + hi) // 2
            nl = raw.rfind("\n", lo, mid + 1)
            end = raw.find("\n", nl + 1)
            if raw[nl:end] < target:
                lo = end
            else:
                hi = nl
        return lo

    def get(self, testName: str) -> str | None:
        if testName in self._testCache:
            return self._testCache[testName]
        if testName.startswith("https:"):
            self._testCache[testName] = None
            return None
        for p in self._prefixCache:
            if testName.startswith(p):
                self._testCache[testName] = None
                return None
        dirPath, sep, _ = testName.rpartition("/")
        if sep:
            self.testsForPrefix(dirPath + "/")
            res = self._testCache.get(testName)
            self._testCache[testName] = res
            return res
        return self._lookupSingle(testName)

    def _lookupSingle(self, testName: str) -> str | None:
        self._ensureLoaded()
        raw = self._raw
        bounds = self._typeBounds
        for testType in LOOKUP_TEST_TYPES:
            b = bounds.get(testType)
            if b is None:
                continue
            target = f"\n{testType} {testName}"
            pos = self._bisect(b[0], b[1], target)
            if raw.startswith(target + "\n", pos):
                self._testCache[testName] = testType
                return testType
        self._testCache[testName] = None
        return None

    def __contains__(self, testName: str) -> bool:
        return self.get(testName) is not None

    def __getitem__(self, testName: str) -> str:
        res = self.get(testName)
        if res is None:
            raise KeyError(testName)
        return res

    def testsForPrefix(self, prefix: str) -> dict[str, str]:
        if prefix in self._prefixCache:
            return self._prefixCache[prefix]
        self._ensureLoaded()
        res: dict[str, str] = {}
        raw = self._raw
        bounds = self._typeBounds
        testCache = self._testCache
        for testType in TEST_TYPES:
            b = bounds.get(testType)
            if b is None:
                continue
            target = f"\n{testType} {prefix}"
            startPos = self._bisect(b[0], b[1], target)
            if not raw.startswith(target, startPos):
                continue
            nextTarget = target[:-1] + chr(ord(target[-1]) + 1)
            endPos = self._bisect(startPos, b[1], nextTarget)
            offset = 1 + len(testType)
            for line in raw[startPos + 1 : endPos].split("\n"):
                path = line[offset:]
                res[path] = testType
                testCache[path] = testType
        self._prefixCache[prefix] = res
        return res


WPT_DATA_CACHE: dict[t.DataFileRequester, WptData] = {}


def loadTestData(doc: t.SpecT) -> WptData:
    if doc.dataFile not in WPT_DATA_CACHE:
        WPT_DATA_CACHE[doc.dataFile] = WptData(doc.dataFile)
    return WPT_DATA_CACHE[doc.dataFile]


def xor(a: t.Any, b: t.Any) -> bool:
    return bool(a) != bool(b)


def commonPathPrefixes(paths: t.Iterable[str]) -> list[str]:
    # Only record the first two segments (dropping the filename),
    # that's good enough for limiting the data slurped.
    oneSegs = set()
    twoSegs = set()
    for path in paths:
        parts = path.strip("/").split("/", 2)
        if len(parts) == 2:
            oneSegs.add(f"/{parts[0]}/")
        elif len(parts) == 3:
            twoSegs.add(f"/{parts[0]}/{parts[1]}/")
        else:
            twoSegs.add("//")
    # Filter out any 2-length segments already covered by a 1-length seg
    for short in oneSegs:
        twoSegs = {x for x in twoSegs if not x.startswith(short)}
    return list(oneSegs) + list(twoSegs)


def guessTestSuiteUrl(paths: t.Iterable[str]) -> str:
    # Do the same transforms as commonPathPrefixes, but then
    # just count the number of paths under each,
    # and return the one that wins.
    prefixCounter: Counter[str] = Counter()
    for path in paths:
        parts = path.strip("/").split("/", 2)
        prefix = "/" + "/".join(parts[:-1]) + "/"
        prefixCounter[prefix] += 1
    bestGuess = prefixCounter.most_common(1)[0][0]
    return f"https://wpt.fyi/results{bestGuess}"
