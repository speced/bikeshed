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

import constructs

class IntegerType(object):   # "short" | "long" ["long"]
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol()):
            if ('long' == token.text):
                token = tokens.pushPosition()
                tokens.popPosition(token and token.isSymbol('long'))
                return tokens.popPosition(True)
            return tokens.popPosition('short' == token.text)
        return tokens.popPosition(False)
    
    def __init__(self, tokens):
        token = tokens.next()
        if ('long' == token.text):
            self.type = 'long'
            token = tokens.next()
            if (token and token.isSymbol('long')):
                self.type += ' long'
            else:
                tokens.restore(token)
        else:
            self.type = token.text

    def __str__(self):
        return self.type


class UnsignedIntegerType(object):   # "unsigned" IntegerType | IntegerType
    @classmethod
    def peek(cls, tokens):
        if (IntegerType.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('unsigned')):
            return tokens.popPosition(IntegerType.peek(tokens))
        return tokens.popPosition(False)
    
    def __init__(self, tokens): #
        self.unsigned = False
        token = tokens.next()
        if (token.isSymbol('unsigned')):
            self.unsigned = True
        else:
            tokens.restore(token)
        self.type = IntegerType(tokens)

    def __str__(self):
        return 'unsigned ' + str(self.type) if (self.unsigned) else str(self.type)


class FloatType(object):   # "float" | "double"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isSymbol('float') or token.isSymbol('double')))
    
    def __init__(self, tokens):
        token = tokens.next()
        self.type = token.text

    def __str__(self):
        return self.type


class UnrestrictedFloatType(object): # "unrestricted" FloatType | FloatType
    @classmethod
    def peek(cls, tokens):
        if (FloatType.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('unrestricted')):
            return tokens.popPosition(FloatType.peek(tokens))
        return tokens.popPosition(False)
    
    def __init__(self, tokens): #
        self.unrestricted = False
        token = tokens.next()
        if (token.isSymbol('unrestricted')):
            self.unrestricted = True
        else:
            tokens.restore(token)
        self.type = FloatType(tokens)

    def __str__(self):
        return ('unrestricted ' + str(self.type)) if (self.unrestricted) else str(self.type)


class PrimitiveType(object): # UnsignedIntegerType | UnrestrictedFloatType | "boolean" | "byte" | "octet"
    @classmethod
    def peek(cls, tokens):
        if (UnsignedIntegerType.peek(tokens) or UnrestrictedFloatType.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol()):
            return tokens.popPosition(('boolean' == token.text) or ('byte' == token.text) or ('octet' == token.text))
        return tokens.popPosition(False)

    def __init__(self, tokens):
        tokens.resetPeek()
        if (UnsignedIntegerType.peek(tokens)):
            self.type = UnsignedIntegerType(tokens)
        elif (UnrestrictedFloatType.peek(tokens)):
            self.type = UnrestrictedFloatType(tokens)
        else:
            self.type = tokens.next().text

    def __str__(self):
        return str(self.type)


class ConstType(object): # PrimitiveType [Null] | identifier [Null]
    @classmethod
    def peek(cls, tokens):
        if (PrimitiveType.peek(tokens)):
            token = tokens.pushPosition()
            tokens.popPosition(token and token.isSymbol('?'))
            return True
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            token = tokens.pushPosition()
            tokens.popPosition(token and token.isSymbol('?'))
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        tokens.resetPeek()
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
        else:
            self.type = tokens.next().text
        self.null = False
        token = tokens.next()
        if (token and token.isSymbol('?')):
            self.null = True
        else:
            tokens.restore(token)

    def __str__(self):
        return str(self.type) + ('?' if self.null else '')


class FloatLiteral(object):  # float | "-" "Infinity" | "Infinity" | "NaN"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isFloat()):
            return tokens.popPosition(True)
        elif (token and token.isSymbol()):
            if ('-' == token.text):
                token = tokens.peek()
                return tokens.popPosition(token and token.isSymbol('Infinity'))
            return tokens.popPosition(('Infinity' == token.text) or ('NaN' == token.text))
        return tokens.popPosition(False)
    
    def __init__(self, tokens): #
        token = tokens.next()
        if (token.isSymbol('-')):
            self.value = '-' + tokens.next().text
        else:
            self.value = token.text

    def __str__(self):
        return self.value


