from __future__ import annotations

import dataclasses
import difflib
import glob
import os
import re
import sys

from alive_progress import alive_it

from . import config, metadata, retrieve, t
from . import messages as m
from .Spec import Spec

if t.TYPE_CHECKING:
    import argparse

TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))
TEST_FILE_EXTENSIONS = (".bs", ".tar")


@dataclasses.dataclass
class TestFilter:
    globs: list[str] | None = None
    folders: list[str] | None = None
    manualOnly: bool = False

    @staticmethod
    def fromOptions(options: argparse.Namespace) -> TestFilter:
        return TestFilter(globs=options.testFiles, folders=options.folder, manualOnly=options.manualOnly)


def testPaths(filters: TestFilter) -> list[str]:
    # if None, get all the test paths
    # otherwise, glob the provided paths, rooted at the test dir
    if not filters.globs:
        return list(sortTests(findTestFiles(filters)))
    return [
        path
        for pattern in filters.globs
        for path in glob.glob(os.path.join(TEST_DIR, pattern))
        if path.endswith(TEST_FILE_EXTENSIONS)
    ]


def findTestFiles(filters: TestFilter) -> t.Generator[str, None, None]:
    for root, _, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            filePath = testNameForPath(os.path.join(root, filename))
            if not allowedPath(filePath, filters):
                continue
            if not filePath.endswith(TEST_FILE_EXTENSIONS):
                continue
            yield os.path.join(root, filename)


def allowedPath(filePath: str, filters: TestFilter) -> bool:
    pathSegs = splitPath(filePath)
    if filters.manualOnly and pathSegs[0] == "github":
        return False
    if re.search(r"\d{3}-files$", pathSegs[0]):
        # support files for a manual test
        return False
    if filters.folders:
        if not any(folder in pathSegs for folder in filters.folders):
            return False
    return True


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
    filters: TestFilter,
    md: t.MetadataManager | None = None,
) -> bool:
    paths = testPaths(filters)
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
        m.say(testName)
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
    try:
        messagesFilename = path[:-2] + "console.txt"
        oldStdout = sys.stdout
        doc = None
        with open(messagesFilename, "w", encoding="utf-8") as fh:
            sys.stdout = fh
            doc = Spec(inputFilename=path, fileRequester=fileRequester, testing=True)
            if md is not None:
                doc.mdCommandLine = md
            addTestMetadata(doc)
            doc.preprocess()
        sys.stdout = oldStdout
    except Exception as e:
        m.p(f"Error running test {path}:\n  {e}")
    assert doc is not None
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


def rebase(
    filters: TestFilter,
    md: t.MetadataManager | None = None,
) -> bool:
    paths = testPaths(filters)
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
