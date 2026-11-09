from __future__ import annotations

import widlparser

from .. import config, h, t
from .. import messages as m


def nodesFromType(prod: widlparser.productions.Production) -> t.ElementT:
    return h.E.code({"class": "idl"}, *_nodesFromProduction(prod))


def _nodesFromProduction(prod: widlparser.productions.Production | widlparser.protocols.Construct) -> list[t.NodeT]:
    # pylint: disable=protected-access
    # Things that should be directly linkifiable from their text
    head: list[t.NodeT]
    tail: list[t.NodeT]
    if isinstance(
        prod,
        (
            widlparser.productions.Symbol,
            widlparser.productions.IntegerType,
            widlparser.productions.UnsignedIntegerType,
            widlparser.productions.FloatType,
            widlparser.productions.UnrestrictedFloatType,
            widlparser.productions.PrimitiveType,
            widlparser.productions.Identifier,
            widlparser.productions.TypeIdentifier,
            widlparser.productions.AnyType,
        ),
    ):
        return [h.E.a({"data-link-type": "idl-name"}, str(prod))]

    # Possibly-decorated containers, with .type
    elif isinstance(
        prod,
        (
            widlparser.productions.SingleType,
            widlparser.productions.ConstType,
            widlparser.productions.UnionMemberType,
            widlparser.productions.Type,
            widlparser.productions.TypeWithExtendedAttributes,
        ),
    ):
        tail = []
        if isinstance(prod, widlparser.productions.ConstType) and prod.null is not None:
            tail.append(str(prod.null))
        if (
            isinstance(
                prod,
                (
                    widlparser.productions.UnionMemberType,
                    widlparser.productions.Type,
                    widlparser.productions.TypeWithExtendedAttributes,
                ),
            )
            and prod.suffix is not None
        ):
            tail.append(str(prod.suffix))
        head = []
        if (
            isinstance(
                prod,
                (
                    widlparser.productions.UnionMemberType,
                    widlparser.productions.TypeWithExtendedAttributes,
                ),
            )
            and prod._extended_attributes is not None
        ):
            head.extend(_nodesFromProduction(prod._extended_attributes))
            head.append(" ")
        if head or tail:
            return [*head, *_nodesFromProduction(prod.type), *tail]
        else:
            return _nodesFromProduction(prod.type)

    # NonAnyType is complicated
    elif isinstance(prod, widlparser.productions.NonAnyType):
        tail = []
        if prod.null:
            tail.append(str(prod.null))
        if prod.suffix:
            tail.append(str(prod.suffix))
        if prod.sequence:
            return [
                h.E.a({"data-link-type": "dfn"}, "sequence"),
                "<",
                *_nodesFromProduction(prod.type),
                ">",
                *tail,
            ]
        elif prod.promise:
            return [
                h.E.a({"data-link-type": "interface"}, "Promise"),
                "<",
                *_nodesFromProduction(prod.type),
                ">",
                *tail,
            ]
        elif prod.record:
            assert prod.key_type is not None
            return [
                h.E.a({"data-link-type": "dfn", "data-link-spec": "webidl"}, "record"),
                "<",
                *_nodesFromProduction(prod.key_type),
                ", ",
                *_nodesFromProduction(prod.type),
                ">",
                *tail,
            ]
        else:
            if tail:
                return [*_nodesFromProduction(prod.type), *tail]
            else:
                return _nodesFromProduction(prod.type)

    # UnionType
    elif isinstance(prod, widlparser.productions.UnionType):
        return ["(", *config.flatIntersperse([_nodesFromProduction(p) for p in prod.types], [" or "]), ")"]

    # Extended Attributes
    elif isinstance(prod, widlparser.productions.ExtendedAttributeList):
        return ["[", *config.flatIntersperse([_nodesFromProduction(p) for p in prod.attributes], [" or "]), "]"]
    elif isinstance(prod, widlparser.constructs.ExtendedAttribute):
        prod = prod.attribute
        if isinstance(prod, widlparser.constructs.ExtendedAttributeNoArgs):
            return [h.E.a({"data-link-type": "extended-attribute"}, str(prod))]
        elif isinstance(prod, widlparser.constructs.ExtendedAttributeIdent):
            return [
                h.E.a({"data-link-type": "extended-attribute"}, str(prod._attribute)),
                "=",
                str(prod._value),
            ]
        elif isinstance(prod, widlparser.constructs.ExtendedAttributeIdentList):
            return [
                h.E.a({"data-link-type": "extended-attribute"}, str(prod._attribute)),
                "=(",
                *_nodesFromProduction(prod._value),
                *(_nodesFromProduction(prod.next) if prod.next else [""]),
                ")",
            ]
        # punt on the rest
        else:
            return [str(prod)]

    # The rest of a comma-separated ident list
    elif isinstance(prod, widlparser.productions.TypeIdentifiers):
        nodes: list[t.NodeT] = [", ", h.E.a({"data-link-type": "idl-name"}, str(prod._name))]
        while prod.next:
            prod = prod.next
            nodes.append(", ")
            nodes.append(h.E.a({"data-link-type": "idl-name"}, str(prod._name)))
        return nodes

    # Things that should just be returned as text
    elif isinstance(
        prod,
        (
            widlparser.productions.String,
            widlparser.productions.Integer,
            widlparser.productions.FloatLiteral,
            widlparser.productions.ConstValue,
            widlparser.productions.EnumValue,
            widlparser.productions.EnumValueList,
            widlparser.productions.Default,
            widlparser.productions.ArgumentName,
        ),
    ):
        return [str(prod)]

    # Anything else, also return as plain str, but warn.
    m.warn(f"Unhandled IDL production type '{type(prod)}' in _nodesFromProduction, please report as a Bikeshed issue.")
    return [str(prod)]
