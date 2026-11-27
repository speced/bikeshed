from __future__ import annotations

from typing import get_args

import cddlparser
from lxml import etree

from . import config, dfns, h, t
from . import messages as m

_PRELUDE_TYPES: frozenset[str] = frozenset(get_args(cddlparser.ast.PreludeType))
_EXTEND_ASSIGN_TOKENS: frozenset[cddlparser.Tokens] = frozenset(
    (cddlparser.Tokens.TCHOICEALT, cddlparser.Tokens.GCHOICEALT),
)
_VALUE_WRAPPERS: dict[str, tuple[str, str]] = {
    "text": ('"', '"'),
    "bytes": ("'", "'"),
    "hex": ("h'", "'"),
    "base64": ("b64'", "'"),
    "number": ("", ""),
}


class CDDLBuilder:
    """
    Walks a cddlparser AST and populates an lxml container directly,
    wrapping CDDL definitions and references in <cddl> and <a> elements.
    """

    # Keep pointers on the current rule context to track generic parameters
    # that are scoped to it.
    currentRule: cddlparser.ast.Rule | None
    currentParameters: set[str]

    # Track all CDDL terms defined so far across blocks to report duplicates:
    # - defined: (type, name, dfnFor) for exact duplicate errors
    # - definedNonParams: (name, dfnFor) -> first non-parameter type, for cross-type duplicate warnings
    defined: set[tuple[str, str, str | None]]
    definedNonParams: dict[tuple[str, str | None], str]

    def __init__(self) -> None:
        self.currentRule = None
        self.currentParameters = set()
        self.defined = set()
        self.definedNonParams = {}
        self._container: t.ElementT | None = None
        self._textBuf: list[str] = []
        self._lastChild: t.ElementT | None = None

    def buildInto(self, container: t.ElementT, ast: cddlparser.ast.CDDLTree) -> None:
        h.clearContents(container)
        self._container = container
        self._textBuf.clear()
        self._lastChild = None
        self.currentRule = None
        self.currentParameters.clear()
        self._visit(ast, parent=None, forName=None)
        self._flushText()
        self._container = None
        self._lastChild = None

    def _flushText(self) -> None:
        if not self._textBuf:
            return
        assert self._container is not None
        chunk = "".join(self._textBuf)
        self._textBuf.clear()
        if self._lastChild is None:
            self._container.text = chunk
        else:
            self._lastChild.tail = chunk

    def _emitText(self, text: str) -> None:
        if text:
            self._textBuf.append(text)

    def _emitToken(self, token: cddlparser.Token | None) -> None:
        if token is not None:
            serialized = token.serialize()
            if serialized:
                self._textBuf.append(serialized)

    def _emitElement(self, tag: str, attrs: dict[str, str], text: str) -> None:
        self._flushText()
        assert self._container is not None
        child = etree.SubElement(self._container, tag, attrs)
        child.text = text
        self._lastChild = child

    def _recordDefinition(self, type: str, name: str, dfnFor: str | None = None) -> bool:
        exactKey = (type, name, dfnFor)
        if exactKey in self.defined:
            forText = "" if dfnFor is None else f' defined in type "{dfnFor}"'
            m.die(
                f"CDDL {type} {name}{forText} creates a duplicate and cannot be referenced.\nPlease create additional CDDL types to disambiguate.",
            )
            return False
        if type != "parameter":
            nameKey = (name, dfnFor)
            existingType = self.definedNonParams.get(nameKey)
            if existingType is not None:
                forText = "" if dfnFor is None else f' defined in type "{dfnFor}"'
                m.warn(
                    f"CDDL {type} {name}{forText} creates a duplicate with a CDDL {existingType}.\nLink type needs to be specified to reference the term.\nConsider creating additional CDDL types to disambiguate.",
                )
            else:
                self.definedNonParams[nameKey] = type
        self.defined.add(exactKey)
        return True

    def _emitCddl(self, cddlType: str, name: str, lt: str, dfnFor: str | None = None) -> None:
        if dfnFor is None:
            attrs = {"bs-cddl-type": cddlType, "bs-lt": lt}
        else:
            attrs = {"bs-cddl-type": cddlType, "bs-cddl-for": dfnFor, "bs-lt": lt}
        self._emitElement("cddl", attrs, name)

    def _emitValue(
        self,
        node: cddlparser.ast.Value,
        parent: cddlparser.ast.CDDLNode | None,
        forName: str | None,
    ) -> None:
        prefix, suffix = _VALUE_WRAPPERS[node.type]
        name = prefix + node.value + suffix
        if node.type not in {"text", "bytes"}:
            self._emitText(name)
            return
        if isinstance(parent, cddlparser.ast.Memberkey) and node.type == "text":
            # A literal text string also gives rise to a type
            # see RFC 8610, section 3.5.1:
            # https://datatracker.ietf.org/doc/html/rfc8610#section-3.5.1
            if forName is None:
                # Cannot easily link member key back to a definition
                self._emitText(name)
                return
            if self._recordDefinition("key", node.value, forName):
                # Create a key with and without quotes as linking text
                self._emitCddl("key", name, f"{node.value}|{name}", forName)
            else:
                # Duplicate found, don't create a dfn
                self._emitText(name)
        elif isinstance(parent, cddlparser.ast.Operator) and parent.controller is node:
            # Probably a ".default" value. It may be possible to link the value
            # back to an enumeration but it's equally possible that this is just
            # a string that's not defined anywhere. Let's ignore.
            self._emitText(name)
        else:
            if forName is None:
                self._emitText(name)
                return
            if self._recordDefinition("value", node.value, forName):
                self._emitCddl("value", name, f"{node.value}|{name}", forName)
            else:
                # Duplicate found, don't create a dfn
                self._emitText(name)

    def _emitTypename(
        self,
        node: cddlparser.ast.Typename,
        parent: cddlparser.ast.CDDLNode | None,
        forName: str | None,
        genericOwner: str | None,
    ) -> None:
        name = node.name
        if isinstance(parent, cddlparser.ast.Rule):
            if parent.assign.type in _EXTEND_ASSIGN_TOKENS:
                # The definition extends a base definition
                self._emitElement("a", {"data-link-type": "cddl-type", "bs-link-for": "/"}, name)
            elif self._recordDefinition("type", name):
                self._emitCddl("type", name, name)
            else:
                # Duplicate found, don't create a dfn
                self._emitText(name)
        elif isinstance(parent, cddlparser.ast.Memberkey):
            # Member definition
            if not parent.hasColon:
                # The key is actually a reference to a type
                if name in _PRELUDE_TYPES:
                    self._emitElement(
                        "a",
                        {"data-link-type": "cddl-type", "bs-link-for": "/", "bs-link-spec": "rfc8610"},
                        name,
                    )
                else:
                    self._emitElement("a", {"data-link-type": "cddl-type", "bs-link-for": "/"}, name)
                return
            if forName is None:
                # Cannot easily link member key back to a definition
                self._emitText(name)
                return
            if name.startswith('"'):
                unquoted = name[1:-1]
                lt = f"{unquoted}|{name}"
            else:
                unquoted = name
                lt = f'{name}|"{name}"'
            if self._recordDefinition("key", unquoted, forName):
                self._emitCddl("key", name, lt, forName)
            else:
                # Duplicate found, don't create a dfn
                self._emitText(name)
        elif isinstance(parent, cddlparser.ast.GenericParameters):
            assert genericOwner is not None
            if self._recordDefinition("parameter", name, genericOwner):
                self._emitCddl("parameter", name, name, genericOwner)
            else:
                # Duplicate found, don't create a dfn
                self._emitText(name)
        elif name in _PRELUDE_TYPES:
            # Link types that come from the CDDL prelude in RFC 8610
            self._emitElement(
                "a",
                {"data-link-type": "cddl-type", "bs-link-for": "/", "bs-link-spec": "rfc8610"},
                name,
            )
        elif name in self.currentParameters:
            # Name is a reference to a generic parameter
            assert self.currentRule is not None
            self._emitElement(
                "a",
                {"data-link-type": "cddl-parameter", "bs-link-for": self.currentRule.name.name},
                name,
            )
        else:
            self._emitElement("a", {"data-link-type": "cddl", "bs-link-for": "/"}, name)

    def _visit(
        self,
        node: cddlparser.ast.CDDLNode,
        parent: cddlparser.ast.CDDLNode | None,
        forName: str | None,
        genericOwner: str | None = None,
    ) -> None:
        if isinstance(node, cddlparser.ast.TokenNode):
            if isinstance(node, cddlparser.ast.Typename):
                self._emitToken(node.unwrapped)
            for comment in node.comments:
                self._emitToken(comment)
            if node.whitespace:
                self._textBuf.append(node.whitespace)
            self._emitToken(node.openToken)
        elif isinstance(node, cddlparser.ast.WrappedNode):
            self._emitToken(node.openToken)

        if isinstance(node, cddlparser.ast.CDDLTree):
            for rule in node.rules:
                self._visit(rule, node, None)
        elif isinstance(node, cddlparser.ast.Rule):
            self.currentRule = node
            self.currentParameters.clear()
            if node.name.parameters is not None:
                assert isinstance(node.name.parameters, cddlparser.ast.GenericParameters)
                self.currentParameters.update(p.name for p in node.name.parameters.parameters)
            ruleFor = node.name.name
            self._visit(node.name, node, ruleFor)
            self._emitToken(node.assign)
            self._visit(node.type, node, ruleFor)
        elif isinstance(node, cddlparser.ast.Typename):
            self._emitTypename(node, parent, forName, genericOwner)
            if node.parameters is not None:
                if isinstance(node.parameters, cddlparser.ast.GenericParameters):
                    self._visit(node.parameters, node, forName, genericOwner=node.name)
                else:
                    argFor = (
                        f"{forName}/{node.name}"
                        if (isinstance(parent, cddlparser.ast.Memberkey) and forName is not None)
                        else forName
                    )
                    self._visit(node.parameters, node, argFor)
        elif isinstance(node, cddlparser.ast.Value):
            self._emitValue(node, parent, forName)
        elif isinstance(node, cddlparser.ast.Type):
            for item in node.types:
                self._visit(item, node, forName)
        elif isinstance(node, cddlparser.ast.GroupEntry):
            if node.occurrence is not None:
                self._visit(node.occurrence, node, forName)
            entryFor = forName
            if node.key is not None:
                keyType = node.key.type
                keyFor: str | None = None
                if isinstance(keyType, cddlparser.ast.Value) and keyType.type == "text":
                    keyFor = forName
                    entryFor = f"{forName}/{keyType.value}" if forName is not None else None
                elif isinstance(keyType, cddlparser.ast.Typename):
                    keyFor = forName
                    entryFor = f"{forName}/{keyType.name}" if forName is not None else None
                else:
                    entryFor = None
                self._visit(node.key, node, keyFor)
            self._visit(node.type, node, entryFor)
        elif isinstance(node, cddlparser.ast.Memberkey):
            self._visit(node.type, node, forName)
            for tok in node.tokens:
                self._emitToken(tok)
        elif isinstance(node, cddlparser.ast.Group):
            for choice in node.groupChoices:
                self._visit(choice, node, forName)
        elif isinstance(node, cddlparser.ast.GroupChoice):
            for entry in node.groupEntries:
                self._visit(entry, node, forName)
        elif isinstance(node, cddlparser.ast.Operator):
            self._visit(node.type, node, forName)
            self._emitToken(node.name)
            self._visit(node.controller, node, forName)
        elif isinstance(node, cddlparser.ast.Range):
            self._visit(node.min, node, forName)
            self._emitToken(node.rangeop)
            self._visit(node.max, node, forName)
        elif isinstance(node, cddlparser.ast.Tag):
            self._textBuf.append("#")
            self._emitToken(node.numericPart)
            if node.typePart is not None:
                self._visit(node.typePart, node, forName)
        elif isinstance(node, cddlparser.ast.ChoiceFrom):
            self._textBuf.append("&")
            self._visit(node.target, node, forName)
        elif isinstance(node, cddlparser.ast.Occurrence):
            for tok in node.tokens:
                self._emitToken(tok)
        elif isinstance(node, cddlparser.ast.GenericParameters):
            for param in node.parameters:
                self._visit(param, node, forName, genericOwner=genericOwner)
        elif isinstance(node, cddlparser.ast.GenericArguments):
            for arg in node.parameters:
                self._visit(arg, node, forName)
        else:
            msg = f"Unexpected CDDL AST node: {type(node).__name__}"
            raise TypeError(msg)

        if isinstance(node, cddlparser.ast.WrappedNode):
            self._emitToken(node.closeToken)
        if isinstance(node, cddlparser.ast.TokenNode):
            self._emitToken(node.separator)


