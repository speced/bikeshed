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

    def serializeValue(self, prefix: str, value: str, suffix: str, node: cddlparser.ast.CDDLNode) -> str:
        name = prefix + value + suffix
        if node.type not in {"text", "bytes"}:
            return name
        parent = node.parentNode
        if isinstance(parent, cddlparser.ast.Memberkey) and node.type == "text":
            # A literal text string also gives rise to a type
            # see RFC 8610, section 3.5.1:
            # https://datatracker.ietf.org/doc/html/rfc8610#section-3.5.1
            forName = self._getFor(parent.parentNode)
            if forName is None:
                # Cannot easily link member key back to a definition
                return name
            else:
                # Name of created type should not include the quotes
                return '<cddl data-cddl-type="key" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(forName),
                    h.escapeAttr(value),
                    name,
                )
        elif isinstance(parent, cddlparser.ast.Operator) and parent.controller == node:
            # Probably a ".default" value. It may be possible to link the value
            # back to an enumeration but it's equally possible that this is just
            # a string that's not defined anywhere. Let's ignore.
            return name
        else:
            forName = self._getFor(node)
            if forName is None:
                return name
            else:
                return '<cddl data-cddl-type="value" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(forName),
                    h.escapeAttr(name),
                    name,
                )

    def serializeName(self, name: str, node: cddlparser.ast.CDDLNode) -> str:
        # The node is a Typename. Such a node may appear in a Rule, a Type,
        # a Reference, a Memberkey, a GroupEntry, or GenericParameters
        parent = node.parentNode
        if isinstance(parent, cddlparser.ast.Rule):
            # Rule definition
            if parent.assign.type in {cddlparser.Tokens.TCHOICEALT, cddlparser.Tokens.GCHOICEALT}:
                # The definition extends a base definition
                return '<a data-link-type="cddl" data-link-for="/">{}</a>'.format(name)
            else:
                return '<cddl data-cddl-type="type" data-lt="{}">{}</cddl>'.format(h.escapeAttr(name), name)
        elif isinstance(parent, cddlparser.ast.Memberkey):
            # Member definition
            if not parent.hasColon:
                # The key is actually a reference to a type
                if name in get_args(cddlparser.ast.PreludeType):
                    # From the CDDL prelude, nothing to link to
                    return name
                else:
                    return '<a data-link-type="cddl" data-link-for="/">{}</a>'.format(name)
            forName = self._getFor(parent.parentNode)
            if forName is None:
                # Cannot easily link member key back to a definition
                return name
            else:
                return '<cddl data-cddl-type="key" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                    h.escapeAttr(forName),
                    h.escapeAttr(name),
                    name,
                )
        elif isinstance(parent, cddlparser.ast.GenericParameters):
            typename = parent.parentNode
            assert isinstance(typename, cddlparser.ast.Typename)
            return '<cddl data-cddl-type="parameter" data-cddl-for="{}" data-lt="{}">{}</cddl>'.format(
                h.escapeAttr(typename.name),
                h.escapeAttr(name),
                name,
            )
        elif name in get_args(cddlparser.ast.PreludeType):
            # Do not link types that come from the CDDL prelude
            # defined in RFC 8610
            return name
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
                return t.cast(str, parent.name.name)
            elif isinstance(parent, cddlparser.ast.GroupEntry) and parent.key is not None:
                # A type in a member key definition
                parentFor = self._getFor(parent.parentNode)
                if parentFor is None:
                    return parentFor
                if isinstance(parent.key.type, cddlparser.ast.Value) and parent.key.type.type == "text":
                    return parentFor + "/" + t.cast(str, parent.key.type.value)
                elif isinstance(parent.key.type, cddlparser.ast.Typename):
                    return parentFor + "/" + t.cast(str, parent.key.type.name)
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
    forcedDfns = []
    for x in (h.treeAttr(pre, "data-dfn-force") or "").split():
        x = x.strip()
        if x.endswith("<interface>"):
            x = x[:-11]
        forcedDfns.append(x)
    for el in h.findAll("cddl", pre):
        # Prefix CDDL types with "cddl-" to avoid confusion with other
        # types (notably CSS ones such as "value")
        cddlType = "cddl-" + (el.get("data-cddl-type") or "")
        assert isinstance(cddlType, str)
        url = None
        forceDfn = False
        ref = None
        cddlText = None
        for cddlText in (el.get("data-lt") or "").split("|"):
            if cddlType == "interface" and cddlText in forcedDfns:
                forceDfn = True
            linkFors = t.cast("list[str|None]", config.splitForValues(el.get("data-cddl-for", ""))) or [None]
            for linkFor in linkFors:
                ref = doc.refs.getRef(
                    cddlType,
                    cddlText,
                    linkFor=linkFor,
                    status="local",
                    el=el,
                    error=False,
                )
                if ref:
                    url = ref.url
                    break
            if ref:
                break
        if url is None or forceDfn:
            el.tag = "dfn"
            el.set("data-dfn-type", cddlType)
            del el.attrib["data-cddl-type"]
            if el.get("data-cddl-for"):
                el.set("data-dfn-for", el.get("data-cddl-for") or "")
                del el.attrib["data-cddl-for"]
        else:
            # Copy over the auto-generated linking text to the manual dfn.
            dfn = h.find(url, doc)
            # How in the hell does this work, the url is not a selector???
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
