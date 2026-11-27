from __future__ import annotations

import dataclasses
import re

import widlparser
from lxml import etree

from .. import config, h, t
from .. import messages as m

_MarkupGenerator = widlparser.markup.MarkupGenerator
_MarkupType = widlparser.markup.MarkupType
_MarkupPrimitiveType = widlparser.markup.MarkupPrimitiveType
_MarkupBufferType = widlparser.markup.MarkupBufferType
_MarkupStringType = widlparser.markup.MarkupStringType
_MarkupObjectType = widlparser.markup.MarkupObjectType
_MarkupText = widlparser.markup.MarkupText
_MarkupTypeName = widlparser.markup.MarkupTypeName
_MarkupName = widlparser.markup.MarkupName
_MarkupKeyword = widlparser.markup.MarkupKeyword
_MarkupEnumValue = widlparser.markup.MarkupEnumValue
_Argument = widlparser.constructs.Argument

_BUILTIN_TYPES: dict[str, str] = {
    "any": "interface",
    "sequence": "dfn",
    "record": "dfn",
    "Promise": "interface",
    "FrozenArray": "interface",
    "ObservableArray": "interface",
    "iterable": "dfn",
    "maplike": "dfn",
    "setlike": "dfn",
}

if t.TYPE_CHECKING:
    ElementSpecT = tuple[str, dict[str, str]] | None


@dataclasses.dataclass
class IDLUI:
    lineStart: int | None
    parseContext: str | None = None
    buffered: bool = False
    messages: list[tuple[bool, m.MessageOptions]] = dataclasses.field(default_factory=list)

    @staticmethod
    def fromEl(el: t.ElementT, *, buffered: bool = False) -> IDLUI:
        lineNum = h.parseLineNumber(el)
        context = el.get("bs-parse-context", None)
        return IDLUI(lineStart=lineNum, parseContext=context, buffered=buffered)

    def formatLineNum(self, localNum: int) -> str:
        ret = str((self.lineStart or 0) + localNum)
        if self.parseContext:
            ret += f" of {self.parseContext}"
        return ret

    def formatMessage(self, msg: str) -> m.MessageOptions:
        match = re.match(r".*?LINE: (\d+) - (.*)", msg.strip())
        if not match:
            return m.MessageOptions(msg.rstrip())
        localLineNum = int(match[1])
        detail = match[2]
        return m.MessageOptions(detail, lineNum=self.formatLineNum(localLineNum))

    def warn(self, msg: str) -> None:
        opts = self.formatMessage(msg)
        if self.buffered:
            self.messages.append((True, opts))
        else:
            opts.die()

    def note(self, msg: str) -> None:
        opts = self.formatMessage(msg)
        if self.buffered:
            self.messages.append((False, opts))
        else:
            opts.warn()

    def flush(self) -> None:
        for isError, opts in self.messages:
            if isError:
                opts.die()
            else:
                opts.warn()
        self.messages.clear()


class IDLSilent:
    def warn(self, msg: str) -> None:
        pass

    def note(self, msg: str) -> None:
        pass


