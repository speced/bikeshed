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

from productions import *
from markup import MarkupGenerator

class Construct(ChildProduction):
    @classmethod
    def peek(cls, tokens):
        return ExtendedAttributeList.peek(tokens)

    def __init__(self, tokens, parent, parseExtendedAttributes = True, parser = None):
        ChildProduction.__init__(self, tokens, parent)
        self._parser = parser
        self._extendedAttributes = self._parseExtendedAttributes(tokens, self) if (parseExtendedAttributes) else None

    def _parseExtendedAttributes(self, tokens, parent):
        return ExtendedAttributeList(tokens, parent) if (ExtendedAttributeList.peek(tokens)) else None

    @property
    def idlType(self):
        assert(False)   # subclasses must override
        return None

    @property
    def constructors(self):
        return [attribute for attribute in self._extendedAttributes if ('constructor' == attribute.idlType)] if (self._extendedAttributes) else []

    @property
    def parser(self):
        return self._parser if (self._parser) else self.parent.parser

    @property
    def extendedAttributes(self):
        return self._extendedAttributes if (self._extendedAttributes) else {}

    def __nonzero__(self):
        return True

    def __len__(self):
        return 0

    def keys(self):
        return []

    def __getitem__(self, key):
        return None

    def __iter__(self):
        return iter(())

    def __contains__(self, key):
        return False

    def findMember(self, name):
        return None

    def findMembers(self, name):
        return []

    def findMethod(self, name, argumentNames=None):
        return None

    def findMethods(self, name, argumentNames=None):
        return []

    def findArgument(self, name, searchMembers = True):
        return None

    def findArguments(self, name, searchMembers = True):
        return []

    @property
    def complexityFactor(self):
        return 1

    def _unicode(self):
        return unicode(self._extendedAttributes) if (self._extendedAttributes) else ''

    def __repr__(self):
        return repr(self._extendedAttributes) if (self._extendedAttributes) else ''

    def markup(self, generator):
        if (not generator):
            return unicode(self)

        if (isinstance(generator, MarkupGenerator)):
            marker = None
            generator.addText(self._leadingSpace)
        else:
            marker = generator
            generator = None

        myGenerator = MarkupGenerator(self)
        if (self._extendedAttributes):
            self._extendedAttributes.markup(myGenerator)
        target = self._markup(myGenerator)
        if (target._tail):
            myGenerator.addText(''.join([unicode(token) for token in target._tail]))
        myGenerator.addText(unicode(target._semicolon))

        if (generator):
            generator.addGenerator(myGenerator)
            if (self != target):
                generator.addText(target._trailingSpace)
            generator.addText(self._trailingSpace)
            return self
        return myGenerator.markup(marker)



class Const(Construct):    # "const" ConstType identifier "=" ConstValue ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'const')):
            if (ConstType.peek(tokens)):
                token = tokens.peek()
                if (token and token.isIdentifier()):
                    if (Symbol.peek(tokens, '=')):
                        return tokens.popPosition(ConstValue.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, False, parser = parser)
        self._const = Symbol(tokens, 'const')
        self.type = ConstType(tokens)
        self.name = tokens.next().text
        self._equals = Symbol(tokens, '=')
        self.value = ConstValue(tokens)
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'const'

    @property
    def methodName(self):
        return None

    @property
    def methodNames(self):
        return []

    @property
    def complexityFactor(self):
        return 0

    def _unicode(self):
        return unicode(self._const) + unicode(self.type) + self.name + unicode(self._equals) + unicode(self.value)

    def _markup(self, generator):
        self._const.markup(generator)
        generator.addType(self.type)
        generator.addName(self.name)
        generator.addText(self._equals)
        self.value.markup(generator)
        return self

    def __repr__(self):
        return ('[const: ' + repr(self.type) +
                '[name: ' + self.name + '] = [value: ' + unicode(self.value) + ']]')


