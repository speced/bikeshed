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
        return self.__unicode__()
    
    def __unicode__(self):
        output = self._leadingSpace + self._unicode()
        output += ''.join([unicode(token) for token in self._tail]) if (self._tail) else ''
        return output + unicode(self._semicolon) + self._trailingSpace

    def _markup(self, generator):
        generator.addText(self._unicode())
        return self

    def markup(self, generator):
        generator.addText(self._leadingSpace)
        target = self._markup(generator)
        if (target._tail):
            generator.addText(''.join([unicode(token) for token in target._tail]))
        generator.addText(unicode(target._semicolon))
        if (self != target):
            generator.addText(target._trailingSpace)
        generator.addText(self._trailingSpace)


    def _consumeSemicolon(self, tokens, consumeTail = True):
        if (Symbol.peek(tokens, ';')):
            self._semicolon = Symbol(tokens, ';', False)
        elif (not Symbol.peek(tokens, '}')):
            if (consumeTail):
                skipped = tokens.syntaxError((';', '}'))
                if (0 < len(skipped)):
                    self._tail = skipped[:-1]
                    tokens.restore(skipped[-1])
                    self._semicolon = Symbol(tokens, ';', False) if (Symbol.peek(tokens, ';')) else ''
            else:
                tokens.syntaxError(None)
        else:
            tokens.syntaxError(None)



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

    def _unicode(self):
        return self.symbol

    def __repr__(self):
        return self.symbol.encode('ascii', 'replace')


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

    def _unicode(self):
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

    def _unicode(self):
        return (unicode(self.unsigned) + unicode(self.type)) if (self.unsigned) else unicode(self.type)

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

    def _unicode(self):
        return self.type

    def __repr__(self):
        return '[FloatType: ' + self.type.encode('ascii', 'replace') + ']'


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

    def _unicode(self):
        return (unicode(self.unrestricted) + unicode(self.type)) if (self.unrestricted) else unicode(self.type)

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

    def _unicode(self):
        return unicode(self.type)

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

    def _unicode(self):
        return unicode(self.type) + (unicode(self.null) if (self.null) else '')
    
    def _markup(self, generator):
        if (isinstance(self.type, basestring)):
            generator.addType(self.type)
            if (self.null):
                generator.addText(self.null)
                return self.null
            return self
        return Production._markup(self, generator)
    
    def __repr__(self):
        return '[ConstType: ' + repr(self.type) + (' [null]' if (self.null) else '') + ']'

class FloatLiteral(Production):  # float | "-Infinity" | "Infinity" | "NaN"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isFloat()):
            return tokens.popPosition(True)
        return tokens.popPosition(token and token.isSymbol(('-Infinity', 'Infinity', 'NaN')))
    
    def __init__(self, tokens): #
        Production.__init__(self, tokens)
        self.value = tokens.next().text
        self._didParse(tokens)

    def _unicode(self):
        return self.value

    def __repr__(self):
        return '[FloatLiteral: ' + self.value.encode('ascii', 'replace') + ']'


