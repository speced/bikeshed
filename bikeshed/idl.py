# -*- coding: utf-8 -*-


import re

from widlparser import parser
from . import config
from .h import *
from .messages import *
from .unsortedJunk import classifyDfns


class IDLUI(object):
    def warn(self, msg):
        die("{0}", msg.rstrip())


class IDLSilent(object):
    def warn(self, msg):
        pass


class DebugMarker(object):
    # Debugging tool for IDL markup

    def markup_construct(self, text, construct):
        return ('<construct-' + construct.idl_type + '>', '</construct-' + construct.idl_type + '>')

    def markup_type(self, text, construct):
        return ('<TYPE for="' + construct.idl_type + '" idlType="' + text + '">', '</TYPE>')

    def markup_primitive_type(self, text, construct):
        return ('<PRIMITIVE for="' + construct.idl_type + '" idlType="' + text + '">', '</PRIMITIVE>')

    def markup_buffer_type(self, text, construct):
        return ('<BUFFER for="' + construct.idl_type + '" idlType="' + text + '">', '</BUFFER>')

    def markup_string_type(self, text, construct):
        return ('<STRING for="' + construct.idl_type + '" idlType="' + text + '">', '</STRING>')

    def markup_object_type(self, text, construct):
        return ('<OBJECT for="' + construct.idl_type + '" idlType="' + text + '">', '</OBJECT>')

    def markup_type_name(self, text, construct):
        return ('<TYPE-NAME idlType="' + construct.idl_type + '">', '</TYPE-NAME>')

    def markup_name(self, text, construct):
        return ('<NAME idlType="' + construct.idl_type + '">', '</NAME>')

    def markup_keyword(self, text, construct):
        return ('<KEYWORD idlType="' + construct.idl_type + '">', '</KEYWORD>')

    def markup_enum_value(self, text, construct):
        return ('<ENUM-VALUE for="' + construct.name + '">', '</ENUM-VALUE>')


