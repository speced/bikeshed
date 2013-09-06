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
import itertools

class Production(object):
    def __init__(self, tokens):
        self._leadingSpace = self._whitespace(tokens)
        self._tail = None
        self._semicolon = ''
    
    def _didParse(self, tokens, includeTrailingSpace = True):
        self._trailingSpace = self._whitespace(tokens) if (includeTrailingSpace) else ''

    def _whitespace(self, tokens):
        whitespace = tokens.whitespace()
        return whitespace.text if (whitespace) else ''
    
    def __str__(self):
        output = self._leadingSpace + self._str()
        output += ''.join([str(token) for token in self._tail]) if (self._tail) else ''
        return output + str(self._semicolon) + self._trailingSpace

    def _markup(self, marker, parent):
        return (self._str(), self)

    def markup(self, marker, parent = None):
        text, target = self._markup(marker, parent)
        text += (''.join([str(token) for token in target._tail]) if (target._tail) else '') + str(target._semicolon)
        if (self != target):
            text += (''.join([str(token) for token in self._tail]) if (self._tail) else '') + str(self._semicolon)
        output = self._leadingSpace + text
        output += target._trailingSpace if (self != target) else ''
        return output + self._trailingSpace

    def _consumeSemicolon(self, tokens):
        if (Symbol.peek(tokens, ';')):
            self._semicolon = Symbol(tokens, ';', False)
        elif (not Symbol.peek(tokens, '}')):
            skipped = tokens.syntaxError((';', '}'))
            self._tail = skipped[:-1]
            tokens.restore(skipped[-1])
            self._semicolon = Symbol(tokens, ';', False) if (Symbol.peek(tokens, ';')) else ''


class Symbol(Production):
    @classmethod
    def peek(cls, tokens, symbol):
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol(symbol))

    def __init__(self, tokens, symbol = None, includeTrailingSpace = True):
        Production.__init__(self, tokens)
        self.symbol = tokens.next().text
        if (symbol):
            assert(self.symbol == symbol)
        self._didParse(tokens, includeTrailingSpace)

    def _str(self):
        return self.symbol

    def __repr__(self):
        return self.symbol


class IntegerType(Production):   # "short" | "long" ["long"]
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
        Production.__init__(self, tokens)
        self._space = None
        token = tokens.next()
        if ('long' == token.text):
            self.type = 'long'
            token = tokens.sneakPeek()
            if (token and token.isSymbol('long')):
                self._space = self._whitespace(tokens)
                self.type += ' ' + tokens.next().text
        else:
            self.type = token.text
        self._didParse(tokens)

    def _str(self):
        if (self._space):
            return self._space.join(self.type.split(' '))
        return self.type

    def __repr__(self):
        return '[IntegerType: ' + self.type + ']'


class UnsignedIntegerType(Production):   # "unsigned" IntegerType | IntegerType
    @classmethod
    def peek(cls, tokens):
        if (IntegerType.peek(tokens)):
            return True
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'unsigned')):
            return tokens.popPosition(IntegerType.peek(tokens))
        return tokens.popPosition(False)
    
    def __init__(self, tokens): #
        Production.__init__(self, tokens)
        self.unsigned = Symbol(tokens, 'unsigned') if (Symbol.peek(tokens, 'unsigned')) else None
        self.type = IntegerType(tokens)
        self._didParse(tokens)

    def _str(self):
        return (str(self.unsigned) + str(self.type)) if (self.unsigned) else str(self.type)

    def __repr__(self):
        return '[UnsignedIntegerType: ' + ('[unsigned]' if (self.unsigned) else '') + repr(self.type) + ']'


class FloatType(Production):   # "float" | "double"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isSymbol('float') or token.isSymbol('double')))
    
    def __init__(self, tokens):
        Production.__init__(self, tokens)
        token = tokens.next()
        self.type = token.text
        self._didParse(tokens)

    def _str(self):
        return self.type

    def __repr__(self):
        return '[FloatType: ' + self.type + ']'


