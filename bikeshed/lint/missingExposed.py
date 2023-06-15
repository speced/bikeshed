from __future__ import annotations

import widlparser  # pylint: disable=unused-import

from .. import messages as m
from .. import t


def missingExposed(doc: t.SpecT) -> None:
    """
    Checks that every IDL interface or namespace has an [Exposed] attribute.
    Specifically:
    * Any namespace
    * Any non-callback interface without [NoInterfaceObject]
    * Any callback interface that has constants in it.

    Partials never need to declare [Exposed], I think?
    """
    if not doc.md.complainAbout["missing-exposed"]:
        return

    for construct in doc.widl.constructs:
        extendedAttrs: list[str]
        if construct.extended_attributes is None:
            extendedAttrs = []
        else:
            extendedAttrs = [x.name for x in construct.extended_attributes if x.name is not None]
        if construct.idl_type == "namespace":
            good = False
            for attr in extendedAttrs:
                if attr == "Exposed":
                    good = True
                    break
            if not good:
                m.lint(
                    f"The '{construct.name}' namespace is missing an [Exposed] extended attribute. Does it need [Exposed=Window], or something more?",
                )
        elif construct.idl_type == "interface":
            good = False
            for attr in extendedAttrs:
                if attr == "Exposed":
                    good = True
                    break
                if attr == "NoInterfaceObject":
                    good = True
                    break
            if not good:
                m.lint(
                    f"The '{construct.name}' interface is missing an [Exposed] extended attribute. Does it need [Exposed=Window], or something more?",
                )
        elif construct.idl_type == "callback":
            if not hasattr(construct, "interface"):
                # Just a callback function, it's fine
                continue
