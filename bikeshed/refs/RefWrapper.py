# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import copy

from .utils import stripLineBreaks
from .. import attr

@attr.s(slots=True)
class RefWrapper(object):
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.

    text = attr.ib()
    _ref = attr.ib()

    def __getattr__(self, name):
        '''
        Indirect all attr accesses into the self._ref dict.
        Also, strip whitespace from the values (they'll have \n at the end) on access.
        '''
        if name == "for_":
            refKey = "for"
        else:
            refKey = name
        val = self._ref[refKey]
        if isinstance(val, basestring):
            val = decode(val.strip())
        elif isinstance(val, list):
            val = [decode(x.strip()) for x in val]
        return val

    def __json__(self):
        refCopy = copy.copy(self._ref)
        refCopy['text'] = self.text
        return stripLineBreaks(refCopy)

def decode(s):
    if isinstance(s, str):
        return unicode(s, encoding="utf-8")
    return s