class Enum(Construct):    # [ExtendedAttributes] "enum" identifier "{" EnumValueList "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('enum')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                token = tokens.peek()
                if (token and token.isSymbol('{')):
                    if (EnumValueList.peek(tokens)):
                        token = tokens.peek()
                        return tokens.popPosition(token and token.isSymbol('}'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._enum = Symbol(tokens, 'enum')
        self.name = tokens.next().text
        self._openBrace = Symbol(tokens, '{')
        self.values = EnumValueList(tokens)
        self._closeBrace = Symbol(tokens, '}')
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'enum'

    def _unicode(self):
        return Construct._unicode(self) + unicode(self._enum) + self.name + unicode(self._openBrace) + unicode(self.values) + unicode(self._closeBrace)

    def _markup(self, generator):
        self._enum.markup(generator)
        generator.addName(self.name)
        generator.addText(self._openBrace)
        self.values.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        return ('[enum: ' + Construct.__repr__(self) + '[name: ' + self.name + '] ' +
                '[values: ' + repr(self.values) + ']]')


class Typedef(Construct):    # [ExtendedAttributes] "typedef" TypeWithExtendedAttributes identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'typedef')):
            if (TypeWithExtendedAttributes.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._typedef = Symbol(tokens, 'typedef')
        self.type = TypeWithExtendedAttributes(tokens)
        self.name = tokens.next().text
        self._consumeSemicolon(tokens)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'typedef'

    def _unicode(self):
        output = Construct._unicode(self) + unicode(self._typedef)
        return output + unicode(self.type) + unicode(self.name)

    def _markup(self, generator):
        self._typedef.markup(generator)
        generator.addType(self.type)
        generator.addName(self.name)
        return self

    def __repr__(self):
        output = '[typedef: ' + Construct.__repr__(self)
        return output + repr(self.type) + ' [name: ' + self.name + ']]'


class Argument(Construct):    # [ExtendedAttributeList] "optional" [IgnoreInOut] TypeWithExtendedAttributes ArgumentName [Default] |
                              # [ExtendedAttributeList] [IgnoreInOut] Type ["..."] ArgumentName
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        IgnoreInOut.peek(tokens)
        if (Type.peek(tokens)):
            Symbol.peek(tokens, '...')
            return tokens.popPosition(ArgumentName.peek(tokens))
        else:
            if (Symbol.peek(tokens, 'optional')):
                IgnoreInOut.peek(tokens)
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (ArgumentName.peek(tokens)):
                        Default.peek(tokens)
                        return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        if (Symbol.peek(tokens, 'optional')):
            self.optional = Symbol(tokens, 'optional')
            self._ignore = IgnoreInOut(tokens) if (IgnoreInOut.peek(tokens)) else None
            self.type = TypeWithExtendedAttributes(tokens)
            self.variadic = None
            self._name = ArgumentName(tokens)
            self.default = Default(tokens) if (Default.peek(tokens)) else None
        else:
            self.optional = None
            self._ignore = IgnoreInOut(tokens) if (IgnoreInOut.peek(tokens)) else None
            self.type = Type(tokens)
            self.variadic = Symbol(tokens, '...') if (Symbol.peek(tokens, '...')) else None
            self._name = ArgumentName(tokens)
            self.default = None
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'argument'

    @property
    def name(self):
        return self._name.name

    @property
    def required(self):
        return ((self.optional is None) and (self.variadic is None))

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.optional) if (self.optional) else ''
        output += unicode(self._ignore) if (self._ignore) else ''
        output += unicode(self.type)
        output += unicode(self.variadic) if (self.variadic) else ''
        return output + unicode(self._name) + (unicode(self.default) if (self.default) else '')

    def _markup(self, generator):
        if (self.optional):
            self.optional.markup(generator)
        if (self._ignore):
            self._ignore.markup(generator)
        generator.addType(self.type)
        generator.addText(self.variadic)
        self._name.markup(generator)
        if (self.default):
            self.default.markup(generator)
        return self

    def __repr__(self):
        output = '[argument: ' + Construct.__repr__(self)
        output += '[optional] ' if (self.optional) else ''
        output += '[type: ' + unicode(self.type) + ']'
        output += '[...] ' if (self.variadic) else ' '
        output += '[name: ' + unicode(self.name) + ']'
        return output + ((' [default: ' + repr(self.default) + ']]') if (self.default) else ']')


class InterfaceMember(Construct):  # [ExtendedAttributes] Constructor | Const | Operation | SpecialOperation | Stringifier | StaticMember | AsyncIterable | Iterable | Attribute | Maplike | Setlike
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        return tokens.popPosition(Constructor.peek(tokens) or Const.peek(tokens) or
                                  Stringifier.peek(tokens) or StaticMember.peek(tokens) or
                                  AsyncIterable.peek(tokens) or Iterable.peek(tokens) or
                                  Maplike.peek(tokens) or Setlike.peek(tokens) or
                                  Attribute.peek(tokens) or
                                  SpecialOperation.peek(tokens) or Operation.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        if (Constructor.peek(tokens)):
            self.member = Constructor(tokens, parent)
        elif (Const.peek(tokens)):
            self.member = Const(tokens, parent)
        elif (Stringifier.peek(tokens)):
            self.member = Stringifier(tokens, parent)
        elif (StaticMember.peek(tokens)):
            self.member = StaticMember(tokens, parent)
        elif (AsyncIterable.peek(tokens)):
            self.member = AsyncIterable(tokens, parent)
        elif (Iterable.peek(tokens)):
            self.member = Iterable(tokens, parent)
        elif (Maplike.peek(tokens)):
            self.member = Maplike(tokens, parent)
        elif (Setlike.peek(tokens)):
            self.member = Setlike(tokens, parent)
        elif (Attribute.peek(tokens)):
            self.member = Attribute(tokens, parent)
        elif (SpecialOperation.peek(tokens)):
            self.member = SpecialOperation(tokens, parent)
        else:
            self.member = Operation(tokens, parent)
        self._didParse(tokens)

    @property
    def idlType(self):
        return self.member.idlType

    @property
    def name(self):
        return self.member.name

    @property
    def methodName(self):
        return self.member.methodName

    @property
    def methodNames(self):
        return self.member.methodNames

    @property
    def normalName(self):
        return self.methodName if (self.methodName) else self.name

    @property
    def arguments(self):
        return self.member.arguments

    def findArgument(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            for argument in self.member.arguments:
                if (name == argument.name):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            return [argument for argument in self.member.arguments if (name == argument.name)]
        return []

    def matchesArgumentNames(self, argumentNames):
        if (self.arguments):
            return self.arguments.matchesNames(argumentNames)
        return (not argumentNames)

    def _unicode(self):
        return Construct._unicode(self) + unicode(self.member)

    def _markup(self, generator):
        return self.member._markup(generator)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + repr(self.member) + ']'


class MixinMember(Construct): # [ExtendedAttributes] Const | Operation | Stringifier | ReadOnly AttributeRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        return tokens.popPosition(Const.peek(tokens) or Stringifier.peek(tokens) or
                                  MixinAttribute.peek(tokens) or Operation.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        if (Const.peek(tokens)):
            self.member = Const(tokens, parent)
        elif (Stringifier.peek(tokens)):
            self.member = Stringifier(tokens, parent)
        elif (MixinAttribute.peek(tokens)):
            self.member = MixinAttribute(tokens, parent)
        else:
            self.member = Operation(tokens, parent)
        self._didParse(tokens)

    @property
    def idlType(self):
        return self.member.idlType

    @property
    def name(self):
        return self.member.name

    @property
    def methodName(self):
        return self.member.methodName

    @property
    def methodNames(self):
        return self.member.methodNames

    @property
    def normalName(self):
        return self.methodName if (self.methodName) else self.name

    @property
    def arguments(self):
        return self.member.arguments

    def findArgument(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            for argument in self.member.arguments:
                if (name == argument.name):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            return [argument for argument in self.member.arguments if (name == argument.name)]
        return []

    def matchesArgumentNames(self, argumentNames):
        if (self.arguments):
            return self.arguments.matchesNames(argumentNames)
        return (not argumentNames)

    def _unicode(self):
        return Construct._unicode(self) + unicode(self.member)

    def _markup(self, generator):
        return self.member._markup(generator)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + repr(self.member) + ']'


class SyntaxError(Construct):   # ... ";" | ... "}"
    def __init__(self, tokens, parent, parser = None):
        Construct.__init__(self, tokens, parent, False, parser = parser)
        self.tokens = tokens.syntaxError((';', '}'), False)
        if ((1 < len(self.tokens)) and self.tokens[-1].isSymbol('}')):
            tokens.restore(self.tokens[-1])
            self.tokens = self.tokens[:-1]
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'unknown'

    @property
    def name(self):
        return None

    @property
    def required(self):
        return False

    def _unicode(self):
        return ''.join([unicode(token) for token in self.tokens])

    def __repr__(self):
        output = '[unknown: ' + Construct.__repr__(self) + ' tokens: '
        return output + ''.join([repr(token) for token in self.tokens]) + ']'


class Interface(Construct):    # [ExtendedAttributes] ["partial"] "interface" identifier [Inheritance] "{" [InterfaceMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'interface')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._interface = Symbol(tokens, 'interface')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = self.constructors
        self._closeBrace = None
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (InterfaceMember.peek(tokens)):
                self.members.append(InterfaceMember(tokens, parent if (parent) else self))
            else:
                self.members.append(SyntaxError(tokens, parent if (parent) else self))
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'interface'

    @property
    def complexityFactor(self):
        return len(self.members) + 1

    def __len__(self):
        return len(self.members)

    def keys(self):
        return [member.name for member in self.members]

    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return member
            return None
        return self.members[key]

    def __iter__(self):
        return iter(self.members)

    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return True
            return False
        return (key in self.members)

    def findMember(self, name):
        for member in reversed(self.members):
            if (name == member.name):
                return member
        return None

    def findMembers(self, name):
        return [member for member in self.members if (name == member.name)]

    def findMethod(self, name, argumentNames=None):
        for member in reversed(self.members):
            if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames))):
                return member
        return None

    def findMethods(self, name, argumentNames=None):
        return [member for member in self.members if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames)))]

    def findArgument(self, name, searchMembers = True):
        if (searchMembers):
            for member in reversed(self.members):
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        result = []
        if (searchMembers):
            for member in self.members:
                result += member.findArguments(name)
        return result

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.partial) if (self.partial) else ''
        output += unicode(self._interface) + self.name
        output += unicode(self.inheritance) if (self.inheritance) else ''
        output += unicode(self._openBrace)
        for member in self.members:
            if ('constructor' != member.idlType):
                output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._interface.markup(generator)
        generator.addName(self.name)
        if (self.inheritance):
            self.inheritance.markup(generator)
        generator.addText(self._openBrace)
        for member in self.members:
            if ('constructor' != member.idlType):
                member.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        output = '[interface: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + self.name.encode('ascii', 'replace') + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class Mixin(Construct):    # [ExtendedAttributes] ["partial"] "interface" "mixin" identifier [Inheritance] "{" [MixinMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'interface') and Symbol.peek(tokens, 'mixin')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._interface = Symbol(tokens, 'interface')
        self._mixin = Symbol(tokens, 'mixin')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = self.constructors
        self._closeBrace = None
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (MixinMember.peek(tokens)):
                self.members.append(MixinMember(tokens, parent if (parent) else self))
            else:
                self.members.append(SyntaxError(tokens, parent if (parent) else self))
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'interface'

    @property
    def complexityFactor(self):
        return len(self.members) + 1

    def __len__(self):
        return len(self.members)

    def keys(self):
        return [member.name for member in self.members]

    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return member
            return None
        return self.members[key]

    def __iter__(self):
        return iter(self.members)

    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return True
            return False
        return (key in self.members)

    def findMember(self, name):
        for member in reversed(self.members):
            if (name == member.name):
                return member
        return None

    def findMembers(self, name):
        return [member for member in self.members if (name == member.name)]

    def findMethod(self, name, argumentNames=None):
        for member in reversed(self.members):
            if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames))):
                return member
        return None

    def findMethods(self, name, argumentNames=None):
        return [member for member in self.members if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames)))]

    def findArgument(self, name, searchMembers = True):
        if (searchMembers):
            for member in reversed(self.members):
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        result = []
        if (searchMembers):
            for member in self.members:
                result += member.findArguments(name)
        return result

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.partial) if (self.partial) else ''
        output += unicode(self._interface) + unicode(self._mixin) + self.name
        output += unicode(self.inheritance) if (self.inheritance) else ''
        output += unicode(self._openBrace)
        for member in self.members:
            if ('constructor' != member.idlType):
                output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._interface.markup(generator)
        self._mixin.markup(generator)
        generator.addName(self.name)
        if (self.inheritance):
            self.inheritance.markup(generator)
        generator.addText(self._openBrace)
        for member in self.members:
            if ('constructor' != member.idlType):
                member.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        output = '[interface: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[mixin] '
        output += '[name: ' + self.name.encode('ascii', 'replace') + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class NamespaceMember(Construct): # [ExtendedAttributes] Operation | "readonly" Attribute
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'readonly')):
            return tokens.popPosition(Attribute.peek(tokens))
        return tokens.popPosition(Operation.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        token = tokens.sneakPeek()
        if (token.isSymbol('readonly')):
            self.member = Attribute(tokens, parent)
        else:
            self.member = Operation(tokens, parent)
        self._didParse(tokens)

    @property
    def idlType(self):
        return self.member.idlType

    @property
    def name(self):
        return self.member.name

    @property
    def methodName(self):
        return self.member.methodName

    @property
    def methodNames(self):
        return self.member.methodNames

    @property
    def normalName(self):
        return self.methodName if (self.methodName) else self.name

    @property
    def arguments(self):
        return self.member.arguments

    def findArgument(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            for argument in self.member.arguments:
                if (name == argument.name):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            return [argument for argument in self.member.arguments if (name == argument.name)]
        return []

    def matchesArgumentNames(self, argumentNames):
        if (self.arguments):
            return self.arguments.matchesNames(argumentNames)
        return (not argumentNames)

    def _unicode(self):
        return Construct._unicode(self) + unicode(self.member)

    def _markup(self, generator):
        return self.member._markup(generator)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + repr(self.member) + ']'



class Namespace(Construct):    # [ExtendedAttributes] ["partial"] "namespace" identifier "{" [NamespaceMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'namespace')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._namespace = Symbol(tokens, 'namespace')
        self.name = tokens.next().text
        self._openBrace = Symbol(tokens, '{')
        self.members = []
        self._closeBrace = None
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (NamespaceMember.peek(tokens)):
                self.members.append(NamespaceMember(tokens, parent if (parent) else self))
            else:
                self.members.append(SyntaxError(tokens, parent if (parent) else self))
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'namespace'

    @property
    def complexityFactor(self):
        return len(self.members) + 1

    def __len__(self):
        return len(self.members)

    def keys(self):
        return [member.name for member in self.members]

    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return member
            return None
        return self.members[key]

    def __iter__(self):
        return iter(self.members)

    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return True
            return False
        return (key in self.members)

    def findMember(self, name):
        for member in reversed(self.members):
            if (name == member.name):
                return member
        return None

    def findMembers(self, name):
        return [member for member in self.members if (name == member.name)]

    def findMethod(self, name, argumentNames=None):
        for member in reversed(self.members):
            if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames))):
                return member
        return None

    def findMethods(self, name, argumentNames=None):
        return [member for member in self.members if (('method' == member.idlType) and (name == member.name)
                    and ((argumentNames is None) or member.matchesArgumentNames(argumentNames)))]

    def findArgument(self, name, searchMembers = True):
        if (searchMembers):
            for member in reversed(self.members):
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        result = []
        if (searchMembers):
            for member in self.members:
                result += member.findArguments(name)
        return result

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.partial) if (self.partial) else ''
        output += unicode(self._namespace) + self.name
        output += unicode(self._openBrace)
        for member in self.members:
            output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._namespace.markup(generator)
        generator.addName(self.name)
        generator.addText(self._openBrace)
        for member in self.members:
            member.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        output = '[namespace: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + self.name.encode('ascii', 'replace') + '] '
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class DictionaryMember(Construct): # [ExtendedAttributes] ["required"] TypeWithExtendedAttributes identifier [Default] ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        Symbol.peek(tokens, 'required')
        if (TypeWithExtendedAttributes.peek(tokens)):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Default.peek(tokens)
                return tokens.popPosition(True)
        tokens.popPosition(False)

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.required = Symbol(tokens, 'required') if (Symbol.peek(tokens, 'required')) else None
        self.type = TypeWithExtendedAttributes(tokens)
        self.name = tokens.next().text
        self.default = Default(tokens) if (Default.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'dict-member'

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.required) if (self.required) else ''
        output += unicode(self.type) + unicode(self.name)
        return output + (unicode(self.default) if (self.default) else '')

    def _markup(self, generator):
        if (self.required):
            self.required.markup(generator)
        generator.addType(self.type)
        generator.addName(self.name)
        if (self.default):
            self.default.markup(generator)
        return self

    def __repr__(self):
        output = '[dict-member: ' + Construct.__repr__(self)
        output += '[required] ' if (self.required) else ''
        output += repr(self.type)
        output += ' [name: ' + self.name.encode('ascii', 'replace') + ']'
        if (self.default):
            output += ' = [default: ' + repr(self.default) + ']'
        output += ']'
        return output