class ConstValue(object):    # "true" | "false" | FloatLiteral | integer | "null"
    @classmethod
    def peek(cls, tokens):
        if (FloatLiteral.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol()):
            return tokens.popPosition(('true' == token.text) or ('false' == token.text) or ('null' == token.text))
        return tokens.popPosition(token and token.isInteger())
    
    def __init__(self, tokens): #
        tokens.resetPeek()
        if (FloatLiteral.peek(tokens)):
            self.value = FloatLiteral(tokens)
        else:
            self.value = tokens.next().text

    def __str__(self):
        return str(self.value)


class EnumValueList(object): # string ["," string]...
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isString()):
            token = tokens.pushPosition()
            if (token and token.isSymbol(',')):
                return tokens.popPosition(tokens.popPosition(EnumValueList.peek(tokens)))
            tokens.popPosition(False)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        self.values = []
        self.values.append(tokens.next().text)
        token = tokens.next()
        while (token):
            if (token.isString()):
                self.values.append(token.text)
                token = tokens.next()
                continue
            elif (token.isSymbol(',')):
                token = tokens.next()
                continue
            tokens.restore(token)
            break
            
    def __str__(self):
        return ', '.join(self.values)


class TypeSuffix(object):    # "[" "]" [TypeSuffix] | "?" [TypeSuffixStartingWithArray]
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('[')):
            token = tokens.peek()
            if (token and token.isSymbol(']')):
                TypeSuffix.peek(tokens)
                return tokens.popPosition(True)
        elif (token and token.isSymbol('?')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()
        self.array = False
        self.null = False
        if (token.isSymbol('[')):
            token = tokens.next()   # "]"
            self.array = True
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            self.null = True
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None

    def __str__(self):
        output = '[]' if (self.array) else ''
        output += '?' if (self.null) else ''
        return output + (str(self.suffix) if (self.suffix) else '')


class TypeSuffixStartingWithArray(object):   # "[" "]" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('[')):
            token = tokens.peek()
            if (token and token.isSymbol(']')):
                TypeSuffix.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()   # "["
        token = tokens.next()   # "]"
        self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        
    def __str__(self):
        return '[]' + (str(self.suffix) if (self.suffix) else '')


class SingleType(object):    # NonAnyType | "any" [TypeSuffixStartingWithArray]
    @classmethod
    def peek(cls, tokens):
        if (NonAnyType.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('any')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        tokens.resetPeek()
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens)
            self.suffix = None
        else:
            token = tokens.next()   # "any"
            self.type = 'any'
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None

    def __str__(self):
        output = str(self.type)
        return output + (str(self.suffix) if (self.suffix) else '')


class NonAnyType(object):    # PrimitiveType [TypeSuffix] | "DOMString" [TypeSuffix] | identifier [TypeSuffix] |
                             #   "sequence" "<" Type ">" [Null] | "object" [TypeSuffix] | "Date" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (PrimitiveType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        token = tokens.pushPosition()
        if (token and (token.isSymbol('DOMString') or token.isIdentifier() or token.isSymbol('object') or token.isSymbol('Date'))):
            TypeSuffix.peek(tokens)
            return tokens.popPosition(True)
        elif (token and token.isSymbol('sequence')):
            token = tokens.peek()
            if (token and token.isSymbol('<')):
                if (Type.peek(tokens)):
                    token = tokens.peek()
                    if (token and token.isSymbol('>')):
                        token = tokens.pushPosition()
                        tokens.popPosition(token and token.isSymbol('?'))
                        return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        tokens.resetPeek()
        self.sequence = False
        self.null = False
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            token = tokens.next()
            if (token.isSymbol('DOMString') or token.isIdentifier() or token.isSymbol('object') or token.isSymbol('Date')):
                self.type = token.text
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            elif (token.isSymbol('sequence')):
                self.sequence = True
                token = tokens.next()   # "<"
                self.type = Type(tokens)
                token = tokens.next()   # ">"
                token = tokens.next()
                self.suffix = None
                if (token and token.isSymbol('?')):
                    self.null = True
                else:
                    tokens.restore(token)

    def __str__(self):
        output = 'sequence<' if (self.sequence) else ''
        output += str(self.type)
        output += '>' if (self.sequence) else ''
        output += (str(self.suffix) if (self.suffix) else '')
        return output + ('?' if (self.null) else '')


class UnionMemberType(object):   # NonAnyType | UnionType [TypeSuffix] | "any" "[" "]" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (NonAnyType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('any')):
            token = tokens.peek()
            if (token and token.isSymbol('[')):
                token = tokens.peek()
                if (token and token.isSymbol(']')):
                    TypeSuffix.peek(tokens)
                    return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        tokens.resetPeek()
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens)
            self.suffix = None
        elif (UnionType.peek(tokens)):
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            token = tokens.next()   # "any"
            token = tokens.next()   # "["
            token = tokens.next()   # "]"
            self.type = 'any[]'
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None

    def __str__(self):
        return str(self.type) + (str(self.suffix) if self.suffix else '')
        

