import re
from collections import defaultdict

from .. import t

dfnClassToType = {
    "abstract-opdef": "abstract-op",
    "propdef": "property",
    "valdef": "value",
    "at-ruledef": "at-rule",
    "descdef": "descriptor",
    "typedef": "type",
    "funcdef": "function",
    "selectordef": "selector",
    "elementdef": "element",
    "element-attrdef": "element-attr",
    "attr-valuedef": "attr-value",
    "element-statedef": "element-state",
    "eventdef": "event",
    "interfacedef": "interface",
    "namespacedef": "namespace",
    "extendedattrdef": "extended-attribute",
    "constructordef": "constructor",
    "methoddef": "method",
    "argdef": "argument",
    "attrdef": "attribute",
    "callbackdef": "callback",
    "dictdef": "dictionary",
    "dict-memberdef": "dict-member",
    "enumdef": "enum",
    "enum-valuedef": "enum-value",
    "exceptiondef": "exception",
    "constdef": "const",
    "typedefdef": "typedef",
    "stringdef": "stringifier",
    "serialdef": "serializer",
    "iterdef": "iterator",
    "mapdef": "maplike",
    "setdef": "setlike",
    "grammardef": "grammar",
    "schemedef": "scheme",
    "statedef": "state",
    "modedef": "mode",
    "contextdef": "context",
    "facetdef": "facet",
    "http-headerdef": "http-header",
    "permissiondef": "permission",
}


dfnTypes = frozenset(list(dfnClassToType.values()) + ["dfn"])
maybeTypes = frozenset(["value", "type", "at-rule", "function", "selector"])
cssTypes = frozenset(["property", "value", "at-rule", "descriptor", "type", "function", "selector"])
markupTypes = frozenset(["element", "element-attr", "element-state", "attr-value"])
idlTypes = frozenset(
    [
        "event",
        "interface",
        "namespace",
        "extended-attribute",
        "constructor",
        "method",
        "argument",
        "attribute",
        "callback",
        "dictionary",
        "dict-member",
        "enum",
        "enum-value",
        "exception",
        "const",
        "typedef",
        "stringifier",
        "serializer",
        "iterator",
        "maplike",
        "setlike",
        "permission",
    ]
)
idlNameTypes = frozenset(["interface", "namespace", "dictionary", "enum", "typedef", "callback"])
functionishTypes = frozenset(["function", "method", "constructor", "stringifier"])
idlMethodTypes = frozenset(["method", "constructor", "stringifier", "idl", "idl-name"])
linkTypes = dfnTypes | frozenset(["propdesc", "functionish", "idl", "idl-name", "element-sub", "maybe", "biblio"])
typesUsingFor = frozenset(
    [
        "descriptor",
        "value",
        "element-attr",
        "attr-value",
        "element-state",
        "method",
        "constructor",
        "argument",
        "attribute",
        "const",
        "dict-member",
        "event",
        "enum-value",
        "stringifier",
        "serializer",
        "iterator",
        "maplike",
        "setlike",
        "state",
        "mode",
        "context",
        "facet",
    ]
)
typesNotUsingFor = frozenset(
    [
        "property",
        "element",
        "interface",
        "namespace",
        "callback",
        "dictionary",
        "enum",
        "exception",
        "typedef",
        "http-header",
        "permission",
    ]
)
assert not (typesUsingFor & typesNotUsingFor)
lowercaseTypes = (
    cssTypes
    | markupTypes
    | frozenset(["propdesc", "element-sub", "maybe", "dfn", "grammar", "http-header", "permission"])
)


linkTypeToDfnType = {
    "propdesc": frozenset(["property", "descriptor"]),
    "functionish": functionishTypes,
    "idl": idlTypes,
    "idl-name": idlNameTypes,
    "element-sub": frozenset(["element-attr", "element-state"]),
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"]),
    "biblio": frozenset(["biblio"]),
    "codelike": frozenset(["element", "element-attr", "element-state", "attr-value"]) | idlTypes,
    "all": linkTypes,
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])


specStatuses = frozenset(["current", "snapshot"])
linkStatuses = frozenset(["current", "snapshot", "local", "anchor-block"])


def linkTypeIn(startTypes, targetTypes="all"):
    # Tests if two link/dfn types are "compatible",
    # such that they share at least one base type when expanded.
    # (All dfn types are "base"; link types like "idl" are shorthand,
    #  and expand into one or more base types.)
    # Called with no arguments,
    # tests if the passed type is a valid dfn/link type.
    if isinstance(startTypes, str):
        startTypes = linkTypeToDfnType[startTypes]
    else:
        startTypes = set(startTypes)
    if isinstance(targetTypes, str):
        targetTypes = linkTypeToDfnType[targetTypes]
    else:
        targetTypes = set(targetTypes)
    return bool(startTypes & targetTypes)


# Elements that are allowed to provide definitions to Shepherd
dfnElements = frozenset(["dfn", "h2", "h3", "h4", "h5", "h6"])
anchorishElements = dfnElements.union(["a"])
dfnElementsSelector = "dfn:not([data-var-ignore]), h2[data-dfn-type], h3[data-dfn-type], h4[data-dfn-type], h5[data-dfn-type], h6[data-dfn-type]"


# Some of the more significant types and their patterns
trivialPattern = re.compile(r".+")
typeRe: t.Dict[str, re.Pattern]
typeRe = defaultdict(lambda: trivialPattern)
typeRe["property"] = re.compile(r"^[\w-]+$")
typeRe["at-rule"] = re.compile(r"^@[\w-]+$")
typeRe["descriptor"] = typeRe["property"]
typeRe["type"] = re.compile(r"^<[\w-]+>$")
typeRe["function"] = re.compile(r"^[\w-]+\(.*\)$")
typeRe["selector"] = re.compile(r"^::?[\w-]+(\(|$)")
typeRe["constructor"] = typeRe["function"]
typeRe["method"] = typeRe["function"]
typeRe["interface"] = re.compile(r"^\w+$")