class Dictionary(Construct):  # [ExtendedAttributes] ["partial"] "dictionary" identifier [Inheritance] "{" [DictionaryMember]... "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'dictionary')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._dictionary = Symbol(tokens, 'dictionary')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = []
        self._closeBrace = None
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (DictionaryMember.peek(tokens)):
                self.members.append(DictionaryMember(tokens, self))
            else:
                self.members.append(SyntaxError(tokens, self))
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'dictionary'

    @property
    def complexityFactor(self):
        return len(self.members) + 1

    @property
    def required(self):
        for member in self.members:
            if (member.required):
                return True
        return False

    def __len__(self):
        return len(self.members)

    def keys(self):
        return [member.name for member in self.members]

    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return member
            return None
        return self.members[key]

    def __iter__(self):
        return iter(self.members)

    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for member in self.members:
                if (key == member.name):
                    return True
            return False
        return (key in self.members)

    def findMember(self, name):
        for member in reversed(self.members):
            if (name == member.name):
                return member
        return None

    def findMembers(self, name):
        return [member for member in self.members if (name == member.name)]

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.partial) if (self.partial) else ''
        output += unicode(self._dictionary) + self.name
        output += unicode(self.inheritance) if (self.inheritance) else ''
        output += unicode(self._openBrace)
        for member in self.members:
            output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._dictionary.markup(generator)
        generator.addName(self.name)
        if (self.inheritance):
            self.inheritance.markup(generator)
        generator.addText(self._openBrace)
        for member in self.members:
            member.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        output = '[dictionary: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + self.name.encode('ascii', 'replace') + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class Callback(Construct):    # [ExtendedAttributes] "callback" identifier "=" ReturnType "(" [ArgumentList] ")" ";" |
                              # [ExtendedAttributes] "callback" Interface
                              # [ExtendedAttributes] "callback" Mixin
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'callback')):
            if (Mixin.peek(tokens, False)):
                return tokens.popPosition(True)
            if (Interface.peek(tokens, False)):
                return tokens.popPosition(True)
            token = tokens.peek()
            if (token and token.isIdentifier()):
                if (Symbol.peek(tokens, '=')):
                    if (ReturnType.peek(tokens)):
                        if (Symbol.peek(tokens, '(')):
                            ArgumentList.peek(tokens)
                            token = tokens.peek()
                            return tokens.popPosition(token and token.isSymbol(')'))
        tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._callback = Symbol(tokens, 'callback')
        token = tokens.sneakPeek()
        if (token.isIdentifier()):
            self.name = tokens.next().text
            self._equals = Symbol(tokens, '=')
            self.returnType = ReturnType(tokens)
            self._openParen = Symbol(tokens, '(')
            self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
            self._closeParen = Symbol(tokens, ')')
            self.interface = None
            self._consumeSemicolon(tokens)
        else:
            self._equals = None
            self.returnType = None
            self._openParen = None
            self.arguments = None
            self._closeParen = None
            if (Mixin.peek(tokens, False)):
                self.interface = Mixin(tokens, self)
            else:
                self.interface = Interface(tokens, self)
            self.name = self.interface.name
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'callback'

    @property
    def complexityFactor(self):
        return self.interface.complexityFactor if (self.interface) else 1

    def __len__(self):
        return len(self.interface.members) if (self.interface) else 0

    def keys(self):
        return [member.name for member in self.interface.members] if (self.interface) else []

    def __getitem__(self, key):
        if (self.interface):
            if (isinstance(key, basestring)):
                for member in self.interface.members:
                    if (key == member.name):
                        return member
                return None
            return self.members[key]
        return None

    def __iter__(self):
        if (self.interface):
            return iter(self.interface.members)
        return iter(())

    def __contains__(self, key):
        if (self.interface):
            if (isinstance(key, basestring)):
                for member in self.interface.members:
                    if (key == member.name):
                        return True
                return False
            return (key in self.interface.members)
        return False

    def findMember(self, name):
        if (self.interface):
            for member in reversed(self.interface.members):
                if (name == member.name):
                    return member
        return None

    def findMembers(self, name):
        if (self.interface):
            return [member for member in self.interface.members if (name == member.name)]
        return []

    def findArgument(self, name, searchMembers = True):
        if (self.arguments):
            for argument in self.arguments:
                if (name == argument.name):
                    return argument
        if (self.interface and searchMembers):
            for member in reversed(self.interface.members):
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        result = []
        if (self.arguments):
            result = [argument for argument in self.arguments if (name == argument.name)]
        if (self.interface and searchMembers):
            for member in self.interface.members:
                result += member.findArguments(name)
        return result

    def _unicode(self):
        output = Construct._unicode(self) + unicode(self._callback)
        if (self.interface):
            return output + unicode(self.interface)
        output += self.name + unicode(self._equals) + unicode(self.returnType)
        return output + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        self._callback.markup(generator)
        if (self.interface):
            return self.interface._markup(generator)
        generator.addName(self.name)
        generator.addText(self._equals)
        self.returnType.markup(generator)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        output = '[callback: ' + Construct.__repr__(self)
        if (self.interface):
            return output + repr(self.interface) + ']'
        output += '[name: ' + self.name.encode('ascii', 'replace') + '] [returnType: ' + unicode(self.returnType) + '] '
        return output + '[argumentlist: ' + (repr(self.arguments) if (self.arguments) else '') + ']]'


