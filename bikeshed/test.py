from __future__ import annotations

import difflib
import glob
import os
import re
from alive_progress import alive_it

from . import config, messages as m, metadata, retrieve, t
from .Spec import Spec

TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))
TEST_FILE_EXTENSIONS = (".bs", ".tar")


def findTestFiles(manualOnly: bool = False) -> t.Generator[str, None, None]:
    for root, _, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            filePath = testNameForPath(os.path.join(root, filename))
            pathSegs = splitPath(filePath)
            if manualOnly and pathSegs[0] == "github":
                continue
            if re.search(r"\d{3}-files$", pathSegs[0]):
                # support files for a manual test
                continue
            if filePath.endswith(TEST_FILE_EXTENSIONS):
                yield os.path.join(root, filename)


def splitPath(path: str, reverseSegs: list[str] | None = None) -> list[str]:
    if reverseSegs is None:
        reverseSegs = []
    [head, tail] = os.path.split(path)
    reverseSegs.append(tail)
    if head in ["", "/"]:
        return list(reversed(reverseSegs))
    return splitPath(head, reverseSegs)


# The test name will be the path relative to the tests directory, or the path as
# given if the test is outside of that directory.
def testNameForPath(path: str) -> str:
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR) + 1 :]
    return path


def sortTests(tests: t.Iterable[str]) -> t.Iterable[str]:
    return sorted(tests, key=lambda x: ("/" in testNameForPath(x), x))


def runAllTests(
    patterns: list[str] | None = None,
    manualOnly: bool = False,  # pylint: disable=unused-argument
    md: t.MetadataManager | None = None,
) -> bool:
    paths = testPaths(patterns)
    if len(paths) == 0:
        m.p("No tests were found")
        return True
    numPassed = 0
    total = 0
    fails = []
    pathProgress = alive_it(paths, dual_line=True, length=20)
    try:
        for path in pathProgress:
            testName = testNameForPath(path)
            pathProgress.text(testName)
            total += 1
            doc = processTest(path, md)
            outputText = doc.serialize()
            if outputText is None:
                m.p(m.printColor("Serialization failed.", color="red"))
                fails.append(testName)
                continue
            with open(os.path.splitext(path)[0] + ".html", encoding="utf-8") as golden:
                goldenText = golden.read()
            if compare(outputText, goldenText):
                numPassed += 1
            else:
                fails.append(testName)
    except:  # pylint: disable=bare-except
        print(testName)
    if numPassed == total:
        m.p(m.printColor("✔ All tests passed.", color="green"))
        return True
    m.p(m.printColor(f"✘ {numPassed}/{total} tests passed.", color="red"))
    m.p(m.printColor("Failed Tests:", color="red"))
    for fail in fails:
        m.p("* " + fail)
    return False


def processTest(
    path: str,
    md: metadata.MetadataManager | None = None,
    fileRequester: t.DataFileRequester = retrieve.DataFileRequester(fileType="readonly"),
) -> t.SpecT:
    doc = Spec(inputFilename=path, fileRequester=fileRequester, testing=True)
    if md is not None:
        doc.mdCommandLine = md
    addTestMetadata(doc)
    doc.preprocess()
    return doc


def compare(suspect: str, golden: str) -> bool:
    if suspect == golden:
        return True
    for line in difflib.unified_diff(golden.split("\n"), suspect.split("\n"), fromfile="golden", tofile="suspect"):
        if line[0] == "-":
            m.p(m.printColor(line, color="red"))
        elif line[0] == "+":
            m.p(m.printColor(line, color="green"))
        else:
            m.p(line)
    m.p("")
    return False


def rebase(patterns: list[str] | None = None, md: t.MetadataManager | None = None) -> bool:
    paths = testPaths(patterns)
    if len(paths) == 0:
        m.p("No tests were found.")
        return True
    pathProgress = alive_it(paths, dual_line=True, length=20)
    for path in pathProgress:
        name = testNameForPath(path)
        pathProgress.text(name)
        m.resetSeenMessages()
        doc = processTest(path, md)
        doc.finish(newline="\n")
    return True


def testPaths(patterns: list[str] | None = None) -> list[str]:
    # if None, get all the test paths
    # otherwise, glob the provided paths, rooted at the test dir
    if not patterns:
        return list(sortTests(findTestFiles()))
    return [
        path
        for pattern in patterns
        for path in glob.glob(os.path.join(TEST_DIR, pattern))
        if path.endswith(TEST_FILE_EXTENSIONS)
    ]


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