class UnrestrictedFloatType(Production): # "unrestricted" FloatType | FloatType
    @classmethod
    def peek(cls, tokens):
        if (FloatType.peek(tokens)):
            return True
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'unrestricted')):
            return tokens.popPosition(FloatType.peek(tokens))
        return tokens.popPosition(False)
    
    def __init__(self, tokens): #
        Production.__init__(self, tokens)
        self.unrestricted = Symbol(tokens, 'unrestricted') if (Symbol.peek(tokens, 'unrestricted')) else None
        self.type = FloatType(tokens)
        self._didParse(tokens)

    def _str(self):
        return (str(self.unrestricted) + str(self.type)) if (self.unrestricted) else str(self.type)

    def __repr__(self):
        return '[UnrestrictedFloatType: ' + ('[unrestricted]' if (self.unrestricted) else '') + repr(self.type) + ']'


class PrimitiveType(Production): # UnsignedIntegerType | UnrestrictedFloatType | "boolean" | "byte" | "octet"
    @classmethod
    def peek(cls, tokens):
        if (UnsignedIntegerType.peek(tokens) or UnrestrictedFloatType.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol()):
            return tokens.popPosition(('boolean' == token.text) or ('byte' == token.text) or ('octet' == token.text))
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (UnsignedIntegerType.peek(tokens)):
            self.type = UnsignedIntegerType(tokens)
        elif (UnrestrictedFloatType.peek(tokens)):
            self.type = UnrestrictedFloatType(tokens)
        else:
            self.type = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return str(self.type)

    def __repr__(self):
        return '[PrimitiveType: ' + repr(self.type) + ']'


class ConstType(Production): # PrimitiveType [Null] | identifier [Null]
    @classmethod
    def peek(cls, tokens):
        if (PrimitiveType.peek(tokens)):
            Symbol.peek(tokens, '?')
            return True
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            Symbol.peek(tokens, '?')
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
        else:
            self.type = tokens.next().text
        self.null = Symbol(tokens, '?') if (Symbol.peek(tokens, '?')) else None
        self._didParse(tokens)

    def _str(self):
        return str(self.type) + (str(self.null) if (self.null) else '')
    
    def _markup(self, marker, parent):
        if (isinstance(self.type, basestring)):
            if (self.null):
                return (marker.markupType(self.type, parent) + str(self.null), self.null)
            return (marker.markupType(self.type, parent), self)
        return Production._markup(self, marker, parent)
    
    def __repr__(self):
        return '[ConstType: ' + repr(self.type) + (' [null]' if (self.null) else '') + ']'

class FloatLiteral(Production):  # float | "-" "Infinity" | "Infinity" | "NaN"
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
        Production.__init__(self, tokens)
        self.negative = Symbol(tokens, '-') if (Symbol.peek(tokens, '-')) else None
        self.value = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return (str(self.negative) if (self.negative) else '') + self.value

    def __repr__(self):
        return '[FloatLiteral: ' + (repr(self.negative) if (self.negative) else '') + self.value + ']'


class ConstValue(Production):    # "true" | "false" | FloatLiteral | integer | "null"
    @classmethod
    def peek(cls, tokens):
        if (FloatLiteral.peek(tokens)):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol()):
            return tokens.popPosition(('true' == token.text) or ('false' == token.text) or ('null' == token.text))
        return tokens.popPosition(token and token.isInteger())
    
    def __init__(self, tokens): #
        Production.__init__(self, tokens)
        if (FloatLiteral.peek(tokens)):
            self.value = FloatLiteral(tokens)
        else:
            self.value = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return str(self.value)

    def __repr__(self):
        return '[ConstValue: ' + repr(self.value) + ']'


class EnumValue(Production): # string
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isString())

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.value = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return self.value

    def __repr__(self):
        return '[EnumValue: ' + self.value + ']'


class EnumValueList(Production): # EnumValue ["," EnumValue]... [","]
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (EnumValue.peek(tokens)):
            token = tokens.pushPosition()
            if (token and token.isSymbol(',')):
                token = tokens.sneakPeek()
                if (token and token.isSymbol('}')):
                    return tokens.popPosition(tokens.popPosition(True))
                return tokens.popPosition(tokens.popPosition(EnumValueList.peek(tokens)))
            tokens.popPosition(False)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.values = []
        self._commas = []
        while (tokens.hasTokens()):
            self.values.append(EnumValue(tokens))
            if (Symbol.peek(tokens, ',')):
                self._commas.append(Symbol(tokens, ','))
                token = tokens.sneakPeek()
                if (token and token.isSymbol('}')):
                    break
                continue
            break
        self._didParse(tokens)

    def _str(self):
        return ''.join([str(value) + str(comma) for value, comma in itertools.izip_longest(self.values, self._commas, fillvalue = '')])

    def __repr__(self):
        return '[EnumValueList: ' + ''.join([repr(value) for value in self.values]) + ']'


