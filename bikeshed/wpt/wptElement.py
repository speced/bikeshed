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
	for el in wptElements:
		for testName in testNamesFromEl(el):
			if testName not in testData:
				die("Couldn't find WPT test '{0}' - did you misspell something?", testName, el=el)
				continue
	createHTML(doc, wptElements)


def createHTML(doc, wptElements):
	if doc.md.wptDisplay == "none":
		for el in wptElements:
			removeNode(el)
	elif doc.md.wptDisplay == "inline":
		for blockEl in wptElements:
			testNames = testNamesFromEl(blockEl)
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


def testNamesFromEl(el):
	return [x.strip() for x in textContent(el).split("\n") if x.strip() != ""]


def loadTestData(doc):
	return set(x.strip() for x in config.retrieveDataFile("wpt-tests.txt", quiet=True).readlines())
