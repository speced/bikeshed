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
"""Classes to convert input strings into tokens."""

import collections
import enum
import re
from typing import Any, Container, Deque, Iterator, List, Optional, Union

from typing_extensions import Protocol


class UserInterface(Protocol):
    """Object to provide error output."""

    def warn(self, message: str) -> None:
        ...

    def note(self, message: str) -> None:
        ...


class TokenType(enum.Enum):
    """Enum for token types."""

    SYMBOL = 'symbol'
    IDENTIFIER = 'identifier'
    FLOAT = 'float'
    INTEGER = 'integer'
    STRING = 'string'
    WHITESPACE = 'whitespace'
    OTHER = 'other'


class Token(object):
    """WebIDL token."""

    type: TokenType
    text: str
    # XXX add line and column numbers

    def __init__(self, type: TokenType, text: str) -> None:
        self.type = type
        self.text = text

    def is_symbol(self, symbol: Union[str, Container[str]] = None) -> bool:
        """Check if token is a symbol, and optionally one of a given symbol."""
        if (TokenType.SYMBOL == self.type):
            if (symbol):
                if isinstance(symbol, str):
                    return (symbol == self.text)
                return (self.text in symbol)
            return True
        return False

    def is_identifier(self, identifier: Union[str, Container[str]] = None) -> bool:
        """Check if token is an identifier."""
        if (TokenType.IDENTIFIER == self.type):
            if (identifier):
                if isinstance(identifier, str):
                    return (identifier == self.text)
                return (self.text in identifier)
            return True
        return False

    def is_float(self) -> bool:
        """Check if token is a float."""
        return (TokenType.FLOAT == self.type)

    def is_integer(self) -> bool:
        """Check if token is an integer."""
        return (TokenType.INTEGER == self.type)

    def is_string(self) -> bool:
        """Check if token is a string."""
        return (TokenType.STRING == self.type)

    def is_whitespace(self) -> bool:
        """Check if token is whitespace."""
        return (TokenType.WHITESPACE == self.type)

    def __str__(self) -> str:
        """Convert to string."""
        return self.text

    def __repr__(self) -> str:
        """Debug info."""
        return '[' + self.type.value + ':' + self.text + ']'


