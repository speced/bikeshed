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
"""Basic language productions for WebIDL."""


import itertools
from typing import Any, Container, Iterator, List, Optional, Sequence, Tuple, Union, cast

from . import constructs, tokenizer
from . import protocols
from .tokenizer import Token, Tokenizer


def _name(thing: Any) -> str:
    return getattr(thing, 'name', '') if (thing) else ''


class Production(object):
    """
    Base class for all productions.

    Consumes leading and optionally trailing whitespace,
    also may consume following semicolon.
    """

    leading_space: str
    _tail: Optional[List[tokenizer.Token]]
    semicolon: Union[str, protocols.Production]
    trailing_space: str

    def __init__(self, tokens: Tokenizer) -> None:
        self.leading_space = self._whitespace(tokens)
        self._tail = None
        self.semicolon = ''

    def _did_parse(self, tokens: Tokenizer, include_trailing_space: bool = True) -> None:
        self.trailing_space = self._whitespace(tokens) if (include_trailing_space) else ''

    def _whitespace(self, tokens: Tokenizer) -> str:
        whitespace = tokens.whitespace()
        return whitespace.text if (whitespace) else ''

    @property
    def idl_type(self) -> str:
        raise NotImplementedError

    @property
    def name(self) -> Optional[str]:
        return None

    @property
    def tail(self) -> str:
        return ''.join([str(token) for token in self._tail]) if (self._tail) else ''

    def _str(self) -> str:
        """Return self as string without leading or trailing space or semicolon."""
        raise NotImplementedError

    def __str__(self) -> str:
        return self.leading_space + self._str() + self.tail + str(self.semicolon) + self.trailing_space

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self._str())
        return self

    def define_markup(self, generator: protocols.MarkupGenerator) -> None:
        generator.add_text(self.leading_space)
        target = self._define_markup(generator)
        generator.add_text(target.tail)
        generator.add_text(str(target.semicolon))
        if (self != target):
            generator.add_text(target.trailing_space)
        generator.add_text(self.trailing_space)

    def _consume_semicolon(self, tokens: Tokenizer, consume_tail: bool = True) -> None:
        if (Symbol.peek(tokens, ';')):
            self.semicolon = Symbol(tokens, ';', False)
        elif (not Symbol.peek(tokens, '}')):
            if (consume_tail):
                skipped = tokens.syntax_error((';', '}'))
                if (skipped):
                    self._tail = skipped[:-1]
                    tokens.restore(skipped[-1])
                    self.semicolon = Symbol(tokens, ';', False) if (Symbol.peek(tokens, ';')) else ''
            else:
                tokens.syntax_error(None)
        else:
            tokens.syntax_error(None)


class ChildProduction(Production):
    """Base class for productions that have parents."""

    parent: Optional[protocols.ChildProduction]

    def __init__(self, tokens: Tokenizer, parent: Optional[protocols.ChildProduction]) -> None:
        Production.__init__(self, tokens)
        self.parent = parent

    @property
    def full_name(self) -> Optional[str]:
        if (not self.normal_name):
            return None
        return self.parent.full_name + '/' + self.normal_name if (self.parent and self.parent.full_name) else self.normal_name

    @property
    def normal_name(self) -> Optional[str]:
        return self.method_name if (self.method_name) else self.name

    @property
    def method_name(self) -> Optional[str]:
        return None

    @property
    def method_names(self) -> List[str]:
        return []

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    @property
    def symbol_table(self) -> Optional[protocols.SymbolTable]:
        return self.parent.symbol_table if (self.parent) else None


class String(Production):
    """
    String production.

    Syntax:
    <string-token>
    """

    string: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_string())

    def __init__(self, tokens: Tokenizer, include_trailing_space: bool = True) -> None:
        Production.__init__(self, tokens)
        self.string = next(tokens).text
        self._did_parse(tokens, include_trailing_space)

    def _str(self) -> str:
        return self.string

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self.string)
        return self

    def __repr__(self) -> str:
        return self.string


class Symbol(Production):
    """
    String literal production.

    Syntax:
    <symbol-token>
    """

    symbol: str

    @classmethod
    def peek(cls, tokens: Tokenizer, symbol: Union[str, Container[str]] = None) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_symbol(symbol))

    def __init__(self, tokens: Tokenizer, symbol: Union[str, Container[str]] = None, include_trailing_space: bool = True) -> None:
        Production.__init__(self, tokens)
        self.symbol = next(tokens).text
        if (symbol):
            assert(self.symbol == symbol)
        self._did_parse(tokens, include_trailing_space)

    def _str(self) -> str:
        return self.symbol

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.symbol in tokenizer.Tokenizer.SYMBOL_IDENTS):
            generator.add_keyword(self.symbol)
        else:
            generator.add_text(self.symbol)
        return self

    def __repr__(self) -> str:
        return self.symbol


class Integer(Production):
    """
    Integer literal production.

    Syntax:
    <integer-token>
    """

    integer: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_integer())

    def __init__(self, tokens: Tokenizer, include_trailing_space: bool = True) -> None:
        Production.__init__(self, tokens)
        self.integer = next(tokens).text
        self._did_parse(tokens, include_trailing_space)

    def _str(self) -> str:
        return self.integer

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self.integer)
        return self

    def __repr__(self) -> str:
        return self.integer


class IntegerType(Production):
    """
    Integer type production.

    Syntax:
    "short" | "long" ["long"]
    """

    type: str
    _space: Optional[str]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        if (token and token.is_symbol()):
            if ('long' == token.text):
                token = tokens.push_position()
                tokens.pop_position((token is not None) and token.is_symbol('long'))
                return tokens.pop_position(True)
            return tokens.pop_position('short' == token.text)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._space = None
        token = next(tokens)
        if ('long' == token.text):
            self.type = 'long'
            next_token = tokens.sneak_peek()
            if (next_token and next_token.is_symbol('long')):
                self._space = self._whitespace(tokens)
                self.type += ' ' + next(tokens).text
        else:
            self.type = token.text
        self._did_parse(tokens, False)

    def _str(self) -> str:
        if (self._space):
            return self._space.join(self.type.split(' '))
        return self.type

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self._space):
            keywords = self.type.split(' ')
            generator.add_keyword(keywords[0])
            generator.add_text(self._space)
            generator.add_keyword(keywords[1])
        else:
            generator.add_keyword(self.type)
        return self

    def __repr__(self) -> str:
        return '[IntegerType: ' + self.type + ']'


class UnsignedIntegerType(Production):
    """
    Unsigned integer type production.

    Syntax:
    "unsigned" IntegerType | IntegerType
    """

    unsigned: Optional[Symbol]
    type: IntegerType

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (IntegerType.peek(tokens)):
            return True
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'unsigned')):
            return tokens.pop_position(IntegerType.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.unsigned = Symbol(tokens, 'unsigned') if (Symbol.peek(tokens, 'unsigned')) else None
        self.type = IntegerType(tokens)
        self._did_parse(tokens, False)

    def _str(self) -> str:
        return (str(self.unsigned) + self.type._str()) if (self.unsigned) else self.type._str()

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.unsigned):
            self.unsigned.define_markup(generator)
        return self.type._define_markup(generator)

    def __repr__(self) -> str:
        return '[UnsignedIntegerType: ' + ('[unsigned]' if (self.unsigned) else '') + repr(self.type) + ']'


class FloatType(Production):
    """
    Float type production.

    Syntax:
    "float" | "double"
    """

    type: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and (token.is_symbol(('float', 'double'))))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        token = next(tokens)
        self.type = token.text
        self._did_parse(tokens, False)

    def _str(self) -> str:
        return self.type

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_keyword(self.type)
        return self

    def __repr__(self) -> str:
        return '[FloatType: ' + self.type + ']'