class TypeSuffix(Production):    # "[" "]" [TypeSuffix] | "?" [TypeSuffixStartingWithArray]
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '[')):
            if (Symbol.peek(tokens, ']')):
                TypeSuffix.peek(tokens)
                return tokens.popPosition(True)
        elif (Symbol.peek(tokens, '?')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (Symbol.peek(tokens, '[')):
            self._openBracket = Symbol(tokens, '[')
            self._closeBracket = Symbol(tokens, ']')
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            self.array = True
            self.null = None
        else:
            self.null = Symbol(tokens, '?')
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
            self.array = False
            self._openBracket = None
            self._closeBracket = None
        self._didParse(tokens)

    def _str(self):
        output = (str(self._openBracket) + str(self._closeBracket)) if (self.array) else ''
        output += str(self.null) if (self.null) else ''
        return output + (str(self.suffix) if (self.suffix) else '')

    def __repr__(self):
        output = '[TypeSuffix: ' + ('[array] ' if (self.array) else '') + ('[null] ' if (self.null) else '')
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class TypeSuffixStartingWithArray(Production):   # "[" "]" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '[')):
            if (Symbol.peek(tokens, ']')):
                TypeSuffix.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._openBracket = Symbol(tokens, '[')
        self._closeBracket = Symbol(tokens, ']')
        self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)
    
    def _str(self):
        return str(self._openBracket) + str(self._closeBracket) + (str(self.suffix) if (self.suffix) else '')

    def __repr__(self):
        return '[TypeSuffixStartingWithArray: ' + (repr(self.suffix) if (self.suffix) else '') + ']'


class SingleType(Production):    # NonAnyType | "any" [TypeSuffixStartingWithArray]
    @classmethod
    def peek(cls, tokens):
        if (NonAnyType.peek(tokens)):
            return True
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'any')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens)
            self.suffix = None
        else:
            self.type = Symbol(tokens, 'any')
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        return str(self.type) + (str(self.suffix) if (self.suffix) else '')
    
    def _markup(self, marker, parent):
        return (self.type.markup(marker, parent), self)
    
    def __repr__(self):
        return '[SingleType: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class NonAnyType(Production):   # PrimitiveType [TypeSuffix] | "DOMString" [TypeSuffix] | identifier [TypeSuffix] |
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
            if (Symbol.peek(tokens, '<')):
                if (Type.peek(tokens)):
                    if (Symbol.peek(tokens, '>')):
                        Symbol.peek(tokens, '?')
                        return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.sequence = None
        self._openSequence = None
        self._closeSequence = None
        self.null = False
        self.suffix = None
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            token = tokens.sneakPeek()
            if (token.isIdentifier()):
                self.type = tokens.next().text
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            elif (token.isSymbol('sequence')):
                self.sequence = Symbol(tokens, 'sequence')
                self._openSequence = Symbol(tokens, '<')
                self.type = Type(tokens)
                self._closeSequence = Symbol(tokens, '>')
                self.null = Symbol(tokens, '?') if (Symbol.peek(tokens, '?')) else None
            else:
                self.type = Symbol(tokens)  # "DOMString" | "object" | "Date"
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        if (self.sequence):
            output = str(self.sequence) + str(self._openSequence) + str(self.type) + str(self._closeSequence)
            return output + (str(self.null) if (self.null) else '')
        output = str(self.type)
        return output + (str(self.suffix) if (self.suffix) else '')

    def _markup(self, marker, parent):
        if (isinstance(self.type, basestring)):
            text = marker.markupType(self.type, parent)
            text += str(self.suffix) if (self.suffix) else ''
            return (text, self)
        if (self.sequence):
            output = str(self.sequence) + str(self._openSequence) + self.type.markup(marker, parent) + str(self._closeSequence)
            return (output + (str(self.null) if (self.null) else ''), self)
        return Production._markup(self, marker, parent)

    def __repr__(self):
        output = '[NonAnyType: ' + ('[sequence]' if (self.sequence) else '') + repr(self.type)
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class UnionMemberType(Production):   # NonAnyType | UnionType [TypeSuffix] | "any" "[" "]" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (NonAnyType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        tokens.pushPosition()
        if (Symbol.peek(tokens, 'any')):
            if (Symbol.peek(tokens, '[')):
                if (Symbol.peek(tokens, ']')):
                    TypeSuffix.peek(tokens)
                    return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.any = None
        self._openBracket = None
        self._closeBracket = None
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens)
            self.suffix = None
        elif (UnionType.peek(tokens)):
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            self.any = Symbol(tokens, 'any')
            self._openBracket = Symbol(tokens, '[')
            self._closeBracket = Symbol(tokens, ']')
            self.type = 'any[]'
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        output = (str(self.any) + str(self._openBracket) + str(self._closeBracket)) if (self.any) else str(self.type)
        return output + (str(self.suffix) if (self.suffix) else '')
    
    def _markup(self, marker, parent):
        output = (str(self.any) + str(self._openBracket) + str(self._closeBracket)) if (self.any) else self.type.markup(marker, parent)
        return (output + (str(self.suffix) if (self.suffix) else ''), self)
    
    def __repr__(self):
        output = '[UnionMemberType: ' + ('[any[]]' if (self.any) else repr(self.type))
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class UnionType(Production): # "(" UnionMemberType ["or" UnionMemberType]... ")"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '(')):
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
        Production.__init__(self, tokens)
        self._openParen = Symbol(tokens, '(')
        self.types = []
        self._ors = []
        while (tokens.hasTokens()):
            self.types.append(UnionMemberType(tokens))
            token = tokens.sneakPeek()
            if (token and token.isSymbol()):
                if ('or' == token.text):
                    self._ors.append(Symbol(tokens, 'or'))
                    continue
                elif (')' == token.text):
                    break
            break
        self._closeParen = Symbol(tokens, ')')
        self._didParse(tokens)

    def _str(self):
        output = str(self._openParen)
        output += ''.join([str(type) + str(_or) for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = '')])
        return output + str(self._closeParen)
    
    def _markup(self, marker, parent):
        output = str(self._openParen)
        output += ''.join([type.markup(marker, parent) + str(_or) for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = '')])
        return (output + str(self._closeParen), self)
    
    def __repr__(self):
        return '[UnionType: ' + ''.join([repr(type) for type in self.types]) + ']'