class ConstValue(Production):    # "true" | "false" | FloatLiteral | integer | "null"
    @classmethod
    def peek(cls, tokens):
        if (FloatLiteral.peek(tokens)):
            return True
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isSymbol(('true', 'false', 'null')) or token.isInteger()))
    
    def __init__(self, tokens): #
        Production.__init__(self, tokens)
        if (FloatLiteral.peek(tokens)):
            self.value = FloatLiteral(tokens)
        else:
            self.value = tokens.next().text
        self._didParse(tokens)

    def _unicode(self):
        return unicode(self.value)

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

    def _unicode(self):
        return self.value

    def __repr__(self):
        return '[EnumValue: ' + self.value.encode('ascii', 'replace') + ']'


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
                if ((not token) or token.isSymbol('}')):
                    tokens.didIgnore(',')
                    break
                continue
            break
        self._didParse(tokens)

    def _unicode(self):
        return ''.join([unicode(value) + unicode(comma) for value, comma in itertools.izip_longest(self.values, self._commas, fillvalue = '')])

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

    def _unicode(self):
        output = (unicode(self._openBracket) + unicode(self._closeBracket)) if (self.array) else ''
        output += unicode(self.null) if (self.null) else ''
        return output + (unicode(self.suffix) if (self.suffix) else '')

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
    
    def _unicode(self):
        return unicode(self._openBracket) + unicode(self._closeBracket) + (unicode(self.suffix) if (self.suffix) else '')

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

    def _unicode(self):
        return unicode(self.type) + (unicode(self.suffix) if (self.suffix) else '')
    
    def _markup(self, generator):
        self.type.markup(generator)
        return self
    
    def __repr__(self):
        return '[SingleType: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class NonAnyType(Production):   # PrimitiveType [TypeSuffix] | "ByteString" [TypeSuffix] | "DOMString" [TypeSuffix] |
                                # identifier [TypeSuffix] | "sequence" "<" Type ">" [Null] | "object" [TypeSuffix] |
                                # "Date" [TypeSuffix] | "RegExp" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (PrimitiveType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        token = tokens.pushPosition()
        if (token and (token.isSymbol(('ByteString', 'DOMString', 'object', 'Date', 'RegExp')) or token.isIdentifier())):
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
                self.type = Symbol(tokens)  # "ByteString" | "DOMString" | "object" | "Date" | "RegExp"
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)

    def _unicode(self):
        if (self.sequence):
            output = unicode(self.sequence) + unicode(self._openSequence) + unicode(self.type) + unicode(self._closeSequence)
            return output + (unicode(self.null) if (self.null) else '')
        output = unicode(self.type)
        return output + (unicode(self.suffix) if (self.suffix) else '')

    def _markup(self, generator):
        if (isinstance(self.type, basestring)):
            generator.addType(self.type)
            if (self.suffix):
                self.suffix.markup(generator)
            return self
        if (self.sequence):
            generator.addText(self.sequence)
            generator.addText(self._openSequence)
            self.type.markup(generator)
            generator.addText(self._closeSequence)
            generator.addText(self.null)
            return self
        return Production._markup(self, generator)
    
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

    def _unicode(self):
        output = (unicode(self.any) + unicode(self._openBracket) + unicode(self._closeBracket)) if (self.any) else unicode(self.type)
        return output + (unicode(self.suffix) if (self.suffix) else '')
    
    def _markup(self, generator):
        if (self.any):
            generator.addText(self.any)
            generator.addText(self._openBracket)
            generator.addText(self._closeBracket)
        else:
            self.type.markup(generator)
        generator.addText(self.suffix)
        return self

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

    def _unicode(self):
        output = unicode(self._openParen)
        output += ''.join([unicode(type) + unicode(_or) for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = '')])
        return output + unicode(self._closeParen)
    
    def _markup(self, generator):
        generator.addText(self._openParen)
        for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = ''):
            type.markup(generator)
            generator.addText(_or)
        generator.addText(self._closeParen)
        return self
    
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

    def _unicode(self):
        return unicode(self.type) + (unicode(self.suffix) if (self.suffix) else '')

    def _markup(self, generator):
        self.type.markup(generator)
        generator.addText(self.suffix)
        return self
    
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
        tokens.didIgnore(self.text)

    def _unicode(self):
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
            space = tokens.whitespace()
            if (space):
                self.tokens.append(space)
            self.tokens.append(tokens.next())   # "getter"
        else:
            space = tokens.whitespace()
            if (space):
                self.tokens.append(space)
            self.tokens.append(tokens.next())    # "("
            self.tokens += tokens.seekSymbol(')')
        self._didParse(tokens)
        tokens.didIgnore(self.tokens)

    def _unicode(self):
        return ''.join([unicode(token) for token in self.tokens])


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

    def __init__(self, tokens, continuation = False):
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self.inherit = tokens.next().text
        self.next = IgnoreMultipleInheritance(tokens, True) if (IgnoreMultipleInheritance.peek(tokens)) else None
        self._didParse(tokens)
        if (not continuation):
            tokens.didIgnore(self)

    def _unicode(self):
        return unicode(self._comma) + self.inherit + (unicode(self.next) if (self.next) else '')

    def _markup(self, generator):
        generator.addText(self._comma)
        generator.addType(self.inherit)
        if (self.next):
            self.next.markup(generator)
        return self


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

    def _unicode(self):
        return unicode(self._colon) + self.base + (unicode(self._ignore) if (self._ignore) else '')
    
    def _markup(self, generator):
        generator.addText(self._colon)
        generator.addType(self.base)
        if (self._ignore):
            self._ignore.markup(generator)
        return self
    
    def __repr__(self):
        return '[inherits: ' + self.base.encode('ascii', 'replace') + ']'


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

    def _unicode(self):
        return unicode(self._equals) + unicode(self.value)

    def __repr__(self):
        return '[Default: ' + repr(self.value) + ']'