class UnrestrictedFloatType(Production):
    """
    Unrestricted float type production.

    Syntax:
    "unrestricted" FloatType | FloatType
    """

    unrestricted: Optional[Symbol]
    type: FloatType

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (FloatType.peek(tokens)):
            return True
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'unrestricted')):
            return tokens.pop_position(FloatType.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.unrestricted = Symbol(tokens, 'unrestricted') if (Symbol.peek(tokens, 'unrestricted')) else None
        self.type = FloatType(tokens)
        self._did_parse(tokens, False)

    def _str(self) -> str:
        return (str(self.unrestricted) + str(self.type)) if (self.unrestricted) else str(self.type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.unrestricted):
            self.unrestricted.define_markup(generator)
        return self.type._define_markup(generator)

    def __repr__(self) -> str:
        return '[UnrestrictedFloatType: ' + ('[unrestricted]' if (self.unrestricted) else '') + repr(self.type) + ']'


class PrimitiveType(Production):
    """
    Primitive type production.

    Syntax:
    UnsignedIntegerType | UnrestrictedFloatType | "boolean" | "byte" | "octet"
    """

    type: Union[UnsignedIntegerType, UnrestrictedFloatType, Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        return (UnsignedIntegerType.peek(tokens) or UnrestrictedFloatType.peek(tokens) or Symbol.peek(tokens, ('boolean', 'byte', 'octet')))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        if (UnsignedIntegerType.peek(tokens)):
            self.type = UnsignedIntegerType(tokens)
        elif (UnrestrictedFloatType.peek(tokens)):
            self.type = UnrestrictedFloatType(tokens)
        else:
            self.type = Symbol(tokens, None, False)
        self._did_parse(tokens, False)

    @property
    def type_name(self) -> Optional[str]:
        return str(self.type)

    def _str(self) -> str:
        return self.type._str()

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        return self.type._define_markup(generator)

    def __repr__(self) -> str:
        return '[PrimitiveType: ' + repr(self.type) + ']'


class Identifier(Production):
    """
    Identifier production.

    Syntax:
    <identifier-token>
    """

    _name: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position(True)
        return tokens.pop_position((token is not None) and token.is_identifier())

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = next(tokens).text
        self._did_parse(tokens, False)

    @property
    def name(self) -> Optional[str]:
        return self._name[1:] if ('_' == self._name[0]) else self._name

    def _str(self) -> str:
        return str(self._name)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_name(self._name)
        return self

    def __repr__(self) -> str:
        return self._name


class TypeIdentifier(Production):
    """
    Type identifier production.

    Syntax:
    <identifier-token>
    """

    _name: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position(True)
        return tokens.pop_position((token is not None) and token.is_identifier())

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = next(tokens).text
        self._did_parse(tokens, False)

    @property
    def name(self) -> Optional[str]:
        return self._name[1:] if ('_' == self._name[0]) else self._name

    @property
    def type_name(self) -> Optional[str]:
        return self.name

    def _str(self) -> str:
        return str(self._name)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_type_name(self._name)
        return self

    def __repr__(self) -> str:
        return self._name


class ConstType(Production):
    """
    Const type production.

    Syntax:
    PrimitiveType [Null] | TypeIdentifier [Null]
    """

    type: Union[PrimitiveType, TypeIdentifier]
    null: Optional[Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (PrimitiveType.peek(tokens)):
            Symbol.peek(tokens, '?')
            return True
        tokens.push_position(False)
        if (TypeIdentifier.peek(tokens)):
            Symbol.peek(tokens, '?')
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
        else:
            self.type = TypeIdentifier(tokens)
        self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
        self._did_parse(tokens)

    @property
    def type_name(self) -> Optional[str]:
        return self.type.type_name

    def _str(self) -> str:
        return str(self.type) + (str(self.null) if (self.null) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (isinstance(self.type, TypeIdentifier)):
            self.type.define_markup(generator)
            if (self.null):
                generator.add_text(self.null)
                return self.null
            return self
        generator.add_primitive_type(self.type)
        if (self.null):
            self.null.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[ConstType: ' + repr(self.type) + (' [null]' if (self.null) else '') + ']'


class FloatLiteral(Production):
    """
    Float literal production.

    Syntax:
    <float-token> | "-Infinity" | "Infinity" | "NaN"
    """

    value: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        if (token and token.is_float()):
            return tokens.pop_position(True)
        return tokens.pop_position((token is not None) and token.is_symbol(('-Infinity', 'Infinity', 'NaN')))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.value = next(tokens).text
        self._did_parse(tokens)

    def _str(self) -> str:
        return self.value

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.value in tokenizer.Tokenizer.SYMBOL_IDENTS):
            generator.add_keyword(self.value)
        else:
            generator.add_text(self.value)
        return self

    def __repr__(self) -> str:
        return '[FloatLiteral: ' + self.value + ']'


class ConstValue(Production):
    """
    Const value production.

    Syntax:
    "true" | "false" | FloatLiteral | <integer-token> | "null"
    """

    value: Union[FloatLiteral, Symbol, Integer]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (FloatLiteral.peek(tokens)):
            return True
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and (token.is_symbol(('true', 'false', 'null')) or token.is_integer()))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        if (FloatLiteral.peek(tokens)):
            self.value = FloatLiteral(tokens)
        elif (Symbol.peek(tokens)):
            self.value = Symbol(tokens, None, False)
        else:
            self.value = Integer(tokens)
        self._did_parse(tokens)

    def _str(self) -> str:
        return str(self.value)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (isinstance(self.value, str)):
            if (self.value in tokenizer.Tokenizer.SYMBOL_IDENTS):
                generator.add_keyword(self.value)
            else:
                generator.add_text(self.value)
            return self
        return self.value._define_markup(generator)

    def __repr__(self) -> str:
        return '[ConstValue: ' + repr(self.value) + ']'


class EnumValue(Production):
    """
    Enum value production.

    Syntax:
    <string-token>
    """

    value: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_string())

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.value = next(tokens).text
        self._did_parse(tokens)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_enum_value(self.value)
        return self

    def _str(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return '[EnumValue: ' + self.value + ']'


class EnumValueList(Production):
    """
    Enum value list production.

    Syntax:
    EnumValue ["," EnumValue]... [","]
    """

    values: List[EnumValue]
    _commas: List[Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (EnumValue.peek(tokens)):
            token = tokens.push_position()
            if (token and token.is_symbol(',')):
                token = tokens.sneak_peek()
                if (token and token.is_symbol('}')):
                    return tokens.pop_position(tokens.pop_position(True))
                return tokens.pop_position(tokens.pop_position(EnumValueList.peek(tokens)))
            tokens.pop_position(False)
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.values = []
        self._commas = []
        while (tokens.has_tokens()):
            self.values.append(EnumValue(tokens))
            if (Symbol.peek(tokens, ',')):
                self._commas.append(Symbol(tokens, ','))
                token = tokens.sneak_peek()
                if ((not token) or token.is_symbol('}')):
                    tokens.did_ignore(',')
                    break
                continue
            break
        self._did_parse(tokens)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        for value, _comma in itertools.zip_longest(self.values, self._commas, fillvalue=''):
            value.define_markup(generator)
            if (_comma):
                _comma.define_markup(generator)
        return self

    def _str(self) -> str:
        return ''.join([str(value) + str(comma) for value, comma in itertools.zip_longest(self.values, self._commas, fillvalue='')])

    def __repr__(self) -> str:
        return '[EnumValueList: ' + ''.join([repr(value) for value in self.values]) + ']'


class TypeSuffix(Production):
    """
    Type suffix production.

    Syntax:
    "[" "]" [TypeSuffix] | "?" [TypeSuffixStartingWithArray]
    """

    _open_bracket: Optional[Symbol]
    _close_bracket: Optional[Symbol]
    suffix: Optional[Union['TypeSuffix', 'TypeSuffixStartingWithArray']]
    array: bool
    null: Optional[Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, '[')):
            if (Symbol.peek(tokens, ']')):
                TypeSuffix.peek(tokens)
                return tokens.pop_position(True)
        elif (Symbol.peek(tokens, '?')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        if (Symbol.peek(tokens, '[')):
            self._open_bracket = Symbol(tokens, '[')
            self._close_bracket = Symbol(tokens, ']', False)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            self.array = True
            self.null = None
        else:
            self.null = Symbol(tokens, '?', False)
            self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
            self.array = False
            self._open_bracket = None
            self._close_bracket = None
        self._did_parse(tokens, False)

    def _str(self) -> str:
        output = (str(self._open_bracket) + str(self._close_bracket)) if (self.array) else ''
        output += str(self.null) if (self.null) else ''
        return output + (str(self.suffix) if (self.suffix) else '')

    def __repr__(self) -> str:
        output = '[TypeSuffix: ' + ('[array] ' if (self.array) else '') + ('[null] ' if (self.null) else '')
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class TypeSuffixStartingWithArray(Production):
    """
    Type suffix starting with array production.

    Syntax:
    "[" "]" [TypeSuffix]
    """

    _open_bracket: Symbol
    _close_bracket: Symbol
    suffix: Optional[TypeSuffix]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, '[')):
            if (Symbol.peek(tokens, ']')):
                TypeSuffix.peek(tokens)
                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._open_bracket = Symbol(tokens, '[')
        self._close_bracket = Symbol(tokens, ']', False)
        self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._did_parse(tokens, False)

    def _str(self) -> str:
        return str(self._open_bracket) + str(self._close_bracket) + (str(self.suffix) if (self.suffix) else '')

    def __repr__(self) -> str:
        return '[TypeSuffixStartingWithArray: ' + (repr(self.suffix) if (self.suffix) else '') + ']'


class AnyType(Production):
    """
    Any type production.

    Syntax:
    "any" [TypeSuffixStartingWithArray]
    """

    any: Symbol
    suffix: Optional[TypeSuffixStartingWithArray]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'any')):
            TypeSuffixStartingWithArray.peek(tokens)
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.any = Symbol(tokens, 'any', False)
        self.suffix = TypeSuffixStartingWithArray(tokens) if (TypeSuffixStartingWithArray.peek(tokens)) else None
        self._did_parse(tokens, False)

    @property
    def type_name(self) -> Optional[str]:
        return None

    @property
    def type_names(self) -> List[str]:
        return []

    def _str(self) -> str:
        return str(self.any) + (str(self.suffix) if (self.suffix) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self.any.define_markup(generator)
        if (self.suffix):
            self.suffix.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[AnyType: ' + (repr(self.suffix) if (self.suffix) else '') + ']'


class SingleType(ChildProduction):
    """
    Single type production.

    Syntax:
    NonAnyType | AnyType
    """

    type: Union['NonAnyType', AnyType]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        return (NonAnyType.peek(tokens) or AnyType.peek(tokens))

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens, self)
        else:
            self.type = AnyType(tokens)
        self._did_parse(tokens, False)

    @property
    def type_name(self) -> Optional[str]:
        return self.type.type_name

    @property
    def type_names(self) -> List[str]:
        return self.type.type_names

    def _str(self) -> str:
        return str(self.type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self.type._define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[SingleType: ' + repr(self.type) + ']'


class NonAnyType(ChildProduction):
    """
    Non-any type production.

    Syntax:
    PrimitiveType [TypeSuffix] | "ByteString" [TypeSuffix] | "DOMString" [TypeSuffix]
    | "USVString" TypeSuffix | Identifier [TypeSuffix] | "sequence" "<" TypeWithExtendedAttributes ">" [Null]
    | "object" [TypeSuffix] | "Error" TypeSuffix | "Promise" "<" ReturnType ">" [Null] | BufferRelatedType [Null]
    | "FrozenArray" "<" TypeWithExtendedAttributes ">" [Null] | "record" "<" StringType "," TypeWithExtendedAttributes ">"
    """

    BUFFER_RELATED_TYPES = frozenset(['ArrayBuffer', 'DataView', 'Int8Array', 'Int16Array', 'Int32Array',
                                      'Uint8Array', 'Uint16Array', 'Uint32Array', 'Uint8ClampedArray',
                                      'Float32Array', 'Float64Array'])
    STRING_TYPES = frozenset(['ByteString', 'DOMString', 'USVString'])
    OBJECT_TYPES = frozenset(['object', 'Error'])

    type: Union[PrimitiveType, TypeIdentifier, 'TypeWithExtendedAttributes', 'ReturnType', Symbol]
    type_name: Optional[str]
    sequence: Optional[Symbol]
    promise: Optional[Symbol]
    record: Optional[Symbol]
    _open_type: Optional[Symbol]
    _close_type: Optional[Symbol]
    null: Optional[Symbol]
    suffix: Optional[TypeSuffix]
    key_type: Optional[Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (PrimitiveType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        token = tokens.push_position()
        if (token and (token.is_symbol(cls.STRING_TYPES | cls.OBJECT_TYPES) or token.is_identifier())):
            TypeSuffix.peek(tokens)
            return tokens.pop_position(True)
        elif (token and token.is_symbol(('sequence', 'FrozenArray'))):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, '>')):
                        Symbol.peek(tokens, '?')
                        return tokens.pop_position(True)
        elif (token and token.is_symbol('Promise')):
            if (Symbol.peek(tokens, '<')):
                if (ReturnType.peek(tokens)):
                    if (Symbol.peek(tokens, '>')):
                        Symbol.peek(tokens, '?')
                        return tokens.pop_position(True)
        elif (token and token.is_symbol(cls.BUFFER_RELATED_TYPES)):
            Symbol.peek(tokens, '?')
            return tokens.pop_position(True)
        elif (token and token.is_symbol('record')):
            if (Symbol.peek(tokens, '<')):
                if (Symbol.peek(tokens, cls.STRING_TYPES)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            if (Symbol.peek(tokens, '>')):
                                Symbol.peek(tokens, '?')
                                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.sequence = None
        self.promise = None
        self.record = None
        self._open_type = None
        self._close_type = None
        self.null = None
        self.suffix = None
        self.type_name = None
        self.key_type = None
        if (PrimitiveType.peek(tokens)):
            self.type = PrimitiveType(tokens)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            token = cast(Token, tokens.sneak_peek())
            if (token.is_identifier()):
                self.type = TypeIdentifier(tokens)
                self.type_name = self.type.type_name
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
            elif (token.is_symbol(('sequence', 'FrozenArray'))):
                self.sequence = Symbol(tokens)
                self._open_type = Symbol(tokens, '<')
                self.type = TypeWithExtendedAttributes(tokens, self)
                self._close_type = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.is_symbol('Promise')):
                self.promise = Symbol(tokens, 'Promise')
                self._open_type = Symbol(tokens, '<')
                self.type = ReturnType(tokens, self)
                self._close_type = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.is_symbol(self.BUFFER_RELATED_TYPES)):
                self.type = Symbol(tokens, None, False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            elif (token.is_symbol('record')):
                self.record = Symbol(tokens)
                self._open_type = Symbol(tokens, '<')
                self.key_type = Symbol(tokens)
                self._comma = Symbol(tokens, ',')
                self.type = TypeWithExtendedAttributes(tokens, self)
                self._close_type = Symbol(tokens, '>', False)
                self.null = Symbol(tokens, '?', False) if (Symbol.peek(tokens, '?')) else None
            else:
                self.type = Symbol(tokens, None, False)  # string or object
                self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._did_parse(tokens, False)

    @property
    def type_names(self) -> List[str]:
        return [self.type_name] if (self.type_name) else []

    def _str(self) -> str:
        if (self.sequence):
            output = str(self.sequence) + str(self._open_type) + str(self.type) + str(self._close_type)
            return output + (str(self.null) if (self.null) else '')
        if (self.promise):
            output = str(self.promise) + str(self._open_type) + str(self.type) + str(self._close_type)
            return output + (str(self.null) if (self.null) else '')
        if (self.record):
            output = str(self.record) + str(self._open_type) + str(self.key_type) + str(self._comma) + str(self.type) + str(self._close_type)
            return output + (str(self.null) if (self.null) else '')

        output = str(self.type)
        output = output + (str(self.null) if (self.null) else '')
        return output + (str(self.suffix) if (self.suffix) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.sequence):
            self.sequence.define_markup(generator)
            generator.add_text(self._open_type)
            generator.add_type(self.type)
            generator.add_text(self._close_type)
            generator.add_text(self.null)
            return self
        if (self.promise):
            self.promise.define_markup(generator)
            generator.add_text(self._open_type)
            self.type.define_markup(generator)
            generator.add_text(self._close_type)
            generator.add_text(self.null)
            return self
        if (self.record):
            self.record.define_markup(generator)
            generator.add_text(self._open_type)
            generator.add_string_type(self.key_type)
            generator.add_text(self._comma)
            self.type.define_markup(generator)
            generator.add_text(self._close_type)
            generator.add_text(self.null)
            return self
        if (isinstance(self.type, TypeIdentifier)):
            self.type.define_markup(generator)
            if (self.suffix):
                self.suffix.define_markup(generator)
            return self
        if (isinstance(self.type, PrimitiveType)):
            generator.add_primitive_type(self.type)
        elif (isinstance(self.type, Symbol)):
            if (self.type.symbol in self.BUFFER_RELATED_TYPES):
                generator.add_buffer_type(self.type)
            elif (self.type.symbol in self.STRING_TYPES):
                generator.add_string_type(self.type)
            elif (self.type.symbol in self.OBJECT_TYPES):
                generator.add_object_type(self.type)
            else:
                assert(False)
        else:
            self.type._define_markup(generator)
        generator.add_text(self.null)
        if (self.suffix):
            self.suffix.define_markup(generator)
        return self

    def __repr__(self) -> str:
        output = ('[NonAnyType: ' + ('[sequence] ' if (self.sequence) else '') + ('[Promise] ' if (self.promise) else '')
                  + ('[record] [StringType: ' + repr(self.key_type) + '] ' if (self.record) else ''))
        output += repr(self.type) + ('[null]' if (self.null) else '')
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class UnionMemberType(ChildProduction):
    """
    Union member type production.

    Syntax:
    [ExtendedAttributeList] NonAnyType | UnionType [TypeSuffix] | AnyType
    """

    type: Union[NonAnyType, 'UnionType', AnyType]
    suffix: Optional[TypeSuffix]
    _extended_attributes: Optional['ExtendedAttributeList']

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (ExtendedAttributeList.peek(tokens)):
            if (NonAnyType.peek(tokens)):
                return True
        if (NonAnyType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return AnyType.peek(tokens)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._extended_attributes = ExtendedAttributeList(tokens, self) if (ExtendedAttributeList.peek(tokens)) else None
        self.suffix = None
        if (NonAnyType.peek(tokens)):
            self.type = NonAnyType(tokens, self)
        elif (UnionType.peek(tokens)):
            self.type = UnionType(tokens, self)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        else:
            self.type = AnyType(tokens)
        self._did_parse(tokens, False)

    @property
    def extended_attributes(self) -> Optional['ExtendedAttributeList']:
        return self._extended_attributes

    @property
    def type_name(self) -> Optional[str]:
        return self.type.type_name

    @property
    def type_names(self) -> List[str]:
        return self.type.type_names

    def _str(self) -> str:
        output = str(self._extended_attributes) if (self._extended_attributes) else ''
        output += str(self.type)
        return output + (str(self.suffix) if (self.suffix) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self._extended_attributes):
            self._extended_attributes.define_markup(generator)
        self.type.define_markup(generator)
        generator.add_text(self.suffix)
        return self

    def __repr__(self) -> str:
        output = '[UnionMemberType: ' + repr(self.type)
        return output + (repr(self.suffix) if (self.suffix) else '') + ']'


class UnionType(ChildProduction):
    """
    Union member type production.

    Syntax:
    "(" UnionMemberType ["or" UnionMemberType]... ")"
    """

    _open_paren: Symbol
    types: List[UnionMemberType]
    _ors: List[Symbol]
    _close_paren: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, '(')):
            while (tokens.has_tokens()):
                if (UnionMemberType.peek(tokens)):
                    token = tokens.peek()
                    if (token and token.is_symbol('or')):
                        continue
                    if (token and token.is_symbol(')')):
                        return tokens.pop_position(True)
                return tokens.pop_position(False)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._open_paren = Symbol(tokens, '(')
        self.types = []
        self._ors = []
        while (tokens.has_tokens()):
            self.types.append(UnionMemberType(tokens, self))
            token = tokens.sneak_peek()
            if (token and token.is_symbol()):
                if ('or' == token.text):
                    self._ors.append(Symbol(tokens, 'or'))
                    continue
                elif (')' == token.text):
                    break
            break
        self._close_paren = Symbol(tokens, ')', False)
        self._did_parse(tokens, False)

    @property
    def type_name(self) -> Optional[str]:
        return None

    @property
    def type_names(self) -> List[str]:
        return [type.type_name for type in self.types if (type.type_name)]

    def _str(self) -> str:
        output = str(self._open_paren)
        output += ''.join([str(type) + str(_or) for type, _or in itertools.zip_longest(self.types, self._ors, fillvalue='')])
        return output + str(self._close_paren)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self._open_paren)
        for type, _or in itertools.zip_longest(self.types, self._ors, fillvalue=''):
            generator.add_type(type)
            if (_or):
                _or.define_markup(generator)
        generator.add_text(self._close_paren)
        return self

    def __repr__(self) -> str:
        return '[UnionType: ' + ''.join([repr(type) for type in self.types]) + ']'