class Type(Production):  # SingleType | UnionType [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (SingleType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return False
        
    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (SingleType.peek(tokens)):
            self.type = SingleType(tokens)
            self.suffix = None
        else:
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        return str(self.type) + (str(self.suffix) if (self.suffix) else '')

    def _markup(self, marker, parent):
        if (self.suffix):
            return (self.type.markup(marker, parent) + str(self.suffix), self)
        return (self.type.markup(marker, parent), self)
                    
    def __repr__(self):
        return '[Type: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class IgnoreInOut(Production):  # "in" | "out"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier() and (('in' == token.text) or ('out' == token.text))):
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.text = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return self.text


class Ignore(Production):    # "inherits" "getter" | "getraises" "(" ... ")" | "setraises" "(" ... ")" | "raises" "(" ... ")"
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
        Production.__init__(self, tokens)
        self.tokens = []
        token = tokens.next()
        self.tokens.append(token)
        if (token and token.isIdentifier() and ('inherits' == token.text)):
            self.tokens.append(tokens.whitespace())
            self.tokens.append(tokens.next())   # "getter"
        else:
            self.tokens.append(tokens.whitespace())
            self.tokens.append(tokens.next())    # "("
            self.tokens += tokens.seekSymbol(')')
        self._didParse(tokens)

    def _str(self):
        return ''.join([str(token) for token in self.tokens])


class IgnoreMultipleInheritance(Production):    # [, identifier]...
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, ',')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self.inherit = tokens.next().text
        self.next = IgnoreMultipleInheritance(tokens) if (IgnoreMultipleInheritance.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        return str(self._comma) + self.inherit + (str(self.next) if (self.next) else '')

    def _markup(self, marker, parent):
        return (str(self._comma) + marker.markupType(self.inherit, parent) + (self.next.markup(marker, parent) if (self.next) else ''), self)


class Inheritance(Production):   # ":" identifier [IgnoreMultipleInheritance]
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, ':')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._colon = Symbol(tokens, ':')
        self.base = tokens.next().text
        self._ignore = IgnoreMultipleInheritance(tokens) if (IgnoreMultipleInheritance.peek(tokens)) else None
        self._didParse(tokens)

    def _str(self):
        return str(self._colon) + self.base + (str(self._ignore) if (self._ignore) else '')
    
    def _markup(self, marker, parent):
        text = str(self._colon) + marker.markupType(self.base, parent)
        if (self._ignore):
            return (text + self._ignore.markup(marker, parent), self._ignore)
        return (text, self)
    
    def __repr__(self):
        return '[inherits: ' + self.base + ']'


