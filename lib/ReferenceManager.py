from fuckunicode import u
import re

class ReferenceManager(object):
    properties = dict()
    descriptors = dict()
    values = dict()
    links = dict()

    def processDfns(self, dfns):
        for el in dfns:
            if re.search("no-ref", el.get('class') or ""):
                continue
            linkTexts = linkTextsFromElement(el)
            for linkText in linkTexts:
                type = el.get('data-dfn-type')
                if type == "value":
                    if linkText in self.values:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.values[linkText]['el'])
                    self.values[linkText] = {'id':u(el.get('id')), 'el':el}
                elif type == "property":
                    if linkText in self.properties:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.properties[linkText]['el'])
                    self.properties[linkText] = {'id':u(el.get('id')), 'el':el}
                elif type == "descriptor":
                    if linkText in self.descriptors:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.descriptors[linkText]['el'])
                    self.descriptors[linkText] = {'id':u(el.get('id')), 'el':el}
                else:
                    if linkText in self.links:
                        die(u"Two link-targets have the same linking text:\n{0}\n{1}", el, self.links[linkText]['el'])
                    self.links[linkText] = {'id':u(el.get('id')), 'el':el}

    def getRef(self, type, text):
        if type == "property":
            if text in self.properties:
                return self.properties[text]['id']
            elif text in self.descriptors:
                return self.descriptors[text]['id']
        elif type == "value":
            if text in self.values:
                return self.values[text]['id']
        elif type == "link":
            for var in linkTextVariations(text):
                if var in self.links:
                    return self.links[var]['id']
        elif type == "maybe":
            # Most value links will be encoded as maybes.
            if text in self.values:
                return self.values[text]['id']
            for var in linkTextVariations(text):
                if var in self.links:
                    return self.links[var]['id']

        

def linkTextsFromElement(el, preserveCasing=False):
    from lib.htmlhelpers import textContent
    if el.get('title') == '':
        return []
    elif el.get('title'):
        return [u(x.strip()) for x in el.get('title').split('|')]
    elif preserveCasing:
        return [textContent(el).strip()]
    else:
        return [textContent(el).strip().lower()]


def linkTextVariations(str):
    # Generate intelligent variations of the provided link text,
    # so explicitly adding a title attr isn't usually necessary.
    yield str

    if str[-3:] == u"ies":
        yield str[:-3]+u"y"
    if str[-2:] == u"es":
        yield str[:-2]
    if str[-2:] == u"'s":
        yield str[:-2]
    if str[-1:] == u"s":
        yield str[:-1]
    if str[-1:] == u"'":
        yield str[:-1]