class ImplementsStatement(Construct):  # [ExtendedAttributes] identifier "implements" identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, 'implements')):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self.name = tokens.next().text
        self._implements = Symbol(tokens, 'implements')
        self.implements = tokens.next().text
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'implements'

    def _unicode(self):
        return Construct._unicode(self) + self.name + unicode(self._implements) + self.implements

    def _markup(self, generator):
        generator.addTypeName(self.name)
        self._implements.markup(generator)
        generator.addTypeName(self.implements)
        return self

    def __repr__(self):
        return '[implements: ' + Construct.__repr__(self) + '[name: ' + self.name.encode('ascii', 'replace') + '] [implements: ' + self.implements + ']]'


class IncludesStatement(Construct):  # identifier "includes" identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        token = tokens.peek()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, 'includes')):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self.name = tokens.next().text
        self._includes = Symbol(tokens, 'includes')
        self.includes = tokens.next().text
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'includes'

    def _unicode(self):
        return Construct._unicode(self) + self.name + unicode(self._includes) + self.includes

    def _markup(self, generator):
        generator.addTypeName(self.name)
        self._includes.markup(generator)
        generator.addTypeName(self.includes)
        return self

    def __repr__(self):
        return '[includes: ' + Construct.__repr__(self) + '[name: ' + self.name.encode('ascii', 'replace') + '] [includes: ' + self.includes + ']]'


