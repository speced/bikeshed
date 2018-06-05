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

	atLeastOneElement = False

	# <wpt> elements
	wptElements = findAll("wpt", doc)
	seenTestNames = set()
	for el in wptElements:
		atLeastOneElement = True
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
	elif len(wptRestElements) == 1:
		if pathPrefix is None:
			die("Can't use <wpt-rest> without a WPT Path Prefix metadata.")
			return
		atLeastOneElement = True
		prefixedNames = [p for p in testData if p.startswith(pathPrefix) and p not in seenTestNames]
		if len(prefixedNames) == 0:
			die("Couldn't find any tests with the path prefix '{0}'.", pathPrefix)
			return
		createHTML(doc, wptRestElements[0], prefixedNames)
	else:
		checkForOmittedTests(pathPrefix, testData, seenTestNames)

	if atLeastOneElement:
		doc.extraStyles['style-wpt'] = wptStyle



def createHTML(doc, blockEl, testNames):
	if doc.md.wptDisplay == "none":
		removeNode(blockEl)
	elif doc.md.wptDisplay == "inline":
		blockEl.tag = "ul"
		addClass(blockEl, "wpt-tests-block")
		clearContents(blockEl)
		for testName in testNames:
			_,_,lastNameFragment = testName.rpartition("/")
			singleTestEl = E.li({"class": "wpt-test"},
				E.a({"href": "https://wpt.fyi/results/"+testName}, lastNameFragment),
				" ",
				E.a({"title": testName, "href": "http://w3c-test.org/"+testName}, E.small("(live test)")),
				" ",
				E.a({"href": "https://github.com/web-platform-tests/wpt/blob/master/"+testName}, E.small("(source)")))
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


def checkForOmittedTests(pathPrefix, testData, seenTestNames):
	unseenTests = []
	for testPath in testData.keys():
		if testPath.startswith(pathPrefix):
			if testPath not in seenTestNames:
				unseenTests.append(testPath)
	if unseenTests:
		die("There are {0} WPT tests underneath your path prefix aren't in your document and must be added:\n{1}",
			len(unseenTests),
			"\n".join("  " + path for path in sorted(unseenTests)))


def loadTestData(doc):
	paths = {}
	for line in doc.dataFile.fetch("wpt-tests.txt", str=True).split("\n")[1:]:
		testType,_,testPath = line.strip().partition(" ")
		paths[testPath] = testType
	return paths

def xor(a, b):
	return bool(a) != bool(b)

wptStyle = '''
.wpt-tests-block {
	list-style: none;
	border-left: .5em solid hsl(290, 70%, 60%);
	background: hsl(290, 70%, 95%);
	margin: 1em auto;
	padding: .5em;
	display: grid;
	grid-template-columns: 1fr auto auto;
	grid-column-gap: .5em;
}
.wpt-tests-block::before {
	content: "Tests";
	grid-column: 1/-1;
	color: hsl(290, 70%, 30%);
	text-transform: uppercase;
}
.wpt-test {
	display: contents;
}
.wpt-test > a {
	text-decoration: underline;
	border: none;
}
'''
