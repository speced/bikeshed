from __future__ import annotations

from typing import get_args

import cddlparser

from . import config, dfns, h, t
from . import messages as m

_PRELUDE_TYPES: frozenset[str] = frozenset(get_args(cddlparser.ast.PreludeType))
_EXTEND_ASSIGN_TOKENS: frozenset[cddlparser.Tokens] = frozenset(
    (cddlparser.Tokens.TCHOICEALT, cddlparser.Tokens.GCHOICEALT),
)


class CDDLMarker(cddlparser.ast.Marker):
    """
    Marker that wraps CDDL definitions and references in <cddl> and <a> blocks
    so that cross-referencing logic may take place.
    """

    # Keep pointers on the current rule context to track generic parameters
    # that are scoped to it
    currentRule: cddlparser.ast.Rule | None
    currentParameters: set[str]

    # Track all CDDL terms defined so far to report duplicates:
    # - defined: (type, name, dfnFor) for exact duplicate errors
    # - definedNonParams: (name, dfnFor) -> first non-parameter type, for cross-type duplicate warnings
    defined: set[tuple[str, str, str | None]]
    definedNonParams: dict[tuple[str, str | None], str]

    def __init__(self) -> None:
        self.currentRule = None
        self.currentParameters = set()
        self.defined = set()
        self.definedNonParams = {}

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

    def _wrapCddl(self, cddlType: str, name: str, lt: str, dfnFor: str | None = None) -> str:
        if dfnFor is None:
            return f'<cddl data-cddl-type="{cddlType}" data-lt="{h.escapeAttr(lt)}">{name}</cddl>'
        return f'<cddl data-cddl-type="{cddlType}" data-cddl-for="{h.escapeAttr(dfnFor)}" data-lt="{h.escapeAttr(lt)}">{name}</cddl>'

    def serializeValue(self, prefix: str, value: str, suffix: str, node: cddlparser.ast.Value) -> str:
        name = prefix + value + suffix
        if node.type not in {"text", "bytes"}:
            return name
        parent = node.parentNode
        assert parent is not None
        if isinstance(parent, cddlparser.ast.Memberkey) and node.type == "text":
            # A literal text string also gives rise to a type
            # see RFC 8610, section 3.5.1:
            # https://datatracker.ietf.org/doc/html/rfc8610#section-3.5.1
            assert parent.parentNode is not None
            forName = self._getFor(parent.parentNode)
            if forName is None:
                # Cannot easily link member key back to a definition
                return name
            if self._recordDefinition("key", value, forName):
                # Create a key with and without quotes as linking text
                return self._wrapCddl("key", name, f"{value}|{name}", forName)
            # Duplicate found, don't create a dfn
            return name
        elif isinstance(parent, cddlparser.ast.Operator) and parent.controller is node:
            # Probably a ".default" value. It may be possible to link the value
            # back to an enumeration but it's equally possible that this is just
            # a string that's not defined anywhere. Let's ignore.
            return name
        else:
            forName = self._getFor(node)
            if forName is None:
                return name
            if self._recordDefinition("value", value, forName):
                return self._wrapCddl("value", name, f"{value}|{name}", forName)
            # Duplicate found, don't create a dfn
            return name

    def serializeName(self, name: str, node: cddlparser.ast.CDDLNode) -> str:
        # The node is a Typename. Such a node may appear in a Rule, a Type,
        # a Reference, a Memberkey, a GroupEntry, or GenericParameters
        parent = node.parentNode
        if isinstance(parent, cddlparser.ast.Rule):
            # Rule definition
            # Keep a pointer to the rule not to have to look for it again
            # when the function is called on the rule's children
            self.currentRule = parent
            self.currentParameters.clear()
            if parent.name.parameters is not None:
                assert isinstance(parent.name.parameters, cddlparser.ast.GenericParameters)
                self.currentParameters.update(p.name for p in parent.name.parameters.parameters)
            if parent.assign.type in _EXTEND_ASSIGN_TOKENS:
                # The definition extends a base definition
                return f'<a data-link-type="cddl-type" data-link-for="/">{name}</a>'
            if self._recordDefinition("type", name):
                return self._wrapCddl("type", name, name)
            # Duplicate found, don't create a dfn
            return name
        elif isinstance(parent, cddlparser.ast.Memberkey):
            # Member definition
            if not parent.hasColon:
                # The key is actually a reference to a type
                if name in _PRELUDE_TYPES:
                    return f'<a data-link-type="cddl-type" data-link-for="/" data-link-spec="rfc8610">{name}</a>'
                return f'<a data-link-type="cddl-type" data-link-for="/">{name}</a>'
            assert parent.parentNode is not None
            forName = self._getFor(parent.parentNode)
            if forName is None:
                # Cannot easily link member key back to a definition
                return name
            if name.startswith('"'):
                unquoted = name[1:-1]
                lt = f"{unquoted}|{name}"
            else:
                unquoted = name
                lt = f'{name}|"{name}"'
            if self._recordDefinition("key", unquoted, forName):
                return self._wrapCddl("key", name, lt, forName)
            # Duplicate found, don't create a dfn
            return name
        elif isinstance(parent, cddlparser.ast.GenericParameters):
            typename = parent.parentNode
            assert isinstance(typename, cddlparser.ast.Typename)
            if self._recordDefinition("parameter", name, typename.name):
                return self._wrapCddl("parameter", name, name, typename.name)
            # Duplicate found, don't create a dfn
            return name
        elif name in _PRELUDE_TYPES:
            # Link types that come from the CDDL prelude in RFC 8610
            return f'<a data-link-type="cddl-type" data-link-for="/" data-link-spec="rfc8610">{name}</a>'
        elif name in self.currentParameters:
            # Name is a reference to a generic parameter
            assert self.currentRule is not None
            return f'<a data-link-type="cddl-parameter" data-link-for="{h.escapeAttr(self.currentRule.name.name)}">{name}</a>'
        else:
            return f'<a data-link-type="cddl" data-link-for="/">{name}</a>'

    def _getFor(self, node: cddlparser.ast.CDDLNode) -> str | None:
        """
        Retrieve the "for" attribute for the node.
        """
        parent = node.parentNode
        while parent is not None:
            if isinstance(parent, cddlparser.ast.Rule):
                # Something defined in a rule
                return parent.name.name
            elif isinstance(parent, cddlparser.ast.GroupEntry) and parent.key is not None:
                # A type in a member key definition
                keyType = parent.key.type
                if isinstance(keyType, cddlparser.ast.Value) and keyType.type == "text":
                    keyName = keyType.value
                elif isinstance(keyType, cddlparser.ast.Typename):
                    keyName = keyType.name
                else:
                    return None
                assert parent.parentNode is not None
                parentFor = self._getFor(parent.parentNode)
                if parentFor is None:
                    return None
                return f"{parentFor}/{keyName}"
            parent = parent.parentNode
        return None