class Type(ChildProduction):
    """
    Type production.

    Syntax:
    SingleType | UnionType [TypeSuffix]
    """

    type: Union[SingleType, UnionType]
    suffix: Optional[TypeSuffix]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (SingleType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return False

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        if (SingleType.peek(tokens)):
            self.type = SingleType(tokens, self)
            self.suffix = None
        else:
            self.type = UnionType(tokens, self)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._did_parse(tokens)

    @property
    def type_names(self) -> List[str]:
        return self.type.type_names

    def _str(self) -> str:
        return str(self.type) + (self.suffix._str() if (self.suffix) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self.type.define_markup(generator)
        generator.add_text(self.suffix)
        return self

    def __repr__(self) -> str:
        return '[Type: ' + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']'


class TypeWithExtendedAttributes(ChildProduction):
    """
    Type with extended attributes production.

    Syntax:
    [ExtendedAttributeList] SingleType | UnionType [TypeSuffix]
    """

    _extended_attributes: Optional['ExtendedAttributeList']
    type: Union[SingleType, UnionType]
    suffix: Optional[TypeSuffix]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        ExtendedAttributeList.peek(tokens)
        if (SingleType.peek(tokens)):
            return True
        if (UnionType.peek(tokens)):
            TypeSuffix.peek(tokens)
            return True
        return False

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._extended_attributes = ExtendedAttributeList(tokens, self) if (ExtendedAttributeList.peek(tokens)) else None
        if (SingleType.peek(tokens)):
            self.type = SingleType(tokens, self)
            self.suffix = None
        else:
            self.type = UnionType(tokens, self)
            self.suffix = TypeSuffix(tokens) if (TypeSuffix.peek(tokens)) else None
        self._did_parse(tokens)

    @property
    def type_names(self) -> List[str]:
        return self.type.type_names

    @property
    def extended_attributes(self) -> Optional['ExtendedAttributeList']:
        return self._extended_attributes

    def _str(self) -> str:
        return (str(self._extended_attributes) if (self._extended_attributes) else '') + str(self.type) + (self.suffix._str() if (self.suffix) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self._extended_attributes):
            self._extended_attributes.define_markup(generator)
        self.type.define_markup(generator)
        generator.add_text(self.suffix)
        return self

    def __repr__(self) -> str:
        return ('[TypeWithExtendedAttributes: ' + (repr(self._extended_attributes) if (self._extended_attributes) else '')
                + repr(self.type) + (repr(self.suffix) if (self.suffix) else '') + ']')


class IgnoreInOut(Production):
    """
    Consume an 'in' or 'out' token to ignore for backwards compat.

    Syntax:
    "in" | "out"
    """

    text: str

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        if (token and token.is_identifier(('in', 'out'))):
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.text = next(tokens).text
        self._did_parse(tokens)
        tokens.did_ignore(self.text)

    def _str(self) -> str:
        return self.text


class Ignore(Production):
    """
    Consume deprecated syntax for backwards compat.

    Syntax:
    "inherits" "getter" | "getraises" "(" ... ")" | "setraises" "(" ... ")" | "raises" "(" ... ")"
    """

    tokens: List[Token]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        if (token and token.is_identifier('inherits')):
            token = tokens.peek()
            return tokens.pop_position((token is not None) and token.is_symbol('getter'))
        if (token and token.is_identifier(('getraises', 'setraises', 'raises'))):
            token = tokens.peek()
            if (token and token.is_symbol('(')):
                return tokens.pop_position(tokens.peek_symbol(')'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self.tokens = []
        token = next(tokens)
        self.tokens.append(token)
        if (token.is_identifier('inherits')):
            space = tokens.whitespace()
            if (space):
                self.tokens.append(space)
            self.tokens.append(next(tokens))   # "getter"
        else:
            space = tokens.whitespace()
            if (space):
                self.tokens.append(space)
            self.tokens.append(next(tokens))    # "("
            self.tokens += tokens.seek_symbol(')')
        self._did_parse(tokens)
        tokens.did_ignore(self.tokens)

    def _str(self) -> str:
        return ''.join([str(token) for token in self.tokens])


class IgnoreMultipleInheritance(Production):
    """
    Consume deprecated multiple inheritance syntax for backwards compat.

    Syntax:
    "," TypeIdentifier [", TypeIdentifier]...
    """

    _comma: Symbol
    _inherit: TypeIdentifier
    next: Optional['IgnoreMultipleInheritance']

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, ',')):
            if (TypeIdentifier.peek(tokens)):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, continuation: bool = False) -> None:
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self._inherit = TypeIdentifier(tokens)
        self.next = IgnoreMultipleInheritance(tokens, True) if (IgnoreMultipleInheritance.peek(tokens)) else None
        self._did_parse(tokens)
        if (not continuation):
            tokens.did_ignore(self)

    def _str(self) -> str:
        return str(self._comma) + str(self._inherit) + (str(self.next) if (self.next) else '')

    @property
    def inherit(self) -> str:
        return _name(self._inherit)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self._comma)
        self._inherit.define_markup(generator)
        if (self.next):
            self.next.define_markup(generator)
        return self


