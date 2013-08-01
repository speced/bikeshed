debug = False
quiet = False
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
    "html-elemdef":"html-element",
    "html-attrdef":"html-attribute"
}
# The types that a "maybe" link will attempt to look to find its value.
dfnTypes = set(dfnClassToType.values())
maybeTypes = frozenset(("value", "type", "at-rule", "function", "selector", "token"))
idlTypes = frozenset(("interface", "method", "attribute", "dictionary", "dictmember", "enum", "const"))
linkTypes = dfnTypes | frozenset(("propdesc", "functionish", "idl", "maybe", "biblio"))
typesUsingFor = frozenset(("descriptor", "value", "method", "attribute", "const", "dictmember"))