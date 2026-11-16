from __future__ import annotations

import dataclasses
import difflib
import http.client
import io
import os
import re
import time

import kdl
from alive_progress import alive_it

from . import config, metadata, retrieve, t
from . import messages as m
from .Spec import Spec

if t.TYPE_CHECKING:
    import argparse

TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))
TEST_FILE_EXTENSIONS = (".bs", ".tar")


@dataclasses.dataclass
class TestMetadata:
    networkTests: list[str] = dataclasses.field(default_factory=list)

    @staticmethod
    def fromTestDir() -> TestMetadata:
        path = os.path.join(TEST_DIR, "metadata.kdl")
        with open(path, encoding="utf-8") as fh:
            data = fh.read()
        return TestMetadata.fromKdlStr(data)

    @staticmethod
    def fromKdlStr(data: str) -> TestMetadata:
        self = TestMetadata()
        kdlDoc = kdl.parse(data)
        for node in kdlDoc.getAll("network-tests"):
            for child in node.nodes:
                if child.name == "-" and child.args:
                    self.networkTests.append(str(child.args[0]).strip("/"))
                else:
                    self.networkTests.append(child.name.strip("/"))
        return self

    def isNetworkTest(self, testName: str) -> bool:
        normPath = "/".join(splitPath(testName))
        return any(normPath == p or normPath.startswith(p + "/") for p in self.networkTests)


@dataclasses.dataclass
class TestFilter:
    folders: list[str] | None = None
    files: list[str] | None = None
    manualOnly: bool = True

    @staticmethod
    def fromOptions(options: argparse.Namespace) -> TestFilter:
        if options.manualOnly is not None:
            manualOnly = options.manualOnly
        elif options.folders or options.files or options.rebase:
            manualOnly = False
        else:
            manualOnly = True
        return TestFilter(folders=options.folders, files=options.files, manualOnly=manualOnly)


def testPaths(filters: TestFilter) -> list[str]:
    testMd = TestMetadata.fromTestDir()
    tests = list(sortTests(findTestFiles(filters)))
    if any(testMd.isNetworkTest(testNameForPath(p)) for p in tests):
        if not probablyHaveInternet():
            m.warn("Can't immediately see the internet, so skipping network-tests.")
            tests = [p for p in tests if not testMd.isNetworkTest(testNameForPath(p))]
    return tests


def findTestFiles(filters: TestFilter) -> t.Generator[str, None, None]:
    for root, _, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            fullPath = os.path.join(root, filename)
            filePath = testNameForPath(fullPath)
            if not allowedPath(filePath, filters):
                continue
            yield fullPath


def allowedPath(filePath: str, filters: TestFilter) -> bool:
    extension = os.path.splitext(filePath)[1]
    pathSegs = splitPath(filePath)
    fileName = pathSegs[-1]

    if extension not in TEST_FILE_EXTENSIONS:
        return False

    if re.search(r"\d{3}-files$", pathSegs[-2]):
        # support files for a manual test
        return False

    if filters.manualOnly and pathSegs[0] != "manual":
        return False

    if filters.folders:
        if not any(folder in filePath for folder in filters.folders):
            return False

    if filters.files:
        if not any(fileSubstring in fileName for fileSubstring in filters.files):
            return False

    return True


def splitPath(path: str) -> list[str]:
    [head, tail] = os.path.split(path)
    if head in ["", "/"]:
        return [tail]
    return [*splitPath(head), tail]


# The test name will be the path relative to the tests directory,
# or the path as given if the test is outside of that directory.
def testNameForPath(path: str) -> str:
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR) + 1 :]
    return path


def sortTests(tests: t.Iterable[str]) -> t.Iterable[str]:
    return sorted(tests, key=lambda x: (0 if testNameForPath(x).startswith("manual") else 1, x))