class Inheritance(Production):
    """
    Inheritance production.

    Syntax:
    ":" Identifier [IgnoreMultipleInheritance]
    """

    _colon: Symbol
    _base: TypeIdentifier
    _ignore: Optional[IgnoreMultipleInheritance]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, ':')):
            if (TypeIdentifier.peek(tokens)):
                IgnoreMultipleInheritance.peek(tokens)
                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._colon = Symbol(tokens, ':')
        self._base = TypeIdentifier(tokens)
        self._ignore = IgnoreMultipleInheritance(tokens) if (IgnoreMultipleInheritance.peek(tokens)) else None
        self._did_parse(tokens)

    @property
    def base(self) -> str:
        return _name(self._base)

    def _str(self) -> str:
        return str(self._colon) + str(self._base) + (str(self._ignore) if (self._ignore) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self._colon)
        self._base.define_markup(generator)
        if (self._ignore):
            self._ignore.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[Inheritance: ' + repr(self._base) + ']'


class Default(Production):
    """
    Default value production.

    Syntax:
    "=" ConstValue | "=" String | "=" "[" "]" | "=" "{" "}"
    """

    _equals: Symbol
    _open: Optional[Symbol]
    _close: Optional[Symbol]
    _value: Optional[Union[ConstValue, String]]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, '=')):
            if (ConstValue.peek(tokens)):
                return tokens.pop_position(True)
            if (Symbol.peek(tokens, '[')):
                return tokens.pop_position(Symbol.peek(tokens, ']'))
            if (Symbol.peek(tokens, '{')):
                return tokens.pop_position(Symbol.peek(tokens, '}'))
            token = tokens.peek()
            return tokens.pop_position((token is not None) and token.is_string())
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._equals = Symbol(tokens, '=')
        self._open = None
        self._close = None
        self._value = None
        token = cast(Token, tokens.sneak_peek())
        if (token.is_string()):
            self._value = String(tokens)
        elif (token.is_symbol('[')):
            self._open = Symbol(tokens, '[')
            self._close = Symbol(tokens, ']', False)
        elif (token.is_symbol('{')):
            self._open = Symbol(tokens, '{')
            self._close = Symbol(tokens, '}', False)
        else:
            self._value = ConstValue(tokens)
        self._did_parse(tokens)

    @property
    def value(self) -> str:
        return str(self._value) if (self._value) else (cast(Symbol, self._open)._str() + cast(Symbol, self._close)._str())

    def _str(self) -> str:
        return str(self._equals) + (str(self._value) if (self._value) else str(self._open) + str(self._close))

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._equals.define_markup(generator)
        if (self._value):
            return self._value._define_markup(generator)
        cast(Symbol, self._open).define_markup(generator)
        cast(Symbol, self._close).define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[Default: ' + (repr(self.value) if (self.value) else str(self._open) + str(self._close)) + ']'


