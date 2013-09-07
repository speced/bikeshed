widlparser
==========

Stand-alone WebIDL Parser in Python

Parses WebIDL per: http://www.w3.org/TR/2012/CR-WebIDL-20120419/ (plus a few legacy compatability items)

Tis parser was created to support a W3C specification parser and pre-processor, it's API is geared towards finding and identifying various WebIDL constructs by name. However, all of the WebIDL source is parsed and stored in the construct objects.


Installation
------------

Standard python package installation:

       python setup.py install


Usage
-----

Import the parser module from the widlparser package and instantiate a Parser.

       from widlparser import parser

       widl = parser.Parser()

Either pass the WebIDL text to be parsed in the constructor or call the **Parser.parse(text)** method.


Parser class
------------
**class parser.Parser([text[, ui]])**

The Parser's constructor takes two optional arguments, text and ui. If present, text is a string containing the WebIDL text to parse. ui.warn() will get called with any syntax errors encountered during parsing. 

**Parser.constructs**

All top-level WebIDL constructs are stored in source order in the 'constructs' attribute. 

**Parser.parse(text)**

Parse additional WebIDL text. All parsed constructs will be appended to the 'constructs' attribute.

**Parser.reset()**

Clears all stored constructs.

**Parser.find(name)**

Return a named construct. If a single name is provided, a breadth-first search through all parsed constructs is performed. Alternatively, a path (names separated by "/" or ".") may be passed to target the search more narrowly. e.g.: find("Foo/bar/baz") looks for an Attribute 'baz', inside a Method 'bar', inside an Interface 'Foo'.

**Parser.normalizedMethodName(name)**

Provide a normalized version of a method name, including the names of all arguments, e.g. "drawCircle(long x, long y, long radius)" becomes: "drawCircle(x, y, radius)". If a valid set of arguments is passed, the passed argument names will be returned in the normalized form. Otherwise, a search is performed for a matching previously parsed method name.

**Parser.markup(marker)**

Returns a marked-up version of the WebIDL input text. For each Construct, Type, and Name, the 'marker' will get called with 'markupConstruct(text, construct)', 'markupType(text, construct)', or 'markupName(text, construct)' repsectively, if implemented. The 'markup*' methods need to return a tuple of the prefix and suffix for the text, or '(None, None)'. If the 'marker' also implements 'encode(text)' it will get called with each block of text to return in any encoding necessary for the output format.

Constructs
----------
**Construct.name**

The name of the construct.

**Construct.idlType**

Contains a string indicating the type of the construct. Possible values are: "const", "enum", "typedef", "interface", "constructor", "attribute", "method", "argument", "dictionary", "dictmember", "callback", "exception", "exceptfield", "implements", "extended-attribute", and "unknown".

**Construct.fullName**

The name of the construct and all of its parents in path form, e.g.: 'Interface/methodName(argument)/argument'.

**Construct.normalName**

For 'method' Constructs, contains the normalized method name, otherwise the name of the construct.

**Construct.parent**

The parent construct, or None.

**Construct.extendedAttributes**

A list of extended attributes, or None. Extended attributes are stored as Constructs, those of the forms: 'identifier', 'identifier=identifier', 'identifier(ArgumentList)', or 'identifier=identifier(ArgumentList)' are parsed. The first identifier is stored in 'Construct.attribute', the second, if present, is stored in 'Construct.name', arguments are stored in 'Construct.arguments'.  Extended attributes not mathing those four forms contain a list of tokens in 'Construct.tokens' and their name is set to 'None'.

**Construct.constructors**

A list of any extended attributes matching the Constructor or NamedConstructor form. Any constructors present will be prepended to the 'members' attribute of an 'interface' Construct.

**Construct.members**

Only present on 'interface', 'dictionary', and 'exception' Constructs. A list of members of the Construct, or 'None'.

**Construct.interface**

Only present on 'callback' Constructs. The 'interface' Construct of the callback, or 'None'.

**Construct.arguments**

Only present on 'method', 'callback', and 'extended-attribute' constructs of the forms with ArgumentLists. Contains a list of any arguments present or 'None'.

**Construct.typeExtendedAtributes**

Only present on 'typedef' Constructs. Contains a list of extended attributes immediately preceding the Type or 'None'.

**Construct.findMember(name)**

Find a member of the construct. For 'callback' Constructs with an interface, will search the interface.

**Construct.findMethod(name)**

Find a method within the construct.

**Construct.findArgument(name[, searchMembers = True])**

Find an argument within the construct. If 'searchMembers' is true, all members will be searched as well. This allows distinguishing between arguments of a callback versus arguments of a callback interface's methods.

Notes
-----
The parser itself is iterable, and indexable. Top-level constructs can be tested by the 'in' operator and retrieved by name or index via []. The unicode() or str() functions can also be used on the parser to re-serialize the parsed WebIDL. The serialized output is nullipotent, i.e. str(parser.Parser(text)) == text

Constructs are also iterable and indexable to access members. Additionally constructs can be re-serialized as valid WebIDL via the unicode() or str() functions.

All other WebIDL input is stored in the various constructs as Production objects. Refer to the productions.py source file for details.