class Default(Production):   # "=" ConstValue | "=" string
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '=')):
            if (ConstValue.peek(tokens)):
                return tokens.popPosition(True)
            token = tokens.peek()
            return tokens.popPosition(token and token.isString())
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._equals = Symbol(tokens, '=')
        token = tokens.sneakPeek()
        if (token.isString()):
            self.value = tokens.next().text
        else:
            self.value = ConstValue(tokens)
        self._didParse(tokens)

    def _str(self):
        return str(self._equals) + str(self.value)

    def __repr__(self):
        return '[Default: ' + repr(self.value) + ']'


class ArgumentName(Production):   # identifier | NameSymbol
    NameSymbols = frozenset(['attribute', 'callback', 'const', 'creator', 'deleter', 'dictionary', 'enum', 'exception',
                             'getter', 'implements', 'inherit', 'interface', 'legacycaller', 'partial', 'setter', 'static',
                             'stringifier', 'typedef', 'unrestricted'])

    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isIdentifier() or (token.isSymbol() and (token.text in cls.NameSymbols))))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.name = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return self.name
    
    def _markup(self, marker, parent):
        return (marker.markupName(self.name, parent), self)
    
    def __repr__(self):
        return '[ArgumentName: ' + repr(self.name) + ']'


class ArgumentList(Production):    # Argument ["," Argument]...
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
        Production.__init__(self, tokens)
        self.arguments = []
        self._commas = []
        self.arguments.append(constructs.Argument(tokens, parent))
        token = tokens.sneakPeek()
        while (token and token.isSymbol(',')):
            self._commas.append(Symbol(tokens, ','))
            self.arguments.append(constructs.Argument(tokens, parent))
            token = tokens.sneakPeek()
        self._didParse(tokens)

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
    
    def _str(self):
        return ''.join([str(argument) + str(comma) for argument, comma in itertools.izip_longest(self.arguments, self._commas, fillvalue = '')])
    
    def _markup(self, marker, parent):
        return (''.join([argument.markup(marker, parent) + str(comma) for argument, comma in itertools.izip_longest(self.arguments, self._commas, fillvalue = '')]), self)
    
    def __repr__(self):
        return ' '.join([repr(argument) for argument in self.arguments])


class ReturnType(Production):    # Type | "void"
    @classmethod
    def peek(cls, tokens):
        if (Type.peek(tokens)):
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol('void'))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        token = tokens.sneakPeek()
        if (token.isSymbol('void')):
            self.type = Symbol(tokens, 'void')
        else:
            self.type = Type(tokens)
        self._didParse(tokens)

    def _str(self):
        return str(self.type)
    
    def _markup(self, marker, parent):
        return self.type._markup(marker, parent)
    
    def __repr__(self):
        return repr(self.type)


class Special(Production):   # "getter" | "setter" | "creator" | "deleter" | "legacycaller"
    SpecialSymbols = frozenset(['getter', 'setter', 'creator', 'deleter', 'legacycaller'])
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol() and (token.text in cls.SpecialSymbols))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.name = tokens.next().text
        self._didParse(tokens)

    def _str(self):
        return self.name

    def __repr__(self):
        return '[' + self.name + ']'


class Qualifiers(Production):    # "static" | [Special]...
    @classmethod
    def peek(cls, tokens):
        if (Special.peek(tokens)):
            while (Special.peek(tokens)):
                pass
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and token.isSymbol('static'))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.static = None
        self.specials = []
        token = tokens.sneakPeek()
        if (token.isSymbol('static')):
            self.static = Symbol(tokens, 'static')
        else:
            self.specials.append(Special(tokens))
            while (Special.peek(tokens)):
                self.specials.append(Special(tokens))
        self._didParse(tokens)

    @property
    def name(self):
        return 'static' if (self.static) else ' '.join([special.name for special in self.specials])

    def _str(self):
        if (self.static):
            return str(self.static)
        return ''.join([str(special) for special in self.specials])

    def __repr__(self):
        if (self.static):
            return '[static]'
        return ' '.join([repr(special) for special in self.specials])