class ArgumentName(Production):   # identifier | ArgumentNameKeyword
    ArgumentNameKeywords = frozenset(['attribute', 'callback', 'const', 'creator', 'deleter', 'dictionary', 'enum', 'exception',
                                      'getter', 'implements', 'inherit', 'interface', 'legacycaller', 'partial', 'serializer',
                                      'setter', 'static', 'stringifier', 'typedef', 'unrestricted'])
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isIdentifier() or (token.isSymbol() and (token.text in cls.ArgumentNameKeywords))))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.name = tokens.next().text
        self._didParse(tokens)

    def _unicode(self):
        return self.name
    
    def _markup(self, generator):
        generator.addName(self.name)
        return self
    
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
    
    def _unicode(self):
        return ''.join([unicode(argument) + unicode(comma) for argument, comma in itertools.izip_longest(self.arguments, self._commas, fillvalue = '')])
    
    def _markup(self, generator):
        for argument, comma in itertools.izip_longest(self.arguments, self._commas, fillvalue = ''):
            argument.markup(generator)
            generator.addText(comma)
        return self

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

    def _unicode(self):
        return unicode(self.type)
    
    def _markup(self, generator):
        return self.type._markup(generator)
    
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

    def _unicode(self):
        return self.name

    def __repr__(self):
        return '[' + self.name.encode('ascii', 'replace') + ']'


class AttributeRest(Production):   # ["readonly"] "attribute" Type identifier [Ignore] ";"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('readonly')):
            token = tokens.peek()
        if (token and token.isSymbol('attribute')):
            if (Type.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)
    
    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._attribute = Symbol(tokens, 'attribute')
        self.type = Type(tokens)
        self.name = tokens.next().text
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    def _unicode(self):
        output = unicode(self.readonly) if (self.readonly) else ''
        return output + unicode(self._attribute) + unicode(self.type) + self.name + (unicode(self._ignore) if (self._ignore) else '')
    
    def _markup(self, generator):
        generator.addText(self.readonly)
        generator.addText(self._attribute)
        self.type.markup(generator)
        generator.addName(self.name)
        if (self._ignore):
            self._ignore.markup(generator)
        return self

    def __repr__(self):
        output = '[AttributeRest: '
        output += '[readonly] ' if (self.readonly) else ''
        return output + repr(self.type) + ' [name: ' + self.name + ']]'


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