def findCDDLBlocks(doc: t.SpecT) -> list[t.ElementT]:
    return [
        el
        for el in h.treeElements(doc.document, "pre", "xmp")
        if el.get("data-no-cddl") is None and h.hasClass(doc, el, "cddl")
    ]


def markupCDDL(doc: t.SpecT) -> None:
    cddlEls = findCDDLBlocks(doc)
    if not cddlEls:
        return

    marker = CDDLMarker()
    for el in cddlEls:
        if h.isNormative(doc, el):
            text = h.textContent(el)
            try:
                ast = cddlparser.parse(text)
                h.parseInto(el, h.safeHtml(ast.serialize(marker)))
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
        cddlType = "cddl-" + (el.get("data-cddl-type") or "")
        cddlFor = el.get("data-cddl-for")
        linkFors: t.Sequence[str | None] | None = config.splitForValues(cddlFor)
        if linkFors is None:
            linkFors = [None]
        elLt = el.get("data-lt")

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

        h.removeAttr(el, "data-cddl-type")
        if ref is None:
            el.tag = "dfn"
            el.set("data-dfn-type", cddlType)
            if cddlFor:
                el.set("data-dfn-for", cddlFor)
                del el.attrib["data-cddl-for"]
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
            el.set("data-lt", matchedText)
            if cddlFor:
                el.set("data-link-for", cddlFor)
                del el.attrib["data-cddl-for"]
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
