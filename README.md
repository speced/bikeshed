widlparser
==========

Stand-alone WebIDL Parser in Python. Requires Python 2.6 or 2.7.

Parses WebIDL per: http://dev.w3.org/2006/webapi/WebIDL/ (plus a few legacy compatability items)

Tis parser was created to support a W3C specification parser and pre-processor, it's API is geared towards finding and identifying various WebIDL constructs by name. However, all of the WebIDL source is parsed and stored in the construct objects. The parser has error recovery and preserves the entire input for re-serialization and markup of the WebIDL constructs.


Installation
------------

Standard python package installation:

       python setup.py install


Usage
-----

Import the widlparser package and instantiate a Parser.

       import widlparser

       widl = widlparser.parser.Parser()

Either pass the WebIDL text to be parsed in the constructor or call the **Parser.parse(text)** method.


Parser class
------------
**class parser.Parser([text[, ui]])**

The Parser's constructor takes two optional arguments, text and ui. If present, text is a unicode string containing the WebIDL text to parse. ui.warn() will get called with any syntax errors encountered during parsing (if implemented). ui.note() will get called for any legacy WebIDL that was ignored during parsing (if implemented). 

**Parser.constructs**

All top-level WebIDL constructs are stored in source order in the 'constructs' attribute. 

**Parser.complexityFactor**

An index of the relative complexity of the Constructs defined in the parsed WebIDL. Useful as an index for specification test coverage

**Parser.parse(text)**

Parse additional WebIDL text. All parsed constructs will be appended to the 'constructs' attribute.

**Parser.reset()**

Clears all stored constructs.

**Parser.find(name)**

Return a named construct. If a single name is provided, a breadth-first search through all parsed constructs is performed. Alternatively, a path (names separated by "/" or ".") may be passed to target the search more narrowly. e.g.: find("Foo/bar/baz") looks for an Attribute 'baz', inside a Method 'bar', inside an Interface 'Foo'.

**Parser.normalizedMethodName(name [, interfaceName = None])**

Provide a normalized version of a method name, including the names of all arguments, e.g. "drawCircle(long x, long y, long radius)" becomes: "drawCircle(x, y, radius)". If a valid set of arguments is passed, the passed argument names will be returned in the normalized form. Otherwise, a search is performed for a matching previously parsed method name. The search may be narrowed to a particular interface by passing the name fo the interface or callbak in interfaceName.

**Parser.markup(marker)**

Returns a marked-up version of the WebIDL input text. For each Construct, Type, and Name, the 'marker' will get called with 'markupConstruct(text, construct)', 'markupType(text, construct)', 'markupTypeName(text, construct)', or 'markupName(text, construct)' repsectively, if implemented. Implementation of each method is optional. The 'markup*' methods must return a tuple of the prefix and suffix to inject as markup around the text, or '(None, None)'. 'markupConstruct' will get called for each construct, 'markupType' will get called for each type, 'markupTypeName' will get called for each interface name within a type, 'markupName' will get called for the defining name of a construct (at most one per construct). If the 'marker' also implements 'encode(text)' it will get called with each block of text to return in any encoding necessary for the output format. Markup and encode calls will happen in source order, the text will be split at markup boundaries.


Constructs
----------
All Constructs accessed from the parser's Parser.constructs attribute or returned from the parser's find() method are subclasses of the Construct class. The base class provides the following:

**Construct.name**

The name of the construct.

**Construct.idlType**

Contains a string indicating the type of the construct. Possible values are: "const", "enum", "typedef", "interface", "constructor", "attribute", "iterator", "stringifier", "serializer", "method", "argument", "dictionary", "dict-member", "callback", "exception", "except-field", "implements", "extended-attribute", and "unknown".

**Construct.fullName**

The name of the construct and all of its parents in path form, e.g.: 'Interface/methodName(argument)/argument'.

**Construct.normalName**

For 'method' Constructs, contains the normalized method name, otherwise the name of the construct.

**Construct.parent**

The parent construct, or None if it is a top-level Construct in the source WebIDL.

**Construct.extendedAttributes**

A list of extended attributes, or None. Extended attributes are stored as Constructs, those of the forms: 'identifier', 'identifier=identifier', 'identifier(ArgumentList)', 'identifier=identifier(ArgumentList)', or 'identifier(Type,Type)' are parsed. The first identifier is stored in 'Construct.attribute', the second, if present, is stored in 'Construct.name', arguments are stored in 'Construct.arguments'.  Extended attributes not mathing those five forms contain a list of tokens in 'Construct.tokens' and their name is set to 'None'.

