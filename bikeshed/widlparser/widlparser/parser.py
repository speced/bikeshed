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
"""Parser class to parse WebIDL."""

import itertools
import re
from typing import Dict, Iterator, List, Optional, Sequence, Tuple, Union, cast

from . import constructs
from . import markup
from . import protocols
from . import tokenizer


class Parser(object):
    """Class to parse WebIDL."""

    ui: Optional[tokenizer.UserInterface]
    symbol_table: Dict[str, protocols.Construct]
    constructs: List[protocols.Construct]

    def __init__(self, text: str = None, ui: tokenizer.UserInterface = None, symbol_table: dict = None) -> None:
        self.ui = ui
        self.symbol_table = symbol_table if (symbol_table) else {}
        self.reset()
        if (text):
            self.parse(text)

    def reset(self) -> None:
        """Clear all parsed data."""
        self.constructs = []

    @property
    def complexity_factor(self) -> int:
        """Return measure of overall complexity."""
        complexity = 0
        for construct in self.constructs:
            complexity += construct.complexity_factor
        return complexity

    def parse(self, text: str) -> None:
        """Parse input text, appending to existing content."""
        tokens = tokenizer.Tokenizer(text, self.ui)

        while (tokens.has_tokens()):
            if (constructs.Callback.peek(tokens)):
                self.constructs.append(constructs.Callback(tokens, symbol_table=self))
            elif (constructs.Interface.peek(tokens)):
                self.constructs.append(constructs.Interface(tokens, symbol_table=self))
            elif (constructs.Mixin.peek(tokens)):
                self.constructs.append(constructs.Mixin(tokens, symbol_table=self))
            elif (constructs.Namespace.peek(tokens)):
                self.constructs.append(constructs.Namespace(tokens, symbol_table=self))
            elif (constructs.Dictionary.peek(tokens)):
                self.constructs.append(constructs.Dictionary(tokens, symbol_table=self))
            elif (constructs.Enum.peek(tokens)):
                self.constructs.append(constructs.Enum(tokens, symbol_table=self))
            elif (constructs.Typedef.peek(tokens)):
                self.constructs.append(constructs.Typedef(tokens, symbol_table=self))
            elif (constructs.Const.peek(tokens)):   # Legacy support (SVG spec)
                self.constructs.append(constructs.Const(tokens, symbol_table=self))
            elif (constructs.ImplementsStatement.peek(tokens)):
                self.constructs.append(constructs.ImplementsStatement(tokens, symbol_table=self))
            elif (constructs.IncludesStatement.peek(tokens)):
                self.constructs.append(constructs.IncludesStatement(tokens, symbol_table=self))
            else:
                self.constructs.append(constructs.SyntaxError(tokens, None, symbol_table=self))

    def __str__(self) -> str:
        """
        Convert parsed WebIDL back in to a string.

        The parser is nullipotent, so output will match input unless contents have been modified.
        """
        return ''.join([str(construct) for construct in self.constructs])

    def __repr__(self) -> str:
        """Debug info."""
        return '[Parser: ' + ''.join([(repr(construct) + '\n') for construct in self.constructs]) + ']'

    def __bool__(self) -> bool:
        """True if non-empty."""
        return (0 < len(self.constructs))

    def __len__(self) -> int:
        """Number of parsed constucts."""
        return len(self.constructs)

    def __getitem__(self, key: Union[str, int]) -> protocols.Construct:
        """Access a construct by name or index."""
        if (isinstance(key, str)):
            for construct in self.constructs:
                if (key == construct.name):
                    return construct
            raise IndexError
        return self.constructs[key]

    def __contains__(self, key: Union[str, int]) -> bool:
        """Test is construct is present by name or index."""
        if (isinstance(key, str)):
            for construct in self.constructs:
                if (key == construct.name):
                    return True
            return False
        return (key in self.constructs)

    def __iter__(self) -> Iterator[protocols.Construct]:
        """Get an iterator for the constructs."""
        return iter(self.constructs)

    def keys(self) -> Sequence[str]:
        """Names of all constructs."""
        return [construct.name for construct in self.constructs if (construct.name)]

    def values(self) -> Sequence[protocols.Construct]:
        return [construct for construct in self.constructs if (construct.name)]

    def items(self) -> Sequence[Tuple[str, protocols.Construct]]:
        return [(construct.name, construct) for construct in self.constructs if (construct.name)]

    def get(self, key: Union[str, int]) -> Optional[protocols.Construct]:
        try:
            return self[key]
        except IndexError:
            return None

    def add_type(self, type: protocols.Construct) -> None:
        """Add a type to the symbol table."""
        if (type.name):
            self.symbol_table[type.name] = type

    def get_type(self, name: str) -> Optional[protocols.Construct]:
        """Lookup a type in the symbol table."""
        return self.symbol_table.get(name)

    def find(self, name: str) -> Optional[protocols.Construct]:
        """
        Find a construct by name.

        Searches entire tree in reverse order.
        """
        match = re.match(r'(.*)\(.*\)(.*)', name)    # strip ()'s
        while (match):
            name = match.group(1) + match.group(2)
            match = re.match(r'(.*)\(.*\)(.*)', name)

        path = None
        if ('/' in name):
            path = name.split('/')
        elif ('.' in name):
            path = name.split('.')

        construct: Optional[protocols.Construct]
        member: Optional[protocols.Construct]
        if (path):
            construct_name = path[0]
            member_name = path[1]
            argument_name = path[2] if (2 < len(path)) else member_name
            for construct in reversed(self.constructs):
                if (construct_name == construct.name):
                    if (1 == len(path)):
                        return construct
                    for member in reversed(construct):
                        if (member_name == member.name):
                            if (2 < len(path)):
                                argument = member.find_argument(argument_name)
                                if (argument):
                                    return argument
                            else:
                                return member
                    else:
                        if (2 == len(path)):
                            argument = construct.find_argument(argument_name, False)
                            if (argument):
                                return argument
            return None

        for construct in reversed(self.constructs):
            if (name == construct.name):
                return construct

        # check inside top level constructs
        for construct in reversed(self.constructs):
            member = construct.find_member(name)
            if (member):
                return member

        # check argument names last
        for construct in reversed(self.constructs):
            argument = construct.find_argument(name)
            if (argument):
                return argument

        return None

    def find_all(self, name: str) -> List[protocols.Construct]:
        """
        Find all constructs with a given name.

        Searches entire tree.
        """
        match = re.match(r'(.*)\(.*\)(.*)', name)    # strip ()'s
        while (match):
            name = match.group(1) + match.group(2)
            match = re.match(r'(.*)\(.*\)(.*)', name)

        path = None
        if ('/' in name):
            path = name.split('/')
        elif ('.' in name):
            path = name.split('.')

        result = []

        if (path):
            construct_name = path[0]
            member_name = path[1]
            argument_name = path[2] if (2 < len(path)) else member_name
            for construct in self.constructs:
                if (construct_name == construct.name):
                    if (1 == len(path)):
                        result.append(construct)
                        continue
                    for member in construct:
                        if (member_name == member.name):
                            if (2 < len(path)):
                                argument = member.find_argument(argument_name)
                                if (argument):
                                    result.append(argument)
                            else:
                                result.append(member)
                    else:
                        if (2 == len(path)):
                            argument = construct.find_argument(argument_name, False)
                            if (argument):
                                result.append(argument)
            return result

        for construct in self.constructs:
            if (name == construct.name):
                result.append(construct)

        # check inside top level constructs
        for construct in self.constructs:
            result += construct.find_members(name)

        # check argument names last
        for construct in self.constructs:
            result += construct.find_arguments(name)

        return result

    def normalized_method_name(self, method_text: str, interface_name: str = None) -> str:
        """Return normalized name for a method description."""
        argument_names: Optional[List[str]]
        match = re.match(r'(.*)\((.*)\)(.*)', method_text)
        if (match):
            tokens = tokenizer.Tokenizer(match.group(2))
            if (constructs.ArgumentList.peek(tokens)):
                arguments = constructs.ArgumentList(tokens, None)
                return match.group(1).strip() + '(' + arguments.argument_names[0] + ')'
            name = match.group(1).strip() + match.group(3)
            argument_names = [argument.strip() for argument in match.group(2).split(',')]
        else:
            name = method_text
            argument_names = None

        if (interface_name):
            interface = self.find(interface_name)
            if (interface):
                method = interface.find_method(name, argument_names)
                if (method):
                    return cast(str, method.method_name)
            return name + '(' + ', '.join(argument_names or []) + ')'

        construct: Optional[protocols.Construct]
        for construct in self.constructs:
            method = construct.find_method(name, argument_names)
            if (method):
                return cast(str, method.method_name)

        construct = self.find(name)
        if (construct and ('method' == construct.idl_type)):
            return cast(str, construct.method_name)
        return name + '(' + ', '.join(argument_names or []) + ')'

    def normalized_method_names(self, method_text: str, interface_name: str = None) -> List[str]:
        """Return all possible normalized names for a method description."""
        argument_names: Optional[List[str]]
        match = re.match(r'(.*)\((.*)\)(.*)', method_text)
        if (match):
            tokens = tokenizer.Tokenizer(match.group(2))
            if (constructs.ArgumentList.peek(tokens)):
                arguments = constructs.ArgumentList(tokens, None)
                return [match.group(1).strip() + '(' + argument_name + ')' for argument_name in arguments.argument_names]
            name = match.group(1).strip() + match.group(3)
            argument_names = [argument.strip() for argument in match.group(2).split(',')]
        else:
            name = method_text
            argument_names = None

        if (interface_name):
            interface = self.find(interface_name)
            if (interface):
                methods = interface.find_methods(name, argument_names)
                if (methods):
                    return list(itertools.chain(*[method.method_names for method in methods]))
            return [name + '(' + ', '.join(argument_names or []) + ')']

        construct: Optional[protocols.Construct]
        for construct in self.constructs:
            methods = construct.find_methods(name, argument_names)
            if (methods):
                return list(itertools.chain(*[method.method_names for method in methods]))

        construct = self.find(name)
        if (construct and ('method' == construct.idl_type)):
            return construct.method_names
        return [name + '(' + ', '.join(argument_names or []) + ')']

    def markup(self, marker: protocols.Marker = None) -> str:
        """Generate marked up version of parsed content."""
        if (marker):
            generator = markup.MarkupGenerator(None)
            for construct in self.constructs:
                construct.define_markup(generator)
            return generator.markup(marker)
        return str(self)
