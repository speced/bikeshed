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
        token = tokens.pushPosition()
        if (token and token.isSymbol('[')):
            return tokens.popPosition(tokens.peekSymbol(']'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None):
        self.parent = parent
        self.extendedAttributes = self._parseExtendedAttributes(tokens) if (tokens) else None

    def _parseExtendedAttributes(self, tokens):
        token = tokens.next()
        if (token and ('[' == token.text)):
            return tokens.seekSymbol(']')[:-1]
        tokens.restore(token)
        return None

    @property
    def idlType(self):
        assert(False)   # subclasses must override
        return None

    @property
    def fullName(self):
        return self.parent.fullName + '/' + self.name if (self.parent) else self.name
    
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

    def __str__(self):
        return ('[' + ''.join([str(token) for token in self.extendedAttributes]) + '] ') if (self.extendedAttributes) else ''

    def __repr__(self):
        return ('[Extended Attributes: ' + ''.join([str(token) for token in self.extendedAttributes]) + '] ') if (self.extendedAttributes) else ''


class Const(Construct):    # "const" ConstType identifier "=" ConstValue ";"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('const')):
            if (ConstType.peek(tokens)):
                token = tokens.peek()
                if (token and token.isIdentifier()):
                    token = tokens.peek()
                    if (token and token.isSymbol('=')):
                        return tokens.popPosition(ConstValue.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, None, parent)
        token = tokens.next()   # "const"
        self.type = ConstType(tokens)
        self.name = tokens.next().text
        token = tokens.next()   # "="
        self.value = ConstValue(tokens)
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'const'
        
    def complexityFactor(self):
        return 0
    
    def __str__(self):
        return 'const ' + str(self.type) + ' ' + self.name + ' = ' + str(self.value) + ';'

    def __repr__(self):
        return ('[const: [type: ' + str(self.type) + '] ' +
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
        token = tokens.next()   # "enum"
        self.name = tokens.next().text
        token = tokens.next()   # "{"
        self.values = EnumValueList(tokens)
        token = tokens.next()   # "}"
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'enum'
    
    def complexityFactor(self):
        return 1
    
    def __str__(self):
        return Construct.__str__(self) + 'enum ' + self.name + ' {' + str(self.values)+ '};'

    def __repr__(self):
        return ('[enum: ' + Construct.__repr__(self) + '[name: ' + self.name + '] ' +
                '[values: ' + str(self.values) + ']]')


class Typedef(Construct):    # [ExtendedAttributes] "typedef" [ExtendedAttributes] Type identifier ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('typedef')):
            Construct.peek(tokens)
            if (Type.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)
        
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        token = tokens.next()   # "typedef"
        self.typeExtendedAttributes = self._parseExtendedAttributes(tokens)
        self.type = Type(tokens)
        self.name = tokens.next().text
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'typedef'
    
    def complexityFactor(self):
        return 1
    
    def __str__(self):
        output = Construct.__str__(self) + 'typedef '
        output += ('[' + ''.join([str(token) for token in self.typeExtendedAttributes]) + '] ') if (self.typeExtendedAttributes) else ''
        return output + str(self.type) + ' ' + str(self.name) + ';'

    def __repr__(self):
        output = '[typedef: ' + Construct.__repr__(self) + '[type: '
        output += ('[ExtendedAttributes: ' + ''.join([str(token) for token in self.typeExtendedAttributes]) + '] ') if (self.typeExtendedAttributes) else ''
        return output + str(self.type) + '] [name: ' + str(self.name) + ']]'


class Argument(Construct):    # [ExtendedAttributeList] "optional" [IgnoreInOut] Type ArgumentName [Default] |
                              # [ExtendedAttributeList] [IgnoreInOut] Type ["..."] ArgumentName
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        IgnoreInOut.peek(tokens)
        if (Type.peek(tokens)):
            token = tokens.pushPosition()
            tokens.popPosition(token and token.isSymbol('...'))
            return tokens.popPosition(ArgumentName.peek(tokens))
        else:
            token = tokens.peek()
            if (token and token.isSymbol('optional')):
                IgnoreInOut.peek(tokens)
                if (Type.peek(tokens)):
                    if (ArgumentName.peek(tokens)):
                        Default.peek(tokens)
                        return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        token = tokens.next()
        self.optional = False
        self.variadic = False
        if (token.isSymbol('optional')):
            self.optional = True
            if (IgnoreInOut.peek(tokens)):
                IgnoreInOut(tokens)
            self.type = Type(tokens)
            self.name = ArgumentName(tokens).name
            self.default = Default(tokens) if (Default.peek(tokens)) else None
        else:
            tokens.restore(token)
            if (IgnoreInOut.peek(tokens)):
                IgnoreInOut(tokens)
            self.type = Type(tokens)
            token = tokens.next()
            if (token.isSymbol('...')):
                self.variadic = True
            else:
                tokens.restore(token)
            self.name = ArgumentName(tokens).name
            self.default = None

    @property
    def idlType(self):
        return 'argument'

    def __str__(self):
        output = Construct.__str__(self)
        output += 'optional ' if (self.optional) else ''
        output += str(self.type)
        output += '... ' if (self.variadic) else ' '
        return output + str(self.name) + (str(self.default) if (self.default) else '')

    def __repr__(self):
        output = '[argument: ' + Construct.__repr__(self)
        output += '[optional] ' if (self.optional) else ''
        output += '[type: ' + str(self.type) + ']'
        output += '[...] ' if (self.variadic) else ' '
        output += '[name: ' + str(self.name) + ']'
        return output + ((' = [default: ' + repr(self.default) + ']]') if (self.default) else ']')


class InterfaceMember(Construct): # [ExtendedAttributes] Const | [ExtendedAttributes] AttributeOrOperation
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        return tokens.popPosition(Const.peek(tokens) or AtributeOrOperation.peek(tokens))

    def __init__(self, tokens, parent):
        Construct.__init__(self, tokens, parent)
        tokens.resetPeek()
        self.member = Const(tokens, parent) if (Const.peek(tokens)) else AtributeOrOperation(tokens, parent)

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
    def arguments(self):
        return self.member.arguments

    def findArgument(self, name, searchMembers = True):
        if (hasattr(self.member, 'arguments') and self.member.arguments):
            for argument in self.member.arguments:
                if (name == argument.name):
                    return argument
        return None

    def __str__(self):
        return Construct.__str__(self) + str(self.member)

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + repr(self.member) + ']'


class Interface(Construct):    # [ExtendedAttributes] ["partial"] "interface" identifier [Inheritance] "{" [InterfaceMember]... "}" ";"
    @classmethod
    def peek(cls, tokens, acceptExtendedAttributes = True):
        tokens.pushPosition(False)
        if (acceptExtendedAttributes):
            Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('partial')):
            token = tokens.peek()
        if (token and token.isSymbol('interface')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                token = tokens.peek()
                return tokens.popPosition(token and token.isSymbol('{'))
        return tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens if (not parent) else None, parent)
        self.partial = False
        token = tokens.next()   # "partial" or "interface"
        if (token.isSymbol('partial')):
            self.partial = True
            token = tokens.next()   # "interface"
        self.name = tokens.next().text
        self.inheritance = None
        if (Inheritance.peek(tokens)):
            self.inheritance = Inheritance(tokens)
        token = tokens.next()   # "{"
        self.members = []
        while (tokens.hasTokens()):
            token = tokens.next()
            if (token.isSymbol('}')):
                break
            tokens.restore(token)
            if (InterfaceMember.peek(tokens)):
                self.members.append(InterfaceMember(tokens, parent if (parent) else self))
            else:
                tokens.syntaxError(';')
        self._consumeSemicolon(tokens)

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
        for member in self.members:
            if (name == member.name):
                return member
        return None

    def findMethod(self, name):
        for member in self.members:
            if (('method' == member.idlType) and (name == member.name)):
                return member
        return None
    
    def findArgument(self, name, searchMembers = True):
        if (searchMembers):
            for member in self.members:
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def __str__(self):
        output = Construct.__str__(self)
        output += 'partial ' if (self.partial) else ''
        output += 'interface ' + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += ' {\n'
        for member in self.members:
            output += '  ' + str(member) + '\n'
        return output + '};'

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
        self.default = None
        if (Default.peek(tokens)):
            self.default = Default(tokens)
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'dictmember'
    
    def complexityFactor(self):
        return 1
    
    def __str__(self):
        output = Construct.__str__(self) + str(self.type) + ' ' + str(self.name)
        return output + (str(self.default) if (self.default) else '') + ';'

    def __repr__(self):
        output = '[dictmember: ' + Construct.__repr__(self) + repr(self.type) + ' [name: ' + self.name + ']'
        return output + ((' = [default: ' + repr(self.default) + ']]') if (self.default) else ']')


class Dictionary(Construct):  # [ExtendedAttributes] ["partial"] "dictionary" identifier [Inheritance] "{" [DictionaryMember]... "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('partial')):
            token = tokens.peek()
        if (token and token.isSymbol('dictionary')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                token = tokens.peek()
                return tokens.popPosition(token and token.isSymbol('{'))
        return tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.partial = False
        token = tokens.next()   # "partial" or "dictionary"
        if (token.isSymbol('partial')):
            self.partial = True
            token = tokens.next()   # "dictionary"
        self.name = tokens.next().text
        self.inheritance = None
        if (Inheritance.peek(tokens)):
            self.inheritance = Inheritance(tokens)
        token = tokens.next()   # "{"
        self.members = []
        while (tokens.hasTokens()):
            token = tokens.next()
            if (token.isSymbol('}')):
                break
            tokens.restore(token)
            if (DictionaryMember.peek(tokens)):
                self.members.append(DictionaryMember(tokens, self))
            else:
                tokens.syntaxError(';')
        self._consumeSemicolon(tokens)

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
        for member in self.members:
            if (name == member.name):
                return member
        return None

    def __str__(self):
        output = Construct.__str__(self)
        output += 'partial ' if (self.partial) else ''
        output += 'dictionary ' + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += ' {\n'
        for member in self.members:
            output += '  ' + str(member) + '\n'
        return output + '};'

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
        token = tokens.peek()
        if (token and token.isSymbol('callback')):
            if (Interface.peek(tokens, False)):
                return tokens.popPosition(True)
            token = tokens.peek()
            if (token and token.isIdentifier()):
                token = tokens.peek()
                if (token and token.isSymbol('=')):
                    if (ReturnType.peek(tokens)):
                        token = tokens.peek()
                        if (token and token.isSymbol('(')):
                            ArgumentList.peek(tokens)
                            token = tokens.peek()
                            return tokens.popPosition(token and token.isSymbol(')'))
        tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        token = tokens.next()   # "callback"
        token = tokens.next()
        if (token.isIdentifier()):
            self.name = token.text
            token = tokens.next()   # "="
            self.returnType = ReturnType(tokens)
            token = tokens.next()   # "("
            self.arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
            token = tokens.next()   # ")"
            self.interface = None
            self._consumeSemicolon(tokens)
        else:
            tokens.restore(token)
            self.returnType = None
            self.arguments = None
            self.interface = Interface(tokens, self)
            self.name = self.interface.name

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
            for member in self.interface.members:
                if (name == member.name):
                    return member
        return None

    def findArgument(self, name, searchMembers = True):
        if (self.arguments):
            for argument in self.arguments:
                if (name == argument.name):
                    return argument
        if (self.interface and searchMembers):
            for member in self.interface.members:
                argument = member.findArgument(name)
                if (argument):
                    return argument
        return None

    def __str__(self):
        output = Construct.__str__(self) + 'callback '
        if (self.interface):
            return output + str(self.interface)
        output += self.name + ' = ' + str(self.returnType)
        return output + '(' + (str(self.arguments) if (self.arguments) else '') + ');'

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
        tokens.resetPeek()
        if (Const.peek(tokens)):
            self.const = Const(tokens)
            self.type = None
            self.name = self.const.name
        else:
            self.const = None
            self.type = Type(tokens)
            self.name = tokens.next().text
            self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'const' if (self.const) else 'exceptfield'

    def __str__(self):
        output = Construct.__str__(self)
        return output + (str(self.const) if (self.const) else str(self.type) + ' ' + self.name + ';')

    def __repr__(self):
        output = '[member: ' + Construct.__repr__(self)
        return output + ((repr(self.const) + ']') if (self.const) else repr(self.type) + ' [name: ' + self.name + ']]')


class Exception(Construct):   # [ExtendedAttributes] "exception" identifier [Inheritance] "{" [ExceptionMembers]... "}" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Construct.peek(tokens)
        token = tokens.peek()
        if (token and token.isSymbol('exception')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Inheritance.peek(tokens)
                token = tokens.peek()
                return tokens.popPosition(token and token.isSymbol('{'))
        tokens.popPosition(False)
    
    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        token = tokens.next()   # "exception"
        self.name = tokens.next().text
        self.inheritance = None
        if (Inheritance.peek(tokens)):
            self.inheritance = Inheritance(tokens)
        token = tokens.next()   # "{"
        self.members = []
        while (tokens.hasTokens()):
            token = tokens.next()
            if (token.isSymbol('}')):
                break
            tokens.restore(token)
            if (ExceptionMember.peek(tokens)):
                self.members.append(ExceptionMember(tokens, self))
            else:
                tokens.syntaxError(';')
        self._consumeSemicolon(tokens)

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
        for member in self.members:
            if (name == member.name):
                return member
        return None

    def findMember(self, name):
        for member in self.members:
            if (name == member.name):
                return member
        return None

    def __str__(self):
        output = Construct.__str__(self) + 'exception ' + self.name
        output += str(self.inheritance) if (self.inheritance) else ''
        output += ' {\n'
        for member in self.members:
            output += '  ' + str(member) + '\n'
        return output + '};'

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
            token = tokens.peek()
            if (token and token.isSymbol('implements')):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)

    def __init__(self, tokens, parent = None):
        Construct.__init__(self, tokens, parent)
        self.name = tokens.next().text
        token = tokens.next()   # "implements"
        self.implements = tokens.next().text
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'implements'

    def complexityFactor(self):
        return 1
    
    def __str__(self):
        return Construct.__str__(self) + self.name + ' implements ' + self.implements + ';'

    def __repr__(self):
        return '[implements: ' + Construct.__repr__(self) + '[name: ' + self.name + '] [implements: ' + self.implements + ']]'

