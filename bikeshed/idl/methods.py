from __future__ import annotations

import re

import widlparser


def find_webidl_methods(parser: widlparser.Parser, method_text: str) -> list[widlparser.Construct]:
    # Until https://github.com/plinss/widlparser/pull/98 is merged,
    # this copies the function over manually.
    # Once merged/updated, switch to `doc.widl.find_methods()` and delete this.
    match = re.match(r"(?:([^./(]+)[./])?([^./(]+)(?:\((.*)\))?", method_text)
    if not match:
        return []
    interface_name, name, arg_text = match.groups()

    empty_args = False  # Empty args might indicate explicitly zero arguments, or just args not passed
    if arg_text is not None:
        tokens = widlparser.Tokenizer(arg_text)
        if widlparser.productions.ArgumentList.peek(tokens):
            arguments = widlparser.productions.ArgumentList(tokens, None)
            arg_text = arguments.argument_names[0]
        argument_names = [argument.strip() for argument in arg_text.split(",") if argument.strip() != ""]
        if len(argument_names) == 0:
            empty_args = True
    else:
        argument_names = None

    if interface_name:
        interfaces = parser.find_all(interface_name)
        for interface in interfaces:
            methods = interface.find_methods(name, argument_names)
            if not methods and empty_args:
                methods = interface.find_methods(name)
            methods.reverse()
            if methods:
                return methods
        return []

    result = []
    construct: widlparser.Construct | None
    for construct in parser.constructs:
        methods = construct.find_methods(name, argument_names)
        if not methods and empty_args:
            methods = construct.find_methods(name)
        if methods:
            result.extend(methods)
    if result:
        result.reverse()
        return result

    construct = parser.find(name)
    if construct and (construct.idl_type == "method"):
        return [construct]

    return []