def run(
    filters: TestFilter,
    md: t.MetadataManager | None = None,
    profile: bool = False,
) -> bool:
    paths = testPaths(filters)
    if len(paths) == 0:
        m.p("No tests were found")
        return True
    numPassed = 0
    total = 0
    fails = []
    times: list[tuple[float, str]] = []
    pathProgress = alive_it(paths, dual_line=True, length=20)
    try:
        for path in pathProgress:
            testName = testNameForPath(path)
            pathProgress.text(testName)  # type: ignore
            total += 1
            start = time.perf_counter()
            consoleFh = io.StringIO()
            with m.withMessageState(fh=consoleFh, printMode="plain") as _:
                doc = processTest(path, md)
                testConsole = consoleFh.getvalue()
            testOutput = doc.serialize()
            times.append((time.perf_counter() - start, testName))
            if testOutput is None:
                m.p(m.printColor("Serialization failed.", color="red"))
                fails.append(testName)
                continue
            with open(replaceExtension(path, ".html"), "r", encoding="utf-8") as golden:
                goldenOutput = golden.read()
            with open(replaceExtension(path, ".console.txt"), "r", encoding="utf-8") as golden:
                goldenConsole = golden.read()
            if compare(testOutput, goldenOutput, path=path) and compare(testConsole, goldenConsole, path=path):
                numPassed += 1
            else:
                fails.append(testName)
    except UnicodeEncodeError:
        # On Windows, the alive_it() library throws this error
        # *sometimes*. Can't figure out wth is going on.
        pass
    except Exception as e:
        print(f"Python threw an error when running '{testName}':\n{e}")  # noqa: T201
        raise e
    if profile:
        printProfile(times)
    if numPassed == total:
        m.p(m.printColor("✔ All tests passed.", color="green"))
        return True
    m.p(m.printColor(f"✘ {numPassed}/{total} tests passed.", color="red"))
    m.p(m.printColor("Failed Tests:", color="red"))
    for fail in fails:
        m.p("* " + fail)
    return False


def rebase(
    filters: TestFilter,
    md: t.MetadataManager | None = None,
    profile: bool = False,
) -> bool:
    paths = testPaths(filters)
    if len(paths) == 0:
        m.p("No tests were found.")
        return True
    times: list[tuple[float, str]] = []
    pathProgress = alive_it(paths, dual_line=True, length=20)
    try:
        for path in pathProgress:
            testName = testNameForPath(path)
            pathProgress.text(testName)  # type: ignore
            start = time.perf_counter()
            with m.withMessageState(fh=replaceExtension(path, ".console.txt"), printMode="plain") as _:
                doc = processTest(path, md)
            with m.messagesSilent() as _:
                doc.finish(newline="\n")
            times.append((time.perf_counter() - start, testName))
    except Exception as e:
        print(f"Python threw an error when running '{testName}':\n{e}")  # noqa: T201
        raise e
    if profile:
        printProfile(times)
    return True


def printProfile(times: list[tuple[float, str]]) -> None:
    for dt, testName in sorted(times, reverse=True):
        m.p(f"{dt:6.3f}s\t{testName}")


def processTest(
    path: str,
    md: metadata.MetadataManager | None = None,
    fileRequester: t.DataFileRequester = retrieve.DataFileRequester(fileType="readonly"),
) -> t.SpecT:
    try:
        doc = None
        doc = Spec(inputFilename=path, fileRequester=fileRequester, testing=True)
        if md is not None:
            doc.mdCommandLine = md
        addTestMetadata(doc)
        doc.preprocess()
    except Exception as e:
        print(f"Error running test {path}:\n  {e}")  # noqa: T201
        raise e
    assert doc is not None
    return doc


def compare(suspect: str, golden: str, path: str) -> bool:
    if suspect == golden:
        return True
    m.p(f"FILE: {path}")
    for line in difflib.unified_diff(golden.split("\n"), suspect.split("\n"), fromfile="golden", tofile="suspect"):
        if line[0] == "-":
            m.p(m.printColor(line, color="red"))
        elif line[0] == "+":
            m.p(m.printColor(line, color="green"))
        else:
            m.p(line)
    m.p("")
    return False


def addTestMetadata(doc: t.SpecT) -> None:
    assert doc.mdBaseline is not None
    assert doc.mdCommandLine is not None
    doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
    doc.mdBaseline.addData("Repository", "test/test")
    _, md = metadata.parse(lines=doc.lines)
    if "Date" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Date", "1970-01-01")
    if "Inline Github Issue" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Inline Github Issues", "no")


def replaceExtension(path: str, newExt: str) -> str:
    assert newExt[0] == "."
    trunk = os.path.splitext(path)[0]
    return f"{trunk}{newExt}"


def probablyHaveInternet() -> bool:
    conn = http.client.HTTPSConnection("8.8.8.8", timeout=1)
    try:
        conn.request("HEAD", "/")
        return True
    except Exception:
        return False
    finally:
        conn.close()
