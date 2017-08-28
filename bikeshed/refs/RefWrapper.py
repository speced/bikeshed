# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

import copy

class RefWrapper(object):
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.
    def __init__(self, text, ref):
        self.text = text
        self._ref = ref

    def __getattr__(self, name):
        '''
        Indirect all attr accesses into the self._ref dict.
        Also, strip whitespace from the values (they'll have \n at the end) on access,
        and store them directly on the RefWrapper for fast access next time.
        '''
        if name == "for_":
            refKey = "for"
        else:
            refKey = name
        val = self._ref[refKey]
        if isinstance(val, basestring):
            val = val.strip()
        elif isinstance(val, list):
            val = [x.strip() for x in val]
        self.key = val
        return val

    def __json__(self):
        refCopy = copy.copy(self._ref)
        refCopy['text'] = self.text
        return stripLineBreaks(refCopy)

    def __repr__(self):
        return "RefWrapper(" + repr(self.text) + ", " + repr(self._ref) + ")"
