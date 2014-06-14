# -*- coding: utf-8 -*-

from __future__ import division, unicode_literals
import glob
import io
from itertools import *
from .htmlhelpers import parseDocument, outerHTML
from . import config

def runAllTests(constructor):
	for testname in glob.glob("*.bs"):
		config.doc = constructor(inputFilename=testname)
		config.doc.preprocess()
		outputText = config.doc.serialize()
		goldenText = io.open(testname[:-2] + "html", encoding="utf-8").read()
		if compare(outputText, goldenText):
			continue
		else:
			print "Generated document for {0} doesn't match golden.".format(testname)
			return
	print "\033[32;1mAll tests passed.\033[0m"

def compare(suspect, golden):
	suspectDoc = parseDocument(suspect)
	goldenDoc = parseDocument(golden)
	for s, g in izip(suspectDoc.iter(), goldenDoc.iter()):
		if s.tag == g.tag and s.text == g.text and s.tail == g.tail:
			continue
		print s.tag, g.tag
		return False
	return True
