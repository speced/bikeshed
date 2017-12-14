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
import itertools

import tokenizer
from constructs import *


class Parser(object):
    def __init__(self, text = None, ui = None, symbolTable = None):
        self.ui = ui
        self.symbolTable = symbolTable if (symbolTable) else {}
        self.reset()
        if (text):
            self.parse(text)

    def reset(self):
        self.constructs = []

    @property
    def complexityFactor(self):
        complexity = 0
        for construct in self.constructs:
            complexity += construct.complexityFactor
        return complexity

    def parse(self, text):
        tokens = tokenizer.Tokenizer(text, self.ui)

        while (tokens.hasTokens()):
            if (Callback.peek(tokens)):
                self.constructs.append(Callback(tokens, parser = self))
            elif (Interface.peek(tokens)):
                self.constructs.append(Interface(tokens, parser = self))
            elif (Mixin.peek(tokens)):
                self.constructs.append(Mixin(tokens, parser = self))
            elif (Namespace.peek(tokens)):
                self.constructs.append(Namespace(tokens, parser = self))
            elif (Dictionary.peek(tokens)):
                self.constructs.append(Dictionary(tokens, parser = self))
            elif (Enum.peek(tokens)):
                self.constructs.append(Enum(tokens, parser = self))
            elif (Typedef.peek(tokens)):
                self.constructs.append(Typedef(tokens, parser = self))
            elif (Const.peek(tokens)):   # Legacy support (SVG spec)
                self.constructs.append(Const(tokens, parser = self))
            elif (ImplementsStatement.peek(tokens)):
                self.constructs.append(ImplementsStatement(tokens, parser = self))
            elif (IncludesStatement.peek(tokens)):
                self.constructs.append(IncludesStatement(tokens, parser = self))
            else:
                self.constructs.append(SyntaxError(tokens, None, parser = self))

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return u''.join([unicode(construct) for construct in self.constructs])

    def __repr__(self):
        return '[Parser: ' + ''.join([(repr(construct) + '\n') for construct in self.constructs]) + ']'

    def __len__(self):
        return len(self.constructs)

    def keys(self):
        return [construct.name for construct in self.constructs]

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

    def addType(self, type):
        self.symbolTable[type.name] = type

    def getType(self, name):
        return self.symbolTable.get(name)

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
                    for member in reversed(construct):
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

        return None

    def findAll(self, name):
        match = re.match('(.*)\(.*\)(.*)', name)    # strip ()'s
        while (match):
            name = match.group(1) + match.group(2)
            match = re.match('(.*)\(.*\)(.*)', name)

        path = None
        if ('/' in name):
            path = name.split('/')
        elif ('.' in name):
            path = name.split('.')

        result = []

        if (path):
            constructName = path[0]
            memberName = path[1]
            argumentName = path[2] if (2 < len(path)) else memberName
            for construct in self.constructs:
                if (constructName == construct.name):
                    if (1 == len(path)):
                        result.append(construct)
                        continue
                    for member in construct:
                        if (memberName == member.name):
                            if (2 < len(path)):
                                argument = member.findArgument(argumentName)
                                if (argument):
                                    result.append(argument)
                            else:
                                result.append(member)
                    else:
                        if (2 == len(path)):
                            argument = construct.findArgument(argumentName, False)
                            if (argument):
                                result.append(argument)
            return result

        for construct in self.constructs:
            if (name == construct.name):
                result.append(construct)

        # check inside top level constructs
        for construct in self.constructs:
            result += construct.findMembers(name)

        # check argument names last
        for construct in self.constructs:
            result += construct.findArguments(name)

        return result

    def normalizedMethodName(self, methodText, interfaceName = None):
        match = re.match(r'(.*)\((.*)\)(.*)', methodText)
        if (match):
            tokens = tokenizer.Tokenizer(match.group(2))
            if (ArgumentList.peek(tokens)):
                arguments = ArgumentList(tokens, None)
                return match.group(1) + '(' + arguments.argumentNames[0] + ')'
            name = match.group(1) + match.group(3)
            argumentNames = [argument.strip() for argument in match.group(2).split(',')]
        else:
            name = methodText
            argumentNames = None

        if (interfaceName):
            interface = self.find(interfaceName)
            if (interface):
                method = interface.findMethod(name, argumentNames)
                if (method):
                    return method.methodName
            return name + '(' + ', '.join(argumentNames or []) + ')'

        for construct in self.constructs:
            method = construct.findMethod(name, argumentNames)
            if (method):
                return method.methodName

        construct = self.find(name)
        if (construct and ('method' == construct.idlType)):
            return construct.methodName
        return name + '(' + ', '.join(argumentNames or []) + ')'

    def normalizedMethodNames(self, methodText, interfaceName = None):
        match = re.match(r'(.*)\((.*)\)(.*)', methodText)
        if (match):
            tokens = tokenizer.Tokenizer(match.group(2))
            if (ArgumentList.peek(tokens)):
                arguments = ArgumentList(tokens, None)
                return [match.group(1) + '(' + argumentName + ')' for argumentName in arguments.argumentNames]
            name = match.group(1) + match.group(3)
            argumentNames = [argument.strip() for argument in match.group(2).split(',')]
        else:
            name = methodText
            argumentNames = None

        if (interfaceName):
            interface = self.find(interfaceName)
            if (interface):
                methods = interface.findMethods(name, argumentNames)
                if (methods):
                    return list(itertools.chain(*[method.methodNames for method in methods]))
            return [name + '(' + ', '.join(argumentNames or []) + ')']

        for construct in self.constructs:
            methods = construct.findMethods(name, argumentNames)
            if (methods):
                return list(itertools.chain(*[method.methodNames for method in methods]))

        construct = self.find(name)
        if (construct and ('method' == construct.idlType)):
            return construct.methodNames
        return [name + '(' + ', '.join(argumentNames or []) + ')']

    def markup(self, marker):
        if (marker):
            generator = MarkupGenerator(None)
            for construct in self.constructs:
                construct.markup(generator)
            return generator.markup(marker)
        return unicode(self)