class IDLTreeBuilder:
    """
    Walks a widlparser MarkupGenerator tree and populates an lxml container directly,
    without round-tripping through HTML string serialization and reparsing.
    """

    def __init__(self) -> None:
        self._parentEl: t.ElementT | None = None
        self._lastChild: t.ElementT | None = None
        self._textBuf: list[str] = []
        self._strippingLeading: bool = True
        self._lineOffset: int = 1
        self._symbolTable: dict[str, widlparser.Construct] | None = None
        self._ui: IDLUI | None = None

    def buildInto(self, container: t.ElementT, widl: widlparser.parser.Parser) -> None:
        self.buildIntoConstructs(container, widl.constructs)

    def buildIntoConstructs(
        self,
        container: t.ElementT,
        constructs: t.Sequence[widlparser.Construct],
        *,
        symbolTable: dict[str, widlparser.Construct] | None = None,
        ui: IDLUI | None = None,
    ) -> None:
        h.clearContents(container)
        generator = _MarkupGenerator(None)
        for construct in constructs:
            construct.define_markup(generator)
        self._parentEl = container
        self._lastChild = None
        self._textBuf = []
        self._strippingLeading = True
        self._lineOffset = 1
        self._symbolTable = symbolTable
        self._ui = ui
        self._visitChildren(generator.children, None)
        self._flushText()
        self._parentEl = None
        self._lastChild = None
        self._symbolTable = None
        self._ui = None

    def buildNodes(self, widl: widlparser.parser.Parser) -> list[t.NodeT]:
        return self.buildNodesFromConstructs(widl.constructs)

    def buildNodesFromConstructs(
        self,
        constructs: t.Sequence[widlparser.Construct],
        *,
        symbolTable: dict[str, widlparser.Construct] | None = None,
        ui: IDLUI | None = None,
    ) -> list[t.NodeT]:
        container = etree.Element("div")
        self.buildIntoConstructs(container, constructs, symbolTable=symbolTable, ui=ui)
        return h.childNodes(container, clear=True)

    def _flushText(self) -> None:
        if not self._textBuf:
            return
        assert self._parentEl is not None
        chunk = "".join(self._textBuf)
        self._textBuf.clear()
        if self._lastChild is None:
            self._parentEl.text = chunk
        else:
            self._lastChild.tail = chunk

    def _emitText(self, text: str) -> None:
        if not text:
            return
        if "\n" in text:
            self._lineOffset += text.count("\n")
        if self._strippingLeading:
            text = text.lstrip()
            if not text:
                return
            self._strippingLeading = False
        self._textBuf.append(text)

    def _emitLeaf(self, spec: ElementSpecT, text: str) -> None:
        if spec is None:
            self._emitText(text)
            return
        if "\n" in text:
            self._lineOffset += text.count("\n")
        self._flushText()
        self._strippingLeading = False
        assert self._parentEl is not None
        tag, attrs = spec
        child = etree.SubElement(self._parentEl, tag, attrs)
        child.text = text
        self._lastChild = child

    def _emitWrapped(
        self,
        spec: ElementSpecT,
        children: list[widlparser.markup.MarkupGenerator],
        construct: widlparser.Construct | None,
    ) -> None:
        if spec is None:
            self._visitChildren(children, construct)
            return
        self._flushText()
        self._strippingLeading = False
        assert self._parentEl is not None
        tag, attrs = spec
        child = etree.SubElement(self._parentEl, tag, attrs)
        prevParent = self._parentEl
        prevBuf = self._textBuf
        self._parentEl = child
        self._lastChild = None
        self._textBuf = []
        self._visitChildren(children, construct)
        self._flushText()
        self._parentEl = prevParent
        self._lastChild = child
        self._textBuf = prevBuf

    def _checkDictionaryArguments(self, args: list[widlparser.constructs.Argument], lineOffset: int) -> None:
        assert self._symbolTable is not None
        for index, argument in enumerate(args):
            if argument.required and argument.type is not None:
                for typeName in argument.type.type_names:
                    sym = self._symbolTable.get(typeName)
                    if (
                        sym is not None
                        and sym.idl_type == "dictionary"
                        and not t.cast(widlparser.Dictionary, sym).required
                        and not any(arg2.required for arg2 in args[index + 1 :])
                    ):
                        lineNum = self._ui.formatLineNum(lineOffset) if self._ui is not None else None
                        m.die(
                            f'Dictionary argument "{argument.name}" without required members must be marked optional',
                            lineNum=lineNum,
                        )

    def _visitChildren(
        self,
        nodes: list[widlparser.markup.MarkupGenerator],
        construct: widlparser.Construct | None,
    ) -> None:
        args: list[widlparser.constructs.Argument] | None = None
        lastArgLine = 1
        for node in nodes:
            nodeType = type(node)
            if nodeType is _MarkupText:
                self._emitText(node.text)
            elif nodeType is _MarkupGenerator:
                spec = self._constructSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
                if isinstance(node.construct, _Argument):
                    if args is None:
                        args = [node.construct]
                    else:
                        args.append(node.construct)
                    lastArgLine = self._lineOffset
            elif nodeType is _MarkupType:
                spec = self._typeSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
            elif nodeType is _MarkupKeyword:
                assert construct is not None
                self._emitLeaf(self._keywordSpec(node.text, construct), node.text)
            elif nodeType is _MarkupName:
                assert construct is not None
                self._emitLeaf(self._nameSpec(node.text, construct), node.text)
            elif nodeType is _MarkupTypeName:
                assert construct is not None
                self._emitLeaf(self._typeNameSpec(node.text, construct), node.text)
            elif nodeType is _MarkupPrimitiveType:
                spec = self._primitiveTypeSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
            elif nodeType is _MarkupStringType:
                spec = self._stringTypeSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
            elif nodeType is _MarkupBufferType:
                spec = self._bufferTypeSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
            elif nodeType is _MarkupObjectType:
                spec = self._objectTypeSpec(node) if node.construct is not None else None
                self._emitWrapped(spec, node.children, node.construct)
            elif nodeType is _MarkupEnumValue:
                assert construct is not None
                self._emitLeaf(self._enumValueSpec(node.text, construct), node.text)
            else:
                msg = f"Unexpected widlparser markup node: {nodeType.__name__}"
                raise TypeError(msg)
        if args is not None and self._symbolTable is not None:
            self._checkDictionaryArguments(args, lastArgLine)

    def _constructSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _typeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _primitiveTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _bufferTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _stringTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _objectTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return None

    def _typeNameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text, construct
        return None

    def _nameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text, construct
        return None

    def _keywordSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text, construct
        return None

    def _enumValueSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text, construct
        return None