class Attribute(ChildProduction):   # ["inherit"] AttributeRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Symbol.peek(tokens, 'inherit')
        return tokens.popPosition(AttributeRest.peek(tokens))
    
    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.inherit = Symbol(tokens, 'inherit') if (Symbol.peek(tokens, 'inherit')) else None
        self.rest = AttributeRest(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'attribute'
    
    @property
    def name(self):
        return self.rest.name
    
    @property
    def arguments(self):
        return None
    
    @property
    def methodName(self):
        return None
    
    def _unicode(self):
        output = unicode(self.inherit) if (self.inherit) else ''
        return output + unicode(self.rest)
    
    def _markup(self, generator):
        generator.addText(self.inherit)
        return self.rest._markup(generator)

    def __repr__(self):
        output = '[attribute: '
        output += '[inherit] ' if (self.inherit) else ''
        return output + repr(self.rest) + ']'


class OperationRest(ChildProduction):   # [identifier] "(" [ArgumentList] ")" [Ignore] ";"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            token = tokens.peek()
        if (token and token.isSymbol('(')):
            ArgumentList.peek(tokens)
            token = tokens.peek()
            return tokens.popPosition(token and token.isSymbol(')'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.name = tokens.next().text if (tokens.sneakPeek().isIdentifier()) else None
        self._openParen = Symbol(tokens, '(')
        self.arguments = ArgumentList(tokens, parent) if (ArgumentList.peek(tokens)) else None
        self._closeParen = Symbol(tokens, ')')
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)
    
    @property
    def idlType(self):
        return 'method'

    def _unicode(self):
        output = self.name if (self.name) else ''
        output += unicode(self._openParen) + (unicode(self.arguments) if (self.arguments) else '') + unicode(self._closeParen)
        return output + (unicode(self._ignore) if (self._ignore) else '')
    
    def _markup(self, generator):
        generator.addName(self.name)
        generator.addText(self._openParen)
        if (self.arguments):
            self.arguments.markup(generator)
        generator.addText(self._closeParen)
        if (self._ignore):
            self._ignore.markup(generator)
        return self
    
    def __repr__(self):
        output = '[OperationRest: '
        output += ('[name: ' + self.name.encode('ascii', 'replace') + '] ') if (self.name) else ''
        return output + '[argumentlist: ' + (repr(self.arguments) if (self.arguments) else '') + ']]'


class Iterator(Production):    # ReturnType "iterator" ["=" identifier | "object"] ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (ReturnType.peek(tokens)):
            if (Symbol.peek(tokens, 'iterator')):
                if (Symbol.peek(tokens, '=')):
                    token = tokens.peek()
                    return tokens.popPosition(token and token.isIdentifier())
                Symbol.peek(tokens, 'object')
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.returnType = ReturnType(tokens)
        self._iterator = Symbol(tokens, 'iterator')
        self._equals = None
        self.interface = None
        self.object = None
        token = tokens.sneakPeek()
        if (token.isSymbol('=')):
            self._equals = Symbol(tokens, '=')
            self.interface = tokens.next().text
        elif (token.isSymbol('object')):
            self.object = Symbol(tokens, 'object')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'iterator'

    @property
    def name(self):
        return None
    
    @property
    def arguments(self):
        return None
    
    @property
    def methodName(self):
        return None
    
    def _unicode(self):
        output = unicode(self.returnType) + unicode(self._iterator)
        if (self._equals):
            output += unicode(self._equals) + self.interface
        elif (self.object):
            output += unicode(self.object)
        return output

    def _markup(self, generator):
        self.returnType.markup(generator)
        generator.addText(self._iterator)
        if (self._equals):
            generator.addText(self._equals)
            generator.addType(self.interface)
        elif (self.object):
            generator.addText(self.object)
        return self

    def __repr__(self):
        output = '[Iterator: ' + repr(self.returnType)
        if (self._equals):
            output += '[interface: ' + self.interface.encode('ascii', 'replace') + ']'
        elif (self.object):
            output += '[object]'
        return output + ']'


class SpecialOperation(ChildProduction):    # Special [Special]... ReturnType OperationRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Special.peek(tokens)):
            while (Special.peek(tokens)):
                pass
            if (ReturnType.peek(tokens)):
                return tokens.popPosition(OperationRest.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.specials = []
        while (Special.peek(tokens)):
            self.specials.append(Special(tokens))
        self.returnType = ReturnType(tokens)
        self.rest = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method'

    @property
    def name(self):
        return self.rest.name if (self.rest.name) else self.specials[0].name

    @property
    def arguments(self):
        return self.rest.arguments

    @property
    def methodName(self):
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += ', '.join([argument.name for argument in self.arguments])
            if (self.arguments[-1].variadic):
                name += '...'
        return name + ')'

    def _unicode(self):
        output = u''.join([unicode(special) for special in self.specials])
        return output + unicode(self.returnType) + unicode(self.rest)

    def _markup(self, generator):
        for special in self.specials:
            special.markup(generator)
        self.returnType.markup(generator)
        return self.rest._markup(generator)

    def __repr__(self):
        output = '[SpecialOperation: ' + ' '.join([repr(special) for special in self.specials])
        return output + ' ' + repr(self.returnType) + ' ' + repr(self.rest) + ']'


class Operation(ChildProduction):   # ReturnType OperationRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (ReturnType.peek(tokens)):
            return tokens.popPosition(OperationRest.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.returnType = ReturnType(tokens)
        self.rest = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method'
        
    @property
    def name(self):
        return self.rest.name

    @property
    def arguments(self):
        return self.rest.arguments
    
    @property
    def methodName(self):
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += ', '.join([argument.name for argument in self.arguments])
            if (self.arguments[-1].variadic):
                name += '...'
        return name + ')'

    def _unicode(self):
        return unicode(self.returnType) + unicode(self.rest)
    
    def _markup(self, generator):
        self.returnType.markup(generator)
        return self.rest._markup(generator)
    
    def __repr__(self):
        return '[Operation: ' + repr(self.returnType) + ' ' + repr(self.rest) + ']'


class Stringifier(ChildProduction): # "stringifier" AttributeRest | "stringifier" ReturnType OperationRest | "stringifier" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'stringifier')):
            if (ReturnType.peek(tokens)):
                return tokens.popPosition(OperationRest.peek(tokens))
            AttributeRest.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._stringifier = Symbol(tokens, 'stringifier')
        self.attribute = None
        self.returnType = None
        self.operation = None
        if (ReturnType.peek(tokens)):
            self.returnType = ReturnType(tokens)
            self.operation = OperationRest(tokens, self)
        elif (AttributeRest.peek(tokens)):
            self.attribute = AttributeRest(tokens)
        else:
            self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'stringifier'
    
    @property
    def name(self):
        if (self.operation):
            return self.operation.name
        return self.attribute.name if (self.attribute) else None
    
    @property
    def arguments(self):
        return self.operation.arguments if (self.operation) else None

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

    def _unicode(self):
        output = unicode(self._stringifier)
        output += (unicode(self.returnType) + unicode(self.operation)) if (self.operation) else ''
        return output + (unicode(self.attribute) if (self.attribute) else '')

    def _markup(self, generator):
        generator.addText(self._stringifier)
        if (self.operation):
            self.returnType.markup(generator)
            return self.operation._markup(generator)
        if (self.attribute):
            return self.attribute._markup(generator)
        return self

    def __repr__(self):
        output = '[Stringifier: '
        if (self.operation):
            output += repr(self.returnType) + ' ' + repr(self.operation)
        else:
            output += repr(self.attribute) if (self.attribute) else ''
        return output + ']'


class Identifiers(Production):  # "," identifier ["," identifier]...
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, ',')):
            token = tokens.peek()
            if (token and token.isIdentifier()):
                Identifiers.peek(tokens)
                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self.name = tokens.next().text
        self.next = Identifiers(tokens) if (Identifiers.peek(tokens)) else None
        self._didParse(tokens)

    def _unicode(self):
        output = unicode(self._comma) + self.name
        return output + (unicode(self.next) if (self.next) else '')

    def __repr__(self):
        return ' ' + self.name.encode('ascii', 'replace') + (repr(self.next) if (self.next) else '')


class SerializationPatternMap(Production):  # "getter" | "attribute" | "inherit" "," "attribute" |
                                            # "inherit" [Identifiers] | identifier [Identifiers]
    @classmethod
    def peek(cls, tokens):
        if (Symbol.peek(tokens, 'getter')):
            return True
        if (Symbol.peek(tokens, 'attribute')):
            return True
        token = tokens.pushPosition()
        if (token and token.isSymbol('inherit')):
            tokens.pushPosition(False)
            if (Symbol.peek(tokens, ',')):
                if (Symbol.peek(tokens, 'attribute')):
                    return tokens.popPosition(tokens.popPosition(True))
            tokens.popPosition(False)
            Identifiers.peek(tokens)
            return tokens.popPosition(True)
        if (token and token.isIdentifier()):
            Identifiers.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._getter = None
        self._attribute = None
        self._inherit = None
        self._comma = None
        self.name = None
        self.next = None
        if (Symbol.peek(tokens, 'getter')):
            self._getter = Symbol(tokens, 'getter')
        elif (Symbol.peek(tokens, 'attribute')):
            self._attribute = Symbol(tokens, 'attribute')
        elif (Symbol.peek(tokens, 'inherit')):
            self._inherit = Symbol(tokens)
            if (Identifiers.peek(tokens)):
                self.next = Identifiers(tokens)
            if (Symbol.peek(tokens, ',')):
                if (Symbol.peek(tokens, 'attribute')):
                    self._comma = Symbol(tokens, ',')
                    self._attribute = Symbol(tokens, 'attribute')
        else:
            self.name = tokens.next().text
            if (Identifiers.peek(tokens)):
                self.next = Identifiers(tokens)
        self._didParse(tokens)

    def _unicode(self):
        output = unicode(self._getter) if (self._getter) else ''
        output += unicode(self._inherit) if (self._inherit) else ''
        output += unicode(self._comma) if (self._comma) else ''
        output += unicode(self._attribute) if (self._attribute) else ''
        output += self.name if (self.name) else ''
        return output + (unicode(self.next) if (self.next) else '')

    def __repr__(self):
        output = '[SerializationPatternMap: '
        output += '[getter] ' if (self._getter) else ''
        output += '[inherit] ' if (self._inherit) else ''
        output += '[attribute] ' if (self._attribute) else ''
        output += self.name.encode('ascii', 'replace') if (self.name) else ''
        output += repr(self.next) if (self.next) else ''
        return output + ']'


class SerializationPatternList(Production): # "getter" | identifer Identifiers
    @classmethod
    def peek(cls, tokens):
        if (Symbol.peek(tokens, 'getter')):
            return True
        token = tokens.pushPosition()
        if (token and token.isIdentifier()):
            Identifiers.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (Symbol.peek(tokens, 'getter')):
            self._getter = Symbol(tokens, 'getter')
            self.name = None
            self.next = None
        else:
            self._getter = None
            self.name = tokens.next().text
            self.next = Identifiers(tokens) if (Identifiers.peek(tokens)) else None
        self._didParse(tokens)

    def _unicode(self):
        output = unicode(self._getter) if (self._getter) else ''
        output += self.name if (self.name) else ''
        return output + (unicode(self.next) if (self.next) else '')

    def __repr__(self):
        output = '[SerializationPatternList: '
        output += '[getter]' if (self._getter) else ''
        output += self.name.encode('ascii', 'replace') if (self.name) else ''
        output += repr(self.next) if (self.next) else ''
        return output + ']'


class SerializationPattern(Production): # "{" [SerializationPatternMap] "}" | "[" [SerializationPatternList] "]" | identifier
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('{')):
            SerializationPatternMap.peek(tokens)
            return tokens.popPosition(Symbol.peek(tokens, '}'))
        elif (token and token.isSymbol('[')):
            SerializationPatternList.peek(tokens)
            return tokens.popPosition(Symbol.peek(tokens, ']'))
        else:
            return tokens.popPosition(token and token.isIdentifier())
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        if (Symbol.peek(tokens, '{')):
            self._open = Symbol(tokens, '{')
            self.pattern = SerializationPatternMap(tokens) if (SerializationPatternMap.peek(tokens)) else None
            self._close = Symbol(tokens, '}')
            self.name = None
        elif (Symbol.peek(tokens, '[')):
            self._open = Symbol(tokens, '[')
            self.pattern = SerializationPatternList(tokens) if (SerializationPatternList.peek(tokens)) else None
            self._close = Symbol(tokens, ']')
            self.name = None
        else:
            self._open = None
            self.pattern = None
            self._close = None
            self.name = tokens.next().text
        self._didParse(tokens)

    def _unicode(self):
        if (self.name):
            return self.name
        output = unicode(self._open)
        output += unicode(self.pattern) if (self.pattern) else ''
        return output + unicode(self._close)

    def __repr__(self):
        output = '[SerializationPattern: '
        output += repr(self.pattern) if (self.pattern) else ''
        output += self.name if (self.name) else ''
        return output + ']'


class Serializer(ChildProduction):  # "serializer" [OperationRest] ";" | "serializer" "=" SerializationPattern ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'serializer')):
            if (Symbol.peek(tokens, '=')):
                return tokens.popPosition(SerializationPattern.peek(tokens))
            OperationRest.peek(tokens)
            return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._serializer = Symbol(tokens, 'serializer')
        if (Symbol.peek(tokens, '=')):
            self._equals = Symbol(tokens, '=')
            self.pattern = SerializationPattern(tokens)
            self.operation = None
        else:
            self._equals = None
            self.pattern = None
            self.operation = OperationRest(tokens, self) if (OperationRest.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'serializer'

    @property
    def name(self):
        return self.operation.name if (self.operation) else None

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
    def arguments(self):
        return self.operation.arguments if (self.operation) else None
    
    def _unicode(self):
        output = unicode(self._serializer)
        if (self.pattern):
            output += unicode(self._equals) + unicode(self.pattern)
        output += unicode(self.operation) if (self.operation) else ''
        return output

    def _markup(self, generator):
        generator.addText(self._serializer)
        if (self.pattern):
            generator.addText(self._equals)
            self.pattern.markup(generator)
        if (self.operation):
            self.operation.markup(generator)
        return self

    def __repr__(self):
        output = '[Serializer: '
        output += repr(self.pattern) if (self.pattern) else ''
        output += repr(self.operation) if (self.operation) else ''
        return output + ']'


class StaticMember(ChildProduction):    # "static" AttributeRest | "static" ReturnType OperationRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'static')):
            if (AttributeRest.peek(tokens)):
                return tokens.popPosition(True)
            if (ReturnType.peek(tokens)):
                return tokens.popPosition(OperationRest.peek(tokens))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._static = Symbol(tokens, 'static')
        if (AttributeRest.peek(tokens)):
            self.attribute = AttributeRest(tokens)
            self.returnType = None
            self.operation = None
        else:
            self.attribute = None
            self.returnType = ReturnType(tokens)
            self.operation = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method' if (self.operation) else 'attribute'
    
    @property
    def name(self):
        return self.operation.name if (self.operation) else self.attribute.name

    @property
    def arguments(self):
        return self.operation.arguments if (self.operation) else None

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

    def _unicode(self):
        output = unicode(self._static)
        if (self.operation):
            return output + unicode(self.returnType) + unicode(self.operation)
        return output + unicode(self.attribute)

    def _markup(self, generator):
        generator.addText(self._static)
        if (self.operation):
            self.returnType.markup(generator)
            return self.operation._markup(generator)
        return self.attribute._markup(generator)

    def __repr__(self):
        output = '[StaticMember: '
        if (self.operation):
            return output + repr(self.returnType) + ' ' + repr(self.operation) + ']'
        return output + repr(self.attribute) + ']'


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

    def _unicode(self):
        output = unicode(self._openBracket)
        output += ''.join([unicode(attribute) + unicode(comma) for attribute, comma in itertools.izip_longest(self.attributes, self._commas, fillvalue = '')])
        return output + unicode(self._closeBracket)
    
    def _markup(self, generator):
        generator.addText(self._openBracket)
        for attribute, comma in itertools.izip_longest(self.attributes, self._commas, fillvalue = ''):
            attribute.markup(generator)
            generator.addText(comma)
        generator.addText(self._closeBracket)
        return self
    
    def __repr__(self):
        return '[Extended Attributes: ' + ' '.join([repr(attribute) for attribute in self.attributes]) + '] '

