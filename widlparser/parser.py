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

import tokenizer
from constructs import *


class Parser(object):
    def __init__(self, text = None, ui = None):
        self.ui = ui
        self.reset()
        if (text):
            self.parse(text)
        
    def reset(self):
        self.constructs = []

    def complexityFactor(self):
        complexity = 0
        for construct in self.constructs:
            complexity += construct.complexityFactor()
        return complexity
    
    def parse(self, text):
        tokens = tokenizer.Tokenizer(text, self.ui)

        while (tokens.hasTokens()):
            if (Callback.peek(tokens)):
                self.constructs.append(Callback(tokens))
            elif (Interface.peek(tokens)):
                self.constructs.append(Interface(tokens))
            elif (Dictionary.peek(tokens)):
                self.constructs.append(Dictionary(tokens))
            elif (Exception.peek(tokens)):
                self.constructs.append(Exception(tokens))
            elif (Enum.peek(tokens)):
                self.constructs.append(Enum(tokens))
            elif (Typedef.peek(tokens)):
                self.constructs.append(Typedef(tokens))
            elif (Const.peek(tokens)):   # Legacy support (SVG spec)
                self.constructs.append(Const(tokens))
            elif (ImplementsStatement.peek(tokens)):
                self.constructs.append(ImplementsStatement(tokens))
            else:
                tokens.syntaxError(';')
        

    def __str__(self):
        return ''.join([str(construct) for construct in self.constructs])

    def __repr__(self):
        return '[Parser: ' + ''.join([(repr(construct) + '\n') for construct in self.constructs]) + ']'

    def __len__(self):
        return len(self.constructs)
    
    def __getitem__(self, key):
        if (isinstance(key, basestring)):
            for construct in self.constructs:
                if (key == construct.name):
                    return construct
            return None
        return self.constructs[key]
    
    def __nonzero__(self):
        return True
    
    def __iter__(self):
        return iter(self.constructs)
    
    def __contains__(self, key):
        if (isinstance(key, basestring)):
            for construct in self.constructs:
                if (key == construct.name):
                    return True
            return False
        return (key in self.constructs)

    def find(self, name):
        match = re.match('(.*)\(.*\)(.*)', name)    # strip ()'s
        while (match):
            name = match.group(1) + match.group(2)
            match = re.match('(.*)\(.*\)(.*)', name)
        
        path = None
        if ('/' in name):
            path = name.split('/')
        elif ('.' in name):
            path = name.split('.')
            
        if (path):
            constructName = path[0]
            memberName = path[1]
            argumentName = path[2] if (2 < len(path)) else memberName
            for construct in reversed(self.constructs):
                if (constructName == construct.name):
                    if (1 == len(path)):
                        return construct
                    for member in construct:
                        if (memberName == member.name):
                            if (2 < len(path)):
                                argument = member.findArgument(argumentName)
                                if (argument):
                                    return argument
                            else:
                                return member
                    else:
                        if (2 == len(path)):
                            argument = construct.findArgument(argumentName, False)
                            if (argument):
                                return argument
            return None
        
        for construct in reversed(self.constructs):
            if (name == construct.name):
                return construct

        # check inside top level constructs
        for construct in reversed(self.constructs):
            member = construct.findMember(name)
            if (member):
                return member

        # check argument names last
        for construct in reversed(self.constructs):
            argument = construct.findArgument(name)
            if (argument):
                return argument

    def normalizedMethodName(self, methodText):
        match = re.match(r'(.*)\((.*)\)(.*)', methodText)
        if (match):
            tokens = tokenizer.Tokenizer(match.group(2))
            if (ArgumentList.peek(tokens)):
                arguments = ArgumentList(tokens, None)
                return match.group(1) + '(' + ', '.join([argument.name for argument in arguments]) + ')'
            name = match.group(1) + match.group(3)
            arguments = match.group(2)
        else:
            name = methodText
            arguments = ''
        construct = self.find(name)
        if (construct and ('method' == construct.idlType)):
            return construct.methodName
        for construct in self.constructs:
            method = construct.findMethod(name)
            if (method):
                return method.methodName
        return name + '(' + arguments + ')'