class UnionType(object): # "(" UnionMemberType ["or" UnionMemberType]... ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('(')):
            while (tokens.hasTokens()):
                if (UnionMemberType.peek(tokens)):
                    token = tokens.peek()
                    if (token and token.isSymbol('or')):
                        continue
                    if (token and token.isSymbol(')')):
                        return tokens.popPosition(True)
                return tokens.popPosition(False)
        return tokens.popPosition(False)
        
    def __init__(self, tokens):
        self.types = []
        token = tokens.next()   # "("
        while (tokens.hasTokens()):
            self.types.append(UnionMemberType(tokens))
            token = tokens.next()
            if (token and token.isSymbol()):
                if ('or' == token.text):
                    continue
                elif (')' == token.text):
                    break
            tokens.restore(token)
            break
    
    def __str__(self):
        return '(' + ' or '.join([str(type) for type in self.types]) + ')'


class Type(object):  # SingleType | UnionType [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (SingleType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return False
        
    def __init__(self, tokens):
        tokens.resetPeek()
        if (SingleType.peek(tokens)):
            self.type = SingleType(tokens)
            self.suffix = None
        else:
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
    
    def __str__(self):
        return str(self.type) + (str(self.suffix) if (self.suffix) else '')
        
    def __repr__(self):
        return '[type: ' + str(self) + ']'


class IgnoreInOut(object):  # "in" | "out"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier() and (('in' == token.text) or ('out' == token.text))):
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()

class Ignore(object):    # "inherits" "getter" | "getraises" "(" ... ")" | "setraises" "(" ... ")" | "raises" "(" ... ")"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier() and ('inherits' == token.text)):
            token = tokens.peek()
            return tokens.popPosition(token and token.isSymbol('getter'))
        if (token and token.isIdentifier() and
            (('getraises' == token.text) or ('setraises' == token.text) or ('raises' == token.text))):
            token = tokens.peek()
            if (token and token.isSymbol('(')):
                return tokens.popPosition(tokens.peekSymbol(')'))
        return tokens.popPosition(False)
        
    def __init__(self, tokens):
        token = tokens.next()
        if (token and token.isIdentifier() and ('inherits' == token.text)):
            token = tokens.next()    # "getter"
        else:
            token = tokens.next()    # "("
            tokens.seekSymbol(')')


class IgnoreMultipleInheritance(object):    # [, identifier]...
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol(',')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()   # ","
        token = tokens.next()   # identifier
        if (IgnoreMultipleInheritance.peek(tokens)):
            IgnoreMultipleInheritance(tokens)


