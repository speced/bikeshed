# -*- coding: utf-8 -*-


import difflib
import glob
import io
import os
import pipes
import re
import subprocess
from itertools import *
from . import config
from .messages import *
from .Spec import Spec


TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))


def findTestFiles(manualOnly=False):
    for root, dirnames, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            filePath = testNameForPath(os.path.join(root, filename))
            if manualOnly and re.match("github/", filePath):
                continue
            if re.match("[^/]*\d{3}-files/", filePath):
                # support files for a manual test
                continue
            if filename.endswith(".bs"):
                yield os.path.join(root, filename)


# The test name will be the path relative to the tests directory, or the path as
# given if the test is outside of that directory.
def testNameForPath(path):
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR)+1:]
    return path


def sortTests(tests):
    return sorted(tests, key=lambda x:("/" in testNameForPath(x), x))


def runAllTests(patterns=None, manualOnly=False, md=None):
    paths = testPaths(patterns)
    if len(paths) == 0:
        p("No tests were found")
        return True
    numPassed = 0
    total = 0
    fails = []
    for i,path in enumerate(paths, 1):
        testName = testNameForPath(path)
        p(f"{ratio(i,len(paths))}: {testName}")
        total += 1
        doc = processTest(path, md)
        outputText = doc.serialize()
        with io.open(path[:-2] + "html", encoding="utf-8") as golden:
            goldenText = golden.read()
        if compare(outputText, goldenText):
            numPassed += 1
        else:
            fails.append(testName)
    if numPassed == total:
        p(printColor("✔ All tests passed.", color="green"))
        return True
    else:
        p(printColor("✘ {0}/{1} tests passed.".format(numPassed, total), color="red"))
        p(printColor("Failed Tests:", color="red"))
        for fail in fails:
            p("* " + fail)

def processTest(path, md=None, fileRequester=config.DataFileRequester(type="readonly")):
    doc = Spec(inputFilename=path, fileRequester=fileRequester, testing=True)
    if md is not None:
        doc.mdCommandLine = md
    addTestMetadata(doc)
    doc.preprocess()
    return doc

def compare(suspect, golden):
    if suspect == golden:
        return True
    for line in difflib.unified_diff(golden.split(), suspect.split(), fromfile="golden", tofile="suspect", lineterm=""):
        if line[0] == "-":
            p(printColor(line, color="red"))
        elif line[0] == "+":
            p(printColor(line, color="green"))
        else:
            p(line)
    p("")
    return False

def rebase(patterns=None, md=None):
    paths = testPaths(patterns)
    if len(paths) == 0:
        p("No tests were found.")
        return True
    for i,path in enumerate(paths, 1):
        name = testNameForPath(path)
        resetSeenMessages()
        p(f"{ratio(i,len(paths))}: Rebasing {name}")
        doc = processTest(path, md)
        doc.finish()

def ratio(i, total):
    justifiedI = str(i).rjust(len(str(total)))
    return f"{justifiedI}/{total}"

def testPaths(patterns=None):
    # if None, get all the test paths
    # otherwise, glob the provided paths, rooted at the test dir
    if not patterns:
        return list(sortTests(findTestFiles()))
    else:
        return [path
            for pattern in patterns
            for path in glob.glob(os.path.join(TEST_DIR, pattern))
            if path.endswith(".bs")]

def addTestMetadata(doc):
    from . import metadata

    doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
    doc.mdBaseline.addData("Repository", "test/test")
    _, md = metadata.parse(lines=doc.lines)
    if "Date" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Date", "1970-01-01")
    if "Inline Github Issue" not in md.manuallySetKeys:
        doc.mdCommandLine.addData("Inline Github Issues", "no")