def findCDDLBlocks(doc: t.SpecT) -> list[t.ElementT]:
    return [
        el
        for el in h.treeElements(doc.document, "pre", "xmp")
        if el.get("bs-no-cddl") is None and h.hasClass(doc, el, "cddl")
    ]


def markupCDDL(doc: t.SpecT) -> None:
    cddlEls = findCDDLBlocks(doc)
    if not cddlEls:
        return

    builder = CDDLBuilder()
    for el in cddlEls:
        if h.isNormative(doc, el):
            text = h.textContent(el)
            try:
                ast = cddlparser.parse(text)
                builder.buildInto(el, ast)
            except Exception as err:
                m.die(
                    f"{err}\nInvalid CDDL block (first 100 characters):\n{text[0:100]}{'...' if len(text) > 100 else ''}",
                )
        h.addClass(doc, el, "highlight")
    doc.extraJC.addCDDLHighlighting()


def markupCDDLBlock(pre: t.ElementT, doc: t.SpecT) -> set[t.ElementT]:
    """
    Convert <cddl> blocks into "dfn" or links.
    """
    localDfns: set[t.ElementT] = set()

    for el in list(h.treeElements(pre, "cddl")):
        # Prefix CDDL types with "cddl-" to avoid confusion with other
        # types (notably CSS ones such as "value")
        cddlType = "cddl-" + (el.get("bs-cddl-type") or "")
        cddlFor = el.get("bs-cddl-for")
        linkFors: t.Sequence[str | None] | None = config.splitForValues(cddlFor)
        if linkFors is None:
            linkFors = [None]
        elLt = el.get("bs-lt")

        ref = None
        matchedText = ""
        for cddlText in (elLt or "").split("|"):
            for linkFor in linkFors:
                foundRef = doc.refs.getRef(
                    text=cddlText,
                    linkType=cddlType,
                    linkFor=linkFor,
                    status="local",
                    el=el,
                    error=True,
                )
                if foundRef is not None and not isinstance(foundRef, str):
                    ref = foundRef
                    matchedText = cddlText
                    break
            if ref is not None:
                break

        if ref is None:
            el.tag = "dfn"
            el.set("data-dfn-type", cddlType)
            if elLt is not None:
                el.set("data-lt", elLt)
                h.removeAttr(el, "bs-lt")
            if cddlFor:
                el.set("data-dfn-for", cddlFor)
        else:
            # Copy over the auto-generated linking text to the manual dfn.
            dfn = ref.el
            assert dfn is not None
            dfnLt = dfn.get("data-lt")
            lts = combineCDDLLinkingTexts(elLt, dfnLt)
            if lts != dfnLt:
                dfn.set("data-lt", lts)
                localDfns.add(dfn)

            # Reset the <cddl> element to be a link to the manual dfn.
            el.tag = "a"
            el.set("data-link-type", cddlType)
            el.set("bs-lt", matchedText)
            if cddlFor:
                el.set("bs-link-for", cddlFor)
            if el.get("id"):
                # ID was defensively added by the Marker.
                del el.attrib["id"]
    return localDfns