class Inheritance(object):   # ":" identifier [IgnoreMultipleInheritance]
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol(':')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()   # ":"
        self.base = tokens.next().text
        if (IgnoreMultipleInheritance.peek(tokens)):
            IgnoreMultipleInheritance(tokens)

    def __str__(self):
        return ': ' + self.base

    def __repr__(self):
        return '[inherits: ' + self.base + ']'


class Default(object):   # "=" ConstValue | "=" string
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('=')):
            if (ConstValue.peek(tokens)):
                return tokens.popPosition(True)
            token = tokens.peek()
            return tokens.popPosition(token and token.isString())
        return tokens.popPosition(False)

    def __init__(self, tokens):
        token = tokens.next()   # '='
        token = tokens.next()
        if (token.isString()):
            self.value = token.text
        else:
            tokens.restore(token)
            self.value = ConstValue(tokens)

    def __str__(self):
        return ' = ' + str(self.value)

    def __repr__(self):
        return str(self.value)


class ArgumentName(object):   # identifier | NameSymbol
    NameSymbols = frozenset(['attribute', 'callback', 'const', 'creator', 'deleter', 'dictionary', 'enum', 'exception',
                             'getter', 'implements', 'inherit', 'interface', 'legacycaller', 'partial', 'setter', 'static',
                             'stringifier', 'typedef', 'unrestricted'])

    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isIdentifier() or (token.isSymbol() and (token.text in cls.NameSymbols))))

    def __init__(self, tokens):
        self.name = tokens.next().text

    def __str__(self):
        return self.name


class ArgumentList(object):    # Argument ["," Argument]...
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (constructs.Argument.peek(tokens)):
            token = tokens.pushPosition()
            if (token and token.isSymbol(',')):
                return tokens.popPosition(tokens.popPosition(ArgumentList.peek(tokens)))
            tokens.popPosition(False)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        self.arguments = []
        self.arguments.append(constructs.Argument(tokens, parent))
        token = tokens.next()
        while (token and token.isSymbol(',')):
            self.arguments.append(constructs.Argument(tokens, parent))
            token = tokens.next()
        tokens.restore(token)

    @property
    def name(self):
        return self.arguments[0].name
    
    def __len__(self):
        return len(self.arguments)
    
    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for argument in self.arguments:
                if (argument.name == key):
                    return argument
            return None
        return self.arguments[key]
    
    def __iter__(self):
        return iter(self.arguments)
    
    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for argument in self.arguments:
                if (argument.name == key):
                    return True
            return False
        return (key in self.arguments)
    
    def __str__(self):
        return ', '.join([str(argument) for argument in self.arguments])

    def __repr__(self):
        return ' '.join([repr(argument) for argument in self.arguments])


class ReturnType(object):    # Type | "void"
    @classmethod
    def peek(cls, tokens):
        if (Type.peek(tokens)):
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol('void'))

    def __init__(self, tokens):
        token = tokens.next()
        if (token.isSymbol('void')):
            self.type = 'void'
        else:
            tokens.restore(token)
            self.type = Type(tokens)

    def __str__(self):
        return str(self.type)

    def __repr__(self):
        return repr(self.type)


class Special(object):   # "getter" | "setter" | "creator" | "deleter" | "legacycaller"
    SpecialSymbols = frozenset(['getter', 'setter', 'creator', 'deleter', 'legacycaller'])
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol() and (token.text in cls.SpecialSymbols))

    def __init__(self, tokens):
        self.name = tokens.next().text

    def __str__(self):
        return self.name

    def __repr__(self):
        return '[' + self.name + ']'


class Qualifiers(object):    # "static" | [Special]...
    @classmethod
    def peek(cls, tokens):
        if (Special.peek(tokens)):
            while (Special.peek(tokens)):
                pass
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol('static'))

    def __init__(self, tokens):
        self.static = False
        self.specials = []
        token = tokens.next()
        if (token.isSymbol('static')):
            self.static = True
        else:
            tokens.restore(token)
            self.specials.append(Special(tokens))
            while (Special.peek(tokens)):
                self.specials.append(Special(tokens))

    @property
    def name(self):
        return 'static' if (self.static) else ' '.join([special.name for special in self.specials])

    def __str__(self):
        if (self.static):
            return 'static'
        return ' '.join([str(special) for special in self.specials])

    def __repr__(self):
        if (self.static):
            return '[static]'
        return ' '.join([repr(special) for special in self.specials])


