from . import railroaddiagrams as rr, messages as m


def parse(string):
    """
    Parses a DSL for railroad diagrams,
    based on significant whitespace.
    Each command must be on its own line,
    and is written like "Sequence:\n".
    Children are indented on following lines.
    Some commands have non-child arguments;
    for block commands they are put on the same line, after the :,
    for text commands they are put on the same line *before* the :,
    like:
        Choice: 0
            Terminal: foo
            Terminal raw: bar
    """
    import re

    lines = string.splitlines()

    # Strip off any common initial whitespace from lines.
    initialIndent = re.match(r"(\s*)", lines[0]).group(1)
    for i, line in enumerate(lines):
        if line.startswith(initialIndent):
            lines[i] = line[len(initialIndent) :]
        else:
            m.die(f"Inconsistent indentation: line {i} is indented less than the first line.")
            return rr.Diagram()

    # Determine subsequent indentation
    for line in lines:
        match = re.match(r"(\s+)", line)
        if match:
            indentText = match.group(1)
            break
    else:
        indentText = "\t"

    # Turn lines into tree
    lastIndent = 0
    tree = {"command": "Diagram", "prelude": "", "children": []}
    activeCommands = {"0": tree}
    blockNames = "And|Seq|Sequence|Stack|Or|Choice|Opt|Optional|Plus|OneOrMore|Star|ZeroOrMore"
    textNames = "T|Terminal|N|NonTerminal|C|Comment|S|Skip"
    for i, line in enumerate(lines, 1):
        indent = 0
        while line.startswith(indentText):
            indent += 1
            line = line[len(indentText) :]
        if indent > lastIndent + 1:
            m.die(f"Line {i} jumps more than 1 indent level from the previous line:\n{line.strip()}")
            return rr.Diagram()
        lastIndent = indent
        if re.match(rf"\s*({blockNames})\W", line):
            match = re.match(r"\s*(\w+)\s*:\s*(.*)", line)
            if not match:
                m.die(f"Line {i} doesn't match the grammar 'Command: optional-prelude'. Got:\n{line.strip()}")
                return rr.Diagram()
            command = match.group(1)
            prelude = match.group(2).strip()
            node = {"command": command, "prelude": prelude, "children": [], "line": i}
        elif re.match(rf"\s*({textNames})\W", line):
            match = re.match(r"\s*(\w+)(\s[\w\s]+)?:\s*(.*)", line)
            if not match:
                m.die(f"Line {i} doesn't match the grammar 'Command [optional prelude]: text'. Got:\n{line.strip()},")
                return rr.Diagram()
            command = match.group(1)
            if match.group(2):
                prelude = match.group(2).strip()
            else:
                prelude = None
            text = match.group(3).strip()
            node = {
                "command": command,
                "prelude": prelude,
                "text": text,
                "children": [],
                "line": i,
            }
        else:
            m.die(
                f"Line {i} doesn't contain a valid railroad-diagram command. Got:\n{line.strip()}",
            )
            return

        activeCommands[str(indent)]["children"].append(node)
        activeCommands[str(indent + 1)] = node

    return _createDiagram(**tree)


def _createDiagram(command, prelude, children, text=None, line=-1):
    """
    From a tree of commands,
    create an actual Diagram class.
    Each command must be {command, prelude, children}
    """
    if command == "Diagram":
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Diagram(*children)
    if command in ("T", "Terminal"):
        if children:
            return m.die(f"Line {line} - Terminal commands cannot have children.")
        return rr.Terminal(text, prelude)
    if command in ("N", "NonTerminal"):
        if children:
            return m.die(f"Line {line} - NonTerminal commands cannot have children.")
        return rr.NonTerminal(text, prelude)
    if command in ("C", "Comment"):
        if children:
            return m.die(f"Line {line} - Comment commands cannot have children.")
        return rr.Comment(text, prelude)
    if command in ("S", "Skip"):
        if children:
            return m.die(f"Line {line} - Skip commands cannot have children.")
        if text:
            return m.die(f"Line {line} - Skip commands cannot have text.")
        return rr.Skip()
    if command in ("And", "Seq", "Sequence"):
        if prelude:
            return m.die(f"Line {line} - Sequence commands cannot have preludes.")
        if not children:
            return m.die(f"Line {line} - Sequence commands need at least one child.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Sequence(*children)
    if command in ("Stack",):
        if prelude:
            return m.die(f"Line {line} - Stack commands cannot have preludes.")
        if not children:
            return m.die(f"Line {line} - Stack commands need at least one child.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Stack(*children)
    if command in ("Or", "Choice"):
        if prelude == "":
            default = 0
        else:
            try:
                default = int(prelude)
            except ValueError:
                m.die(f"Line {line} - Choice preludes must be an integer. Got:\n{prelude}")
                default = 0
        if not children:
            return m.die(f"Line {line} - Choice commands need at least one child.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Choice(default, *children)
    if command in ("Opt", "Optional"):
        if prelude not in ("", "skip"):
            return m.die(f"Line {line} - Optional preludes must be nothing or 'skip'. Got:\n{prelude}")
        if len(children) != 1:
            return m.die(f"Line {line} - Optional commands need exactly one child.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Optional(*children, skip=(prelude == "skip"))
    if command in ("Plus", "OneOrMore"):
        if prelude:
            return m.die(f"Line {line} - OneOrMore commands cannot have preludes.")
        if 0 == len(children) > 2:
            return m.die(f"Line {line} - OneOrMore commands must have one or two children.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.OneOrMore(*children)
    if command in ("Star", "ZeroOrMore"):
        if prelude:
            return m.die(f"Line {line} - ZeroOrMore commands cannot have preludes.")
        if 0 == len(children) > 2:
            return m.die(f"Line {line} - ZeroOrMore commands must have one or two children.")
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.ZeroOrMore(*children)
    return m.die(f"Line {line} - Unknown command '{command}'.")
