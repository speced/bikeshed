# -*- coding: utf-8 -*-


import difflib
import io
import os
import pipes
import re
import subprocess
from itertools import *
from . import config
from .htmlhelpers import parseDocument, outerHTML, nodeIter, isElement, findAll
from .messages import *


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


def runAllTests(Spec, testFiles=None, manualOnly=False, md=None):
    fileRequester = config.DataFileRequester(type="readonly")
    if not testFiles:
        testFiles = list(sortTests(findTestFiles(manualOnly=manualOnly)))
        if len(testFiles) == 0:
            p("No tests were found")
            return True
    else:
        testFiles = [os.path.join(TEST_DIR, x) for x in testFiles]
    numPassed = 0
    total = 0
    fails = []
    for i,testPath in enumerate(testFiles, 1):
        justifiedI = str(i).rjust(len(str(len(testFiles))))
        testName = testNameForPath(testPath)
        p("{0}/{1}: {2}".format(justifiedI, len(testFiles), testName))
        total += 1
        doc = Spec(inputFilename=testPath, fileRequester=fileRequester, testing=True)
        if md is not None:
            doc.mdCommandLine = md
        addTestMetadata(doc)
        doc.preprocess()
        outputText = doc.serialize()
        with io.open(testPath[:-2] + "html", encoding="utf-8") as golden:
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

def compareDicts(a, b):
    aKeys = set(a.keys())
    bKeys = set(b.keys())
    if aKeys != bKeys:
        return False
    for key in aKeys:
        if a[key] != b[key]:
            return False
    return True

def equalOrEmpty(a, b):
    if a == b:
        return True
    if a is not None and b is not None and "" == a.strip() == b.strip():
        return True
    return False


def rebase(Spec, files=None, md=None):
    fileRequester = config.DataFileRequester(type="readonly")
    if not files:
        files = list(sortTests(findTestFiles()))
        if len(files) == 0:
            p("No tests were found")
            return True
    else:
        files = [os.path.join(TEST_DIR, x) for x in files]
    for i,path in enumerate(files, 1):
        justifiedI = str(i).rjust(len(str(len(files))))
        resetSeenMessages()
        name = testNameForPath(path)
        p("{0}/{1}: Rebasing {2}".format(justifiedI, len(files), name))
        doc = Spec(path, fileRequester=fileRequester, testing=True)
        if md:
            doc.mdCommandLine = md
        addTestMetadata(doc)
        doc.preprocess()
        doc.finish()

def addTestMetadata(doc):
    doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
    doc.mdCommandLine.addData("Date", "1970-01-01")
    doc.mdCommandLine.addData("Inline Github Issues", "no")
