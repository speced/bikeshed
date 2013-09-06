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


class Construct(ChildProduction):
    @classmethod
    def peek(cls, tokens):
        return ExtendedAttributeList.peek(tokens)

    def __init__(self, tokens, parent, parseExtendedAttributes = True):
        ChildProduction.__init__(self, tokens, parent)
        self.extendedAttributes = self._parseExtendedAttributes(tokens, self) if (parseExtendedAttributes) else None

    def _parseExtendedAttributes(self, tokens, parent):
        return ExtendedAttributeList(tokens, parent) if (ExtendedAttributeList.peek(tokens)) else None

    @property
    def idlType(self):
        assert(False)   # subclasses must override
        return None

    @property
    def constructors(self):
        return [attribute for attribute in self.extendedAttributes if ('constructor' == attribute.idlType)] if (self.extendedAttributes) else []
    
    def __nonzero__(self):
        return True
    
    def __len__(self):
        return 0
    
    def __getitem__(self, key):
        return None
    
    def __iter__(self):
        return iter(())

    def __contains__(self, key):
        return False

    def findMember(self, name):
        return None
    
    def findMethod(self, name):
        return None
    
    def findArgument(self, name, searchMembers = True):
        return None

    def _str(self):
        return str(self.extendedAttributes) if (self.extendedAttributes) else ''

    def __repr__(self):
        return repr(self.extendedAttributes) if (self.extendedAttributes) else ''


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

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent, False)
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

    def complexityFactor(self):
        return 0
    
    def _str(self):
        return str(self._const) + str(self.type) + self.name + str(self._equals) + str(self.value)

    def __repr__(self):
        return ('[const: ' + repr(self.type) +
                '[name: ' + self.name + '] = [value: ' + str(self.value) + ']]')


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

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self._enum = Symbol(tokens, 'enum')
        self.name = tokens.next().text
        self._openBrace = Symbol(tokens, '{')
        self.values = EnumValueList(tokens)
        self._closeBrace = Symbol(tokens, '}')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'enum'
    
    def complexityFactor(self):
        return 1
    
    def _str(self):
        return Construct._str(self) + str(self._enum) + self.name + str(self._openBrace) + str(self.values) + str(self._closeBrace)

    def __repr__(self):
        return ('[enum: ' + Construct.__repr__(self) + '[name: ' + self.name + '] ' +
                '[values: ' + repr(self.values) + ']]')


class Typedef(Construct):    # [ExtendedAttributes] "typedef" [ExtendedAttributes] Type identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'typedef')):
            Construct.peek(tokens)
            if (Type.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)
        
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self._typedef = Symbol(tokens, 'typedef')
        self.typeExtendedAttributes = self._parseExtendedAttributes(tokens, self)
        self.type = Type(tokens)
        self.name = tokens.next().text
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'typedef'
    
    def complexityFactor(self):
        return 1
    
    def _str(self):
        output = Construct._str(self) + str(self._typedef)
        output += str(self.typeExtendedAttributes) if (self.typeExtendedAttributes) else ''
        return output + str(self.type) + str(self.name)

    def __repr__(self):
        output = '[typedef: ' + Construct.__repr__(self) + '[type: '
        output += repr(self.typeExtendedAttributes) if (self.typeExtendedAttributes) else ''
        return output + str(self.type) + '] [name: ' + str(self.name) + ']]'


class Argument(Construct):    # [ExtendedAttributeList] "optional" [IgnoreInOut] Type ArgumentName [Default] |
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
                if (Type.peek(tokens)):
                    if (ArgumentName.peek(tokens)):
                        Default.peek(tokens)
                        return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        if (Symbol.peek(tokens, 'optional')):
            self.optional = Symbol(tokens, 'optional')
            self._ignore = IgnoreInOut(tokens) if (IgnoreInOut.peek(tokens)) else None
            self.type = Type(tokens)
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

    def _str(self):
        output = Construct._str(self)
        output += str(self.optional) if (self.optional) else ''
        output += str(self._ignore) if (self._ignore) else ''
        output += str(self.type)
        output += str(self.variadic) if (self.variadic) else ''
        return output + str(self._name) + (str(self.default) if (self.default) else '')

    def __repr__(self):
        output = '[argument: ' + Construct.__repr__(self)
        output += '[optional] ' if (self.optional) else ''
        output += '[type: ' + str(self.type) + ']'
        output += '[...] ' if (self.variadic) else ' '
        output += '[name: ' + str(self.name) + ']'
        return output + ((' [default: ' + repr(self.default) + ']]') if (self.default) else ']')