class Tokenizer(object):
    """Consume a string and convert to tokens."""

    SYMBOL_IDENTS = frozenset((
        'any', 'async', 'attribute', 'ArrayBuffer', 'boolean', 'byte', 'ByteString', 'callback', 'const', 'constructor', 'creator', 'DataView',
        'deleter', 'dictionary', 'DOMString', 'double', 'enum', 'Error', 'exception', 'false', 'float',
        'Float32Array', 'Float64Array', 'FrozenArray', 'getter', 'implements', 'includes', 'Infinity', '-Infinity', 'inherit', 'Int8Array',
        'Int16Array', 'Int32Array', 'interface', 'iterable', 'legacycaller', 'legacyiterable', 'long', 'maplike', 'mixin',
        'namespace', 'NaN', 'null', 'object', 'octet', 'optional', 'or', 'partial', 'Promise', 'readonly', 'record', 'required',
        'sequence', 'setlike', 'setter', 'short', 'static', 'stringifier', 'true', 'typedef',
        'Uint8Array', 'Uint16Array', 'Uint32Array', 'Uint8ClampedArray', 'unrestricted', 'unsigned', 'USVString',
        'void'))

    ui: Optional[UserInterface]
    tokens: Deque[Token]
    position_stack: List[int]
    peek_index: int
    line_number: int
    # XXX add column number

    def __init__(self, text: str, ui: UserInterface = None) -> None:
        self.ui = ui
        self.tokens = collections.deque()
        self.position_stack = []
        self.peek_index = -1
        self.line_number = 1
        self._tokenize(text)

    def _tokenize(self, text: str) -> None:
        while (0 < len(text)):
            match = re.match(r'(-?(([0-9]+\.[0-9]*|[0-9]*\.[0-9]+)([Ee][+-]?[0-9]+)?|[0-9]+[Ee][+-]?[0-9]+))(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token(TokenType.FLOAT, match.group(1)))
                text = match.group(5)
                continue
            match = re.match(r'(-?(0[Xx][0-9A-Fa-f]+|0[0-7]*|[1-9][0-9]*))(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token(TokenType.INTEGER, match.group(1)))
                text = match.group(3)
                continue
            match = re.match(r'(_?[A-Z_a-z][0-9A-Z_a-z]*)(.*)', text, re.DOTALL)
            if (match):
                if (match.group(1) in self.SYMBOL_IDENTS):
                    self.tokens.append(Token(TokenType.SYMBOL, match.group(1)))
                else:
                    self.tokens.append(Token(TokenType.IDENTIFIER, match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'("[^"]*")(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token(TokenType.STRING, match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'((\s+|//[^\n\r]*|/\*.*?\*/)+)(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token(TokenType.WHITESPACE, match.group(1)))
                text = match.group(3)
                continue
            match = re.match(r'(-Infinity|-|,|;|:|\?|\.\.\.|\.|\(|\)|\[|\]|\{|\}|\<|=|\>)(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token(TokenType.SYMBOL, match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'([^\s0-9A-Z_a-z])(.*)', text, re.DOTALL)
            if (match is None):
                break
            self.tokens.append(Token(TokenType.OTHER, match.group(1)))
            text = match.group(2)

    def __str__(self) -> str:
        """Convert all tokens to string."""
        return ''.join([str(token) for token in self.tokens])

    def __repr__(self) -> str:
        """Debug info."""
        return ''.join([repr(token) for token in self.tokens])

    def has_tokens(self, skip_whitespace: bool = True) -> bool:
        """Test if one or more tokens are available, optionally ignoring whitespace."""
        if (self.tokens):
            if (skip_whitespace and self.tokens[0].is_whitespace()):
                return (1 < len(self.tokens))
            return True
        return False

    def __iter__(self) -> Iterator[Token]:
        return self

    def __next__(self) -> Token:
        token = self.next()
        if (token is None):
            raise StopIteration
        return token

    def next(self, skip_whitespace: bool = True) -> Optional[Token]:
        """Remove and return next available token, optionally skipping whitespace."""
        self.reset_peek()
        if (self.tokens):
            token = self.tokens.popleft()
            self.line_number += token.text.count('\n')
            if (skip_whitespace and token.is_whitespace()):
                if (not self.tokens):
                    return None
                token = self.tokens.popleft()
                self.line_number += token.text.count('\n')
            return token
        return None

    def restore(self, token: Token) -> None:
        """Return token to the front of the stream."""
        if (token):
            self.line_number -= token.text.count('\n')
            self.tokens.appendleft(token)

    def whitespace(self) -> Optional[Token]:
        """Get next token only if it is whitespace."""
        token = self.next(False)
        if (token):
            if (token.is_whitespace()):
                return token
            self.restore(token)
        return None

    def push_position(self, and_peek: bool = True) -> Optional[Token]:  # XXX split into two functions
        """Save current lookahead index and optionally lookahead next token."""
        self.position_stack.append(self.peek_index)
        return self.peek() if (and_peek) else None

    def pop_position(self, hold_position: bool) -> bool:  # XXX rename, split into 3 funcs?
        """Remove saved lookahead state and optionally rewind lookahead index."""
        index = self.position_stack.pop()
        if (not hold_position):
            self.peek_index = index
        return hold_position

    def peek(self, skip_whitespace: bool = True) -> Optional[Token]:
        """Return next available token without removing it, advance lookahead index, optionally skip whitespace."""
        self.peek_index += 1
        if (self.peek_index < len(self.tokens)):
            token = self.tokens[self.peek_index]
            if (skip_whitespace and token.is_whitespace()):
                self.peek_index += 1
                return self.tokens[self.peek_index] if (self.peek_index < len(self.tokens)) else None
            return token
        return None

    def sneak_peek(self, skip_whitespace: bool = True) -> Optional[Token]:
        """Return next available token without removing it or advancing lookahead index, optionally skip whitespace."""
        if ((self.peek_index + 1) < len(self.tokens)):
            token = self.tokens[self.peek_index + 1]
            if (skip_whitespace and token.is_whitespace()):
                return self.tokens[self.peek_index + 2] if ((self.peek_index + 2) < len(self.tokens)) else None
            return token
        return None

    def peek_symbol(self, symbol: str) -> bool:
        """Advance lookahead index until symbol token is found, respect nesting of (), {}, []."""
        token = self.peek()
        while (token and (not token.is_symbol(symbol))):
            if (token.is_symbol('(')):
                self.peek_symbol(')')
            elif (token.is_symbol('{')):
                self.peek_symbol('}')
            elif (token.is_symbol('[')):
                self.peek_symbol(']')
            token = self.peek()
        return ((token is not None) and token.is_symbol(symbol))

    def reset_peek(self) -> None:
        """Reset lookahead index to first available token."""
        assert (0 == len(self.position_stack))
        self.peek_index = -1

    def seek_symbol(self, symbol: Union[str, Container[str]]) -> List[Token]:
        """Return all tokens up to and inculding symbol, respect nesting of (), {}, []."""
        token = self.next(False)
        skipped = []
        while (token and (not token.is_symbol(symbol))):
            skipped.append(token)
            if (token.is_symbol('(')):
                skipped += self.seek_symbol(')')
            elif (token.is_symbol('{')):
                skipped += self.seek_symbol('}')
            elif (token.is_symbol('[')):
                skipped += self.seek_symbol(']')
            token = self.next(False)
        if (token):
            skipped.append(token)
        return skipped

    def syntax_error(self, symbol: Union[None, str, Container[str]], ending: bool = True) -> List[Token]:
        """Seek to symbol and report skipped tokens as syntax error."""
        line_number = self.line_number
        skipped = self.seek_symbol(symbol) if (symbol) else []
        if (self.ui and hasattr(self.ui, 'warn')):
            message = 'IDL SYNTAX ERROR LINE: ' + str(line_number) + ' - '
            if (ending):
                message += 'expected ";" '

            skip = skipped[:-1] if (skipped and (0 < len(skipped))
                                    and (skipped[-1].is_symbol(';')
                                    or ((1 < len(skipped)) and skipped[-1].is_symbol('}')))) else skipped

            if (symbol):
                if (skip):
                    self.ui.warn(message + 'skipped: "' + ''.join([str(token) for token in skip]) + '"\n')
            else:
                self.ui.warn(message + '\n')
        return skipped

    def error(self, *args) -> None:
        """Report non-syntax error."""
        if (self.ui and hasattr(self.ui, 'warn')):
            message = 'IDL ERROR LINE: ' + str(self.line_number) + ' - ' + ''.join([str(arg) for arg in args])
            self.ui.warn(message + '\n')

    def did_ignore(self, ignored: Any) -> None:
        """Report ignored content."""
        if (self.ui and hasattr(self.ui, 'note')):
            message = 'IGNORED LEGACY IDL LINE: ' + str(self.line_number) + ' - "'
            ignore_text = ''.join(str(ignore) for ignore in ignored) if (hasattr(ignored, '__iter__')) else str(ignored)
            self.ui.note(message + ignore_text + '"\n')
