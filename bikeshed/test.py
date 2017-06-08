# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import difflib
import glob
import io
import pipes
import subprocess
from itertools import *
from . import config
from .htmlhelpers import parseDocument, outerHTML, nodeIter, isElement, findAll
from .messages import *


def runAllTests(constructor, testFiles):
    numPassed = 0
    if len(testFiles) == 0:
        testFolder = config.scriptPath + "/../tests/"
        testFiles = glob.glob(testFolder + "*.bs")
        if len(testFiles) == 0:
            p("No tests were found in '{0}'.".format(testFolder))
            return True
    total = 0
    fails = []
    for testPath in testFiles:
        _,_,testName = testPath.rpartition("/")
        p(testName)
        total += 1
        doc = constructor(inputFilename=testPath)
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


def rebase(files=None):
    if not files:
        files = glob.glob(config.scriptPath + "/../tests/*.bs")
    for path in files:
        _,_,name = path.rpartition("/")
        p("Rebasing {0}".format(name))
        subprocess.call("bikeshed -qf spec {0}".format(pipes.quote(path)), shell=True)