**Construct.constructors**

A list of any extended attributes matching the Constructor or NamedConstructor form. Any constructors present will be prepended to the 'members' attribute of an 'interface' Construct.

**Construct.complexityFactor**

An index of the complexity of the construct. See Parser.complexityFactor.

**Construct.findMember(name)**

Find a member of the construct. For 'callback' Constructs with an interface, will search the interface.

**Construct.findMethod(name)**

Find a method within the construct.

**Construct.findArgument(name[, searchMembers = True])**

Find an argument within the construct. If 'searchMembers' is true, all members will be searched as well. This allows distinguishing between arguments of a callback versus arguments of a callback interface's methods.

**Construct.markup(marker)**

Returns a marked-up version of the Constructs's WebIDL source text. See Parser.markup(marker) for information.


Construct Subclasses
--------------------
Each Construct will be an instance of a Construct subclass corresponding to its 'Construct.idlType'. Specific subclasses provide the following additional attributes:

**Const.type**

The Type Production of the Const.

**Const.value**

The ConstValue Production of the Const.

**Enum.values**

The EnumValueList Production of the Enum.

**Typedef.type**

The Type Production of the Typedef.

**Argument.type**

The Type Production of the Argument.

**Argument.variadic**

The Symbol "variadic" or 'None'.

**Argument.default**

The Default Production of the Argument or 'None'.

**InterfaceMember.member**

Either a Const Construct or an AttributeOrOperationOrIterator Production.

**InterfaceMember.arguments**

Contains a list of any arguments present or 'None'.

**Interface.partial**

The Symbol "partial" or 'None'.

**Interface.inheritance**

The Inheritance Production of the Interface or 'None'.

**Interface.members**

A list of InterfaceMembers.

**DictionaryMember.type**

The Type Production of the DictionaryMember.

**DictionaryMember.default**

The Default Production of the DictionaryMember or 'None'.

**Dictionary.inheritance**

The Inheritance Production of the Dictionary or 'None'.

**Dictionary.members**

A list of DictionaryMembers.

**Callback.returnType**

The ReturnType Production of the Callback.

**Callback.arguments**

Contains a list of any arguments present or 'None' for interface callbacks.

**Callback.interface**

The 'interface' Construct of the callback, or 'None' for function callbacks.

**ExceptionMember.const**

The Const Production of the ExceptionMember or 'None'.

**ExceptionMember.type**

The Type Production of the ExceptionMember. 'None' for Const members.

**Exception.inheritance**

The Inheritance Production of the Exception or 'None'.

**Exception.members**

A list of ExceptionMembers.

**ImplementsStatement.implements**

A string of the type implemented in the ImplementsStatement.

**ExtendedAttribute.attribute**

The ExtendedAttribute sub-type Production of an ExtendedAttribute. See below. Each of the below ExtendedAttribute sub-type also has an '.attribute' attribute designating the first identifier in the ExtendedAttribute. ExtendedAttributes other than Constructor or NamedConstructor types will also contain this identifier in the '.name' attribute.

**ExtendedAttributeArgList.arguments.**

Contains a list of any arguments present or 'None'.

**ExtendedAttributeIdent.value**

Contains a string of the identifier present after the "=".

**ExtendedAttributeNamedArgList.value**

Contains a string of the identifier present after the "=".

**ExtendedAttributeNamedArgList.arguments**

Contains a list of any arguments present or 'None'.

**ExtendedAttributeTypePair.keyType**

The first Type Production of the pair.

**ExtendedAttributeTypePair.valueType**

The second Type Production of the pair.

**ExtendedAttributeUnknown.tokens**

Contains a list of tokens in ExtendedAttributes not matching one of the five basic types.

**SyntaxError.tokens**

Contains a list of tokens that did not match the WebIDL grammar.


Notes
-----
The parser itself is iterable and indexable. Top-level constructs can be tested by the 'in' operator and retrieved by name or index via []. The unicode() or str() functions can also be used on the parser to re-serialize the parsed WebIDL. The serialized output is nullipotent, i.e. str(parser.Parser(text)) == text

Constructs are also iterable and indexable to access members. Additionally constructs can be re-serialized as valid WebIDL via the unicode() or str() functions.

All other WebIDL input is stored in the various constructs as Production objects. Refer to the productions.py source file for details. Productions can be re-serialized as their source WebIDL via the unicode() or str() functions.



