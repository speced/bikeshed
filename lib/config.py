debug = False
quiet = False
dryRun = False
scriptPath = "~"
doc = None
textMacros = {}
dfnClassToType = {
    'propdef'         : 'property',
    'valuedef'        : 'value',
    'at-ruledef'      : 'at-rule',
    'descdef'         : 'descriptor',
    'typedef'         : 'type',
    'funcdef'         : 'function',
    'selectordef'     : 'selector',
    'tokendef'        : 'token',
    'elementdef'      : 'element',
    'element-attrdef' : 'element-attr',
    'eventdef'        : 'event',
    'interfacedef'    : 'interface',
    'constructordef'  : 'constructor',
    'methoddef'       : 'method',
    'argdef'          : 'argument',
    'attrdef'         : 'attribute',
    'callbackdef'     : 'callback',
    'dictdef'         : 'dictionary',
    'dict-memberdef'  : 'dict-member',
    'exceptdef'       : 'exception',
    'except-fielddef' : 'except-field',
    'enumdef'         : 'enum',
    'constdef'        : 'const',
    'typedefdef'      : 'typedef' }

dfnTypes = frozenset(dfnClassToType.values()) | frozenset(["dfn"])
maybeTypes = frozenset(["value", "type", "at-rule", "function", "selector", "token"])
idlTypes = frozenset(['event', 'interface', 'constructor', 'method', 'argument', 'attribute', 'callback', 'dictionary', 'dict-member', 'exception', 'except-field', 'enum', 'const', 'typedef'])
functionishTypes = frozenset(["function", "method"])
linkTypes = dfnTypes | frozenset(["propdesc", "functionish", "idl", "maybe", "biblio"])
typesUsingFor = frozenset(["descriptor", "value", "method", "constructor", "argument", "attribute", "const", "dict-member", "event", "except-field"])

linkTypeToDfnType = {
    "propdesc": frozenset(["property", "descriptor"]),
    "functionish": functionishTypes,
    "idl": idlTypes,
    "maybe": maybeTypes,
    "dfn": frozenset(["dfn"])
}
for dfnType in dfnClassToType.values():
    linkTypeToDfnType[dfnType] = frozenset([dfnType])

anchorDataContentTypes = ["application/json", "application/vnd.csswg.shepherd.v1+json"]