# -*- coding: utf-8 -*-


import io

from .. import config
from ..h import findAll, textContent, removeNode, E, addClass, appendChild, clearContents
from ..messages import *

def processWptElements(doc):
	pathPrefix = doc.md.wptPathPrefix

	atLeastOneElement = False
	testData = None
	# <wpt> elements
	wptElements = findAll("wpt", doc)
	seenTestNames = set()
	for el in wptElements:
		atLeastOneElement = True
		if testData is None:
			testData = loadTestData(doc)
		testNames = testNamesFromEl(el, pathPrefix=pathPrefix)
		for testName in testNames:
			if testName not in testData:
				die("Couldn't find WPT test '{0}' - did you misspell something?", testName, el=el)
				continue
			seenTestNames.add(testName)
		createHTML(doc, el, testNames)

	# <wpt-rest> elements
	wptRestElements = findAll("wpt-rest", doc)
	if wptRestElements and testData is None:
		testData = loadTestData(doc)
	if len(wptRestElements) > 1:
		die("Only one <wpt-rest> element allowed per document, you have {0}.", len(wptRestElements))
		wptRestElements = wptRestElements[0:1]
	elif len(wptRestElements) == 1:
		localPrefix = wptRestElements[0].get("pathprefix")
		if localPrefix is not None:
			pathPrefix = localPrefix
		if pathPrefix is None:
			die("Can't use <wpt-rest> without either a pathprefix="" attribute or a 'WPT Path Prefix' metadata.")
			return
		atLeastOneElement = True
		prefixedNames = [p for p in testData if prefixInPath(pathPrefix, p) and p not in seenTestNames]
		if len(prefixedNames) == 0:
			die("Couldn't find any tests with the path prefix '{0}'.", pathPrefix)
			return
		createHTML(doc, wptRestElements[0], prefixedNames)
		warn("<wpt-rest> is intended for debugging only. Move the tests to <wpt> elements next to what they're testing.")
	else:
		if pathPrefix:
			if testData is None:
				testData = loadTestData(doc)
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
			if ".https." in testName or ".serviceworker." in testName:
				liveTestScheme = "https"
			else:
				liveTestScheme = "http"
			_,_,lastNameFragment = testName.rpartition("/")
			singleTestEl = E.li({"class": "wpt-test"},
				E.a({"href": "https://wpt.fyi/results/"+testName}, lastNameFragment),
				" ",
				E.a({"title": testName, "href": "{0}://web-platform-tests.live/{1}".format(liveTestScheme, testName)}, E.small("(live test)")),
				" ",
				E.a({"href": "https://github.com/web-platform-tests/wpt/blob/master/"+testName}, E.small("(source)")))
			appendChild(blockEl, singleTestEl)
	else:
		die("Programming error, uncaught WPT Display value in createHTML.")


def testNamesFromEl(el, pathPrefix=None):
	testNames = []
	localPrefix = el.get("pathprefix")
	if localPrefix is not None:
		pathPrefix = localPrefix
	for name in [x.strip() for x in textContent(el).split("\n")]:
		if name == "":
			continue
		testName = prefixPlusPath(pathPrefix, name)
		testNames.append(testName)
	return testNames


def prefixPlusPath(prefix, path):
	# Join prefix to path, normalizing slashes
	if path.startswith("/"):
		return path[1:]
	prefix = normalizePathSegment(prefix)
	if prefix is None:
		return path
	return prefix + path

def prefixInPath(prefix, path):
	if prefix is None:
		return False
	return path.startswith(normalizePathSegment(prefix))

def normalizePathSegment(pathSeg):
	# No slash at front, yes slash at end
	if pathSeg is None:
		return None
	if pathSeg.startswith("/"):
		pathSeg = pathSeg[1:]
	if not pathSeg.endswith("/"):
		pathSeg += "/"
	return pathSeg

def checkForOmittedTests(pathPrefix, testData, seenTestNames):
	unseenTests = []
	for testPath in testData.keys():
		if ".tentative." in testPath:
			continue
		if prefixInPath(pathPrefix, testPath):
			if testPath not in seenTestNames:
				unseenTests.append(testPath)
	if unseenTests:
		warn("There are {0} WPT tests underneath your path prefix that aren't in your document and must be added:\n{1}",
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
:root {
	--wpt-border: hsl(290, 70%, 60%);
	--wpt-bg: hsl(290, 70%, 95%)
	--wpt-text: var(--text);
	--wptheading-text: hsl(290, 70%, 30%);
}
@media (prefers-color-scheme: dark) {
	:root {
		--wpt-border: hsl(290, 70%, 30%);
		--wpt-bg: var(--borderedblock-bg);
		--wpt-text: var(--text);
		--wptheading-text: hsl(290, 70%, 60%);
	}
}
.wpt-tests-block {
	list-style: none;
	border-left: .5em solid hsl(290, 70%, 30%);
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
