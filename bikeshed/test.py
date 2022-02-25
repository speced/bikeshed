import difflib
import glob
import os
import re

from . import config, messages as m, retrieve
from .Spec import Spec

TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))


def findTestFiles(manualOnly=False):
    for root, _, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            filePath = testNameForPath(os.path.join(root, filename))
            pathSegs = splitPath(filePath)
            if manualOnly and pathSegs[0] == "github":
                continue
            if re.search(r"\d{3}-files$", pathSegs[0]):
                # support files for a manual test
                continue
            if os.path.splitext(filePath)[1] == ".bs":
                yield os.path.join(root, filename)


def splitPath(path, reverseSegs=None):
    if reverseSegs is None:
        reverseSegs = []
    [head, tail] = os.path.split(path)
    reverseSegs.append(tail)
    if head in ["", "/"]:
        return list(reversed(reverseSegs))
    return splitPath(head, reverseSegs)


# The test name will be the path relative to the tests directory, or the path as
# given if the test is outside of that directory.
def testNameForPath(path):
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR) + 1 :]
    return path


def sortTests(tests):
    return sorted(tests, key=lambda x: ("/" in testNameForPath(x), x))


def runAllTests(patterns=None, manualOnly=False, md=None):  # pylint: disable=unused-argument
    paths = testPaths(patterns)
    if len(paths) == 0:
        m.p("No tests were found")
        return True
    numPassed = 0
    total = 0
    fails = []
    for i, path in enumerate(paths, 1):
        testName = testNameForPath(path)
        m.p(f"{ratio(i,len(paths))}: {testName}")
        total += 1
        doc = processTest(path, md)
        outputText = doc.serialize()
        with open(path[:-2] + "html", encoding="utf-8") as golden:
            goldenText = golden.read()
        if compare(outputText, goldenText):
            numPassed += 1
        else:
            fails.append(testName)
    if numPassed == total:
        m.p(m.printColor("✔ All tests passed.", color="green"))
        return True
    m.p(m.printColor(f"✘ {numPassed}/{total} tests passed.", color="red"))
    m.p(m.printColor("Failed Tests:", color="red"))
    for fail in fails:
        m.p("* " + fail)


def processTest(path, md=None, fileRequester=retrieve.DataFileRequester(type="readonly")):
    doc = Spec(inputFilename=path, fileRequester=fileRequester, testing=True)
    if md is not None:
        doc.mdCommandLine = md
    addTestMetadata(doc)
    doc.preprocess()
    return doc


def compare(suspect, golden):
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


def rebase(patterns=None, md=None):
    paths = testPaths(patterns)
    if len(paths) == 0:
        m.p("No tests were found.")
        return True
    for i, path in enumerate(paths, 1):
        name = testNameForPath(path)
        m.resetSeenMessages()
        m.p(f"{ratio(i,len(paths))}: Rebasing {name}")
        doc = processTest(path, md)
        doc.finish(newline="\n")


def ratio(i, total):
    justifiedI = str(i).rjust(len(str(total)))
    return f"{justifiedI}/{total}"


def testPaths(patterns=None):
    # if None, get all the test paths
    # otherwise, glob the provided paths, rooted at the test dir
    if not patterns:
        return list(sortTests(findTestFiles()))
    return [path for pattern in patterns for path in glob.glob(os.path.join(TEST_DIR, pattern)) if path.endswith(".bs")]


def addTestMetadata(doc):
    from . import metadata

    doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
    doc.mdBaseline.addData("Repository", "test/test")
    _, md = metadata.parse(lines=doc.lines)
    if "Date" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Date", "1970-01-01")
    if "Inline Github Issue" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Inline Github Issues", "no")
