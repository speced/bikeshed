# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import difflib
import io
import os
import pipes
import subprocess
from itertools import *
from . import config
from .htmlhelpers import parseDocument, outerHTML, nodeIter, isElement, findAll
from .messages import *


TEST_DIR = os.path.abspath(os.path.join(config.scriptPath(), "..", "tests"))


def findTestFiles():
    for root, dirnames, filenames in os.walk(TEST_DIR):
        for filename in filenames:
            if filename.endswith(".bs"):
                yield os.path.join(root, filename)


# The test name will be the path relative to the tests directory, or the path as
# given if the test is outside of that directory.
def testNameForPath(path):
    if path.startswith(TEST_DIR):
        return path[len(TEST_DIR)+1:]
    return path


def runAllTests(Spec, testFiles=None, md=None):
    if not testFiles:
        testFiles = sorted(findTestFiles())
        if len(testFiles) == 0:
            p("No tests were found")
            return True
    numPassed = 0
    total = 0
    fails = []
    for testPath in testFiles:
        testName = testNameForPath(testPath)
        p(testName)
        total += 1
        doc = Spec(inputFilename=testPath)
        doc.mdBaseline.addData("Date", "1970-01-01")
        doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
        if md is not None:
            doc.mdCommandLine = md
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
    suspectDoc = parseDocument(suspect)
    goldenDoc = parseDocument(golden)
    for s, g in izip(nodeIter(suspectDoc), nodeIter(goldenDoc)):
        if isElement(s) and isElement(g):
            if s.tag == g.tag and compareDicts(s.attrib, g.attrib):
                continue
        elif isinstance(g, basestring) and isinstance(s, basestring):
            if equalOrEmpty(s, g):
                continue
        if isinstance(g, basestring):
            fromText = g
        else:
            fromText = outerHTML(g)
        if isinstance(s, basestring):
            toText = s
        else:
            toText = outerHTML(s)
        differ = difflib.SequenceMatcher(None, fromText, toText)
        for tag, i1, i2, j1, j2 in differ.get_opcodes():
            if tag == "equal":
                p(fromText[i1:i2])
            if tag in ("delete", "replace"):
                p("\033[41m\033[30m" + fromText[i1:i2] + "\033[0m")
            if tag in ("insert", "replace"):
                p("\033[42m\033[30m" + toText[j1:j2] + "\033[0m")
        p("")
        return False
    return True

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
    if not files:
        files = sorted(findTestFiles())
        if len(files) == 0:
            p("No tests were found")
            return True
    for path in files:
        resetSeenMessages()
        name = testNameForPath(path)
        p("Rebasing {0}".format(name))
        doc = Spec(path)
        doc.mdBaseline.addData("Date", "1970-01-01")
        doc.mdBaseline.addData("Boilerplate", "omit feedback-header, omit generator, omit document-revision")
        if md:
            doc.mdCommandLine = md
        doc.preprocess()
        doc.finish()
