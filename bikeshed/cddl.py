from __future__ import annotations

from typing import get_args

import cddlparser

from . import config, h, t
from . import messages as m


class CDDLMarker(cddlparser.ast.Marker):
    """
    Marker that wraps CDDL definitions and references in <cddl> and <a> blocks
    so that cross-referencing logic may take place.
    """

    # Keep pointers on the current rule context to track generic parameters
    # that are scoped to it
    currentRule: cddlparser.ast.Rule | None
    currentParameters: list[str]

    # List of all CDDL terms defined so far to track and report duplicates
    defined: list

    def __init__(self) -> None:
        self.currentRule = None
        self.currentParameters = []
        self.defined = []

    def _recordDefinition(self, type: str, name: str, dfnFor: str | None = None) -> bool:
        for term in self.defined:
            if term["type"] == type and term["name"] == name and term["dfnFor"] == dfnFor:
                forText = "" if dfnFor is None else f' defined in type "{dfnFor}"'
                m.die(
                    f"CDDL {type} {name}{forText} creates a duplicate and cannot be referenced.\nPlease create additional CDDL types to disambiguate.",
                )
                return False
        if type != "parameter":
            for term in self.defined:
                if term["type"] != "parameter" and term["name"] == name and term["dfnFor"] == dfnFor:
                    forText = "" if dfnFor is None else f' defined in type "{dfnFor}"'
                    m.warn(
                        f"CDDL {type} {name}{forText} creates a duplicate with a CDDL {term['type']}.\nLink type needs to be specified to reference the term.\nConsider creating additional CDDL types to disambiguate.",
                    )
                    break
        term = {"type": type, "name": name, "dfnFor": dfnFor}
        self.defined.append(term)
        return True

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
            elif self._recordDefinition("key", value, forName):
                # Create a key with and without quotes as linking text
                lts = [value, name]
                return '<cddl data-cddl-type="key" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(forName),
                    h.escapeAttr("|".join(lts)),
                    name,
                )
            else:
                # Duplicate found, don't create a dfn
                return name
        elif isinstance(parent, cddlparser.ast.Operator) and parent.controller == node:
            # Probably a ".default" value. It may be possible to link the value
            # back to an enumeration but it's equally possible that this is just
            # a string that's not defined anywhere. Let's ignore.
            return name
        else:
            forName = self._getFor(node)
            if forName is None:
                return name
            elif self._recordDefinition("value", value, forName):
                lts = [value, name]
                return '<cddl data-cddl-type="value" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(forName),
                    h.escapeAttr("|".join(lts)),
                    name,
                )
            else:
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
            self.currentParameters = []
            if parent.name.parameters is not None:
                assert isinstance(parent.name.parameters, cddlparser.ast.GenericParameters)
                self.currentParameters = [p.name for p in parent.name.parameters.parameters]
            if parent.assign.type in {cddlparser.Tokens.TCHOICEALT, cddlparser.Tokens.GCHOICEALT}:
                # The definition extends a base definition
                return '<a data-link-type="cddl-type" data-link-for="/">{}</a>'.format(name)
            elif self._recordDefinition("type", name):
                return '<cddl data-cddl-type="type" data-lt="{}">{}</cddl>'.format(h.escapeAttr(name), name)
            else:
                # Duplicate found, don't create a dfn
                return name
        elif isinstance(parent, cddlparser.ast.Memberkey):
            # Member definition
            if not parent.hasColon:
                # The key is actually a reference to a type
                if name in get_args(cddlparser.ast.PreludeType):
                    return '<a data-link-type="cddl-type" data-link-for="/" data-link-spec="rfc8610">{}</a>'.format(
                        name,
                    )
                else:
                    return '<a data-link-type="cddl-type" data-link-for="/">{}</a>'.format(name)
            assert parent.parentNode is not None
            forName = self._getFor(parent.parentNode)
            if forName is None:
                # Cannot easily link member key back to a definition
                return name
            else:
                lts = []
                if name[0] == '"':
                    lts = [name[1:-1], name]
                else:
                    lts = [name, '"' + name + '"']
                if self._recordDefinition("key", lts[0], forName):
                    return '<cddl data-cddl-type="key" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                        h.escapeAttr(forName),
                        h.escapeAttr("|".join(lts)),
                        name,
                    )
                else:
                    # Duplicate found, don't create a dfn
                    return name
        elif isinstance(parent, cddlparser.ast.GenericParameters):
            typename = parent.parentNode
            assert isinstance(typename, cddlparser.ast.Typename)
            if self._recordDefinition("parameter", name, typename.name):
                return '<cddl data-cddl-type="parameter" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(typename.name),
                    h.escapeAttr(name),
                    name,
                )
            else:
                # Duplicate found, don't create a dfn
                return name
        elif name in get_args(cddlparser.ast.PreludeType):
            # Link types that come from the CDDL prelude in RFC 8610
            return '<a data-link-type="cddl-type" data-link-for="/" data-link-spec="rfc8610">{}</a>'.format(name)
        elif name in self.currentParameters:
            # Name is a reference to a generic parameter
            assert self.currentRule is not None
            return '<a data-link-type="cddl-parameter" data-link-for="{}">{}</a>'.format(
                h.escapeAttr(self.currentRule.name.name),
                name,
            )
        else:
            return '<a data-link-type="cddl" data-link-for="/">{}</a>'.format(name)

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
                assert parent.parentNode is not None
                parentFor = self._getFor(parent.parentNode)
                if parentFor is None:
                    return parentFor
                if isinstance(parent.key.type, cddlparser.ast.Value) and parent.key.type.type == "text":
                    return parentFor + "/" + parent.key.type.value
                elif isinstance(parent.key.type, cddlparser.ast.Typename):
                    return parentFor + "/" + parent.key.type.name
                else:
                    return None
            parent = parent.parentNode
        return None


