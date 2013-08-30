debug = False
quiet = False
dryRun = False
scriptPath = "~"
doc = None
textMacros = {}
dfnClassToType = {
    "propdef":"property",
    "descdef":"descriptor",
    "valuedef":"value",
    "typedef":"type",
    "at-ruledef":"at-rule",
    "funcdef":"function",
    "selectordef":"selector",
    "tokendef":"token",
    "interfacedef":"interface",
    "methoddef":"method",
    "attrdef":"attribute",
    "dictdef":"dictionary",
    "dictmemberdef":"dictmember",
    "enumdef":"enum",
    "constdef":"const",
    "callbackdef":"callback",
    "eventdef":"event",
    "html-elemdef":"html-element",
    "html-attrdef":"html-attribute"
}
dfnTypes = frozenset(dfnClassToType.values())
maybeTypes = frozenset(("value", "type", "at-rule", "function", "selector", "token"))
idlTypes = frozenset(("interface", "method", "attribute", "dictionary", "dictmember", "enum", "const", "callback", "event"))
linkTypes = dfnTypes | frozenset(("propdesc", "functionish", "idl", "maybe", "biblio"))
typesUsingFor = frozenset(("descriptor", "value", "method", "attribute", "const", "dictmember", "event"))

linkTypeToDfnType = {
    "propdesc": frozenset(("property", "descriptor")),
    "functionish": frozenset(("function", "method")),
    "idl": idlTypes,
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"])
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])

anchorDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]