class ExtendedAttributeUnknown(Construct): # list of tokens
    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        skipped = tokens.seekSymbol((',', ']'))
        self.tokens = skipped[:-1]
        tokens.restore(skipped[-1])
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'extended-attribute'

    @property
    def name(self):
        return None

    def _unicode(self):
        return ''.join([unicode(token) for token in self.tokens])

    def __repr__(self):
        return '[ExtendedAttribute: ' + ''.join([repr(token) for token in self.tokens]) + ']'


class ExtendedAttributeNoArgs(Construct):   # identifier
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            token = tokens.sneakPeek()
            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('Constructor' == self.attribute) else 'extended-attribute'

    @property
    def name(self):
        return self.parent.name if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.parent.name + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return self.attribute

    def _markup(self, generator):
        generator.addName(self.attribute)
        return self

    def __repr__(self):
        return '[ExtendedAttributeNoArgs: ' + self.attribute.encode('ascii', 'replace') + ']'


class ExtendedAttributeArgList(Construct):  # identifier "(" [ArgumentList] ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '(')):
                ArgumentList.peek(tokens)
                if (Symbol.peek(tokens, ')')):
                    token = tokens.sneakPeek()
                    return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('Constructor' == self.attribute) else 'extended-attribute'

    @property
    def name(self):
        return self.parent.name if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        if ('constructor' == self.idlType):
            return self.parent.name + '(' + (', '.join(argument.name for argument in self.arguments) if (self.arguments) else '') + ')'
        return self.attribute

    def _unicode(self):
        return self.attribute + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        generator.addName(self.attribute)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeArgList: ' + self.attribute.encode('ascii', 'replace') +
                ' [arguments: ' + (repr(self.arguments) if (self.arguments) else '') + ']]')