class ArgumentName(Production):
    """
    Argument name production.

    Syntax:
    Identifier | ArgumentNameKeyword
    """

    ARGUMENT_NAME_KEYWORDS = frozenset(['async', 'attribute', 'callback', 'const', 'constructor',
                                        'deleter', 'dictionary', 'enum', 'getter', 'includes',
                                        'inherit', 'interface', 'iterable', 'maplike', 'namespace',
                                        'partial', 'required', 'setlike', 'setter', 'static',
                                        'stringifier', 'typedef', 'unrestricted'])

    _name: Identifier

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and (token.is_identifier() or (token.is_symbol(cls.ARGUMENT_NAME_KEYWORDS))))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = Identifier(tokens)
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        return str(self._name)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._name.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[ArgumentName: ' + repr(self._name) + ']'


class ArgumentList(Production):
    """
    Argument list production.

    Syntax:
    Argument ["," Argument]...
    """

    arguments: List['constructs.Argument']
    _commas: List[Symbol]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (constructs.Argument.peek(tokens)):
            token = tokens.push_position()
            if (token and token.is_symbol(',')):
                return tokens.pop_position(tokens.pop_position(ArgumentList.peek(tokens)))
            tokens.pop_position(False)
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction = None) -> None:
        Production.__init__(self, tokens)
        self.arguments = []
        self._commas = []
        self.arguments.append(constructs.Argument(tokens, parent))
        token = tokens.sneak_peek()
        while (token and token.is_symbol(',')):
            self._commas.append(Symbol(tokens, ','))
            argument = constructs.Argument(tokens, parent)
            if (len(self.arguments)):
                if (self.arguments[-1].variadic):
                    tokens.error('Argument "', argument.name, '" not allowed to follow variadic argument "', self.arguments[-1].name, '"')
                elif ((not self.arguments[-1].required) and argument.required):
                    tokens.error('Required argument "', argument.name, '" cannot follow optional argument "', self.arguments[-1].name, '"')
            self.arguments.append(argument)
            token = tokens.sneak_peek()
        self._did_parse(tokens)
        if (parent):
            for index in range(0, len(self.arguments)):
                argument = self.arguments[index]
                if (argument.required):
                    for type_name in argument.type.type_names:
                        symbol_table = parent.symbol_table
                        type = symbol_table.get_type(type_name) if (symbol_table) else None
                        # dictionary must be optional unless followed by required argument
                        if (type and ('dictionary' == type.idl_type) and (not cast(constructs.Dictionary, type).required)):
                            for index2 in range(index + 1, len(self.arguments)):
                                if (self.arguments[index2].required):
                                    break
                            else:
                                tokens.error('Dictionary argument "', argument.name, '" without required members must be marked optional')

    @property
    def name(self) -> Optional[str]:
        return self.arguments[0].name

    @property   # get all possible variants of argument names
    def argument_names(self) -> Sequence[str]:
        if (self.arguments):
            args = [argument for argument in self.arguments]
            names = []
            name = ', '.join([('...' + argument.name) if (argument.variadic) else argument.name for argument in args if (argument.name)])
            names.append(name)
            while (args and (args[-1].optional)):
                args.pop()
                names.append(', '.join([argument.name for argument in args if (argument.name)]))
            return names
        return ['']

    def matches_names(self, argument_names: Sequence[str]) -> bool:
        for name, argument in itertools.zip_longest(argument_names, self.arguments, fillvalue=None):
            if (name):
                if ((argument is None) or (argument.name != name)):
                    return False
            else:
                if (argument and argument.required):
                    return False
        return True

    def __len__(self) -> int:
        return len(self.arguments)

    def __getitem__(self, key: Union[str, int]) -> protocols.Construct:
        if (isinstance(key, str)):
            for argument in self.arguments:
                if (argument.name == key):
                    return argument
            raise IndexError
        return self.arguments[key]

    def __contains__(self, key: Union[str, int]) -> bool:
        if (isinstance(key, str)):
            for argument in self.arguments:
                if (argument.name == key):
                    return True
            return False
        return (key in self.arguments)

    def __iter__(self) -> Iterator[protocols.Construct]:
        return iter(self.arguments)

    def keys(self) -> Sequence[str]:
        return [argument.name for argument in self.arguments if (argument.name)]

    def values(self) -> Sequence[protocols.Construct]:
        return [argument for argument in self.arguments if (argument.name)]

    def items(self) -> Sequence[Tuple[str, protocols.Construct]]:
        return [(argument.name, argument) for argument in self.arguments if (argument.name)]

    def get(self, key: Union[str, int]) -> Optional[protocols.Construct]:
        try:
            return self[key]
        except IndexError:
            return None

    def _str(self) -> str:
        return ''.join([str(argument) + str(comma) for argument, comma in itertools.zip_longest(self.arguments, self._commas, fillvalue='')])

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        for argument, comma in itertools.zip_longest(self.arguments, self._commas, fillvalue=''):
            argument.define_markup(generator)
            generator.add_text(comma)
        return self

    def __repr__(self) -> str:
        return ' '.join([repr(argument) for argument in self.arguments])


class ReturnType(ChildProduction):
    """
    Return type production.

    Syntax:
    Type | "void"
    """

    type: Union[Symbol, Type]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        if (Type.peek(tokens)):
            return True
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_symbol('void'))

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        token = cast(Token, tokens.sneak_peek())
        if (token.is_symbol('void')):
            self.type = Symbol(tokens, 'void', False)
        else:
            self.type = Type(tokens, self)
        self._did_parse(tokens)

    def _str(self) -> str:
        return str(self.type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (isinstance(self.type, Symbol)):
            self.type._define_markup(generator)
        else:
            generator.add_type(self.type)
        return self

    def __repr__(self) -> str:
        return repr(self.type)


class Special(Production):
    """
    Special production.

    Syntax:
    "getter" | "setter" | "creator" | "deleter" | "legacycaller"
    """

    _name: str

    SPECIAL_SYMBOLS = frozenset(['getter', 'setter', 'creator', 'deleter', 'legacycaller'])
    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and token.is_symbol(cls.SPECIAL_SYMBOLS))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = next(tokens).text
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name

    def _str(self) -> str:
        return self._name

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_keyword(self._name)
        return self

    def __repr__(self) -> str:
        return '[Special: ' + self._name + ']'


class AttributeName(Production):
    """
    Atttribute name production.

    Syntax:
    Identifier | AttributeNameKeyword
    """

    ATTRIBUTE_NAME_KEYWORDS = frozenset(['async', 'required'])

    _name: Identifier

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and (token.is_identifier() or (token.is_symbol(cls.ATTRIBUTE_NAME_KEYWORDS))))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = Identifier(tokens)
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        return str(self._name)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._name.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[OperationName: ' + repr(self._name) + ']'


