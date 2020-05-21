# -*- coding: utf-8 -*-


import copy

import attr

from .utils import stripLineBreaks

@attr.s(slots=True)
class RefWrapper(object):
    # Refs don't contain their own name, so I don't have to copy as much when there are multiple linkTexts
    # This wraps that, producing an object that looks like it has a text property.
    # It also makes all the ref dict keys look like object attributes.

    text = attr.ib()
    _ref = attr.ib()

    @property
    def type(self):
        return decode(self._ref['type'].strip())
    @property
    def spec(self):
        return decode(self._ref['spec'].strip())
    @property
    def shortname(self):
        return decode(self._ref['shortname'].strip())
    @property
    def level(self):
        if self._ref['level'] is None:
            return ""
        return decode(self._ref['level'].strip())
    @property
    def status(self):
        return decode(self._ref['status'].strip())
    @property
    def url(self):
        return decode(self._ref['url'].strip())
    @property
    def export(self):
        return self._ref['export']
    @property
    def normative(self):
        return self._ref['normative']
    @property
    def for_(self):
        return [x.strip() for x in self._ref['for']]
    @property
    def el(self):
        return self._ref.get('el', None)

    '''
        "type": linesIter.next(),
        "spec": linesIter.next(),
        "shortname": linesIter.next(),
        "level": linesIter.next(),
        "status": linesIter.next(),
        "url": linesIter.next(),
        "export": linesIter.next() != "\n",
        "normative": linesIter.next() != "\n",
        "for": [],
        (optionall) "el": manuallyProvided,
    '''

    def __json__(self):
        refCopy = copy.copy(self._ref)
        refCopy['text'] = self.text
        return stripLineBreaks(refCopy)

def decode(s):
    # TODO: verify that this can be removed
    return s
