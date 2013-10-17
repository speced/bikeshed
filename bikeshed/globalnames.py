import .config
from .messages import *
from .ReferenceManager import linkTextsFromElement

'''
A global name uniquely identifies a definition.
It includes the value itself, its type, and any values that it is for.
For example, the value "auto" for the keyword "width" has the global name "width(property)/auto(value)".
This lets me both uniquely refer to and find definitions,
and do interesting things like say "find me all the values for the width property".

A fully canonicalized global name contains every segment necessary to make it unique in the global namespace,
and a type for each segment.
For example, the value of a descriptor must contain three segments, for itself, its descriptor, and its at-rule.

Partial names can exist, which contain less than the full amount of pieces necessary to uniquify it.
These are mainly useful for matching and manual specification, but may be ambiguous.

Reduced global names can exist, which contain all their pieces but perhaps not all their types.
As long as they're not partial, they can be automatically canonicalized with just the type of the lowermost segment.
For example, "@foo/bar/baz(value)" can be canonicalized into "@foo(at-rule)/bar(descriptor)/baz(value)" automatically,
while "bar/baz(value)" would be canonicalized into "bar(property)/baz(value)".
'''

class GlobalName(object):
	name = []

	def __init__(self, text=None, type=None, childType=None, globalName=None):
		if isinstance(globalName, GlobalName):
			self.name = val.name
			return
		if text is not None:
			if childType is not None:
				return GlobalName.fromFor(text, childType)
			else:
				return GlobalName.fromReduced(text, type)


	def __str__(self):
		return '/'.join(map("{0}({1})".format, self.name))

	@classmethod
	def fromFor(cls, text, childType):
		# Given a single for value, and the type of the child that is using the for,
	    # turns the for text into a global name.
	    def cantParse(text):
	        die("Can't figure out how to canonicalize the for value '{0}'", text)
	        return ""

	    if childType not in config.typesUsingFor:
	        die("Definitions of type '{0}' don't use for=''.", childType)
	        return []
	    splits = forText.rsplit("/", 1)
	    if len(splits) == 1:
	        text = splits[0]
	        rest = ""
	    else:
	        text = splits[1]
	        rest = splits[0]
	    if childType == "value":
	        if config.typeRe["at-rule"].match(text):
	            type = "at-rule"
	        elif config.typeRe["type"].match(text):
	            type = "type"
	        elif config.typeRe["selector"].match(text):
	            type = "selector"
	        elif config.typeRe["function"].match(text):
	            type = "function"
	        elif config.typeRe["descriptor"].match(text) and config.typeRe["at-rule"].match(rest):
	            type = "descriptor"
	        elif config.typeRe["property"].match(text):
	            type = "property"
	        else:
	            return cantParse(text)
	    elif childType == "descriptor":
	        if config.typeRe["at-rule"].match(text):
	            type = "at-rule"
	        else:
	            return cantParse(text)
	    elif childType in ("method", "constructor", "attribute", "const", "event", "stringifier", "serializer", "iterator"):
	        if config.typeRe["interface"].match(text):
	            type = "interface"
	        else:
	            return cantParse(text)
	    elif childType == "argument":
	        if config.typeRe["method"].match(text):
	            type = "method"
	        else:
	            return cantParse(text)
	    elif childType == "dict-member":
	        if config.typeRe["dictionary"].match(text):
	            type = "dictionary"
	        else:
	            return cantParse(text)
	    elif childType == "except-field":
	        if config.typeRe["exception"].match(text):
	            type = "exception"
	        else:
	            return cantParse(text)
	    else:
	        raise Exception("Coding error - I'm missing the '{0}' typeUsingFor.".format(childType))

	    if rest:
	    	ret = cls.fromFor(rest, type)
	    else:
	    	ret = cls()
	    ret.name.append((text, type))
	    return ret

	@classmethod
	def fromReduced(cls, text, type=None):
	    # Turns a "reduced" global name, like "@counter-style/width/<integer>", into a full global name.
	    if type is None:
	        # Assume that the text is like "foo(value)"
	        match = re.match(r"(.*)\([\w-]+\)$", text)
	        if match is None:
	            die("'{0}' doesn't match the format of a reduced global name.")
	            return
	        text = match.group(1)
	        type = match.group(2)

	    if '/' in text:
	        pieces = text.split('/')
	        ret = cls.fromFor('/'.join(pieces[:-1]), type).name
	    else:
	    	ret = cls()
	    ret.name.append((text, type))
	    return ret

	@staticmethod
	def compare(name1, name2):
	    # Returns true if the names are equal,
	    # or at least possibly equal if one was extended to a full global name.
	    # For example, "foo(value)" is true with "bar(property)/foo(value)" or "<baz>(type)/foo(value)".
	    return all(p[0] == p[1] for p in zip(reversed(name1.name), reversed(name2.name)))

	def __eq__(self, other):
		return GlobalName.compare(self, other)



class GlobalNames(object):
	names = []

	def __init__(self, text=None, type=None, childType=None):
		if text is not None:
			self.names = [GlobalName(t, type=type, childType=childType) for t in GlobalNames._splitNames(text)]

	@staticmethod
	def _splitNames(namesText):
	    # If global names are space-separated, you can't just split on spaces.
	    # "Foo/bar(baz, qux)" is a valid global name, for example.
	    # So far, only need to respect parens, which is easy.
	    if namesText is None or namesText == '':
	        return []
	    names = []
	    numOpen = 0
	    numClosed = 0
	    for chunk in namesText.strip().split():
	        if numOpen == numClosed:
	            names.append(chunk)
	        elif numOpen > numClosed:
	            # Inside of a parenthesized section
	            names[-1] += " " + chunk
	        else:
	            # Unbalanced parens?
	            die("Found unbalanced parens when processing the globalnames:\n{0}", outerHTML(el))
	            return []
	        numOpen += chunk.count("(")
	        numClosed += chunk.count(")")
	    if numOpen != numClosed:
	        die("Found unbalanced parens when processing the globalnames:\n{0}", outerHTML(el))
	        return []
	    return names

	@classmethod
	def fromTextAndFor(cls, texts, type, forText=None):
		import copy
		if isinstance(texts, basestring):
			texts = [texts]
		ret = cls()
		for text in texts:
			if forText is None:
				ret.names = [GlobalName(text, type=type) for text in texts]
			else:
				forNames = GlobalNames(forText, childType=type)
				for text in texts:
					for name in forNames:
						cp = copy.deepcopy(name)
						cp.name.append((text, type))
						ret.names.append(cp)
		return ret

	@classmethod
	def fromEl(cls, el):
		texts = linkTextsFromElement(el)
		type = el.get('data-dfn-type') or el.get('data-link-type') or el.get('data-idl-type')
		forText = el.get('data-dfn-for') or el.get('data-link-for') or el.get('data-idl-for')
		return cls.fromTextAndFor(texts, type, forText)

	@classmethod
	def refsFromEl(cls, el):
		type = el.get('data-dfn-type') or el.get('data-link-type') or el.get('data-idl-type')
        forText = el.get('data-dfn-for') or el.get('data-link-for') or el.get('data-idl-for')
        return GlobalNames(forText, childType=type)

    def __contains__(self, other):
    	return any(x == other for x in self.names)

    def __iter__(self):
    	return self.names