def combineCDDLLinkingTexts(t1: str | None, t2: str | None) -> str:
    if t1 == t2:
        return t1 or ""
    t1s = (t1 or "").split("|")
    t2s = (t2 or "").split("|")
    for lt in t2s:
        if lt not in t1s:
            t1s.append(lt)
    return "|".join(t1s)


def processCDDL(doc: t.SpecT) -> None:
    cddlBlocks = findCDDLBlocks(doc)
    if not cddlBlocks:
        return

    localDfns: set[t.ElementT] = set()
    for pre in cddlBlocks:
        if h.isNormative(doc, pre):
            localDfns.update(markupCDDLBlock(pre, doc))

    cddlDfns: list[t.ElementT] = []
    seenDfns: set[t.ElementT] = set()
    for pre in cddlBlocks:
        for dfn in h.treeElements(pre, "dfn"):
            if dfn not in seenDfns:
                seenDfns.add(dfn)
                cddlDfns.append(dfn)
    for dfn in localDfns:
        if dfn not in seenDfns:
            seenDfns.add(dfn)
            cddlDfns.append(dfn)
    if not cddlDfns:
        return

    cddlDfns = h.sortElements(cddlDfns)
    dfns.classifyDfns(doc, cddlDfns)
    h.fixupIDs(doc, cddlDfns)
    doc.refs.addLocalDfns(doc, (dfn for dfn in cddlDfns if dfn.get("id") is not None))