class IDLMarker(object):
    def markup_construct(self, text, construct):
        # Fires for every 'construct' in the WebIDL.
        # Some things are "productions", not "constructs".
        return (None, None)

    def markup_type(self, text, construct):
        # Fires for entire type definitions.
        # It'll contain keywords or names, or sometimes more types.
        # For example, a "type" wrapper surrounds an entire union type,
        # as well as its component types.
        return (None, None)

    def markup_primitive_type(self, text, construct):
        return ("<a data-link-type=interface>", "</a>")

    def markup_string_type(self, text, construct):
        return ("<a data-link-type=interface>", "</a>")

    def markup_buffer_type(self, text, construct):
        return ("<a data-link-type=interface>", "</a>")

    def markup_object_type(self, text, construct):
        return ("<a data-link-type=interface>", "</a>")

    def markup_type_name(self, text, construct):
        # Fires for non-defining type names, such as arg types.

        # The names in [Exposed=Foo] are [Global] tokens, not interface names.
        # Since I don't track globals as a link target yet, don't link them at all.
        if construct.idl_type == "extended-attribute" and construct.name == "Exposed":
            return (None, None)

        # The name in [PutForwards=foo] is an attribute of the same interface.
        if construct.idl_type == "extended-attribute" and construct.name == "PutForwards":
            # In [PutForwards=value] attribute DOMString foo
            # the "value" is a DOMString attr
            attr = construct.parent
            if hasattr(attr.member, "rest"):
                type = attr.member.rest.type
            elif hasattr(attr.member, "attribute"):
                type = attr.member.attribute.type
            typeName = str(type).strip()
            if typeName.endswith("?"):
                typeName = typeName[:-1]
            return ('<a data-link-type=attribute data-link-for="{0}">'.format(typeName), '</a>')

        # LegacyWindowAlias defines additional names for the construct,
        # so all the names should be forced <dfn>s, just like the interface name itself.
        if construct.idl_type == "extended-attribute" and construct.name == "LegacyWindowAlias":
            return ('<idl data-idl-type=interface data-lt="{0}">'.format(text), '</idl>')

        if construct.idl_type == "constructor":
            # This shows up for the method name in a [NamedConstructor] extended attribute.
            # The "NamedConstructor" Name already got markup up, so ignore this one.
            return (None, None)

        return ('<a data-link-type="idl-name">', '</a>')

    def markup_keyword(self, text, construct):
        # Fires on the various "keywords" of WebIDL -
        # words that are part of the WebIDL syntax,
        # rather than names exposed to JS.
        # Examples: "interface", "stringifier", the IDL-defined type names like "DOMString" and "long".
        if text == "stringifier":
            if construct.name is None:
                # If no name was defined, you're required to define stringification behavior.
                return ("<a dfn for='{0}' data-lt='stringification behavior'>".format(construct.parent.full_name), "</a>")
            else:
                # Otherwise, you *can* point to/dfn stringification behavior if you want.
                return ("<idl data-export data-idl-type=dfn data-idl-for='{0}' data-lt='stringification behavior' id='{0}-stringification-behavior'>".format(construct.parent.full_name), "</idl>")
        # The remaining built-in types that aren't covered by a more specific function.
        builtinTypes = {
            "any":"interface",
            "sequence":"dfn",
            "record":"dfn",
            "Promise":"interface",
            "FrozenArray":"interface",
            "ObservableArray":"interface",
        }
        if text in builtinTypes:
            return (f'<a data-link-spec=webidl data-link-type="{builtinTypes[text]}">', '</a>')
        return (None, None)

    def markup_name(self, text, construct):
        # Fires for defining names: method names, arg names, interface names, etc.
        idlType = construct.idl_type
        if idlType not in config.idlTypes:
            return (None, None)

        if idlType == "constructor":
            # the [Constructor] extended attr, now deprecated
            die(f"The [Constructor] extended attribute (on {construct.parent.name}) is deprecated, please switch to a constructor() method.")
            return (None, None)

        if idlType == "argument" and construct.parent.idl_type == "constructor":
            # Don't mark up the arguments to [Constructor] either
            return (None, None)

        idlTitle = construct.normal_name
        if idlType == "method" and idlTitle.startswith("constructor("):
            idlType = "constructor"

        extraParameters = ''
        refType = "idl"
        if idlType in config.functionishTypes:
            idlTitle = '|'.join(self.methodLinkingTexts(construct))
        elif idlType == "extended-attribute":
            refType = "link"
        elif idlType == "attribute":
            if hasattr(construct.member, "rest"):
                rest = construct.member.rest
            elif hasattr(construct.member, "attribute"):
                rest = construct.member.attribute
            else:
                die("Can't figure out how to construct attribute-info from:\n  {0}", construct)
            if rest.readonly is not None:
                readonly = 'data-readonly'
            else:
                readonly = ''
            extraParameters = '{0} data-type="{1}"'.format(readonly, str(rest.type).strip())
        elif idlType == "dict-member":
            extraParameters = 'data-type="{0}"'.format(construct.type)
            if construct.default is not None:
                value = str(construct.default).split('=', 1)[1].strip()
                if value.startswith('['):
                    value = '[]'
                elif value.startswith('}'):
                    value = '{}'
                extraParameters += ' data-default="{0}"'.format(escapeAttr(value))
        elif idlType in ["interface", "namespace", "dictionary"]:
            if construct.partial:
                refType = "link"

        if refType == "link":
            elementName = "a"
        else:
            elementName = "idl"

        if idlType in config.typesUsingFor:
            if idlType == "argument" and construct.parent.idl_type == "method":
                interfaceName = construct.parent.parent.name
                methodNames = ["{0}/{1}".format(interfaceName, m) for m in self.methodLinkingTexts(construct.parent)]
                idlFor = "data-idl-for='{0}'".format(", ".join(methodNames))
            else:
                idlFor = "data-idl-for='{0}'".format(construct.parent.full_name)
        else:
            idlFor = ""
        return ('<{name} data-lt="{0}" data-{refType}-type="{1}" {2} {3}>'.format(idlTitle, idlType, idlFor, extraParameters, name=elementName, refType=refType), '</{0}>'.format(elementName))

    def markup_enum_value(self, text, construct):
        return ("<idl data-idl-type=enum-value data-idl-for='{0}' data-lt='{1}'>".format(escapeAttr(construct.name), escapeAttr(text)), "</idl>")

    def encode(self, text):
        return escapeHTML(text)

    def methodLinkingTexts(self, method):
        '''
        Given a method-ish widlparser Construct,
        finds all possible linking texts.
        The full linking text is "foo(bar, baz)";
        beyond that, any optional or variadic arguments can be omitted.
        So, if both were optional,
        "foo(bar)" and "foo()" would both also be valid linking texts.
        '''
        for i,arg in enumerate(method.arguments or []):
            if arg.optional or arg.variadic:
                optStart = i
                break
        else:
            optStart = None

        texts = []

        if optStart is not None:
            prefixes = [method.name]
            if method.name == "constructor":
                prefixes.append(method.parent.name)
            for i in range(optStart, len(method.arguments)):
                argText = ', '.join(arg.name for arg in method.arguments[:i])
                for prefix in prefixes:
                    texts.append(prefix + "(" + argText + ")")

        texts.append(method.normal_name)
        if method.name == "constructor":
            texts.append(method.parent.name + method.normal_name[11:])
        return reversed(texts)