def markupCDDL(doc: t.SpecT) -> None:
    cddlEls = h.findAll("pre.cddl:not([data-no-cddl]), xmp.cddl:not([data-no-cddl])", doc)

    marker = CDDLMarker()
    for el in cddlEls:
        if h.isNormative(doc, el):
            text = h.textContent(el)
            try:
                ast = cddlparser.parse(text)
                h.replaceContents(el, h.parseHTML(ast.serialize(marker)))
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
    localDfns = set()

    for el in h.findAll("cddl", pre):
        # Prefix CDDL types with "cddl-" to avoid confusion with other
        # types (notably CSS ones such as "value")
        cddlType = "cddl-" + (el.get("data-cddl-type") or "")
        assert isinstance(cddlType, str)
        url = None
        ref = None
        cddlText: str
        for cddlText in (el.get("data-lt") or "").split("|"):
            linkFors: t.Sequence[str | None] | None = config.splitForValues(el.get("data-cddl-for"))
            if linkFors is None:
                linkFors = [None]
            for linkFor in linkFors:
                ref = doc.refs.getRef(
                    cddlType,
                    cddlText,
                    linkFor=linkFor,
                    status="local",
                    el=el,
                    error=True,
                )
                if isinstance(ref, str):
                    ref = None
                if ref:
                    url = ref.url
                    break
            if ref:
                break

        if url is None:
            el.tag = "dfn"
            el.set("data-dfn-type", cddlType)
            del el.attrib["data-cddl-type"]
            if el.get("data-cddl-for"):
                el.set("data-dfn-for", el.get("data-cddl-for") or "")
                del el.attrib["data-cddl-for"]
        else:
            # Copy over the auto-generated linking text to the manual dfn.
            # Note: "url" is not an absolute URL but rather a fragment ref. It
            # can thus be used as an ID selector to find the underlying dfn
            dfn = h.find(url, doc)
            assert dfn is not None
            lts = combineCDDLLinkingTexts(el.get("data-lt"), dfn.get("data-lt"))
            dfn.set("data-lt", lts)
            localDfns.add(dfn)

            # Reset the <cddl> element to be a link to the manual dfn.
            el.tag = "a"
            el.set("data-link-type", cddlType)
            el.set("data-lt", cddlText)
            del el.attrib["data-cddl-type"]
            if el.get("data-cddl-for"):
                el.set("data-link-for", el.get("data-cddl-for") or "")
                del el.attrib["data-cddl-for"]
            if el.get("id"):
                # ID was defensively added by the Marker.
                del el.attrib["id"]
    return localDfns


def combineCDDLLinkingTexts(t1: str | None, t2: str | None) -> str:
    t1s = (t1 or "").split("|")
    t2s = (t2 or "").split("|")
    for lt in t2s:
        if lt not in t1s:
            t1s.append(lt)
    return "|".join(t1s)