class AttributeRest(ChildProduction):
    """
    Atttribute rest production.

    Syntax:
    ["readonly"] "attribute" TypeWithExtendedAttributes AttributeName [Ignore] ";"
    """

    readonly: Optional[Symbol]
    _attribute: Symbol
    type: TypeWithExtendedAttributes
    _name: AttributeName
    _ignore: Optional[Ignore]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        if (token and token.is_symbol('readonly')):
            token = tokens.peek()
        if (token and token.is_symbol('attribute')):
            if (TypeWithExtendedAttributes.peek(tokens)):
                return tokens.pop_position(AttributeName.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._attribute = Symbol(tokens, 'attribute')
        self.type = TypeWithExtendedAttributes(tokens, self)
        self._name = AttributeName(tokens)
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        output = str(self.readonly) if (self.readonly) else ''
        output += str(self._attribute) + str(self.type)
        output += str(self._name)
        return output + (str(self._ignore) if (self._ignore) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.readonly):
            self.readonly.define_markup(generator)
        self._attribute.define_markup(generator)
        generator.add_type(self.type)
        self._name.define_markup(generator)
        if (self._ignore):
            self._ignore.define_markup(generator)
        return self

    def __repr__(self) -> str:
        output = '[AttributeRest: '
        output += '[readonly] ' if (self.readonly) else ''
        output += repr(self.type)
        output += ' [name: ' + _name(self) + ']'
        return output + ']'


class MixinAttribute(ChildProduction):
    """
    Mixin atttribute production.

    Syntax:
    AttributeRest
    """

    attribute: AttributeRest

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        return AttributeRest.peek(tokens)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.attribute = AttributeRest(tokens, self)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'attribute'

    @property
    def stringifier(self) -> bool:
        return False

    @property
    def name(self) -> Optional[str]:
        return self.attribute.name

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        return str(self.attribute)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        return self.attribute._define_markup(generator)

    def __repr__(self) -> str:
        output = '[Attribute: '
        return output + repr(self.attribute) + ']'


class Attribute(ChildProduction):
    """
    Atttribute production.

    Syntax:
    ["inherit"] AttributeRest
    """

    inherit: Optional[Symbol]
    attribute: AttributeRest

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        Symbol.peek(tokens, 'inherit')
        return tokens.pop_position(AttributeRest.peek(tokens))

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.inherit = Symbol(tokens, 'inherit') if (Symbol.peek(tokens, 'inherit')) else None
        self.attribute = AttributeRest(tokens, self)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'attribute'

    @property
    def stringifier(self) -> bool:
        return False

    @property
    def name(self) -> Optional[str]:
        return self.attribute.name

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        output = str(self.inherit) if (self.inherit) else ''
        return output + str(self.attribute)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.inherit):
            self.inherit.define_markup(generator)
        return self.attribute._define_markup(generator)

    def __repr__(self) -> str:
        output = '[Attribute: '
        output += '[inherit] ' if (self.inherit) else ''
        return output + repr(self.attribute) + ']'


class OperationName(Production):
    """
    Operation name production.

    Syntax:
    Identifier | OperationNameKeyword
    """

    OPERATION_NAME_KEYWORDS = frozenset(['includes'])

    _name: Identifier

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        token = tokens.push_position()
        return tokens.pop_position((token is not None) and (token.is_identifier() or (token.is_symbol(cls.OPERATION_NAME_KEYWORDS))))

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._name = Identifier(tokens)
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        return str(self._name)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._name.define_markup(generator)
        return self

    def __repr__(self) -> str:
        return '[OperationName: ' + repr(self._name) + ']'