class ChildProduction(object):
    def __init__(self, parent):
        self.parent = parent

    @property
    def fullName(self):
        return self.parent.fullName + '/' + self.name if (self.parent) else self.name

    def _consumeSemicolon(self, tokens):
        token = tokens.next()
        if (not (token and token.isSymbol(';'))):
            tokens.restore(token)


class Attribute(ChildProduction):   # ["inherit"] ["readonly"] "attribute" Type identifier [Ignore]";"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('inherit')):
            token = tokens.peek()
        if (token and token.isSymbol('readonly')):
            token = tokens.peek()
        if (token and token.isSymbol('attribute')):
            if (Type.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        tokens.popPosition(False)
    
    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, parent)
        self.inherit = False
        self.readonly = False
        token = tokens.next()       # "inherit" or "readonly" or "attribute"
        if (token.isSymbol('inherit')):
            self.inherit = True
            token = tokens.next()   # "readonly" or "attribute"
        if (token.isSymbol('readonly')):
            self.readonly = True
            token = tokens.next()   # "attribute"
        self.type = Type(tokens)
        self.name = tokens.next().text
        if (Ignore.peek(tokens)):
            Ignore(tokens)
        self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'attribute'
    
    def complexityFactor(self):
        return 1
    
    def __str__(self):
        output = 'inherit ' if (self.inherit) else ''
        output += 'readonly ' if (self.readonly) else ''
        return output + 'attribute ' + str(self.type) + ' ' + self.name + ';'

    def __repr__(self):
        output = '[attribute: '
        output += '[inherit] ' if (self.inherit) else ''
        output += '[readonly] ' if (self.readonly) else ''
        return output + '[type: ' + str(self.type) + '] [name: ' + self.name + ']]'


class OperationRest(ChildProduction):   # ReturnType [identifier] "(" [ArgumentList] ")" [Ignore] ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (ReturnType.peek(tokens)):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                token = tokens.peek()
            if (token and token.isSymbol('(')):
                ArgumentList.peek(tokens)
                token = tokens.peek()
                return tokens.popPosition(token and token.isSymbol(')'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, parent)
        self.returnType = ReturnType(tokens)
        token = tokens.next()   # identifier or "("
        self.name = None
        if (token.isIdentifier()):
            self.name = token.text
            token = tokens.next()   # "("
        self.arguments = ArgumentList(tokens, parent) if (ArgumentList.peek(tokens)) else None
        token = tokens.next()   # ")"
        if (Ignore.peek(tokens)):
            Ignore(tokens)
        self._consumeSemicolon(tokens)
        if (self.arguments and not self.name):
            self.name = self.arguments.name

    def __str__(self):
        output = str(self.returnType) + ' '
        output += self.name if (self.name) else ''
        return output + '(' + (str(self.arguments) if (self.arguments) else '') + ');'

    def __repr__(self):
        output = '[rest: [returnType: ' + str(self.returnType) + '] '
        output += ('[name: ' + self.name + '] ') if (self.name) else ''
        return output + '[argumentlist: ' + (repr(self.arguments) if (self.arguments) else '') + ']]'



class Operation(ChildProduction):   # [Qualifiers] OperationRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Qualifiers.peek(tokens)
        return tokens.popPosition(OperationRest.peek(tokens))

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, parent)
        self.qualifiers = None
        tokens.resetPeek()
        if (Qualifiers.peek(tokens)):
            self.qualifiers = Qualifiers(tokens)
        self.rest = OperationRest(tokens, self)

    @property
    def idlType(self):
        return 'method'
        
    @property
    def name(self):
        return self.rest.name if (self.rest.name) else self.qualifiers.name if (self.qualifiers) else None
    
    @property
    def methodName(self):
        return self.name + '(' + (', '.join([argument.name for argument in self.arguments]) if (self.arguments) else '') + ')'
    
    @property
    def fullName(self):
        return self.parent.fullName + '/' + self.methodName if (self.parent) else self.methodName
    
    @property
    def arguments(self):
        return self.rest.arguments
    
    def __str__(self):
        output = str(self.qualifiers) if (self.qualifiers) else ''
        return output + str(self.rest)

    def __repr__(self):
        output = '[operation: ' + ((repr(self.qualifiers) + ' ') if (self.qualifiers) else '')
        return output + repr(self.rest) + ']'


