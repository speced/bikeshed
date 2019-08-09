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

import constructs, tokenizer
import itertools

def _name(thing):
    return thing.name if (thing) else ''


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

    def _markup(self, generator):
        if (self.symbol in tokenizer.Tokenizer.SymbolIdents):
            generator.addKeyword(self.symbol)
        else:
            generator.addText(self.symbol)
        return self

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
        self._didParse(tokens, False)

    def _unicode(self):
        if (self._space):
            return self._space.join(self.type.split(' '))
        return self.type

    def _markup(self, generator):
        if (self._space):
            keywords = self.type.split(' ')
            generator.addKeyword(keywords[0])
            generator.addText(self._space)
            generator.addKeyword(keywords[1])
        else:
            generator.addKeyword(self.type)
        return self

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
        self._didParse(tokens, False)

    def _unicode(self):
        return (unicode(self.unsigned) + self.type._unicode()) if (self.unsigned) else self.type._unicode()

    def _markup(self, generator):
        if (self.unsigned):
            self.unsigned.markup(generator)
        return self.type._markup(generator)

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
        self._didParse(tokens, False)

    def _unicode(self):
        return self.type

    def _markup(self, generator):
        generator.addKeyword(self.type)
        return self

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
        self._didParse(tokens, False)

    def _unicode(self):
        return (unicode(self.unrestricted) + unicode(self.type)) if (self.unrestricted) else unicode(self.type)

    def _markup(self, generator):
        if (self.unrestricted):
            self.unrestricted.markup(generator)
        return self.type._markup(generator)

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
        self._didParse(tokens, False)

    def _unicode(self):
        if (isinstance(self.type, basestring)):
            return unicode(self.type)
        return self.type._unicode()

    def _markup(self, generator):
        if (isinstance(self.type, basestring)):
            generator.addKeyword(self.type)
            return self
        return self.type._markup(generator)

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
        self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
        self._didParse(tokens)

    def _unicode(self):
        return unicode(self.type) + (unicode(self.null) if (self.null) else '')

    def _markup(self, generator):
        if (isinstance(self.type, basestring)):
            generator.addTypeName(self.type)
            if (self.null):
                generator.addText(self.null)
                return self.null
            return self
        generator.addPrimitiveType(self.type)
        if (self.null):
            self.null.markup(generator)
        return self

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

    def _markup(self, generator):
        if (self.value in tokenizer.Tokenizer.SymbolIdents):
            generator.addKeyword(self.value)
        else:
            generator.addText(self.value)
        return self

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

    def _markup(self, generator):
        if (isinstance(self.value, basestring)):
            if (self.value in tokenizer.Tokenizer.SymbolIdents):
                generator.addKeyword(self.value)
            else:
                generator.addText(self.value)
            return self
        return self.value._markup(generator)

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

    def _markup(self, generator):
        generator.addEnumValue(self.value)
        return self

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

    def _markup(self, generator):
        for value, _comma in itertools.izip_longest(self.values, self._commas, fillvalue = ''):
            value.markup(generator)
            if (_comma):
                _comma.markup(generator)
        return self

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
            self._closeBracket = Symbol(tokens, ']', False)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            self.array = True
            self.null = None
        else:
            self.null = Symbol(tokens, '?', False)
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
            self.array = False
            self._openBracket = None
            self._closeBracket = None
        self._didParse(tokens, False)

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
        self._closeBracket = Symbol(tokens, ']', False)
        self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens, False)

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
            self.typeName = self.type.typeName
            self.suffix = None
        else:
            self.type = Symbol(tokens, 'any', False)
            self.typeName = None
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
        self._didParse(tokens, False)

    @property
    def typeNames(self):
        return [self.typeName]

    def _unicode(self):
        return unicode(self.type) + (unicode(self.suffix) if (self.suffix) else '')

    def _markup(self, generator):
        self.type._markup(generator)
        if (self.suffix):
            self.suffix.markup(generator)
        return self

    def __repr__(self):
        return '[SingleType: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class NonAnyType(Production):   # PrimitiveType [TypeSuffix] | "ByteString" [TypeSuffix] | "DOMString" [TypeSuffix] |
                                # "USVString" TypeSuffix | identifier [TypeSuffix] | "sequence" "<" TypeWithExtendedAttributes ">" [Null] |
                                # "object" [TypeSuffix] | "Error" TypeSuffix | "Promise" "<" ReturnType ">" [Null] | BufferRelatedType [Null] |
                                # "FrozenArray" "<" TypeWithExtendedAttributes ">" [Null] | "record" "<" StringType "," TypeWithExtendedAttributes ">"

    BufferRelatedTypes = frozenset(['ArrayBuffer', 'DataView', 'Int8Array', 'Int16Array', 'Int32Array',
                                    'Uint8Array', 'Uint16Array', 'Uint32Array', 'Uint8ClampedArray',
                                    'Float32Array', 'Float64Array'])
    StringTypes = frozenset(['ByteString', 'DOMString', 'USVString'])
    ObjectTypes = frozenset(['object', 'Error'])

    @classmethod
    def peek(cls, tokens):
        if (PrimitiveType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        token = tokens.pushPosition()
        if (token and (token.isSymbol(cls.StringTypes | cls.ObjectTypes) or token.isIdentifier())):
            TypeSuffix.peek(tokens)
            return tokens.popPosition(True)
        elif (token and token.isSymbol(('sequence', 'FrozenArray'))):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, '>')):
                        Symbol.peek(tokens, '?')
                        return tokens.popPosition(True)
        elif (token and token.isSymbol('Promise')):
            if (Symbol.peek(tokens, '<')):
                if (ReturnType.peek(tokens)):
                    if (Symbol.peek(tokens, '>')):
                        Symbol.peek(tokens, '?')
                        return tokens.popPosition(True)
        elif (token and token.isSymbol(cls.BufferRelatedTypes)):
            Symbol.peek(tokens, '?')
            return tokens.popPosition(True)
        elif (token and token.isSymbol('record')):
            if (Symbol.peek(tokens, '<')):
                if (Symbol.peek(tokens, cls.StringTypes)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            if (Symbol.peek(tokens, '>')):
                                Symbol.peek(tokens, '?')
                                return tokens.popPosition(True)
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.sequence = None
        self.promise = None
        self.record = None
        self._openType = None
        self._closeType = None
        self.null = False
        self.suffix = None
        self.typeName = None
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            token = tokens.sneakPeek()
            if (token.isIdentifier()):
                self.type = tokens.next().text
                self.typeName = self.type
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            elif (token.isSymbol(('sequence', 'FrozenArray'))):
                self.sequence = Symbol(tokens)
                self._openType = Symbol(tokens, '<')
                self.type = TypeWithExtendedAttributes(tokens)
                self._closeType = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.isSymbol('Promise')):
                self.promise = Symbol(tokens, 'Promise')
                self._openType = Symbol(tokens, '<')
                self.type = ReturnType(tokens)
                self._closeType = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.isSymbol(self.BufferRelatedTypes)):
                self.type = Symbol(tokens, None, False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.isSymbol('record')):
                self.record = Symbol(tokens)
                self._openType = Symbol(tokens, '<')
                self.keyType = Symbol(tokens)
                self._comma = Symbol(tokens, ',')
                self.type = TypeWithExtendedAttributes(tokens)
                self._closeType = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            else:
                self.type = Symbol(tokens, None, False)  # string or object
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens, False)

    def _unicode(self):
        if (self.sequence):
            output = unicode(self.sequence) + unicode(self._openType) + unicode(self.type) + unicode(self._closeType)
            return output + (unicode(self.null) if (self.null) else '')
        if (self.promise):
            output = unicode(self.promise) + unicode(self._openType) + unicode(self.type) + unicode(self._closeType)
            return output + (unicode(self.null) if (self.null) else '')
        if (self.record):
            output = unicode(self.record) + unicode(self._openType) + unicode(self.keyType) + unicode(self._comma) + unicode(self.type) + unicode(self._closeType)
            return output + (unicode(self.null) if (self.null) else '')

        output = unicode(self.type)
        output = output + (unicode(self.null) if (self.null) else '')
        return output + (unicode(self.suffix) if (self.suffix) else '')

    def _markup(self, generator):
        if (self.sequence):
            self.sequence.markup(generator)
            generator.addText(self._openType)
            generator.addType(self.type)
            generator.addText(self._closeType)
            generator.addText(self.null)
            return self
        if (self.promise):
            self.promise.markup(generator)
            generator.addText(self._openType)
            self.type.markup(generator)
            generator.addText(self._closeType)
            generator.addText(self.null)
            return self
        if (self.record):
            self.record.markup(generator)
            generator.addText(self._openType)
            generator.addStringType(self.keyType)
            generator.addText(self._comma)
            self.type.markup(generator)
            generator.addText(self._closeType)
            generator.addText(self.null)
            return self
        if (isinstance(self.type, basestring)):
            generator.addTypeName(self.type)
            if (self.suffix):
                self.suffix.markup(generator)
            return self
        if (isinstance(self.type, PrimitiveType)):
            generator.addPrimitiveType(self.type)
        elif (isinstance(self.type, Symbol)):
            if (self.type.symbol in self.BufferRelatedTypes):
                generator.addBufferType(self.type)
            elif (self.type.symbol in self.StringTypes):
                generator.addStringType(self.type)
            elif (self.type.symbol in self.ObjectTypes):
                generator.addObjectType(self.type)
            else:
                assert(False)
        else:
            self.type._markup(generator)
        generator.addText(self.null)
        if (self.suffix):
            self.suffix.markup(generator)
        return self

    def __repr__(self):
        output = '[NonAnyType: ' + ('[sequence] ' if (self.sequence) else '') + ('[Promise] ' if (self.promise) else '') + ('[record] [StringType: ' + repr(self.keyType) + '] ' if (self.record) else '')
        output += repr(self.type) + ('[null]' if (self.null) else '')
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class UnionMemberType(Production):   # [ExtendedAttributeList] NonAnyType | UnionType [TypeSuffix] | "any" "[" "]" [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        if (ExtendedAttributeList.peek(tokens)):
            if (NonAnyType.peek(tokens)):
                return True
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
        self.typeName = None
        self._extendedAttributes = ExtendedAttributeList(tokens, self) if (ExtendedAttributeList.peek(tokens)) else None
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens)
            self.suffix = None
            self.typeName = self.type.typeName
        elif (UnionType.peek(tokens)):
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            self.any = Symbol(tokens, 'any')
            self._openBracket = Symbol(tokens, '[')
            self._closeBracket = Symbol(tokens, ']')
            self.type = 'any[]'
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens, False)

    @property
    def extendedAttributes(self):
        return self._extendedAttributes if (self._extendedAttributes) else {}

    def _unicode(self):
        output = unicode(self._extendedAttributes) if (self._extendedAttributes) else ''
        output += (unicode(self.any) + unicode(self._openBracket) + unicode(self._closeBracket)) if (self.any) else unicode(self.type)
        return output + (unicode(self.suffix) if (self.suffix) else '')

    def _markup(self, generator):
        if (self.any):
            self.any.markup(generator)
            generator.addText(self._openBracket)
            generator.addText(self._closeBracket)
        else:
            if (self._extendedAttributes):
                self._extendedAttributes.markup(generator)
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
        self._closeParen = Symbol(tokens, ')', False)
        self._didParse(tokens, False)

    @property
    def typeNames(self):
        return [type.typeName for type in self.types]

    def _unicode(self):
        output = unicode(self._openParen)
        output += ''.join([unicode(type) + unicode(_or) for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = '')])
        return output + unicode(self._closeParen)

    def _markup(self, generator):
        generator.addText(self._openParen)
        for type, _or in itertools.izip_longest(self.types, self._ors, fillvalue = ''):
            generator.addType(type)
            if (_or):
                _or.markup(generator)
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

    @property
    def typeNames(self):
        return self.type.typeNames

    def _unicode(self):
        return unicode(self.type) + (self.suffix._unicode() if (self.suffix) else '')

    def _markup(self, generator):
        self.type.markup(generator)
        generator.addText(self.suffix)
        return self

    def __repr__(self):
        return '[Type: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class TypeWithExtendedAttributes(Production):  # [ExtendedAttributeList] SingleType | UnionType [TypeSuffix]
    @classmethod
    def peek(cls, tokens):
        ExtendedAttributeList.peek(tokens)
        if (SingleType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return False

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._extendedAttributes = ExtendedAttributeList(tokens, self) if (ExtendedAttributeList.peek(tokens)) else None
        if (SingleType.peek(tokens)):
            self.type = SingleType(tokens)
            self.suffix = None
        else:
            self.type = UnionType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._didParse(tokens)

    @property
    def typeNames(self):
        return self.type.typeNames

    @property
    def extendedAttributes(self):
        return self._extendedAttributes if (self._extendedAttributes) else {}

    def _unicode(self):
        return (unicode(self._extendedAttributes) if (self._extendedAttributes) else '') + unicode(self.type) + (self.suffix._unicode() if (self.suffix) else '')

    def _markup(self, generator):
        if (self._extendedAttributes):
            self._extendedAttributes.markup(generator)
        self.type.markup(generator)
        generator.addText(self.suffix)
        return self

    def __repr__(self):
        return '[TypeWithExtendedAttributes: ' + (repr(self._extendedAttributes) if (self._extendedAttributes) else '') + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


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
        generator.addTypeName(self.inherit)
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
        generator.addTypeName(self.base)
        if (self._ignore):
            self._ignore.markup(generator)
        return self

    def __repr__(self):
        return '[inherits: ' + self.base.encode('ascii', 'replace') + ']'


class Default(Production):   # "=" ConstValue | "=" string | "=" "[" "]" | "=" "{" "}"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, '=')):
            if (ConstValue.peek(tokens)):
                return tokens.popPosition(True)
            if (Symbol.peek(tokens, '[')):
                return tokens.popPosition(Symbol.peek(tokens, ']'))
            if (Symbol.peek(tokens, '{')):
                return tokens.popPosition(Symbol.peek(tokens, '}'))
            token = tokens.peek()
            return tokens.popPosition(token and token.isString())
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._equals = Symbol(tokens, '=')
        self._open = None
        self._close = None
        token = tokens.sneakPeek()
        if (token.isString()):
            self.value = tokens.next().text
        elif (token.isSymbol('[')):
            self._open = Symbol(tokens, '[')
            self._close = Symbol(tokens, ']', False)
            self.value = None
        elif (token.isSymbol('{')):
            self._open = Symbol(tokens, '{')
            self._close = Symbol(tokens, '}', False)
            self.value = None
        else:
            self.value = ConstValue(tokens)
        self._didParse(tokens)

    def _unicode(self):
        return unicode(self._equals) + (unicode(self.value) if (self.value) else unicode(self._open) + unicode(self._close))

    def _markup(self, generator):
        self._equals.markup(generator)
        if (self.value):
            if (isinstance(self.value, basestring)):
                generator.addText(self.value)
                return self
            return self.value._markup(generator)
        self._open.markup(generator)
        self._close.markup(generator)
        return self

    def __repr__(self):
        return '[Default: ' + (repr(self.value) if (self.value) else unicode(self._open) + unicode(self._close)) + ']'


class ArgumentName(Production):   # identifier | ArgumentNameKeyword
    ArgumentNameKeywords = frozenset(['attribute', 'callback', 'const', 'creator', 'deleter', 'dictionary', 'enum',
                                      'getter', 'implements', 'inherit', 'interface', 'iterable', 'legacycaller',
                                      'legacyiterable', 'maplike', 'namespace', 'partial', 'required', 'setlike',
                                      'setter', 'static', 'stringifier', 'typedef', 'unrestricted'])
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        return tokens.popPosition(token and (token.isIdentifier() or (token.isSymbol() and (token.text in cls.ArgumentNameKeywords))))

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self._name = tokens.next().text
        self._didParse(tokens)

    @property
    def name(self):
        return self._name[1:] if ('_' == self._name[0]) else self._name

    def _unicode(self):
        return self._name

    def _markup(self, generator):
        generator.addName(self._name)
        return self

    def __repr__(self):
        return '[ArgumentName: ' + repr(self._name) + ']'


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
            argument = constructs.Argument(tokens, parent)
            if (len(self.arguments)):
                if (self.arguments[-1].variadic):
                    tokens.error('Argument "', argument.name, '" not allowed to follow variadic argument "', self.arguments[-1].name, '"')
                elif ((not self.arguments[-1].required) and argument.required):
                    tokens.error('Required argument "', argument.name, '" cannot follow optional argument "', self.arguments[-1].name, '"')
            self.arguments.append(argument)
            token = tokens.sneakPeek()
        self._didParse(tokens)
        if (parent):
            for index in range(0, len(self.arguments)):
                argument = self.arguments[index]
                if (argument.required):
                    for typeName in argument.type.typeNames:
                        type = parent.parser.getType(typeName)
                        if (type and ('dictionary' == type.idlType) and (not type.required)):    # must be optional unless followed by required argument
                            for index2 in range(index + 1, len(self.arguments)):
                                if (self.arguments[index2].required):
                                    break
                            else:
                                tokens.error('Dictionary argument "', argument.name, '" without required members must be marked optional')

    @property
    def name(self):
        return self.arguments[0].name

    @property   # get all possible variants of argument names
    def argumentNames(self):
        if (self.arguments):
            args = [argument for argument in self.arguments]
            names = []
            name = ', '.join([('...' + argument.name) if (argument.variadic) else argument.name for argument in args])
            names.append(name)
            while (args and (args[-1].optional)):
                args.pop()
                names.append(', '.join([argument.name for argument in args]))
            return names
        return ['']

    def matchesNames(self, argumentNames):
        for name, argument in itertools.izip_longest(argumentNames, self.arguments, fillvalue=None):
            if (name):
                if ((argument is None) or (argument.name != name)):
                    return False
            else:
                if (argument and argument.required):
                    return False
        return True

    def __len__(self):
        return len(self.arguments)

    def keys(self):
        return [argument.name for argument in self.arguments]

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
            self.type = Symbol(tokens, 'void', False)
        else:
            self.type = Type(tokens)
        self._didParse(tokens)

    def _unicode(self):
        return unicode(self.type)

    def _markup(self, generator):
        if (isinstance(self.type, Symbol)):
            self.type._markup(generator)
        else:
            generator.addType(self.type)
        return self

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

    def _markup(self, generator):
        generator.addKeyword(self.name)
        return self

    def __repr__(self):
        return '[' + self.name.encode('ascii', 'replace') + ']'


class AttributeRest(Production):   # ["readonly"] "attribute" TypeWithExtendedAttributes ("required" | identifier) [Ignore] ";"
    @classmethod
    def peek(cls, tokens):
        token = tokens.pushPosition()
        if (token and token.isSymbol('readonly')):
            token = tokens.peek()
        if (token and token.isSymbol('attribute')):
            if (TypeWithExtendedAttributes.peek(tokens)):
                token = tokens.peek()
                return tokens.popPosition(token and (token.isIdentifier() or token.isSymbol('required')))
        return tokens.popPosition(False)

    def __init__(self, tokens):
        Production.__init__(self, tokens)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._attribute = Symbol(tokens, 'attribute')
        self.type = TypeWithExtendedAttributes(tokens)
        self.name = tokens.next().text
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    def _unicode(self):
        output = unicode(self.readonly) if (self.readonly) else ''
        output += unicode(self._attribute) + unicode(self.type)
        output += self.name
        return output + (unicode(self._ignore) if (self._ignore) else '')

    def _markup(self, generator):
        if (self.readonly):
            self.readonly.markup(generator)
        self._attribute.markup(generator)
        generator.addType(self.type)
        generator.addName(self.name)
        if (self._ignore):
            self._ignore.markup(generator)
        return self

    def __repr__(self):
        output = '[AttributeRest: '
        output += '[readonly] ' if (self.readonly) else ''
        output += repr(self.type)
        output += ' [name: ' + self.name + ']'
        return output + ']'


class ChildProduction(Production):
    def __init__(self, tokens, parent):
        Production.__init__(self, tokens)
        self.parent = parent

    @property
    def fullName(self):
        return self.parent.fullName + '/' + self.normalName if (self.parent) else self.normalName

    @property
    def methodName(self):
        return None

    @property
    def methodNames(self):
        return []

    @property
    def normalName(self):
        return self.methodName if (self.methodName) else self.name

    @property
    def parser(self):
        return self.parent.parser


class MixinAttribute(ChildProduction):   # ReadOnly AttributeRest
    @classmethod
    def peek(cls, tokens):
        return AttributeRest.peek(tokens)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.attribute = AttributeRest(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'attribute'

    @property
    def stringifier(self):
        return False

    @property
    def name(self):
        return self.attribute.name

    @property
    def arguments(self):
        return None

    def _unicode(self):
        return unicode(self.attribute)

    def _markup(self, generator):
        return self.attribute._markup(generator)

    def __repr__(self):
        output = '[attribute: '
        return output + repr(self.attribute) + ']'


class Attribute(ChildProduction):   # ["inherit"] AttributeRest
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Symbol.peek(tokens, 'inherit')
        return tokens.popPosition(AttributeRest.peek(tokens))

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.inherit = Symbol(tokens, 'inherit') if (Symbol.peek(tokens, 'inherit')) else None
        self.attribute = AttributeRest(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'attribute'

    @property
    def stringifier(self):
        return False

    @property
    def name(self):
        return self.attribute.name

    @property
    def arguments(self):
        return None

    def _unicode(self):
        output = unicode(self.inherit) if (self.inherit) else ''
        return output + unicode(self.attribute)

    def _markup(self, generator):
        if (self.inherit):
            self.inherit.markup(generator)
        return self.attribute._markup(generator)

    def __repr__(self):
        output = '[attribute: '
        output += '[inherit] ' if (self.inherit) else ''
        return output + repr(self.attribute) + ']'


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

    @property
    def argumentNames(self):
        return self.arguments.argumentNames if (self.arguments) else ['']

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


class Iterable(ChildProduction):     # "iterable" "<" TypeWithExtendedAttributes ["," TypeWithExtendedAttributes] ">" ";" | "legacyiterable" "<" Type ">" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'iterable')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            token = tokens.peek()
                            return tokens.popPosition(token and token.isSymbol('>'))
                    token = tokens.peek()
                    return tokens.popPosition(token and token.isSymbol('>'))
        elif (Symbol.peek(tokens, 'legacyiterable')):
            if (Symbol.peek(tokens, '<')):
                if (Type.peek(tokens)):
                    token = tokens.peek()
                    return tokens.popPosition(token and token.isSymbol('>'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._iterable = Symbol(tokens)
        self._openType = Symbol(tokens, '<')
        self.type = TypeWithExtendedAttributes(tokens)
        if (Symbol.peek(tokens, ',')):
            self.keyType = self.type
            self.type = None
            self._comma = Symbol(tokens)
            self.valueType = TypeWithExtendedAttributes(tokens)
        else:
            self.keyType = None
            self.valueType = None
        self._closeType = Symbol(tokens, '>')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'iterable'

    @property
    def name(self):
        return '__iterable__'

    @property
    def arguments(self):
        return None

    def _unicode(self):
        output = unicode(self._iterable) + unicode(self._openType)
        if (self.type):
            output += unicode(self.type)
        else:
            output += unicode(self.keyType) + unicode(self._comma) + unicode(self.valueType)
        return output + unicode(self._closeType)

    def _markup(self, generator):
        self._iterable.markup(generator)
        generator.addText(self._openType)
        if (self.type):
            generator.addType(self.type)
        else:
            generator.addType(self.keyType)
            generator.addText(self._comma)
            generator.addType(self.valueType)
        generator.addText(self._closeType)
        return self

    def __repr__(self):
        output = '[Iterable: '
        if (self.type):
            output += repr(self.type)
        else:
            output += repr(self.keyType) + ' ' + repr(self.valueType)
        return output + ']'


class AsyncIterable(ChildProduction):     # "async iterable" "<" TypeWithExtendedAttributes "," TypeWithExtendedAttributes ">" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        if (Symbol.peek(tokens, 'async')):
            if (Symbol.peek(tokens, 'iterable')):
                if (Symbol.peek(tokens, '<')):
                    if (TypeWithExtendedAttributes.peek(tokens)):
                        if (Symbol.peek(tokens, ',')):
                            if (TypeWithExtendedAttributes.peek(tokens)):
                                token = tokens.peek()
                                return tokens.popPosition(token and token.isSymbol('>'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self._async = Symbol(tokens)
        self._iterable = Symbol(tokens)
        self._openType = Symbol(tokens, '<')
        self.keyType = TypeWithExtendedAttributes(tokens)
        self._comma = Symbol(tokens)
        self.valueType = TypeWithExtendedAttributes(tokens)
        self._closeType = Symbol(tokens, '>')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'async-iterable'

    @property
    def name(self):
        return '__async_iterable__'

    @property
    def arguments(self):
        return None

    def _unicode(self):
        output = unicode(self._async) + unicode(self._iterable) + unicode(self._openType)
        output += unicode(self.keyType) + unicode(self._comma) + unicode(self.valueType)
        return output + unicode(self._closeType)

    def _markup(self, generator):
        self._async.markup(generator)
        self._iterable.markup(generator)
        generator.addText(self._openType)
        generator.addType(self.keyType)
        generator.addText(self._comma)
        generator.addType(self.valueType)
        generator.addText(self._closeType)
        return self

    def __repr__(self):
        output = '[AsyncIterable: '
        output += repr(self.keyType) + ' ' + repr(self.valueType)
        return output + ']'


class Maplike(ChildProduction):      # ["readonly"] "maplike" "<" TypeWithExtendedAttributes "," TypeWithExtendedAttributes ">" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Symbol.peek(tokens, 'readonly')
        if (Symbol.peek(tokens, 'maplike')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            return tokens.popPosition(Symbol.peek(tokens, '>'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._maplike = Symbol(tokens, 'maplike')
        self._openType = Symbol(tokens, '<')
        self.keyType = TypeWithExtendedAttributes(tokens)
        self._comma = Symbol(tokens, ',')
        self.valueType = TypeWithExtendedAttributes(tokens)
        self._closeType = Symbol(tokens, '>')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'maplike'

    @property
    def name(self):
        return '__maplike__'

    @property
    def arguments(self):
        return None

    def _unicode(self):
        output = unicode(self.readonly) if (self.readonly) else ''
        output += unicode(self._maplike) + unicode(self._openType) + unicode(self.keyType) + unicode(self._comma)
        return output + unicode(self.valueType) + unicode(self._closeType)

    def _markup(self, generator):
        if (self.readonly):
            self.readonly.markup(generator)
        self._maplike.markup(generator)
        generator.addText(self._openType)
        generator.addType(self.keyType)
        generator.addText(self._comma)
        generator.addType(self.valueType)
        generator.addText(self._closeType)
        return self

    def __repr__(self):
        output = '[Maplike: ' + '[readonly] ' if (self.readonly) else ''
        output += repr(self.keyType) + ' ' + repr(self.valueType)
        return output + ']'


class Setlike(ChildProduction):      # ["readonly"] "setlike" "<" TypeWithExtendedAttributes ">" ";"
    @classmethod
    def peek(cls, tokens):
        tokens.pushPosition(False)
        Symbol.peek(tokens, 'readonly')
        if (Symbol.peek(tokens, 'setlike')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    return tokens.popPosition(Symbol.peek(tokens, '>'))
        return tokens.popPosition(False)

    def __init__(self, tokens, parent):
        ChildProduction.__init__(self, tokens, parent)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._setlike = Symbol(tokens, 'setlike')
        self._openType = Symbol(tokens, '<')
        self.type = TypeWithExtendedAttributes(tokens)
        self._closeType = Symbol(tokens, '>')
        self._consumeSemicolon(tokens)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'setlike'

    @property
    def name(self):
        return '__setlike__'

    @property
    def arguments(self):
        return None

    def _unicode(self):
        output = unicode(self.readonly) if (self.readonly) else ''
        return output + unicode(self._setlike) + unicode(self._openType) + unicode(self.type) + unicode(self._closeType)

    def _markup(self, generator):
        if (self.readonly):
            self.readonly.markup(generator)
        self._setlike.markup(generator)
        generator.addText(self._openType)
        generator.addType(self.type)
        generator.addText(self._closeType)
        return self

    def __repr__(self):
        output = '[Setlike: ' + ('[readonly] ' if (self.readonly) else '')
        return output + repr(self.type) + ']'


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
        self.operation = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method'

    @property
    def name(self):
        return self.operation.name if (self.operation.name) else ('__' + self.specials[0].name + '__')

    @property
    def arguments(self):
        return self.operation.arguments

    @property
    def methodName(self):
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += self.arguments.argumentNames[0]
        return name + ')'

    @property
    def methodNames(self):
        if (self.arguments):
            return [_name(self) + '(' + argumentName + ')' for argumentName in self.arguments.argumentNames]
        return [self.methodName]

    def _unicode(self):
        output = u''.join([unicode(special) for special in self.specials])
        return output + unicode(self.returnType) + unicode(self.operation)

    def _markup(self, generator):
        for special in self.specials:
            special.markup(generator)
        self.returnType.markup(generator)
        return self.operation._markup(generator)

    def __repr__(self):
        output = '[SpecialOperation: ' + ' '.join([repr(special) for special in self.specials])
        return output + ' ' + repr(self.returnType) + ' ' + repr(self.operation) + ']'


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
        self.operation = OperationRest(tokens, self)
        self._didParse(tokens)

    @property
    def idlType(self):
        return 'method'

    @property
    def name(self):
        return self.operation.name

    @property
    def arguments(self):
        return self.operation.arguments

    @property
    def methodName(self):
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += self.arguments.argumentNames[0]
        return name + ')'

    @property
    def methodNames(self):
        if (self.arguments):
            return [_name(self) + '(' + argumentName + ')' for argumentName in self.arguments.argumentNames]
        return [self.methodName]

    def _unicode(self):
        return unicode(self.returnType) + unicode(self.operation)

    def _markup(self, generator):
        self.returnType.markup(generator)
        return self.operation._markup(generator)

    def __repr__(self):
        return '[Operation: ' + repr(self.returnType) + ' ' + repr(self.operation) + ']'


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
        return 'attribute' if (self.attribute) else 'stringifier'

    @property
    def stringifier(self):
        return True

    @property
    def name(self):
        if (self.operation):
            return self.operation.name if (self.operation.name) else '__stringifier__'
        return self.attribute.name if (self.attribute and self.attribute.name) else '__stringifier__'

    @property
    def arguments(self):
        return self.operation.arguments if (self.operation) else None

    @property
    def methodName(self):
        if (self.operation):
            name = self.name + '(' if (self.name) else '('
            if (self.arguments):
                name += self.arguments.argumentNames[0]
            return name + ')'
        return None

    @property
    def methodNames(self):
        if (self.operation):
            if (self.arguments):
                return [_name(self) + '(' + argumentName + ')' for argumentName in self.arguments.argumentNames]
            return [self.methodName]
        return []

    def _unicode(self):
        output = unicode(self._stringifier)
        output += (unicode(self.returnType) + unicode(self.operation)) if (self.operation) else ''
        return output + (unicode(self.attribute) if (self.attribute) else '')

    def _markup(self, generator):
        self._stringifier.markup(generator)
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
    def stringifier(self):
        return False

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
                name += self.arguments.argumentNames[0]
            return name + ')'
        return None

    @property
    def methodNames(self):
        if (self.operation):
            if (self.arguments):
                return [_name(self) + '(' + argumentName + ')' for argumentName in self.arguments.argumentNames]
            return [self.methodName]
        return []

    def _unicode(self):
        output = unicode(self._static)
        if (self.operation):
            return output + unicode(self.returnType) + unicode(self.operation)
        return output + unicode(self.attribute)

    def _markup(self, generator):
        self._static.markup(generator)
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

    def keys(self):
        return [attribute.name for attribute in self.attributes]

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