class OperationRest(ChildProduction):
    """
    Operation rest production.

    Syntax:
    [OperationName] "(" [ArgumentList] ")" [Ignore] ";"
    """

    _name: Optional[OperationName]
    _open_paren: Symbol
    _arguments: Optional[ArgumentList]
    _close_paren: Symbol
    _ignore: Optional[Ignore]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        OperationName.peek(tokens)
        token = tokens.peek()
        if (token and token.is_symbol('(')):
            ArgumentList.peek(tokens)
            token = tokens.peek()
            return tokens.pop_position((token is not None) and token.is_symbol(')'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._name = OperationName(tokens) if (OperationName.peek(tokens)) else None
        self._open_paren = Symbol(tokens, '(')
        self._arguments = ArgumentList(tokens, parent) if (ArgumentList.peek(tokens)) else None
        self._close_paren = Symbol(tokens, ')')
        self._ignore = Ignore(tokens) if (Ignore.peek(tokens)) else None
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'method'

    @property
    def name(self) -> Optional[str]:
        return self._name.name if (self._name) else None

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self._arguments

    @property
    def argument_names(self) -> Sequence[str]:
        return self._arguments.argument_names if (self._arguments) else ['']

    def _str(self) -> str:
        output = str(self._name) if (self._name) else ''
        output += str(self._open_paren) + (str(self._arguments) if (self._arguments) else '') + str(self._close_paren)
        return output + (str(self._ignore) if (self._ignore) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self._name):
            self._name.define_markup(generator)
        generator.add_text(self._open_paren)
        if (self._arguments):
            self._arguments.define_markup(generator)
        generator.add_text(self._close_paren)
        if (self._ignore):
            self._ignore.define_markup(generator)
        return self

    def __repr__(self) -> str:
        output = '[OperationRest: '
        output += ('[name: ' + repr(self._name) + '] ') if (self._name) else ''
        return output + '[ArgumentList: ' + (repr(self._arguments) if (self._arguments) else '') + ']]'


class Iterable(ChildProduction):
    """
    Iterable production.

    Syntax:
    "iterable" "<" TypeWithExtendedAttributes ["," TypeWithExtendedAttributes] ">" ";" | "legacyiterable" "<" Type ">" ";"
    """

    _iterabe: Symbol
    _open_type: Symbol
    type: Optional[TypeWithExtendedAttributes]
    key_type: Optional[TypeWithExtendedAttributes]
    _comma: Optional[Symbol]
    value_type: Optional[TypeWithExtendedAttributes]
    _close_type: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'iterable')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            token = tokens.peek()
                            return tokens.pop_position((token is not None) and token.is_symbol('>'))
                    token = tokens.peek()
                    return tokens.pop_position((token is not None) and token.is_symbol('>'))
        elif (Symbol.peek(tokens, 'legacyiterable')):
            if (Symbol.peek(tokens, '<')):
                if (Type.peek(tokens)):
                    token = tokens.peek()
                    return tokens.pop_position((token is not None) and token.is_symbol('>'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._iterable = Symbol(tokens)
        self._open_type = Symbol(tokens, '<')
        self.type = TypeWithExtendedAttributes(tokens, self)
        if (Symbol.peek(tokens, ',')):
            self.key_type = self.type
            self.type = None
            self._comma = Symbol(tokens)
            self.value_type = TypeWithExtendedAttributes(tokens, self)
        else:
            self.key_type = None
            self.value_type = None
        self._close_type = Symbol(tokens, '>')
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'iterable'

    @property
    def name(self) -> Optional[str]:
        return '__iterable__'

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        output = str(self._iterable) + str(self._open_type)
        if (self.type):
            output += str(self.type)
        else:
            output += str(self.key_type) + str(self._comma) + str(self.value_type)
        return output + str(self._close_type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._iterable.define_markup(generator)
        generator.add_text(self._open_type)
        if (self.type):
            generator.add_type(self.type)
        else:
            generator.add_type(self.key_type)
            generator.add_text(self._comma)
            generator.add_type(self.value_type)
        generator.add_text(self._close_type)
        return self

    def __repr__(self) -> str:
        output = '[Iterable: '
        if (self.type):
            output += repr(self.type)
        else:
            output += repr(self.key_type) + ' ' + repr(self.value_type)
        return output + ']'


class AsyncIterable(ChildProduction):
    """
    Async iterable production.

    Syntax:
    "async" "iterable" "<" TypeWithExtendedAttributes "," TypeWithExtendedAttributes ">" ";"
    """

    _async: Symbol
    _iterable: Symbol
    _open_type: Symbol
    key_type: TypeWithExtendedAttributes
    _comma: Symbol
    value_type: TypeWithExtendedAttributes
    _close_type: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'async')):
            if (Symbol.peek(tokens, 'iterable')):
                if (Symbol.peek(tokens, '<')):
                    if (TypeWithExtendedAttributes.peek(tokens)):
                        if (Symbol.peek(tokens, ',')):
                            if (TypeWithExtendedAttributes.peek(tokens)):
                                token = tokens.peek()
                                return tokens.pop_position((token is not None) and token.is_symbol('>'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._async = Symbol(tokens)
        self._iterable = Symbol(tokens)
        self._open_type = Symbol(tokens, '<')
        self.key_type = TypeWithExtendedAttributes(tokens, self)
        self._comma = Symbol(tokens)
        self.value_type = TypeWithExtendedAttributes(tokens, self)
        self._close_type = Symbol(tokens, '>')
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'async-iterable'

    @property
    def name(self) -> Optional[str]:
        return '__async_iterable__'

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        output = str(self._async) + str(self._iterable) + str(self._open_type)
        output += str(self.key_type) + str(self._comma) + str(self.value_type)
        return output + str(self._close_type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._async.define_markup(generator)
        self._iterable.define_markup(generator)
        generator.add_text(self._open_type)
        generator.add_type(self.key_type)
        generator.add_text(self._comma)
        generator.add_type(self.value_type)
        generator.add_text(self._close_type)
        return self

    def __repr__(self) -> str:
        output = '[AsyncIterable: '
        output += repr(self.key_type) + ' ' + repr(self.value_type)
        return output + ']'


class Maplike(ChildProduction):
    """
    Maplike production.

    Syntax:
    ["readonly"] "maplike" "<" TypeWithExtendedAttributes "," TypeWithExtendedAttributes ">" ";"
    """

    readonly: Optional[Symbol]
    _maplike: Symbol
    _open_type: Symbol
    key_type: TypeWithExtendedAttributes
    _comma: Symbol
    value_type: TypeWithExtendedAttributes
    _close_type: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        Symbol.peek(tokens, 'readonly')
        if (Symbol.peek(tokens, 'maplike')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    if (Symbol.peek(tokens, ',')):
                        if (TypeWithExtendedAttributes.peek(tokens)):
                            return tokens.pop_position(Symbol.peek(tokens, '>'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._maplike = Symbol(tokens, 'maplike')
        self._open_type = Symbol(tokens, '<')
        self.key_type = TypeWithExtendedAttributes(tokens, self)
        self._comma = Symbol(tokens, ',')
        self.value_type = TypeWithExtendedAttributes(tokens, self)
        self._close_type = Symbol(tokens, '>')
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'maplike'

    @property
    def name(self) -> Optional[str]:
        return '__maplike__'

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        output = str(self.readonly) if (self.readonly) else ''
        output += str(self._maplike) + str(self._open_type) + str(self.key_type) + str(self._comma)
        return output + str(self.value_type) + str(self._close_type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.readonly):
            self.readonly.define_markup(generator)
        self._maplike.define_markup(generator)
        generator.add_text(self._open_type)
        generator.add_type(self.key_type)
        generator.add_text(self._comma)
        generator.add_type(self.value_type)
        generator.add_text(self._close_type)
        return self

    def __repr__(self) -> str:
        output = '[Maplike: ' + '[readonly] ' if (self.readonly) else ''
        output += repr(self.key_type) + ' ' + repr(self.value_type)
        return output + ']'


class Setlike(ChildProduction):
    """
    Setlike production.

    Syntax:
    ["readonly"] "setlike" "<" TypeWithExtendedAttributes ">" ";"
    """

    readonly: Optional[Symbol]
    _setlike: Symbol
    _open_type: Symbol
    type: TypeWithExtendedAttributes
    _close_type: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        Symbol.peek(tokens, 'readonly')
        if (Symbol.peek(tokens, 'setlike')):
            if (Symbol.peek(tokens, '<')):
                if (TypeWithExtendedAttributes.peek(tokens)):
                    return tokens.pop_position(Symbol.peek(tokens, '>'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.readonly = Symbol(tokens, 'readonly') if (Symbol.peek(tokens, 'readonly')) else None
        self._setlike = Symbol(tokens, 'setlike')
        self._open_type = Symbol(tokens, '<')
        self.type = TypeWithExtendedAttributes(tokens, self)
        self._close_type = Symbol(tokens, '>')
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'setlike'

    @property
    def name(self) -> Optional[str]:
        return '__setlike__'

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return None

    def _str(self) -> str:
        output = str(self.readonly) if (self.readonly) else ''
        return output + str(self._setlike) + str(self._open_type) + str(self.type) + str(self._close_type)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self.readonly):
            self.readonly.define_markup(generator)
        self._setlike.define_markup(generator)
        generator.add_text(self._open_type)
        generator.add_type(self.type)
        generator.add_text(self._close_type)
        return self

    def __repr__(self) -> str:
        output = '[Setlike: ' + ('[readonly] ' if (self.readonly) else '')
        return output + repr(self.type) + ']'


class SpecialOperation(ChildProduction):
    """
    Special operation production.

    Syntax:
    Special [Special]... ReturnType OperationRest
    """

    specials: List[Special]
    return_type: ReturnType
    operation: OperationRest

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Special.peek(tokens)):
            while (Special.peek(tokens)):
                pass
            if (ReturnType.peek(tokens)):
                return tokens.pop_position(OperationRest.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.specials = []
        while (Special.peek(tokens)):
            self.specials.append(Special(tokens))
        self.return_type = ReturnType(tokens, self)
        self.operation = OperationRest(tokens, self)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'method'

    @property
    def name(self) -> Optional[str]:
        return self.operation.name if (self.operation.name) else ('__' + _name(self.specials[0]) + '__')

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self.operation.arguments

    @property
    def method_name(self) -> Optional[str]:
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += self.arguments.argument_names[0]
        return name + ')'

    @property
    def method_names(self) -> List[str]:
        if (self.arguments):
            return [_name(self) + '(' + argument_name + ')' for argument_name in self.arguments.argument_names]
        return [self.method_name] if (self.method_name) else []

    def _str(self) -> str:
        output = ''.join([str(special) for special in self.specials])
        return output + str(self.return_type) + str(self.operation)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        for special in self.specials:
            special.define_markup(generator)
        self.return_type.define_markup(generator)
        return self.operation._define_markup(generator)

    def __repr__(self) -> str:
        output = '[SpecialOperation: ' + ' '.join([repr(special) for special in self.specials])
        return output + ' ' + repr(self.return_type) + ' ' + repr(self.operation) + ']'


class Operation(ChildProduction):
    """
    Operation production.

    Syntax:
    ReturnType OperationRest
    """

    return_type: ReturnType
    operation: OperationRest

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (ReturnType.peek(tokens)):
            return tokens.pop_position(OperationRest.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self.return_type = ReturnType(tokens, self)
        self.operation = OperationRest(tokens, self)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'method'

    @property
    def name(self) -> Optional[str]:
        return self.operation.name

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self.operation.arguments

    @property
    def method_name(self) -> Optional[str]:
        name = self.name + '(' if (self.name) else '('
        if (self.arguments):
            name += self.arguments.argument_names[0]
        return name + ')'

    @property
    def method_names(self) -> List[str]:
        if (self.arguments):
            return [_name(self) + '(' + argument_name + ')' for argument_name in self.arguments.argument_names]
        return [self.method_name] if (self.method_name) else []

    def _str(self) -> str:
        return str(self.return_type) + str(self.operation)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self.return_type.define_markup(generator)
        return self.operation._define_markup(generator)

    def __repr__(self) -> str:
        return '[Operation: ' + repr(self.return_type) + ' ' + repr(self.operation) + ']'


class Stringifier(ChildProduction):
    """
    Stringifier production.

    Syntax:
    "stringifier" AttributeRest | "stringifier" ReturnType OperationRest | "stringifier" ";"
    """

    _stringifier: Symbol
    attribute: Optional[AttributeRest]
    return_type: Optional[ReturnType]
    operation: Optional[OperationRest]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'stringifier')):
            if (ReturnType.peek(tokens)):
                return tokens.pop_position(OperationRest.peek(tokens))
            AttributeRest.peek(tokens)
            return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._stringifier = Symbol(tokens, 'stringifier')
        self.attribute = None
        self.return_type = None
        self.operation = None
        if (ReturnType.peek(tokens)):
            self.return_type = ReturnType(tokens, self)
            self.operation = OperationRest(tokens, self)
        elif (AttributeRest.peek(tokens)):
            self.attribute = AttributeRest(tokens, self)
        else:
            self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'attribute' if (self.attribute) else 'stringifier'

    @property
    def stringifier(self) -> bool:
        return True

    @property
    def name(self) -> Optional[str]:
        if (self.operation):
            return self.operation.name if (self.operation.name) else '__stringifier__'
        return self.attribute.name if (self.attribute and self.attribute.name) else '__stringifier__'

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self.operation.arguments if (self.operation) else None

    @property
    def method_name(self) -> Optional[str]:
        if (self.operation):
            name = self.name + '(' if (self.name) else '('
            if (self.arguments):
                name += self.arguments.argument_names[0]
            return name + ')'
        return None

    @property
    def method_names(self) -> List[str]:
        if (self.operation):
            if (self.arguments):
                return [_name(self) + '(' + argument_name + ')' for argument_name in self.arguments.argument_names]
            if (self.method_name):
                return [self.method_name]
        return []

    def _str(self) -> str:
        output = str(self._stringifier)
        output += (str(self.return_type) + str(self.operation)) if (self.operation) else ''
        return output + (str(self.attribute) if (self.attribute) else '')

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._stringifier.define_markup(generator)
        if (self.operation):
            cast(ReturnType, self.return_type).define_markup(generator)
            return self.operation._define_markup(generator)
        if (self.attribute):
            return self.attribute._define_markup(generator)
        return self

    def __repr__(self) -> str:
        output = '[Stringifier: '
        if (self.operation):
            output += repr(self.return_type) + ' ' + repr(self.operation)
        else:
            output += repr(self.attribute) if (self.attribute) else ''
        return output + ']'


class Identifiers(Production):
    """
    Identifiers production.

    Syntax:
    "," Identifier ["," Identifier]...
    """

    _comma: Symbol
    _name: Identifier
    next: Optional['Identifiers']

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, ',')):
            if (Identifier.peek(tokens)):
                Identifiers.peek(tokens)
                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self._name = Identifier(tokens)
        self.next = Identifiers(tokens) if (Identifiers.peek(tokens)) else None
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        output = str(self._comma) + str(self._name)
        return output + (str(self.next) if (self.next) else '')

    def __repr__(self) -> str:
        return ' ' + repr(self._name) + (repr(self.next) if (self.next) else '')


class TypeIdentifiers(Production):
    """
    Type identifiers production.

    Syntax:
    "," Identifier ["," Identifier]...
    """

    _comma: Symbol
    _name: TypeIdentifier
    next: Optional['TypeIdentifiers']

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, ',')):
            if (TypeIdentifier.peek(tokens)):
                TypeIdentifiers.peek(tokens)
                return tokens.pop_position(True)
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer) -> None:
        Production.__init__(self, tokens)
        self._comma = Symbol(tokens, ',')
        self._name = TypeIdentifier(tokens)
        self.next = TypeIdentifiers(tokens) if (TypeIdentifiers.peek(tokens)) else None
        self._did_parse(tokens)

    @property
    def name(self) -> Optional[str]:
        return self._name.name

    def _str(self) -> str:
        output = str(self._comma) + str(self._name)
        return output + (str(self.next) if (self.next) else '')

    def __repr__(self) -> str:
        return ' ' + repr(self._name) + (repr(self.next) if (self.next) else '')


class StaticMember(ChildProduction):
    """
    Static member production.

    Syntax:
    "static" AttributeRest | "static" ReturnType OperationRest
    """

    _static: Symbol
    attribute: Optional[AttributeRest]
    return_type: Optional[ReturnType]
    operation: Optional[OperationRest]

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'static')):
            if (AttributeRest.peek(tokens)):
                return tokens.pop_position(True)
            if (ReturnType.peek(tokens)):
                return tokens.pop_position(OperationRest.peek(tokens))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._static = Symbol(tokens, 'static')
        if (AttributeRest.peek(tokens)):
            self.attribute = AttributeRest(tokens, self)
            self.return_type = None
            self.operation = None
        else:
            self.attribute = None
            self.return_type = ReturnType(tokens, self)
            self.operation = OperationRest(tokens, self)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'method' if (self.operation) else 'attribute'

    @property
    def stringifier(self) -> bool:
        return False

    @property
    def name(self) -> Optional[str]:
        return self.operation.name if (self.operation) else cast(AttributeRest, self.attribute).name

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self.operation.arguments if (self.operation) else None

    @property
    def method_name(self) -> Optional[str]:
        if (self.operation):
            name = self.name + '(' if (self.name) else '('
            if (self.arguments):
                name += self.arguments.argument_names[0]
            return name + ')'
        return None

    @property
    def method_names(self) -> List[str]:
        if (self.operation):
            if (self.arguments):
                return [_name(self) + '(' + argument_name + ')' for argument_name in self.arguments.argument_names]
            if (self.method_name):
                return [self.method_name]
        return []

    def _str(self) -> str:
        output = str(self._static)
        if (self.operation):
            return output + str(self.return_type) + str(self.operation)
        return output + str(self.attribute)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        self._static.define_markup(generator)
        if (self.operation):
            cast(ReturnType, self.return_type).define_markup(generator)
            return self.operation._define_markup(generator)
        return cast(AttributeRest, self.attribute)._define_markup(generator)

    def __repr__(self) -> str:
        output = '[StaticMember: '
        if (self.operation):
            return output + repr(self.return_type) + ' ' + repr(self.operation) + ']'
        return output + repr(self.attribute) + ']'


class Constructor(ChildProduction):
    """
    Constructor production.

    Syntax:
    "constructor" "(" ArgumentList ")" ";"
    """

    _constructor: Identifier
    _open_paren: Symbol
    _arguments: Optional[ArgumentList]
    _close_paren: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, 'constructor')):
            if (Symbol.peek(tokens, '(')):
                ArgumentList.peek(tokens)
                token = tokens.peek()
                return tokens.pop_position((token is not None) and token.is_symbol(')'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._constructor = Identifier(tokens)  # treat 'constructor' as a name
        self._open_paren = Symbol(tokens, '(')
        self._arguments = ArgumentList(tokens, self) if (ArgumentList.peek(tokens)) else None
        self._close_paren = Symbol(tokens, ')')
        self._consume_semicolon(tokens)
        self._did_parse(tokens)

    @property
    def idl_type(self) -> str:
        return 'method'

    @property
    def name(self) -> Optional[str]:
        return self._constructor.name

    @property
    def stringifier(self) -> bool:
        return False

    @property
    def arguments(self) -> Optional[protocols.ArgumentList]:
        return self._arguments

    @property
    def argument_names(self) -> Sequence[str]:
        return self._arguments.argument_names if (self._arguments) else ['']

    @property
    def method_name(self) -> Optional[str]:
        name = 'constructor('
        if (self._arguments):
            name += self._arguments.argument_names[0]
        return name + ')'

    @property
    def method_names(self) -> List[str]:
        if (self._arguments):
            return ['constructor(' + argument_name + ')' for argument_name in self._arguments.argument_names]
        return [self.method_name] if (self.method_name) else []

    def _str(self) -> str:
        output = self.name if (self.name) else ''
        return output + str(self._open_paren) + (str(self._arguments) if (self._arguments) else '') + str(self._close_paren)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        if (self._constructor):
            self._constructor.define_markup(generator)
        generator.add_text(self._open_paren)
        if (self._arguments):
            self._arguments.define_markup(generator)
        generator.add_text(self._close_paren)
        return self

    def __repr__(self) -> str:
        output = '[Constructor: '
        return output + '[ArgumentList: ' + (repr(self._arguments) if (self._arguments) else '') + ']]'


class ExtendedAttributeList(ChildProduction):
    """
    Extended attribute list production.

    Syntax:
    "[" ExtendedAttribute ["," ExtendedAttribute]... "]"
    """

    _open_bracket: Symbol
    attributes: List['constructs.ExtendedAttribute']
    _commas: List[Symbol]
    _close_bracket: Symbol

    @classmethod
    def peek(cls, tokens: Tokenizer) -> bool:
        tokens.push_position(False)
        if (Symbol.peek(tokens, '[')):
            return tokens.pop_position(tokens.peek_symbol(']'))
        return tokens.pop_position(False)

    def __init__(self, tokens: Tokenizer, parent: protocols.ChildProduction) -> None:
        ChildProduction.__init__(self, tokens, parent)
        self._open_bracket = Symbol(tokens, '[')
        self.attributes = []
        self._commas = []
        while (tokens.has_tokens()):
            self.attributes.append(constructs.ExtendedAttribute(tokens, parent))
            token = tokens.sneak_peek()
            if ((not token) or token.is_symbol(']')):
                break
            if (token.is_symbol(',')):
                self._commas.append(Symbol(tokens, ','))
                continue
        self._close_bracket = Symbol(tokens, ']')
        self._did_parse(tokens)

    def __len__(self) -> int:
        return len(self.attributes)

    def __getitem__(self, key: Union[str, int]) -> protocols.Construct:
        if (isinstance(key, str)):
            for attribute in self.attributes:
                if (key == attribute.name):
                    return attribute
            raise IndexError
        return self.attributes[key]

    def __contains__(self, key: Union[str, int]) -> bool:
        if (isinstance(key, str)):
            for attribute in self.attributes:
                if (key == attribute.name):
                    return True
            return False
        return (key in self.attributes)

    def __iter__(self) -> Iterator[protocols.Construct]:
        return iter(self.attributes)

    def keys(self) -> Sequence[str]:
        return [attribute.name for attribute in self.attributes if (attribute.name)]

    def values(self) -> Sequence[protocols.Construct]:
        return [attribute for attribute in self.attributes if (attribute.name)]

    def items(self) -> Sequence[Tuple[str, protocols.Construct]]:
        return [(attribute.name, attribute) for attribute in self.attributes if (attribute.name)]

    def get(self, key: Union[str, int]) -> Optional[protocols.Construct]:
        try:
            return self[key]
        except IndexError:
            return None

    def _str(self) -> str:
        output = str(self._open_bracket)
        output += ''.join([str(attribute) + str(comma) for attribute, comma in itertools.zip_longest(self.attributes, self._commas, fillvalue='')])
        return output + str(self._close_bracket)

    def _define_markup(self, generator: protocols.MarkupGenerator) -> protocols.Production:
        generator.add_text(self._open_bracket)
        for attribute, comma in itertools.zip_longest(self.attributes, self._commas, fillvalue=''):
            attribute.define_markup(generator)
            generator.add_text(comma)
        generator.add_text(self._close_bracket)
        return self

    def __repr__(self) -> str:
        return '[ExtendedAttributes: ' + ' '.join([repr(attribute) for attribute in self.attributes]) + '] '
