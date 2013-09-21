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
            self.children.append(MarkupType(type))
    
    def addName(self, name):
        if (name):
            self.children.append(MarkupName(name))
    
    def addText(self, text):
        if (text):
            if ((0 < len(self.children)) and (type(self.children[-1]) is MarkupText)):
                self.children[-1].text += unicode(text)
            else:
                self.children.append(MarkupText(unicode(text)))

    @property
    def text(self):
        return u''.join([child.text for child in self.children])
    
    def markup(self, marker, parent = None):
        if (self.construct and hasattr(marker, 'markupConstruct')):
            head, tail = marker.markupConstruct(self.text, self.construct)
        else:
            head, tail = (None, None)
        output = unicode(head) if (head) else u''
        output += u''.join([child.markup(marker, self.construct) for child in self.children])
        return output + (unicode(tail) if (tail) else u'')

class MarkupText(object):
    def __init__(self, text):
        self.text = text
    
    def markup(self, marker, construct):
        return unicode(marker.encode(self.text)) if (hasattr(marker, 'encode')) else self.text


class MarkupType(MarkupText):
    def __init__(self, type):
        MarkupText.__init__(self, type)
    
    def markup(self, marker, construct):
        head, tail = marker.markupType(self.text, construct) if (hasattr(marker, 'markupType')) else (None, None)
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



