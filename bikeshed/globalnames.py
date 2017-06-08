# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import collections as col
import copy
import re
from . import config
from .messages import *
from .ReferenceManager import linkTextsFromElement

'''
A global name uniquely identifies a definition
as a sequence of (value, type) tuples,
with the definition itself as the first tuple,
and if the definition need disambiguation to be globally unique,
additional values as following tuples.
For example, the value "auto" for the keyword "width" has the global name [(auto, value), (width, property)].
This lets me both uniquely refer to and find definitions,
and do interesting things like say "find me all the values for the width property".

Global names are written in the opposite order,
with the type in parentheses,
and segments separated by slashes,
like "width<property>/auto<value>".

A fully canonicalized global name contains every segment necessary to make it unique in the global namespace,
and a type for each segment.
For example, the value of a descriptor must contain three segments, for itself, its descriptor, and its at-rule.

Partial names can exist, which contain less than the full amount of pieces necessary to uniquify it.
These are mainly useful for matching and manual specification, but may be ambiguous.

Reduced global names can exist, which contain all their pieces but perhaps not all their types.
As long as they're not partial, they can be automatically canonicalized with just the type of the lowermost segment.
For example, "@foo/bar/baz<value>" can be canonicalized into "@foo<at-rule>/bar<descriptor>/baz<value>" automatically,
while "bar/baz<value>" would be canonicalized into "bar<property>/baz<value>".
'''

Seg = col.namedtuple('Seg', ['value', 'type'])


class GlobalName(object):
    valid = True

    def __init__(self, text=None, type=None, childType=None, partial=False, globalName=None):
        '''
        Constructs a GlobalName from a string.
        If its first segment has a type, or you pass a type or a childType,
        it will be fully canonicalized.
        Otherwise, it'll be left as reduced.
        If you indicate that it's a partial name,
        no canonicalization will occur.
        '''
        text = text
        type = type
        childType = childType
        self.segments = []
        if isinstance(globalName, GlobalName):
            self.segments = copy.deepcopy(val.segments)
            return
        if text is not None:
            segs = self.segments
            for piece in reversed(text.split('/')):
                match = re.match(r"(.+)<([\w-]+)>$", piece)
                if match:
                    segs.append(Seg(match.group(1), match.group(2)))
                else:
                    segs.append(Seg(piece, None))
            if not partial and (type is not None or childType is not None or segs[0].type is not None):
                self.canonicalize(type=type, childType=childType)
            if self.validate():
                return
        # If I haven't returned yet, something's invalid.
        self.valid = False

    def __unicode__(self):
        strPieces = []
        for segment in reversed(self.segments):
            if segment[1] is not None:
                strPieces.append("{0}<{1}>".format(*segment))
            else:
                strPieces.append(segment.value)
        return '/'.join(strPieces)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def canonicalize(self, type=None, childType=None):
        '''
        Guesses at any missing types.
        '''
        type = type
        childType = childType
        # Push type into the first segment, as long as it's possible.
        if type is not None:
            if self.segments[0].type is None:
                self.segments[0] = self.segments[0]._replace(type=type)
            elif self.segments[0] == type:
                pass
            else:
                die("Tried to force-canonicalize '{0}' as type '{1}', but it's already '{2}'.", str(self), type, self.segments[0].type)
                self.valid = False
                return self

        def guessType(value, type, prevType, nextValue):
            if type is not None:
                return type
            if prevType is None:
                if config.typeRe['at-rule'].match(value):
                    return "at-rule"
                if config.typeRe['selector'].match(value):
                    return "selector"
                if config.typeRe['type'].match(value):
                    return "type"
                return None
            else:
                if prevType == "descriptor" and config.typeRe['at-rule'].match(value):
                    return "at-rule"
                if prevType == "value":
                    if config.typeRe['at-rule'].match(value):
                        return "at-rule"
                    if config.typeRe['type'].match(value):
                        return "type"
                    if config.typeRe['function'].match(value):
                        return "function"
                    if config.typeRe['selector'].match(value):
                        return "selector"
                    if config.typeRe['descriptor'].match(value) and config.typeRe['at-rule'].match(nextValue):
                        return "descriptor"
                    if config.typeRe['property'].match(value):
                        return "property"
                if prevType in ("method", "constructor", "attribute", "const", "event", "stringifier", "serializer", "iterator") and config.typeRe['interface'].match(value):
                    return "interface"
                if prevType == "argument" and config.typeRe['method'].match(value):
                    return "method"
                if prevType == "dict-member" and config.typeRe['dictionary'].match(value):
                    return "dictionary"
                if prevType == "except-field" and config.typeRe['exception'].match(value):
                    return "exception"
                return None
        for i, segment in enumerate(self.segments):
            prevType = childType if i == 0 else self.segments[i - 1].type
            nextValue = '' if i + 1 == len(self.segments) else self.segments[i + 1].value
            self.segments[i] = segment._replace(type=guessType(*segment, prevType=prevType, nextValue=nextValue))
        return self

    def validate(self):
        '''
        For now, just makes sure that types are well-known.
        '''
        # TODO: Decide whether I should try and enforce type structures.
        knownTypes = config.dfnTypes.union(["dfn"])
        for i, segment in enumerate(self.segments):
            if segment.type is None or segment.type in knownTypes:
                pass
            else:
                die("Unknown type '{0}' in global name '{1}'.", segment.type, str(self))
                self.valid = False
        return self

    def specialize(self, text, type=None):
        self.segments.insert(0, Seg(text, type))

    def __eq__(self, other):
        '''
        Returns true if two names don't disagree in any particular;
        that is, if they are compatible.
        For example, "foo<value>" is equal to "bar<property>/foo<value>",
        or to just "foo".
        Note that equality is *not* transitive;
        "foo<value>" == "foo", and "foo<property>" == "foo",
        but "foo<value>" != "foo<property>".
        '''
        if not isinstance(other, GlobalName):
            return False
        if not self.valid or not other.valid:
            return False
        for s1, s2 in zip(self.segments, other.segments):
            if s1.value != s2.value:
                return False
            if s1.type is not None and s2.type is not None and s1.type != s2.type:
                return False
        return True


