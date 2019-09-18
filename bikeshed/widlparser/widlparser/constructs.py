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



class Const(Construct):    # "const" ConstType Identifier "=" ConstValue ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'const')):
            if (ConstType.peek(tokens)):
                if (Identifier.peek(tokens)):
                    if (Symbol.peek(tokens, '=')):
                        return tokens.popPosition(ConstValue.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, False, parser = parser)
        self._const = Symbol(tokens, 'const')
        self.type = ConstType(tokens)
        self._name = Identifier(tokens)
        self._equals = Symbol(tokens, '=')
        self.value = ConstValue(tokens)
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'const'

    @property
    def name(self):
        return self._name.name

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
        return unicode(self._const) + unicode(self.type) + unicode(self._name) + unicode(self._equals) + unicode(self.value)

    def _markup(self, generator):
        self._const.markup(generator)
        generator.addType(self.type)
        self._name.markup(generator)
        generator.addText(self._equals)
        self.value.markup(generator)
        return self

    def __repr__(self):
        return ('[const: ' + repr(self.type) +
                '[name: ' + repr(self._name) + '] = [value: ' + unicode(self.value) + ']]')


class Enum(Construct):    # [ExtendedAttributes] "enum" Identifier "{" EnumValueList "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('enum')):
            if (Identifier.peek(tokens)):
                token = tokens.peek()
                if (token and token.isSymbol('{')):
                    if (EnumValueList.peek(tokens)):
                        token = tokens.peek()
                        return tokens.popPosition(token and token.isSymbol('}'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._enum = Symbol(tokens, 'enum')
        self._name = Identifier(tokens)
        self._openBrace = Symbol(tokens, '{')
        self.values = EnumValueList(tokens)
        self._closeBrace = Symbol(tokens, '}')
        self._consumeSemicolon(tokens, False)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'enum'

    @property
    def name(self):
        return self._name.name

    def _unicode(self):
        return Construct._unicode(self) + unicode(self._enum) + unicode(self._name) + unicode(self._openBrace) + unicode(self.values) + unicode(self._closeBrace)

    def _markup(self, generator):
        self._enum.markup(generator)
        self._name.markup(generator)
        generator.addText(self._openBrace)
        self.values.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        return ('[enum: ' + Construct.__repr__(self) + '[name: ' + repr(self._name) + '] ' +
                '[values: ' + repr(self.values) + ']]')


class Typedef(Construct):    # [ExtendedAttributes] "typedef" TypeWithExtendedAttributes Identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'typedef')):
            if (TypeWithExtendedAttributes.peek(tokens)):
                return tokens.popPosition(Identifier.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._typedef = Symbol(tokens, 'typedef')
        self.type = TypeWithExtendedAttributes(tokens)
        self._name = Identifier(tokens)
        self._consumeSemicolon(tokens)
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'typedef'

    @property
    def name(self):
        return self._name.name

    def _unicode(self):
        output = Construct._unicode(self) + unicode(self._typedef)
        return output + unicode(self.type) + unicode(self._name)

    def _markup(self, generator):
        self._typedef.markup(generator)
        generator.addType(self.type)
        self._name.markup(generator)
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
        output += '[name: ' + repr(self._name) + ']'
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


class Interface(Construct):    # [ExtendedAttributes] ["partial"] "interface" Identifier [Inheritance] "{" [InterfaceMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'interface')):
            if (Identifier.peek(tokens)):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._interface = Symbol(tokens, 'interface')
        self._name = Identifier(tokens)
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
    def name(self):
        return self._name.name

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
        output += unicode(self._interface) + unicode(self._name)
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
        self._name.markup(generator)
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
        output += '[name: ' + repr(self._name) + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class Mixin(Construct):    # [ExtendedAttributes] ["partial"] "interface" "mixin" Identifier [Inheritance] "{" [MixinMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'interface') and Symbol.peek(tokens, 'mixin')):
            if (Identifier.peek(tokens)):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._interface = Symbol(tokens, 'interface')
        self._mixin = Symbol(tokens, 'mixin')
        self._name = Identifier(tokens)
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
    def name(self):
        return self._name.name

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
        output += unicode(self._interface) + unicode(self._mixin) + unicode(self._name)
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
        self._name.markup(generator)
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
        output += '[name: ' + repr(self._name) + '] '
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



class Namespace(Construct):    # [ExtendedAttributes] ["partial"] "namespace" Identifier "{" [NamespaceMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'namespace')):
            if (Identifier.peek(tokens)):
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, (not parent), parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._namespace = Symbol(tokens, 'namespace')
        self._name = Identifier(tokens)
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
    def name(self):
        return self._name.name

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
        output += unicode(self._namespace) + unicode(self._name)
        output += unicode(self._openBrace)
        for member in self.members:
            output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._namespace.markup(generator)
        self._name.markup(generator)
        generator.addText(self._openBrace)
        for member in self.members:
            member.markup(generator)
        generator.addText(self._closeBrace)
        return self

    def __repr__(self):
        output = '[namespace: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + repr(self._name) + '] '
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class DictionaryMember(Construct): # [ExtendedAttributes] ["required"] TypeWithExtendedAttributes Identifier [Default] ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        Symbol.peek(tokens, 'required')
        if (TypeWithExtendedAttributes.peek(tokens)):
            if (Identifier.peek(tokens)):
                Default.peek(tokens)
                return tokens.popPosition(True)
        tokens.popPosition(False)

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.required = Symbol(tokens, 'required') if (Symbol.peek(tokens, 'required')) else None
        self.type = TypeWithExtendedAttributes(tokens)
        self._name = Identifier(tokens)
        self.default = Default(tokens) if (Default.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'dict-member'

    @property
    def name(self):
        return self._name.name

    def _unicode(self):
        output = Construct._unicode(self)
        output += unicode(self.required) if (self.required) else ''
        output += unicode(self.type) + unicode(self._name)
        return output + (unicode(self.default) if (self.default) else '')

    def _markup(self, generator):
        if (self.required):
            self.required.markup(generator)
        generator.addType(self.type)
        self._name.markup(generator)
        if (self.default):
            self.default.markup(generator)
        return self

    def __repr__(self):
        output = '[dict-member: ' + Construct.__repr__(self)
        output += '[required] ' if (self.required) else ''
        output += repr(self.type)
        output += ' [name: ' + repr(self._name) + ']'
        if (self.default):
            output += ' = [default: ' + repr(self.default) + ']'
        output += ']'
        return output


class Dictionary(Construct):  # [ExtendedAttributes] ["partial"] "dictionary" Identifier [Inheritance] "{" [DictionaryMember]... "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        Symbol.peek(tokens, 'partial')
        if (Symbol.peek(tokens, 'dictionary')):
            if (Identifier.peek(tokens)):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._dictionary = Symbol(tokens, 'dictionary')
        self._name = Identifier(tokens)
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
    def name(self):
        return self._name.name

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
        output += unicode(self._dictionary) + unicode(self._name)
        output += unicode(self.inheritance) if (self.inheritance) else ''
        output += unicode(self._openBrace)
        for member in self.members:
            output += unicode(member)
        return output + unicode(self._closeBrace) if (self._closeBrace) else output

    def _markup(self, generator):
        if (self.partial):
            self.partial.markup(generator)
        self._dictionary.markup(generator)
        self._name.markup(generator)
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
        output += '[name: ' + repr(self._name) + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class Callback(Construct):    # [ExtendedAttributes] "callback" Identifier "=" ReturnType "(" [ArgumentList] ")" ";" |
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
            if (Identifier.peek(tokens)):
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
            self._name = Identifier(tokens)
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
            self._name = self.interface._name
        self._didParse(tokens)
        self.parser.addType(self)

    @property
    def idlType(self):
        return 'callback'

    @property
    def name(self):
        return self._name.name

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
        output += unicode(self._name) + unicode(self._equals) + unicode(self.returnType)
        return output + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        self._callback.markup(generator)
        if (self.interface):
            return self.interface._markup(generator)
        self._name.markup(generator)
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


class ImplementsStatement(Construct):  # [ExtendedAttributes] Identifier "implements" Identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (TypeIdentifier.peek(tokens)):
            if (Symbol.peek(tokens, 'implements')):
                return tokens.popPosition(TypeIdentifier.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._name = TypeIdentifier(tokens)
        self._implementsSymbol = Symbol(tokens, 'implements')
        self._implements = TypeIdentifier(tokens)
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'implements'

    @property
    def name(self):
        return self._name.name

    @property
    def implements(self):
        return self._implements.name

    def _unicode(self):
        return Construct._unicode(self) + unicode(self._name) + unicode(self._implementsSymbol) + unicode(self._implements)

    def _markup(self, generator):
        self._name.markup(generator)
        self._implementsSymbol.markup(generator)
        self._implements.markup(generator)
        return self

    def __repr__(self):
        return '[implements: ' + Construct.__repr__(self) + '[name: ' + repr(self._name) + '] [implements: ' + repr(self._implements) + ']]'


class IncludesStatement(Construct):  # Identifier "includes" Identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (TypeIdentifier.peek(tokens)):
            if (Symbol.peek(tokens, 'includes')):
                return tokens.popPosition(TypeIdentifier.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None, parser = None):
        Construct.__init__(self, tokens, parent, parser = parser)
        self._name = TypeIdentifier(tokens)
        self._includesSymbol = Symbol(tokens, 'includes')
        self._includes = TypeIdentifier(tokens)
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'includes'

    @property
    def name(self):
        return self._name.name

    @property
    def includes(self):
        return self._includes.name

    def _unicode(self):
        return Construct._unicode(self) + unicode(self._name) + unicode(self._includesSymbol) + unicode(self._includes)

    def _markup(self, generator):
        self._name.markup(generator)
        self._includesSymbol.markup(generator)
        self._includes.markup(generator)
        return self

    def __repr__(self):
        return '[includes: ' + Construct.__repr__(self) + '[name: ' + repr(self._name) + '] [includes: ' + repr(self._includes) + ']]'


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


class ExtendedAttributeNoArgs(Construct):   # Identifier
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
            token = tokens.sneakPeek()
            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self._attribute = Identifier(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('Constructor' == self.attribute) else 'extended-attribute'

    @property
    def attribute(self):
        return self._attribute.name

    @property
    def name(self):
        return self.parent.name if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.parent.name + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return unicode(self._attribute)

    def _markup(self, generator):
        self._attribute.markup(generator)
        return self

    def __repr__(self):
        return '[ExtendedAttributeNoArgs: ' + repr(self._attribute) + ']'


class ExtendedAttributeArgList(Construct):  # Identifier "(" [ArgumentList] ")"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
            if (Symbol.peek(tokens, '(')):
                ArgumentList.peek(tokens)
                if (Symbol.peek(tokens, ')')):
                    token = tokens.sneakPeek()
                    return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self._attribute = Identifier(tokens)
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('Constructor' == self.attribute) else 'extended-attribute'

    @property
    def attribute(self):
        return self._attribute.name

    @property
    def name(self):
        return self.parent.name if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        if ('constructor' == self.idlType):
            return self.parent.name + '(' + (', '.join(argument.name for argument in self.arguments) if (self.arguments) else '') + ')'
        return self.attribute

    def _unicode(self):
        return unicode(self._attribute) + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        self._attribute.markup(generator)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeArgList: ' + repr(self._attribute) +
                ' [arguments: ' + (repr(self.arguments) if (self.arguments) else '') + ']]')


class ExtendedAttributeIdent(Construct):    # Identifier "=" Identifier
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
            if (Symbol.peek(tokens, '=')):
                if (Identifier.peek(tokens)):
                    token = tokens.sneakPeek()
                    return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self._attribute = Identifier(tokens)
        self._equals = Symbol(tokens, '=')
        self._value = TypeIdentifier(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def attribute(self):
        return self._attribute.name

    @property
    def value(self):
        return self._value.name

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.value + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return unicode(self._attribute) + unicode(self._equals) + unicode(self._value)

    def _markup(self, generator):
        self._attribute.markup(generator)
        generator.addText(self._equals)
        self._value.markup(generator)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeIdent: ' + self.attribute.encode('ascii', 'replace') + ' [value: ' + repr(self._value) + ']]')


class ExtendedAttributeIdentList(Construct):    # Identifier "=" "(" Identifier [Identifiers] ")"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
            if (Symbol.peek(tokens, '=')):
                if (Symbol.peek(tokens, '(')):
                    if (TypeIdentifier.peek(tokens)):
                        TypeIdentifiers.peek(tokens)
                        if (Symbol.peek(tokens, ')')):
                            token = tokens.sneakPeek()
                            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self._attribute = Identifier(tokens)
        self._equals = Symbol(tokens, '=')
        self._openParen = Symbol(tokens, '(')
        self._value = TypeIdentifier(tokens)
        self.next = TypeIdentifiers(tokens) if (TypeIdentifiers.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def attribute(self):
        return self._attribute.name

    @property
    def value(self):
        return self._value.name

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        return (self.value + '()') if ('constructor' == self.idlType) else self.attribute

    def _unicode(self):
        return (unicode(self._attribute) + unicode(self._equals) + unicode(self._openParen) + unicode(self._value) +
                (unicode(self.next) if (self.next) else '') + unicode(self._closeParen))

    def _markup(self, generator):
        self._attribute.markup(generator)
        generator.addText(self._equals)
        generator.addText(self._openParen)
        self._value.markup(generator)
        next = self.next
        while (next):
            generator.addText(next._comma)
            next._name.markup(generator)
            next = next.next
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeIdentList: ' + self.attribute.encode('ascii', 'replace') + ' [value: ' + repr(self._value) + ']' +
                (repr(self.next) if (self.next) else '') + ']')


class ExtendedAttributeNamedArgList(Construct): # Identifier "=" Identifier "(" [ArgumentList] ")"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
            if (Symbol.peek(tokens, '=')):
                if (TypeIdentifier.peek(tokens)):
                    if (Symbol.peek(tokens, '(')):
                        ArgumentList.peek(tokens)
                        if (Symbol.peek(tokens, ')')):
                            token = tokens.sneakPeek()
                            return tokens.popPosition((not token) or token.isSymbol((',', ']')))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self._attribute = Identifier(tokens)
        self._equals = Symbol(tokens, '=')
        self._value = TypeIdentifier(tokens)
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'constructor' if ('NamedConstructor' == self.attribute) else 'extended-attribute'

    @property
    def attribute(self):
        return self._attribute.name

    @property
    def value(self):
        return self._value.name

    @property
    def name(self):
        return self.value if ('constructor' == self.idlType) else self.attribute

    @property
    def normalName(self):
        if ('constructor' == self.idlType):
            return self.value + '(' + (', '.join(argument.name for argument in self.arguments) if (self.arguments) else '') + ')'
        return self.attribute

    def _unicode(self):
        output = unicode(self._attribute) + unicode(self._equals) + unicode(self._value)
        return output + unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)

    def _markup(self, generator):
        self._attribute.markup(generator)
        generator.addText(self._equals)
        self._value.markup(generator)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeNamedArgList: ' + repr(self._attribute) + ' [value: ' + repr(self._value) + ']' +
                ' [arguments: ' + (repr(self.arguments) if (self.arguments) else '') + ']]')


class ExtendedAttributeTypePair(Construct): # Identifier "(" Type "," Type ")"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Identifier.peek(tokens)):
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
        self._attribute = Identifier(tokens)
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
    def attribute(self):
        return self._attribute.name

    @property
    def name(self):
        return self.attribute

    def _unicode(self):
        output = unicode(self._attribute) + unicode(self._openParen) + unicode(self.keyType) + unicode(self._comma)
        return output + unicode(self.valueType) + unicode(self._closeParen)

    def _markup(self, generator):
        self._attribute.markup(generator)
        generator.addText(self._openParen)
        self.keyType.markup(generator)
        generator.addText(self._comma)
        self.valueType.markup(generator)
        generator.addText(self._closeParen)
        return self

    def __repr__(self):
        return ('[ExtendedAttributeTypePair: ' + repr(self._attribute) + ' ' +
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