class ExtendedAttributeIdent(Construct):    # identifier "=" identifier
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '=')):
                token = tokens.peek()
                if (token and token.isIdentifier()):
                    token = tokens.sneakPeek()
                    return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._equals = Symbol(tokens, '=')
        self.value = tokens.next().text
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.value + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return self.attribute + unicode(self._equals) + self.value

    def _markup(self, generator):
        generator.addName(self.attribute)
        generator.addText(self._equals)
        generator.addTypeName(self.value)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeIdent: ' + self.attribute.encode('ascii', 'replace') + ' [value: ' + self.value + ']]')


class ExtendedAttributeIdentList(Construct):    # identifier "=" "(" identifier [Identifiers] ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '=')):
                if (Symbol.peek(tokens, '(')):
                    token = tokens.peek()
                    if (token and token.isIdentifier()):
                        Identifiers.peek(tokens)
                        if (Symbol.peek(tokens, ')')):
                            token = tokens.sneakPeek()
                            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._equals = Symbol(tokens, '=')
        self._openParen = Symbol(tokens, '(')
        self.value = tokens.next().text
        self.next = Identifiers(tokens) if (Identifiers.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.value + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return (self.attribute + unicode(self._equals) + unicode(self._openParen) + self.value +
                (unicode(self.next) if (self.next) else '') + unicode(self._closeParen))

    def _markup(self, generator):
        generator.addName(self.attribute)
        generator.addText(self._equals)
        generator.addText(self._openParen)
        generator.addTypeName(self.value)
        next = self.next
        while (next):
            generator.addText(next._comma)
            generator.addTypeName(next.name)
            next = next.next
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeIdentList: ' + self.attribute.encode('ascii', 'replace') + ' [value: ' + self.value + ']' +
                (repr(self.next) if (self.next) else '') + ']')