class InterfaceMember(Construct): # [ExtendedAttributes] Const | [ExtendedAttributes] AttributeOrOperation
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        return tokens.popPosition(Const.peek(tokens) or AtributeOrOperation.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        self.member = Const(tokens, parent) if (Const.peek(tokens)) else AtributeOrOperation(tokens, parent)
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

    def _str(self):
        return Construct._str(self) + str(self.member)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + repr(self.member) + ']'


class SyntaxError(Construct):   # ... ";" | ... "}"
    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        self.tokens = tokens.syntaxError((';', '}'))
        if (self.tokens[-1].isSymbol('}')):
            tokens.restore(self.tokens[-1])
            self.tokens = self.tokens[:-1]
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'unknown'

    @property
    def name(self):
        return None

    def _str(self):
        return ''.join([str(token) for token in self.tokens])


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
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent, (not parent))
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._interface = Symbol(tokens, 'interface')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = self.constructors
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (InterfaceMember.peek(tokens)):
                self.members.append(InterfaceMember(tokens, parent if (parent) else self))
            else:
                self.members.append(SyntaxError(tokens, parent if (parent) else self))
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'interface'

    def complexityFactor(self):
        return len(self.members) + 1

    def __len__(self):
        return len(self.members)
    
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

    def findMethod(self, name):
        for member in reversed(self.members):
            if (('method' == member.idlType) and (name == member.name)):
                return member
        return None
    
    def findArgument(self, name, searchMembers = True):
        if (searchMembers):
            for member in reversed(self.members):
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def _str(self):
        output = Construct._str(self)
        output += str(self.partial) if (self.partial) else ''
        output += str(self._interface) + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += str(self._openBrace)
        for member in self.members:
            if ('constructor' != member.idlType):
                output += str(member)
        return output + str(self._closeBrace)

    def __repr__(self):
        output = '[interface: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + self.name + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class DictionaryMember(Construct): # [ExtendedAttributes] Type identifier [Default] ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Type.peek(tokens)):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Default.peek(tokens)
                return tokens.popPosition(True)
        tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.type = Type(tokens)
        self.name = tokens.next().text
        self.default = Default(tokens) if (Default.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'dictmember'
    
    def complexityFactor(self):
        return 1
    
    def _str(self):
        output = Construct._str(self) + str(self.type) + str(self.name)
        return output + (str(self.default) if (self.default) else '')

    def __repr__(self):
        output = '[dictmember: ' + Construct.__repr__(self) + repr(self.type) + ' [name: ' + self.name + ']'
        return output + ((' = [default: ' + repr(self.default) + ']]') if (self.default) else ']')


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
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.partial = Symbol(tokens, 'partial') if (Symbol.peek(tokens, 'partial')) else None
        self._dictionary = Symbol(tokens, 'dictionary')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = []
        while (tokens.hasTokens()):
            if (Symbol.peek(tokens, '}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (DictionaryMember.peek(tokens)):
                self.members.append(DictionaryMember(tokens, self))
            else:
                self.members.append(SyntaxError(tokens, self))
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'dictionary'
    
    def complexityFactor(self):
        return len(self.members) + 1
    
    def __len__(self):
        return len(self.members)
    
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

    def _str(self):
        output = Construct._str(self)
        output += str(self.partial) if (self.partial) else ''
        output += str(self._dictionary) + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += str(self._openBrace)
        for member in self.members:
            output += str(member)
        return output + str(self._closeBrace)

    def __repr__(self):
        output = '[dictionary: ' + Construct.__repr__(self)
        output += '[partial] ' if (self.partial) else ''
        output += '[name: ' + self.name + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


class Callback(Construct):    # [ExtendedAttributes] "callback" identifier "=" ReturnType "(" [ArgumentList] ")" ";" |
                              # [ExtendedAttributes] "callback" Interface
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'callback')):
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
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
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
            self.interface = Interface(tokens, self)
            self.name = self.interface.name
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'callback'

    def complexityFactor(self):
        return self.interface.complexityFactor() if (self.interface) else 1
    
    def __len__(self):
        return len(self.interface.members) if (self.interface) else 0
    
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

    def _str(self):
        output = Construct._str(self) + str(self._callback)
        if (self.interface):
            return output + str(self.interface)
        output += self.name + str(self._equals) + str(self.returnType)
        return output + str(self._openParen) + (str(self.arguments) if (self.arguments) else '') + str(self._closeParen)

    def __repr__(self):
        output = '[callback: ' + Construct.__repr__(self)
        if (self.interface):
            return output + repr(self.interface) + ']'
        output += '[name: ' + self.name + '] [returnType: ' + str(self.returnType) + '] '
        return output + '[argumentlist: ' + (repr(self.arguments) if (self.arguments) else '') + ']]'


class ExceptionMember(Construct): # [ExtendedAttributes] Const | [ExtendedAttributes] Type identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Const.peek(tokens)):
            return tokens.popPosition(True)
        if (Type.peek(tokens)):
            token = tokens.peek()
            return tokens.popPosition(token and token.isIdentifier())
        tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        if (Const.peek(tokens)):
            self.const = Const(tokens)
            self.type = None
            self.name = self.const.name
        else:
            self.const = None
            self.type = Type(tokens)
            self.name = tokens.next().text
            self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'const' if (self.const) else 'exceptfield'

    def _str(self):
        output = Construct._str(self)
        return output + (str(self.const) if (self.const) else str(self.type) + self.name)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + ((repr(self.const) + ']') if (self.const) else repr(self.type) + ' [name: ' + self.name + ']]')


class Exception(Construct):   # [ExtendedAttributes] "exception" identifier [Inheritance] "{" [ExceptionMembers]... "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        if (Symbol.peek(tokens, 'exception')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                return tokens.popPosition(Symbol.peek(tokens, '{'))
        tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self._exception = Symbol(tokens, 'exception')
        self.name = tokens.next().text
        self.inheritance = Inheritance(tokens) if (Inheritance.peek(tokens)) else None
        self._openBrace = Symbol(tokens, '{')
        self.members = []
        while (tokens.hasTokens()):
            token = tokens.sneakPeek()
            if (token.isSymbol('}')):
                self._closeBrace = Symbol(tokens, '}')
                break
            if (ExceptionMember.peek(tokens)):
                self.members.append(ExceptionMember(tokens, self))
            else:
                self.members.append(SyntaxError(tokens, self))
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'exception'
    
    def complexityFactor(self):
        return len(self.members) + 1
    
    def __len__(self):
        return len(self.members)
    
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

    def _str(self):
        output = Construct._str(self) + str(self._exception) + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += str(self._openBrace)
        for member in self.members:
            output += str(member)
        return output + str(self._closeBrace)

    def __repr__(self):
        output = '[exception: ' + Construct.__repr__(self)
        output += '[name: ' + self.name + '] '
        output += repr(self.inheritance) if (self.inheritance) else ''
        output += '[members: \n'
        for member in self.members:
            output += '  ' + repr(member) + '\n'
        return output + ']]'


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

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.name = tokens.next().text
        self._implements = Symbol(tokens, 'implements')
        self.implements = tokens.next().text
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'implements'

    def complexityFactor(self):
        return 1
    
    def _str(self):
        return Construct._str(self) + self.name + str(self._implements) + self.implements

    def __repr__(self):
        return '[implements: ' + Construct.__repr__(self) + '[name: ' + self.name + '] [implements: ' + self.implements + ']]'


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
    
    def _str(self):
        return ''.join([str(token) for token in self.tokens])
    
    def __repr__(self):
        return '[ExtendedAttribute: ' + ''.join([str(token) for token in self.tokens]) + ']'


class ExtendedAttributeNoArgs(Construct):   # identifier
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            token = tokens.sneakPeek()
            return tokens.popPosition((not token) or token.isSymbol(',') or token.isSymbol(']'))
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
    
    def _str(self):
        return self.attribute
    
    def __repr__(self):
        return '[ExtendedAttributeNoArgs: ' + self.attribute + ']'


class ExtendedAttributeArgList(Construct):  # identifier "(" [ArgumentList] ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            if (Symbol.peek(tokens, '(')):
                ArgumentList.peek(tokens)
                if (Symbol.peek(tokens, ')')):
                    token = tokens.sneakPeek()
                    return tokens.popPosition((not token) or token.isSymbol(',') or token.isSymbol(']'))
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
    
    def _str(self):
        return self.attribute + str(self._openParen) + (str(self.arguments) if (self.arguments) else '') + str(self._closeParen)
    
    def __repr__(self):
        return ('[ExtendedAttributeArgList: ' + self.attribute +
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
                    return tokens.popPosition((not token) or token.isSymbol(',') or token.isSymbol(']'))
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
    
    def _str(self):
        return self.attribute + str(self._equals) + self.value
    
    def __repr__(self):
        return ('[ExtendedAttributeIdent: ' + self.attribute + ' [value: ' + self.value + ']]')


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
                            return tokens.popPosition((not token) or token.isSymbol(',') or token.isSymbol(']'))
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
    
    def _str(self):
        output = self.attribute + str(self._equals) + self.value
        return output + str(self._openParen) + (str(self.arguments) if (self.arguments) else '') + str(self._closeParen)
    
    def __repr__(self):
        return ('[ExtendedAttributeNamedArgList: ' + self.attribute + ' [value: ' + self.value + ']' +
                ' [arguments: ' + (repr(self.arguments) if (self.arguments) else '') + ']]')


class ExtendedAttribute(Construct): # ExtendedAttributeNoArgs | ExtendedAttributeArgList |
                                    # ExtendedAttributeIdent | ExtendedAttributeNamedArgList
    @classmethod
    def peek(cls, tokens):
        return (ExtendedAttributeNamedArgList.peek(tokens) or
                ExtendedAttributeIdent.peek() or
                ExtendedAttributeArgList.peek(tokens) or
                ExtendedAttributeNoArgs.peek())
    
    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent, False)
        if (ExtendedAttributeNamedArgList.peek(tokens)):
            self.attribute = ExtendedAttributeNamedArgList(tokens, parent)
        elif (ExtendedAttributeIdent.peek(tokens)):
            self.attribute = ExtendedAttributeIdent(tokens, parent)
        elif (ExtendedAttributeArgList.peek(tokens)):
            self.attribute = ExtendedAttributeArgList(tokens, parent)
        elif (ExtendedAttributeNoArgs.peek(tokens)):
            self.attribute = ExtendedAttributeNoArgs(tokens, parent)
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
    
    def _str(self):
        return str(self.attribute)
    
    def __repr__(self):
        return repr(self.attribute)




