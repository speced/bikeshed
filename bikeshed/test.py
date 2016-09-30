# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import glob
import io
import difflib
import subprocess
import pipes
from itertools import *
from .messages import *
from .htmlhelpers import parseDocument, outerHTML, nodeIter, isElement, findAll
from . import config


def runAllTests(constructor):
    numPassed = 0
    total = 0
    testFolder = config.scriptPath + "/../tests/"
    fails = []
    for testname in glob.glob(testFolder + "*.bs"):
        p(testname)
        total += 1
        doc = constructor(inputFilename=testname)
        doc.preprocess()
        outputText = doc.serialize()
        with io.open(testname[:-2] + "html", encoding="utf-8") as golden:
            goldenText = golden.read()
        if compare(outputText, goldenText):
            numPassed += 1
        else:
            fails.append(testname)
    if total == 0:
        p("No tests were found in '{0}'.".format(testFolder))
    elif numPassed == total:
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
            if s.tag == g.tag and s.get('id') == g.get('id'):
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

def equalOrEmpty(a, b):
    if a == b:
        return True
    if a is not None and b is not None and "" == a.strip() == b.strip():
        return True
    return False


def rebase(files=None):
    if not files:
        files = glob.glob(config.scriptPath + "/../tests/*.bs")
    for file in files:
        p("Rebasing {0}".format(file))
        subprocess.call("bikeshed -qf spec {0}".format(pipes.quote(file)), shell=True)
