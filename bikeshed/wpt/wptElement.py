# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import io

from .. import config
from ..htmlhelpers import findAll, textContent, removeNode, E, addClass, appendChild, clearContents
from ..messages import *

def processWptElements(doc):
	wptElements = findAll("wpt", doc)
	if not wptElements:
		return
	testData = loadTestData(doc)
	pathPrefix = doc.md.wptPathPrefix
	for el in wptElements:
		testNames = testNamesFromEl(el, pathPrefix = pathPrefix)
		for testName in testNames:
			if testName not in testData:
				die("Couldn't find WPT test '{0}' - did you misspell something?", testName, el=el)
				continue
		createHTML(doc, el, testNames)


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
			if pathPrefix.endswith("/") and name.startswith("/"):
				testPath = pathPrefix[:-1] + name
			elif not pathPrefix.endswith("/") and not name.startswith("/"):
				testPath = pathPrefix + "/" + name
			else:
				testPath = pathPrefix + name
			testNames.append(testPath)
	return testNames


def loadTestData(doc):
	return set(x.strip() for x in config.retrieveDataFile("wpt-tests.txt", quiet=True).readlines())


def xor(a, b):
	return bool(a) != bool(b)