class StringifierAttributeOrOperation(ChildProduction): # Attribute | OperationRest | ";"
    @classmethod
    def peek(cls, tokens):
        if (Attribute.peek(tokens) or OperationRest.peek(tokens)):
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol(';'))

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, parent)
        self.attribute = None
        self.operation = None
        tokens.resetPeek()
        if (Attribute.peek(tokens)):
            self.attribute = Attribute(tokens, parent)
        elif (OperationRest.peek(tokens)):
            self.operation = OperationRest(tokens)
        else:
            self._consumeSemicolon(tokens)

    @property
    def idlType(self):
        return 'attribute' if (self.attribute) else 'method'
        
    @property
    def name(self):
        if (self.attribute):
            return self.attribute.name
        return self.operation.name if (self.operation) else 'stringifier'

    @property
    def methodName(self):
        if (self.operation):
            return self.name + '(' + (', '.join([argument.name for argument in self.arguments]) if (self.arguments) else '') + ')'
        return None
    
    @property
    def fullName(self):
        if (self.operation):
            return self.parent.fullName + '/' + self.methodName if (self.parent) else self.methodName
        return ChildProduction.fullName
    
    @property
    def arguments(self):
        return self.operation.arguments

    def __str__(self):
        output = 'stringifier'
        if (self.attribute):
            output += ' ' + str(self.attribute)
        elif (self.operation):
            output += ' ' + str(self.operation)
        return output + ';'

    def __repr__(self):
        output = '[stringifier'
        if (self.attribute):
            output += ' ' + repr(self.attribute)
        elif (self.operation):
            output += ' ' + repr(self.operation)
        return output + ']'


class AtributeOrOperation(ChildProduction): # "stringifier" StringifierAttributeOrOperation | Attribute | Operation
    @classmethod
    def peek(cls, tokens):
        if (Attribute.peek(tokens) or Operation.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('stringifier')):
            return tokens.popPosition(StringifierAttributeOrOperation.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, parent)
        self.attribute = None
        self.operation = None
        self.stringifier = None
        tokens.resetPeek()
        if (Attribute.peek(tokens)):
            self.attribute = Attribute(tokens, parent)
        elif (Operation.peek(tokens)):
            self.operation = Operation(tokens, parent)
        else:
            token = tokens.next()   # "stringifier"
            self.stringifier = StringifierAttributeOrOperation(tokens, parent)

    @property
    def idlType(self):
        if (self.attribute):
            return 'attribute'
        return 'method' if (self.operation) else self.stringifier.idlType
        
    @property
    def name(self):
        if (self.attribute):
            return self.attribute.name
        return self.operation.name if (self.operation) else self.stringifier.name

    @property
    def methodName(self):
        if (self.operation):
            return self.name + '(' + (', '.join([argument.name for argument in self.arguments]) if (self.arguments) else '') + ')'
        return None
    
    @property
    def fullName(self):
        if (self.operation):
            return self.parent.fullName + '/' + self.methodName if (self.parent) else self.methodName
        return ChildProduction.fullName(self)

    @property
    def arguments(self):
        return self.operation.arguments if (self.operation) else None

    def __str__(self):
        if (self.attribute):
            return str(self.attribute)
        return str(self.operation) if (self.operation) else str(self.stringifier)

    def __repr__(self):
        if (self.attribute):
            return repr(self.attribute)
        return repr(self.operation) if (self.operation) else repr(self.stringifier)