def markupIDL(doc):
    highlightingOccurred = False
    idlEls = findAll("pre.idl:not([data-no-idl]), xmp.idl:not([data-no-idl])", doc)
    for el in findAll("script[type=idl]", doc):
        # To help with syntax-highlighting, <script type=idl> is also allowed here.
        idlEls.append(el)
        el.tag = "pre"
        removeAttr(el, "type")
        addClass(el, "idl")
    # One pass with a silent parser to collect the symbol table.
    symbolTable = None
    for el in idlEls:
        p = parser.Parser(textContent(el), ui=IDLSilent(), symbol_table=symbolTable)
        symbolTable = p.symbol_table
    # Then a real pass to actually mark up the IDL,
    # and collect it for the index.
    for el in idlEls:
        if isNormative(el, doc):
            text = textContent(el)
            # Parse once with a fresh parser, so I can spit out just this <pre>'s markup.
            widl = parser.Parser(text, ui=IDLUI(), symbol_table=symbolTable)
            marker = DebugMarker() if doc.debug else IDLMarker()
            replaceContents(el, parseHTML(str(widl.markup(marker))))
            # Parse a second time with the global one, which collects all data in the doc.
            doc.widl.parse(text)
        addClass(el, "highlight")
        highlightingOccurred = True
    if doc.md.slimBuildArtifact:
        # Remove the highlight-only spans
        for el in idlEls:
            for span in findAll("span", el):
                contents = childNodes(span, clear=True)
                replaceNode(span, *contents)
        return
    if highlightingOccurred:
        doc.extraStyles['style-syntax-highlighting'] += '''
            pre.idl.highlight {
                background: var(--borderedblock-bg, var(--def-bg));
            }
            '''


def processIDL(doc):
    localDfns = set()
    for pre in findAll("pre.idl, xmp.idl", doc):
        if pre.get("data-no-idl") is not None:
            continue
        if not isNormative(pre, doc):
            continue
        forcedInterfaces = []
        for x in (treeAttr(pre, "data-dfn-force") or "").split():
            x = x.strip()
            if x.endswith("<interface>"):
                x = x[:-11]
            forcedInterfaces.append(x)
        for el in findAll("idl", pre):
            idlType = el.get('data-idl-type')
            url = None
            forceDfn = False
            ref = None
            for idlText in el.get('data-lt').split('|'):
                if idlType == "interface" and idlText in forcedInterfaces:
                    forceDfn = True
                for linkFor in config.splitForValues(el.get('data-idl-for', '')) or [None]:
                    ref = doc.refs.getRef(idlType, idlText,
                                          linkFor=linkFor,
                                          status="local",
                                          el=el,
                                          error=False)
                    if ref:
                        url = ref.url
                        break
                if ref:
                    break
            if url is None or forceDfn:
                el.tag = "dfn"
                el.set('data-dfn-type', idlType)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-dfn-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
            else:
                # Copy over the auto-generated linking text to the manual dfn.
                dfn = find(url, doc)
                lts = combineIdlLinkingTexts(el.get("data-lt"), dfn.get("data-lt"))
                dfn.set("data-lt", lts)
                localDfns.add(dfn)

                # Reset the <idl> element to be a link to the manual dfn.
                el.tag = "a"
                el.set('data-link-type', idlType)
                el.set('data-lt', idlText)
                del el.attrib['data-idl-type']
                if el.get('data-idl-for'):
                    el.set('data-link-for', el.get('data-idl-for'))
                    del el.attrib['data-idl-for']
                if el.get('id'):
                    # ID was defensively added by the Marker.
                    del el.attrib['id']

    dfns = findAll("pre.idl:not([data-no-idl]) dfn, xmp.idl:not([data-no-idl]) dfn", doc) + list(localDfns)
    classifyDfns(doc, dfns)
    fixupIDs(doc, dfns)
    doc.refs.addLocalDfns(dfn for dfn in dfns if dfn.get('id') is not None)

def combineIdlLinkingTexts(t1, t2):
    t1s = [normalizeIdlWhitespace(x) for x in (t1 or "").split("|")]
    t2s = [normalizeIdlWhitespace(x) for x in (t2 or "").split("|")]
    for lt in t2s:
        if lt not in t1s:
            t1s.append(lt)
    return "|".join(t1s)

def normalizeIdlWhitespace(text):
    # Remove all whitespace...
    text = re.sub(r"\s+", "", text)
    # Then add whitespace after commas
    text = re.sub(r",", ", ", text)
    return text




def getParser():
    return parser.Parser(ui=IDLSilent())