class ChildProduction(Production):
    def __init__(self, tokens, parent):
        Production.__init__(self, tokens)
        self.parent = parent

    @property
    def fullName(self):
        return self.parent.fullName + '/' + self.normalName if (self.parent) else self.normalName

    @property
    def normalName(self):
        return self.name


class Attribute(ChildProduction):   # ["inherit"] ["readonly"] "attribute" Type identifier [Ignore] ";"
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
        ChildProduction.__init__(self, tokens, parent)
        self.inherit = None
        self.readonly = None
        token = tokens.sneakPeek()       # "inherit" or "readonly" or "attribute"
        if (token.isSymbol('inherit')):
            self.inherit = Symbol(tokens, 'inherit')
            token = tokens.sneakPeek()   # "readonly" or "attribute"
        if (token.isSymbol('readonly')):
            self.readonly = Symbol(tokens, 'readonly')
        self._attribute = Symbol(tokens, 'attribute')
        self.type = Type(tokens)
        self.name = tokens.next().text
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'attribute'
    
    def complexityFactor(self):
        return 1
    
    def _str(self):
        output = str(self.inherit) if (self.inherit) else ''
        output += str(self.readonly) if (self.readonly) else ''
        return output + str(self._attribute) + str(self.type) + self.name + (str(self._ignore) if (self._ignore) else '')
    
    def _markup(self, marker, parent):
        output = str(self.inherit) if (self.inherit) else ''
        output += str(self.readonly) if (self.readonly) else ''
        output += str(self._attribute) + self.type.markup(marker, self)
        output += marker.markupName(self.name, parent)
        return (output + (str(self._ignore) if (self._ignore) else ''), self)
    
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
        ChildProduction.__init__(self, tokens, parent)
        self.returnType = ReturnType(tokens)
        self.name = tokens.next().text if (tokens.sneakPeek().isIdentifier()) else None
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, parent) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    def _str(self):
        output = str(self.returnType)
        output += self.name if (self.name) else ''
        output += str(self._openParen) + (str(self.arguments) if (self.arguments) else '') + str(self._closeParen)
        return output + (str(self._ignore) if (self._ignore) else '')
    
    def _markup(self, marker, parent):
        output = self.returnType.markup(marker, parent)
        output += marker.markupName(self.name, parent) if (self.name) else ''
        output += str(self._openParen) + (self.arguments.markup(marker, parent) if (self.arguments) else '') + str(self._closeParen)
        return (output + (str(self._ignore) if (self._ignore) else ''), self)
    
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
        ChildProduction.__init__(self, tokens, parent)
        self.qualifiers = None
        if (Qualifiers.peek(tokens)):
            self.qualifiers = Qualifiers(tokens)
        self.rest = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method'
        
    @property
    def name(self):
        if (self.rest.name):
            return self.rest.name
        return self.qualifiers.name if (self.qualifiers) else None
    
    @property
    def methodName(self):
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += ', '.join([argument.name for argument in self.arguments])
            if (self.arguments[-1].variadic):
                name += '...'
        return name + ')'
    
    @property
    def normalName(self):
        return self.methodName
    
    @property
    def arguments(self):
        return self.rest.arguments
    
    def _str(self):
        output = str(self.qualifiers) if (self.qualifiers) else ''
        return output + str(self.rest)
    
    def _markup(self, marker, parent):
        text, target = self.rest._markup(marker, parent)
        text = (str(self.qualifiers) if (self.qualifiers) else '') + text
        return (text, target)

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
        ChildProduction.__init__(self, tokens, parent)
        self.attribute = None
        self.operation = None
        if (Attribute.peek(tokens)):
            self.attribute = Attribute(tokens, parent)
        elif (OperationRest.peek(tokens)):
            self.operation = OperationRest(tokens, parent)
        else:
            self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'attribute' if (self.attribute) else 'method'
        
    @property
    def name(self):
        if (self.attribute):
            return self.attribute.name
        return self.operation.name if (self.operation and self.operation.name) else 'stringifier'

    @property
    def methodName(self):
        if (self.operation):
            name = self.name + '('
            if (self.arguments):
                name += ', '.join([argument.name for argument in self.arguments])
                if (self.arguments[-1].variadic):
                    name += '...'
            return name + ')'
        return None
    
    @property
    def normalName(self):
        if (self.operation):
            return self.methodName
        return self.name
    
    @property
    def arguments(self):
        return self.operation.arguments

    def _str(self):
        if (self.attribute):
            return str(self.attribute)
        elif (self.operation):
            return str(self.operation)
        return ''
    
    def _markup(self, marker, parent):
        if (self.attribute):
            return self.attribute._markup(marker, parent)
        elif (self.operation):
            return self.operation._markup(marker, parent)
        return ('', self)

    def __repr__(self):
        output = '[stringifier'
        if (self.attribute):
            output += ' ' + repr(self.attribute)
        elif (self.operation):
            output += ' ' + repr(self.operation)
        return output + ']'