class DebugIDLBuilder(IDLTreeBuilder):
    # Debugging tool for IDL markup

    def _constructSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return (f"construct-{node.construct.idl_type}", {})

    def _typeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return ("type", {"for": node.construct.idl_type, "idltype": node.text})

    def _primitiveTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return ("primitive", {"for": node.construct.idl_type, "idltype": node.text})

    def _bufferTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return ("buffer", {"for": node.construct.idl_type, "idltype": node.text})

    def _stringTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return ("string", {"for": node.construct.idl_type, "idltype": node.text})

    def _objectTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        assert node.construct is not None
        return ("object", {"for": node.construct.idl_type, "idltype": node.text})

    def _typeNameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text
        return ("type-name", {"idltype": construct.idl_type})

    def _nameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text
        return ("name", {"idltype": construct.idl_type})

    def _keywordSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text
        return ("keyword", {"idltype": construct.idl_type})

    def _enumValueSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        del text
        return ("enum-value", {"for": construct.idl_type})


class IDLBuilder(IDLTreeBuilder):
    errors: list[str]

    def __init__(self) -> None:
        super().__init__()
        self.errors = []

    def _primitiveTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return ("a", {"data-link-type": "interface"})

    def _stringTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return ("a", {"data-link-type": "interface"})

    def _bufferTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return ("a", {"data-link-type": "interface"})

    def _objectTypeSpec(self, node: widlparser.markup.MarkupGenerator) -> ElementSpecT:
        del node
        return ("a", {"data-link-type": "interface"})

    def _typeNameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        # Fires for non-defining type names, such as arg types.
        # The names in [Exposed=Foo] are [Global] tokens, not interface names.
        # Since I don't track globals as a link target yet, don't link them at all.
        if construct.idl_type == "extended-attribute" and construct.name == "Exposed":
            return None

        # The name in [PutForwards=foo] is an attribute of the same interface.
        if construct.idl_type == "extended-attribute" and construct.name == "PutForwards":
            # In [PutForwards=value] attribute DOMString foo
            # the "value" is a DOMString attr
            member = construct.parent.member  # type: ignore
            if hasattr(member, "rest"):
                memberType = member.rest.type
            elif hasattr(member, "attribute"):
                memberType = member.attribute.type
            else:
                assert False, "unreachable"
            typeName = str(memberType).strip()
            if typeName.endswith("?"):
                typeName = typeName[:-1]
            return ("a", {"data-link-type": "attribute", "bs-link-for": typeName})

        # LegacyWindowAlias defines additional names for the construct,
        # so all the names should be forced <dfn>s, just like the interface name itself.
        if construct.idl_type == "extended-attribute" and construct.name == "LegacyWindowAlias":
            return ("idl", {"bs-idl-type": "interface", "bs-lt": text})

        # The constructor name in [LegacyFactoryFunction], needs to actually be marked up
        # as the definition of the function.
        if construct.idl_type == "constructor":
            interfaceName = construct.parent.name
            assert interfaceName is not None
            methodName = construct.normal_name
            assert methodName is not None
            return ("idl", {"bs-idl-type": "constructor", "bs-idl-for": interfaceName, "bs-lt": methodName})

        return ("a", {"data-link-type": "idl-name"})

    def _keywordSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        # Fires on the various "keywords" of WebIDL -
        # words that are part of the WebIDL syntax,
        # rather than names exposed to JS.
        # Examples: "interface", "stringifier", the IDL-defined type names like "DOMString" and "long".
        if text == "stringifier":
            parentName = construct.parent.full_name
            assert parentName is not None
            if construct.name is None:
                # If no name was defined, you're required to define stringification behavior.
                return ("a", {"data-link-type": "dfn", "for": parentName, "bs-lt": "stringification behavior"})
            # Otherwise, you *can* point to/dfn stringification behavior if you want.
            return (
                "idl",
                {
                    "data-export": "",
                    "bs-idl-type": "dfn",
                    "bs-idl-for": parentName,
                    "bs-lt": "stringification behavior",
                    "id": f"{parentName}-stringification-behavior",
                },
            )
        if text in ("getter", "setter", "deleter") and construct.idl_type == "method":
            # An unnamed special operation gets the pretend name __getter__ etc,
            # so the keyword stands in for the name.
            # Link it to the method dfn if the spec has one;
            # most specs don't define these, so fail silently otherwise.
            if construct.name == f"__{text}__":
                parentName = construct.parent.full_name
                assert parentName is not None
                return (
                    "a",
                    {
                        "data-link-type": "method",
                        "bs-link-for": parentName,
                        "bs-lt": t.cast(str, construct.normal_name),
                        "bs-okay-to-fail": "",
                        "bs-unwrap-on-link-fail": "",
                    },
                )
            return None
        # The remaining built-in types that aren't covered by a more specific function.
        if (builtinType := _BUILTIN_TYPES.get(text)) is not None:
            return ("a", {"bs-link-spec": "webidl", "data-link-type": builtinType})
        return None

    def _nameSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        # Fires for defining names: method names, arg names, interface names, etc.
        idlType = construct.idl_type
        if idlType not in config.idlTypes:
            return None

        if idlType == "constructor":
            # one of the constructor extended attr, now deprecated
            if text == "Constructor":
                self.errors.append(
                    f"The [Constructor] extended attribute (on {construct.parent.name}) is deprecated, please switch to a constructor() method.",
                )
                return None
            # Otherwise it's [LegacyNamedConstructor], which is allowed
            return ("a", {"data-link-type": "extended-attribute", "bs-link-for": ""})

        if idlType == "argument" and construct.parent.idl_type == "constructor":
            # Don't mark up the arguments to [Constructor] either
            return None

        attrs: dict[str, str] = {}
        refType = "idl"

        idlTitle = construct.normal_name
        if idlType == "method" and idlTitle and idlTitle.startswith("constructor("):
            idlType = "constructor"
        if idlType in config.functionishTypes:
            idlTitle = "|".join(self.methodLinkingTexts(construct))  # type: ignore
        assert idlTitle is not None

        if idlType in config.functionishTypes:
            pass
        elif idlType == "extended-attribute":
            refType = "link"
        elif idlType == "attribute":
            member = construct.member  # type: ignore
            if hasattr(member, "rest"):
                rest = member.rest
            elif hasattr(member, "attribute"):
                rest = member.attribute
            else:
                self.errors.append(f"Can't figure out how to construct attribute-info from:\n  {construct}")
                return None
            if rest.readonly is not None:
                attrs["bs-readonly"] = ""
            attrs["bs-type"] = str(rest.type.type) + str(rest.type.suffix or "")
        elif idlType == "dict-member":
            assert isinstance(construct, widlparser.DictionaryMember)
            attrs["bs-type"] = str(construct.type.type) + str(construct.type.suffix or "")
            if construct.default is not None:
                value = str(construct.default).split("=", 1)[1].strip()
                if value.startswith("["):
                    value = "[]"
                elif value.startswith("}"):
                    value = "{}"
                attrs["bs-default"] = value
        elif idlType in ["interface", "namespace", "dictionary"]:
            if construct.partial:  # type: ignore
                refType = "link"

        elementName = "a" if refType == "link" else "idl"

        if idlType in config.typesUsingFor:
            if idlType == "argument" and construct.parent.idl_type == "method":
                interfaceName = construct.parent.parent.name
                methodNames = [f"{interfaceName}/{m}" for m in self.methodLinkingTexts(construct.parent)]  # type: ignore
                attrs["bs-idl-for"] = ", ".join(methodNames)
            else:
                parentName = construct.parent.full_name
                assert parentName is not None
                attrs["bs-idl-for"] = parentName

        attrs["bs-lt"] = idlTitle
        if refType == "link":
            attrs["data-link-type"] = idlType
        else:
            attrs["bs-idl-type"] = idlType
        return (elementName, attrs)

    def _enumValueSpec(self, text: str, construct: widlparser.Construct) -> ElementSpecT:
        return ("idl", {"bs-idl-type": "enum-value", "bs-idl-for": t.cast(str, construct.name), "bs-lt": text})

    def methodLinkingTexts(self, method: widlparser.OperationRest) -> list[str]:
        """
        Given a method-ish widlparser Construct,
        finds all possible linking texts.
        The full linking text is "foo(bar, baz)";
        beyond that, any optional or variadic arguments can be omitted.
        So, if both were optional,
        "foo(bar)" and "foo()" would both also be valid linking texts.
        """
        for i, arg in enumerate(method.arguments or []):
            assert isinstance(arg, widlparser.constructs.Argument)
            if arg.optional or arg.variadic:
                optStart = i
                break
        else:
            optStart = None

        texts = []

        if optStart is not None:
            prefixes = [t.cast(str, method.name)]
            if method.name == "constructor":
                prefixes.append(t.cast(str, method.parent.name))
            for i in range(optStart, len(method.arguments)):
                argText = ", ".join(t.cast(str, arg.name) for arg in list(method.arguments)[:i])
                for prefix in prefixes:
                    texts.append(prefix + "(" + argText + ")")

        texts.append(t.cast(str, method.normal_name))
        if method.name == "constructor":
            texts.append(t.cast(str, method.parent.name) + t.cast(str, method.normal_name)[11:])
        return list(reversed(texts))
