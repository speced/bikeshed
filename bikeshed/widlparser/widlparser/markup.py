# coding=utf-8
#
#  Copyright © 2013 Hewlett-Packard Development Company, L.P.
#
#  This work is distributed under the W3C® Software License [1]
#  in the hope that it will be useful, but WITHOUT ANY
#  WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
#  [1] http://www.w3.org/Consortium/Legal/2002/copyright-software-20021231
#

import itertools

class MarkupGenerator(object):
    def __init__(self, construct):
        self.construct = construct
        self.children = []

    def addGenerator(self, generator):
        self.children.append(generator)

    def addType(self, type):
        if (type):
            self.addText(type._leadingSpace)
            self.children.append(MarkupType(self.construct, type))
            self.addText(type._semicolon)
            self.addText(type._trailingSpace)

    def addPrimitiveType(self, type):
        if (type):
            self.children.append(MarkupPrimitiveType(self.construct, type))

    def addStringType(self, type):
        if (type):
            self.children.append(MarkupStringType(self.construct, type))

    def addBufferType(self, type):
        if (type):
            self.children.append(MarkupBufferType(self.construct, type))

    def addObjectType(self, type):
        if (type):
            self.children.append(MarkupObjectType(self.construct, type))

    def addTypeName(self, typeName):
        if (typeName):
            self.children.append(MarkupTypeName(typeName))

    def addName(self, name):
        if (name):
            self.children.append(MarkupName(name))

    def addKeyword(self, keyword):
        if (keyword):
            self.children.append(MarkupKeyword(keyword))

    def addEnumValue(self, enumValue):
        if (enumValue):
            self.children.append(MarkupEnumValue(enumValue))

    def addText(self, text):
        if (text):
            if ((0 < len(self.children)) and (type(self.children[-1]) is MarkupText)):
                self.children[-1].text += unicode(text)
            else:
                self.children.append(MarkupText(unicode(text)))

    @property
    def text(self):
        return u''.join([child.text for child in self.children])

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupConstruct')):
            return marker.markupConstruct(self.text, self.construct)
        return (None, None)

    def markup(self, marker, parent = None):
        head, tail = self._markup(marker)
        output = unicode(head) if (head) else u''
        output += u''.join([child.markup(marker, self.construct) for child in self.children])
        return output + (unicode(tail) if (tail) else u'')


class MarkupType(MarkupGenerator):
    def __init__(self, construct, type):
        MarkupGenerator.__init__(self, construct)
        type._markup(self)

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupType')):
            return marker.markupType(self.text, self.construct)
        return (None, None)


class MarkupPrimitiveType(MarkupGenerator):
    def __init__(self, construct, type):
        MarkupGenerator.__init__(self, construct)
        type._markup(self)

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupPrimitiveType')):
            return marker.markupPrimitiveType(self.text, self.construct)
        return (None, None)


class MarkupBufferType(MarkupGenerator):
    def __init__(self, construct, type):
        MarkupGenerator.__init__(self, construct)
        type._markup(self)

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupBufferType')):
            return marker.markupBufferType(self.text, self.construct)
        return (None, None)


class MarkupStringType(MarkupGenerator):
    def __init__(self, construct, type):
        MarkupGenerator.__init__(self, construct)
        type._markup(self)

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupStringType')):
            return marker.markupStringType(self.text, self.construct)
        return (None, None)


class MarkupObjectType(MarkupGenerator):
    def __init__(self, construct, type):
        MarkupGenerator.__init__(self, construct)
        type._markup(self)

    def _markup(self, marker):
        if (self.construct and hasattr(marker, 'markupObjectType')):
            return marker.markupObjectType(self.text, self.construct)
        return (None, None)


class MarkupText(object):
    def __init__(self, text):
        self.text = text

    def markup(self, marker, construct):
        return unicode(marker.encode(self.text)) if (hasattr(marker, 'encode')) else self.text


class MarkupTypeName(MarkupText):
    def __init__(self, type):
        MarkupText.__init__(self, type)

    def markup(self, marker, construct):
        head, tail = marker.markupTypeName(self.text, construct) if (hasattr(marker, 'markupTypeName')) else (None, None)
        output = unicode(head) if (head) else u''
        output += MarkupText.markup(self, marker, construct)
        return output + (unicode(tail) if (tail) else u'')


class MarkupName(MarkupText):
    def __init__(self, name):
        MarkupText.__init__(self, name)

    def markup(self, marker, construct):
        head, tail = marker.markupName(self.text, construct) if (hasattr(marker, 'markupName')) else (None, None)
        output = unicode(head) if (head) else u''
        output += MarkupText.markup(self, marker, construct)
        return output + (unicode(tail) if (tail) else u'')


class MarkupKeyword(MarkupText):
    def __init__(self, keyword):
        MarkupText.__init__(self, keyword)

    def markup(self, marker, construct):
        head, tail = marker.markupKeyword(self.text, construct) if (hasattr(marker, 'markupKeyword')) else (None, None)
        output = unicode(head) if (head) else u''
        output += MarkupText.markup(self, marker, construct)
        return output + (unicode(tail) if (tail) else u'')


class MarkupEnumValue(MarkupText):
    def __init__(self, keyword):
        MarkupText.__init__(self, keyword)

    def markup(self, marker, construct):
        head, tail = marker.markupEnumValue(self.text, construct) if (hasattr(marker, 'markupEnumValue')) else (None, None)
        output = unicode(head) if (head) else u''
        output += MarkupText.markup(self, marker, construct)
        return output + (unicode(tail) if (tail) else u'')