class GlobalNames(col.Set, col.Hashable):
    def __init__(self, text=None, type=None, childType=None):
        self.__names = set()
        text = text
        type = type
        childType = childType
        if isinstance(text, basestring):
            text = GlobalNames.__splitNames(text)
        if isinstance(text, col.Sequence):
            for t in text:
                if isinstance(t, GlobalName):
                    self.__names.add(t)
                else:
                    self.__names.add(GlobalName(t, type=type, childType=childType))
        self.filter().canonicalize()

    @staticmethod
    def __splitNames(namesText):
        '''
        If global names are space-separated, you can't just split on spaces.
        "Foo/bar(baz, qux)" is a valid global name, for example.
        So far, only need to respect parens, which is easy.
        '''
        namesText = namesText
        if not namesText:
            return []
        names = []
        nesting = 0
        for chunk in namesText.strip().split():
            if nesting == 0:
                names.append(chunk)
            elif nesting > 0:
                # Inside of a parenthesized section
                names[-1] += " " + chunk
            else:
                # Unbalanced parens?
                die("Found unbalanced parens when processing the globalnames:\n{0}", namesText)
                return []
            nesting += chunk.count("(") - chunk.count(")")
        if nesting != 0:
            die("Found unbalanced parens when processing the globalnames:\n{0}", namesText)
            return []
        return names

    def specialize(self, texts, type=None):
        type = type
        if isinstance(texts, basestring):
            texts = [texts]
        for text in texts:
            for name in self.__names:
                name.specialize(text, type)
        return self.canonicalize()

    def canonicalize(self, type=None, childType=None):
        type = type
        childType = childType
        for name in self.__names:
            name.canonicalize(type=type, childType=childType)
        return self

    def filter(self):
        self.__names = set(name for name in self.__names if name.validate().valid)
        return self

    def matches(self, other):
        return any(n in other for n in self)

    @classmethod
    def fromEl(cls, el):
        texts = linkTextsFromElement(el)
        type = el.get('data-dfn-type') or el.get('data-link-type') or el.get('data-idl-type')
        forText = el.get('data-dfn-for') or el.get('data-link-for') or el.get('data-idl-for')
        return cls(forText).specialize(texts, type)

    @classmethod
    def refsFromEl(cls, el):
        type = el.get('data-dfn-type') or el.get('data-link-type') or el.get('data-idl-type')
        forText = el.get('data-dfn-for') or el.get('data-link-for') or el.get('data-idl-for')
        return cls(forText, childType=type)

    def __contains__(self, other):
        return any(x == other for x in self)

    def __iter__(self):
        return self.__names.__iter__()

    def __len__(self):
        return len(self.__names)

    __hash__ = col.Set._hash

    def __unicode__(self):
        return ' '.join(map(unicode,self))

    def __str__(self):
        return unicode(self).encode('utf-8')
