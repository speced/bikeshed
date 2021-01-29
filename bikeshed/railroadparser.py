from . import railroaddiagrams as rr
from .messages import *


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
            die(
                "Inconsistent indentation: line {0} is indented less than the first line.",
                i,
            )
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
    blockNames = (
        "And|Seq|Sequence|Stack|Or|Choice|Opt|Optional|Plus|OneOrMore|Star|ZeroOrMore"
    )
    textNames = "T|Terminal|N|NonTerminal|C|Comment|S|Skip"
    for i, line in enumerate(lines, 1):
        indent = 0
        while line.startswith(indentText):
            indent += 1
            line = line[len(indentText) :]
        if indent > lastIndent + 1:
            die(
                "Line {0} jumps more than 1 indent level from the previous line:\n{1}",
                i,
                line.strip(),
            )
            return rr.Diagram()
        lastIndent = indent
        if re.match(fr"\s*({blockNames})\W", line):
            match = re.match(r"\s*(\w+)\s*:\s*(.*)", line)
            if not match:
                die(
                    "Line {0} doesn't match the grammar 'Command: optional-prelude'. Got:\n{1}",
                    i,
                    line.strip(),
                )
                return rr.Diagram()
            command = match.group(1)
            prelude = match.group(2).strip()
            node = {"command": command, "prelude": prelude, "children": [], "line": i}
        elif re.match(fr"\s*({textNames})\W", line):
            match = re.match(r"\s*(\w+)(\s[\w\s]+)?:\s*(.*)", line)
            if not match:
                die(
                    "Line {0} doesn't match the grammar 'Command [optional prelude]: text'. Got:\n{1},",
                    i,
                    line.strip(),
                )
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
            die(
                "Line {0} doesn't contain a valid railroad-diagram command. Got:\n{1}",
                i,
                line.strip(),
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
            return die("Line {0} - Terminal commands cannot have children.", line)
        return rr.Terminal(text, prelude)
    if command in ("N", "NonTerminal"):
        if children:
            return die("Line {0} - NonTerminal commands cannot have children.", line)
        return rr.NonTerminal(text, prelude)
    if command in ("C", "Comment"):
        if children:
            return die("Line {0} - Comment commands cannot have children.", line)
        return rr.Comment(text, prelude)
    if command in ("S", "Skip"):
        if children:
            return die("Line {0} - Skip commands cannot have children.", line)
        if text:
            return die("Line {0} - Skip commands cannot have text.", line)
        return rr.Skip()
    if command in ("And", "Seq", "Sequence"):
        if prelude:
            return die("Line {0} - Sequence commands cannot have preludes.", line)
        if not children:
            return die("Line {0} - Sequence commands need at least one child.", line)
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Sequence(*children)
    if command in ("Stack",):
        if prelude:
            return die("Line {0} - Stack commands cannot have preludes.", line)
        if not children:
            return die("Line {0} - Stack commands need at least one child.", line)
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Stack(*children)
    if command in ("Or", "Choice"):
        if prelude == "":
            default = 0
        else:
            try:
                default = int(prelude)
            except ValueError:
                die(
                    "Line {0} - Choice preludes must be an integer. Got:\n{1}",
                    line,
                    prelude,
                )
                default = 0
        if not children:
            return die("Line {0} - Choice commands need at least one child.", line)
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Choice(default, *children)
    if command in ("Opt", "Optional"):
        if prelude not in ("", "skip"):
            return die(
                "Line {0} - Optional preludes must be nothing or 'skip'. Got:\n{1}",
                line,
                prelude,
            )
        if len(children) != 1:
            return die("Line {0} - Optional commands need exactly one child.", line)
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.Optional(*children, skip=(prelude == "skip"))
    if command in ("Plus", "OneOrMore"):
        if prelude:
            return die("Line {0} - OneOrMore commands cannot have preludes.", line)
        if 0 == len(children) > 2:
            return die(
                "Line {0} - OneOrMore commands must have one or two children.", line
            )
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.OneOrMore(*children)
    if command in ("Star", "ZeroOrMore"):
        if prelude:
            return die("Line {0} - ZeroOrMore commands cannot have preludes.", line)
        if 0 == len(children) > 2:
            return die(
                "Line {0} - ZeroOrMore commands must have one or two children.", line
            )
        children = [_f for _f in [_createDiagram(**child) for child in children] if _f]
        return rr.ZeroOrMore(*children)
    return die("Line {0} - Unknown command '{1}'.", line, command)
