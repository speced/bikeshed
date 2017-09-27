# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from ..htmlhelpers import *
from ..messages import *

def missingExposed(doc):
    '''
    Checks that every IDL interface or namespace has an [Exposed] attribute.
    Specifically:
    * Any namespace
    * Any non-callback interface without [NoInterfaceObject]
    * Any callback interface that has constants in it.

    Partials never need to declare [Exposed], I think?
    '''
    if not doc.md.complainAbout['missing-exposed']:
        return

    for construct in doc.widl.constructs:
        if construct.extendedAttributes is None:
            extendedAttrs = []
        else:
            extendedAttrs = construct.extendedAttributes
        if construct.idlType == "namespace":
            good = False
            for attr in extendedAttrs:
                if attr.name == "Exposed":
                    good = True
                    break
            if not good:
                warn("The '{0}' namespace is missing an [Exposed] extended attribute. Does it need [Exposed=Window], or something more?", construct.name)
        elif construct.idlType == "interface":
            good = False
            for attr in extendedAttrs:
                if attr.name == "Exposed":
                    good = True
                    break
                if attr.name == "NoInterfaceObject":
                    good = True
                    break
            if not good:
                warn("The '{0}' interface is missing an [Exposed] extended attribute. Does it need [Exposed=Window], or something more?", construct.name)
        elif construct.idlType == "callback":
            if not hasattr(construct, "interface"):
                # Just a callback function, it's fine
                continue
            for members in construct.interface.members:
                pass
