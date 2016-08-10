# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import glob
import io
import difflib
import subprocess
import pipes
from itertools import *
from .messages import *
from .htmlhelpers import parseDocument, outerHTML
from . import config

def runAllTests(constructor):
    numPassed = 0
    total = 0
    testFolder = config.scriptPath + "/../tests/"
    for testname in glob.glob(testFolder + "*.bs"):
        total += 1
        doc = constructor(inputFilename=testname)
        doc.preprocess()
        outputText = doc.serialize()
        with io.open(testname[:-2] + "html", encoding="utf-8") as golden:
            goldenText = golden.read()
        if compare(outputText, goldenText):
            numPassed += 1
        else:
            p(testname)
    if total == 0:
        p("No tests were found in '{0}'.".format(testFolder))
    elif numPassed == total:
        p("\033[32;1m✔ All tests passed.\033[0m")
        return True
    else:
        p("\033[31;1m✘ {0}/{1} tests passed.\033[0m".format(numPassed, total))

def compare(suspect, golden):
    suspectDoc = parseDocument(suspect)
    goldenDoc = parseDocument(golden)
    for s, g in izip(suspectDoc.iter(), goldenDoc.iter()):
        if s.tag == g.tag and s.text == g.text and s.tail == g.tail and s.get('id') == g.get('id'):
            continue
        fromText = outerHTML(g)
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

def rebase(files=None):
    if not files:
        files = glob.glob(config.scriptPath + "/../tests/*.bs")
    for file in files:
        p("Rebasing {0}".format(file))
        subprocess.call("bikeshed -qf spec {0}".format(pipes.quote(file)), shell=True)
