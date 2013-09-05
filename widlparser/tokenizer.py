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

import re
import collections

class Token(object):
    def __init__(self, type, text):
        self.type = type
        self.text = text
    
    def isSymbol(self, symbol = None):
        if ('symbol' == self.type):
            if (symbol):
                if isinstance(symbol, basestring):
                    return (symbol == self.text)
                return (self.text in symbol)
            return True
        return False

    def isIdentifier(self):
        return ('identifier' == self.type)
    
    def isFloat(self):
        return ('float' == self.type)
    
    def isInteger(self):
        return ('integer' == self.type)
    
    def isString(self):
        return ('string' == self.type)
    
    def isWhitespace(self):
        return ('whitespace' == self.type)
    
    def __str__(self):
        return self.text

    def __repr__(self):
        return '[' + self.type + ':' + self.text + ']'



class Tokenizer(object):
    SymbolIdents = frozenset([
        'any', 'attribute', 'boolean', 'byte', 'callback', 'const', 'creator', 'Date', 'deleter', 'dictionary',
        'DOMString', 'double', 'enum', 'exception', 'false', 'float', 'getter', 'implements', 'Infinity', 'inherit',
        'interface', 'legacycaller', 'long', 'NaN', 'null', 'object', 'octet', 'optional', 'or', 'partial',
        'readonly', 'sequence', 'setter', 'short', 'static', 'stringifier', 'true', 'typedef', 'unrestricted',
        'unsigned', 'void'])
    
    def __init__(self, text, ui = None):
        self.ui = ui
        self.tokens = collections.deque()
        self.positionStack = []
        self.peekIndex = -1
        self._tokenize(text)

    def _tokenize(self, text):
        while (0 < len(text)):
            match = re.match(r'(-?(([0-9]+\.[0-9]*|[0-9]*\.[0-9]+)([Ee][+-]?[0-9]+)?|[0-9]+[Ee][+-]?[0-9]+))(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token('float', match.group(1)))
                text = match.group(5)
                continue
            match = re.match(r'(-?(0([0-7]*|[Xx][0-9A-Fa-f]+)|[1-9][0-9]*))(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token('integer', match.group(1)))
                text = match.group(4)
                continue
            match = re.match(r'([A-Z_a-z][0-9A-Z_a-z]*)(.*)', text, re.DOTALL)
            if (match):
                if (match.group(1) in self.SymbolIdents):
                    self.tokens.append(Token('symbol', match.group(1)))
                else:
                    self.tokens.append(Token('identifier', match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'("[^"]*")(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token('string', match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'((\s+|//[^\n\r]*|/\*.*?\*/)+)(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token('whitespace', match.group(1)))
                text = match.group(3)
                continue
            match = re.match(r'(-|,|;|:|\?|\.\.\.|\.|\(|\)|\[|\]|\{|\}|\<|=|\>)(.*)', text, re.DOTALL)
            if (match):
                self.tokens.append(Token('symbol', match.group(1)))
                text = match.group(2)
                continue
            match = re.match(r'([^\s0-9A-Z_a-z])(.*)', text, re.DOTALL)
            self.tokens.append(Token('other', match.group(1)))
            text = match.group(2)

    def __str__(self):
        return ''.join([str(token) for token in self.tokens])

    def __repr__(self):
        return ''.join([repr(token) for token in self.tokens])

    def hasTokens(self, skipWhitespace = True):
        "Test if one or more tokens are available, optionally ignoring whitespace"
        if (0 < len(self.tokens)):
            if (skipWhitespace and self.tokens[0].isWhitespace()):
                return (1 < len(self.tokens))
            return True
        return False
    
    def next(self, skipWhitespace = True):
        "Remove and return next available token, optionally skipping whitespace"
        self.resetPeek()
        if (0 < len(self.tokens)):
            token = self.tokens.popleft()
            if (skipWhitespace and token.isWhitespace()):
                return self.tokens.popleft() if (0 < len(self.tokens)) else None
            return token
        return None
    
    def restore(self, token):
        "Return token to the front of the stream"
        if (token):
            self.tokens.appendleft(token)

    def pushPosition(self, andPeek = True):
        "Save current lookahead index and optionally lookahead next token"
        self.positionStack.append(self.peekIndex)
        return self.peek() if (andPeek) else None
    
    def popPosition(self, holdPosition):
        "Remove saved lookahead state and optionally rewind lookahead index"
        index = self.positionStack.pop()
        if (not holdPosition):
            self.peekIndex = index
        return holdPosition
    
    def peek(self, skipWhitespace = True):
        "Return next available token without removing it, advance lookahead index, optionally skip whitespace"
        self.peekIndex += 1
        if (self.peekIndex < len(self.tokens)):
            token = self.tokens[self.peekIndex]
            if (skipWhitespace and token.isWhitespace()):
                self.peekIndex += 1
                return self.tokens[self.peekIndex] if (self.peekIndex < len(self.tokens)) else None
            return token
        return None
    
    def sneakPeek(self, skipWhitespace = True):
        "Return next available token without removing it or advancing lookahead index, optionally skip whitespace"
        if ((self.peekIndex + 1) < len(self.tokens)):
            token = self.tokens[self.peekIndex + 1]
            if (skipWhitespace and token.isWhitespace()):
                return self.tokens[self.peekIndex + 2] if ((self.peekIndex + 2) < len(self.tokens)) else None
        return None
    
    def peekSymbol(self, symbol):
        "Advance lookahead index until symbol token is found, respect nesting of (), {}, []"
        token = self.peek()
        while (token and (not token.isSymbol(symbol))):
            if (token.isSymbol('(')):
                self.peekSymbol(')')
            elif (token.isSymbol('{')):
                self.peekSymbol('}')
            elif (token.isSymbol('[')):
                self.peekSymbol(']')
            token = self.peek()
        return token
    
    def resetPeek(self):
        "Reset lookahead index to first available token"
        assert (0 == len(self.positionStack))
        self.peekIndex = -1

    def seekSymbol(self, symbol):
        "Return all tokens up to and inculding symbol, respect nesting of (), {}, []"
        token = self.next(False)
        skipped = []
        while (token and (not token.isSymbol(symbol))):
            skipped.append(token)
            if (token.isSymbol('(')):
                skipped += self.seekSymbol(')')
            elif (token.isSymbol('{')):
                skipped += self.seekSymbol('}')
            elif (token.isSymbol('[')):
                skipped += self.seekSymbol(']')
            token = self.next(False)
        skipped.append(token)
        return skipped

    def syntaxError(self, symbol):
        "Seek to symbol and report skipped tokens as syntax error"
        skipped = self.seekSymbol(symbol)
        if (self.ui):
            self.ui.warn('IDL SYNTAX ERROR - skipped: ' + ''.join([str(token) for token in skipped]) + '\n')
        return skipped
    