class AttributeOrOperation(ChildProduction): # "stringifier" StringifierAttributeOrOperation | Attribute | Operation
    @classmethod
    def peek(cls, tokens):
        if (Attribute.peek(tokens) or Operation.peek(tokens)):
            return True
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'stringifier')):
            return tokens.popPosition(StringifierAttributeOrOperation.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.attribute = None
        self.operation = None
        self._stringifier = None
        self.stringifier = None
        if (Attribute.peek(tokens)):
            self.attribute = Attribute(tokens, parent)
        elif (Operation.peek(tokens)):
            self.operation = Operation(tokens, parent)
        else:
            self._stringifier = Symbol(tokens, 'stringifier')
            self.stringifier = StringifierAttributeOrOperation(tokens, parent)
        self._didParse(tokens)

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
            name = self.name + '(' if (self.name) else '('
            if (self.arguments):
                name += ', '.join([argument.name for argument in self.arguments])
                if (self.arguments[-1].variadic):
                    name += '...'
            return name + ')'
        return None
    
    @property
    def normalName(self):
        if (self.operation):
            return self.methodName
        return self.name

    @property
    def arguments(self):
        return self.operation.arguments if (self.operation) else None

    def _str(self):
        if (self.attribute):
            return str(self.attribute)
        return str(self.operation) if (self.operation) else (str(self._stringifier) + str(self.stringifier))

    def _markup(self, marker, parent):
        if (self.attribute):
            return self.attribute._markup(marker, parent)
        if (self.operation):
            return self.operation._markup(marker, parent)
        text, target = self.stringifier._markup(marker, parent)
        text = str(self._stringifier) + text
        return (text, target)
    
    def __repr__(self):
        if (self.attribute):
            return repr(self.attribute)
        return repr(self.operation) if (self.operation) else repr(self.stringifier)


class ExtendedAttributeList(ChildProduction):   # "[" ExtendedAttribute ["," ExtendedAttribute]... "]"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '[')):
            return tokens.popPosition(tokens.peekSymbol(']'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._openBracket = Symbol(tokens, '[')
        self.attributes = []
        self._commas = []
        while (tokens.hasTokens()):
            self.attributes.append(constructs.ExtendedAttribute(tokens, parent))
            token = tokens.sneakPeek()
            if ((not token) or token.isSymbol(']')):
                break
            if (token.isSymbol(',')):
                self._commas.append(Symbol(tokens, ','))
                continue
        self._closeBracket = Symbol(tokens, ']')
        self._didParse(tokens)

    def __len__(self):
        return len(self.attributes)
    
    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for attribute in self.attributes:
                if (key == attribute.name):
                    return attribute
            return None
        return self.attributes[key]
    
    def __iter__(self):
        return iter(self.attributes)
    
    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for attribute in self.attributes:
                if (key == attribute.name):
                    return True
            return False
        return (key in self.attributes)

    def _str(self):
        output = str(self._openBracket)
        output += ''.join([str(attribute) + str(comma) for attribute, comma in itertools.izip_longest(self.attributes, self._commas, fillvalue = '')])
        return output + str(self._closeBracket)
    
    def _markup(self, marker, parent):
        output = str(self._openBracket)
        output += ''.join([attribute.markup(marker,parent) + str(comma) for attribute, comma in itertools.izip_longest(self.attributes, self._commas, fillvalue = '')])
        return (output + str(self._closeBracket), self)
    
    def __repr__(self):
        return '[Extended Attributes: ' + ' '.join([repr(attribute) for attribute in self.attributes]) + '] '

