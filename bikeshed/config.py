# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import os.path
import re
from collections import defaultdict

debug = False
quiet = False
dryRun = False
minify = True
scriptPath = unicode(os.path.dirname(os.path.realpath(__file__)), encoding="utf-8")
doc = None
textMacros = {}
dfnClassToType = {
    "propdef"         : "property",
    "valuedef"        : "value",
    "at-ruledef"      : "at-rule",
    "descdef"         : "descriptor",
    "typedef"         : "type",
    "funcdef"         : "function",
    "selectordef"     : "selector",
    "elementdef"      : "element",
    "element-attrdef" : "element-attr",
    "eventdef"        : "event",
    "interfacedef"    : "interface",
    "constructordef"  : "constructor",
    "methoddef"       : "method",
    "argdef"          : "argument",
    "attrdef"         : "attribute",
    "callbackdef"     : "callback",
    "dictdef"         : "dictionary",
    "dict-memberdef"  : "dict-member",
    "exceptdef"       : "exception",
    "except-fielddef" : "except-field",
    "exception-codedef"  : "exception-code",
    "enumdef"         : "enum",
    "constdef"        : "const",
    "typedefdef"      : "typedef",
    "stringdef"       : "stringifier",
    "serialdef"       : "serializer",
    "iterdef"         : "iterator",
    "headingdef"      : "heading" }

dfnTypes = frozenset(dfnClassToType.values())
maybeTypes = frozenset(["value", "type", "at-rule", "function", "selector"])
idlTypes = frozenset(["event", "interface", "constructor", "method", "argument", "attribute", "callback", "dictionary", "dict-member", "exception", "except-field", "exception-code", "enum", "const", "typedef", "stringifier", "serializer", "iterator"])
functionishTypes = frozenset(["function", "method", "constructor"])
linkTypes = dfnTypes | frozenset(["propdesc", "functionish", "idl", "maybe", "biblio"])
typesUsingFor = frozenset(["descriptor", "value", "method", "constructor", "argument", "attribute", "const", "dict-member", "event", "except-field", "stringifier", "serializer", "iterator"])

linkTypeToDfnType = {
    "propdesc": frozenset(["property", "descriptor"]),
    "functionish": functionishTypes,
    "idl": idlTypes,
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"])
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])

# Some of the more significant types and their patterns
trivialPattern = re.compile(".+")
typeRe = defaultdict(lambda:trivialPattern)
typeRe["property"] = re.compile("^[\w-]+$")
typeRe["at-rule"] = re.compile("^@[\w-]+$")
typeRe["descriptor"] = typeRe["property"]
typeRe["type"] = re.compile("^<[\w-]+>$")
typeRe["function"] = re.compile("^[\w-]+\(.*\)$")
typeRe["selector"] = re.compile("^::?[\w-]+(\(|$)")
typeRe["constructor"] = typeRe["function"]
typeRe["method"] = typeRe["function"]
typeRe["interface"] = re.compile("^\w+$")

anchorDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]
testSuiteDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]

testAnnotationURL = "//test.csswg.org/harness/annotate.js#"