class ExtendedAttributeNamedArgList(Construct): # identifier "=" identifier "(" [ArgumentList] ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '=')):
                token = tokens.peek()
                if (token and token.isIdentifier()):
                    if (Symbol.peek(tokens, '(')):
                        ArgumentList.peek(tokens)
                        if (Symbol.peek(tokens, ')')):
                            token = tokens.sneakPeek()
                            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._equals = Symbol(tokens, '=')
        self.value = tokens.next().text
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        if ('constructor' == self.idlType):
            return self.value + '(' + (', '.join(argument.name for argument in self.arguments) if (self.arguments) else '') + ')'
        return self.attribute

    def _unicode(self):
        output = self.attribute + unicode(self._equals) + self.value
        return output + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        generator.addName(self.attribute)
        generator.addText(self._equals)
        generator.addTypeName(self.value)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeNamedArgList: ' + self.attribute.encode('ascii', 'replace') + ' [value: ' + self.value + ']' +
                ' [arguments: ' + (repr(self.arguments) if (self.arguments) else '') + ']]')


class ExtendedAttributeTypePair(Construct): # identifier "(" Type "," Type ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '(')):
                if (Type.peek(tokens)):
                    if (Symbol.peek(tokens, ',')):
                        if (Type.peek(tokens)):
                            if (Symbol.peek(tokens, ')')):
                                token = tokens.sneakPeek()
                                return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.attribute = tokens.next().text
        self._openParen = Symbol(tokens, '(')
        self.keyType = Type(tokens)
        self._comma = Symbol(tokens, ',')
        self.valueType = Type(tokens)
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'extended-attribute'

    @property
    def name(self):
        return self.attribute

    def _unicode(self):
        output = self.attribute + unicode(self._openParen) + unicode(self.keyType) + unicode(self._comma)
        return output + unicode(self.valueType) + unicode(self._closeParen)

    def _markup(self, generator):
        generator.addName(self.attribute)
        generator.addText(self._openParen)
        self.keyType.markup(generator)
        generator.addText(self._comma)
        self.valueType.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeTypePair: ' + self.attribute.encode('ascii', 'replace') + ' ' +
                repr(self.keyType) + ' ' + repr(self.valueType) + ']')


