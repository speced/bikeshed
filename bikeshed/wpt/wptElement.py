# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io

from .. import config
from ..htmlhelpers import findAll, textContent, removeNode, E, addClass, appendChild, clearContents
from ..messages import *

def processWptElements(doc):
	testData = loadTestData(doc)
	pathPrefix = doc.md.wptPathPrefix
	if pathPrefix is not None and not pathPrefix.endswith("/"):
		pathPrefix += "/"

	# <wpt> elements
	wptElements = findAll("wpt", doc)
	seenTestNames = set()
	for el in wptElements:
		testNames = testNamesFromEl(el, pathPrefix=pathPrefix)
		for testName in testNames:
			if testName not in testData:
				die("Couldn't find WPT test '{0}' - did you misspell something?", testName, el=el)
				continue
			seenTestNames.add(testName)
		createHTML(doc, el, testNames)

	# <wpt-rest> elements
	wptRestElements = findAll("wpt-rest", doc)
	if len(wptRestElements) > 1:
		die("Only one <wpt-rest> element allowed per document, you have {0}.", len(wptRestElements))
		wptRestElements = wptRestElements[0:1]
	if len(wptRestElements) == 1:
		if pathPrefix is None:
			die("Can't use <wpt-rest> without a WPT Path Prefix metadata.")
			return
		prefixedNames = [p for p in testData if p.startswith(pathPrefix) and p not in seenTestNames]
		if len(prefixedNames) == 0:
			die("Couldn't find any tests with the path prefix '{0}'.", pathPrefix)
			return
		createHTML(doc, wptRestElements[0], prefixedNames)



def createHTML(doc, blockEl, testNames):
	if doc.md.wptDisplay == "none":
		removeNode(blockEl)
	elif doc.md.wptDisplay == "inline":
		blockEl.tag == "ul"
		addClass(blockEl, "wpt-tests-block")
		clearContents(blockEl)
		for testName in testNames:
			_,_,lastNameFragment = testName.rpartition("/")
			singleTestEl = E.li({"class": "wpt-test"},
				E.a({"title": testName, "href": "http://w3c-test.org/"+testName}, "Test: " + lastNameFragment),
				" ",
				E.a({"href": "view-source:w3c-test.org/"+testName}, E.small("(source)")))
			appendChild(blockEl, singleTestEl)
	else:
		die("Programming error, uncaught WPT Display value in createHTML.")


def testNamesFromEl(el, pathPrefix=None):
	testNames = []
	for name in [x.strip() for x in textContent(el).split("\n")]:
		if name == "":
			continue
		if pathPrefix is None:
			testNames.append(name)
		else:
			if name.startswith("/"):
				testPath = pathPrefix + name[1:]
			else:
				testPath = pathPrefix + name
			testNames.append(testPath)
	return testNames


def prefixPlusPath(prefix, path):
	if prefix.endswith("/") and path.startswith("/"):
		return prefix[:-1] + path
	elif not prefix.endswith("/") and not path.startswith("/"):
		return prefix + "/" + path
	else:
		return prefix + path


def loadTestData(doc):
	return set(x.strip() for x in doc.dataFile.fetch("wpt-tests.txt", str=True).split("\n"))


def xor(a, b):
	return bool(a) != bool(b)