class ExtendedAttribute(Construct): # ExtendedAttributeNoArgs | ExtendedAttributeArgList |
                                    # ExtendedAttributeIdent | ExtendedAttributeNamedArgList |
                                    # ExtendedAttributeIdentList | ExtendedAttributeTypePair
    @classmethod
    def peek(cls, tokens):
        return (ExtendedAttributeNamedArgList.peek(tokens) or
                ExtendedAttributeArgList.peek(tokens) or
                ExtendedAttributeNoArgs.peek(tokens) or
                ExtendedAttributeTypePair.peek(tokens) or
                ExtendedAttributeIdentList(tokens) or
                ExtendedAttributeIdent.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        if (ExtendedAttributeNamedArgList.peek(tokens)):
            self.attribute = ExtendedAttributeNamedArgList(tokens, parent)
        elif (ExtendedAttributeArgList.peek(tokens)):
            self.attribute = ExtendedAttributeArgList(tokens, parent)
        elif (ExtendedAttributeNoArgs.peek(tokens)):
            self.attribute = ExtendedAttributeNoArgs(tokens, parent)
        elif (ExtendedAttributeTypePair.peek(tokens)):
            self.attribute = ExtendedAttributeTypePair(tokens, parent)
        elif (ExtendedAttributeIdentList.peek(tokens)):
            self.attribute = ExtendedAttributeIdentList(tokens, parent)
        elif (ExtendedAttributeIdent.peek(tokens)):
            self.attribute = ExtendedAttributeIdent(tokens, parent)
        else:
            self.attribute = ExtendedAttributeUnknown(tokens, parent)
        self._didParse(tokens)

    @property
    def idlType(self):
        return self.attribute.idlType

    @property
    def name(self):
        return self.attribute.name

    @property
    def normalName(self):
        return self.attribute.normalName

    @property
    def arguments(self):
        if (hasattr(self.attribute, 'arguments')):
            return self.attribute.arguments
        return None

    def findArgument(self, name, searchMembers = True):
        if (hasattr(self.attribute, 'arguments') and self.attribute.arguments):
            for argument in self.attribute.arguments:
                if (name == argument.name):
                    return argument
        return None

    def findArguments(self, name, searchMembers = True):
        if (hasattr(self.attribute, 'arguments') and self.attribute.arguments):
            return [argument for argument in self.attribute.arguments if (name == argument.name)]
        return []

    def matchesArgumentNames(self, argumentNames):
        if (self.arguments):
            return self.arguments.matchesNames(argumentNames)
        return (not argumentNames)

    def _unicode(self):
        return unicode(self.attribute)

    def _markup(self, generator):
        return self.attribute._markup(generator)

    def __repr__(self):
        return repr(self.attribute)




