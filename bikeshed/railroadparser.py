from __future__ import annotations

import dataclasses

from . import messages as m
from . import railroaddiagrams as rr
from . import t


def parse(string: str) -> rr.Diagram | None:
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
    initialIndent = t.cast(re.Match, re.match(r"(\s*)", lines[0])).group(1)
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
    tree = RRCommand(name="Diagram", prelude="", children=[], text=None, line=0)
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
            node = RRCommand(name=command, prelude=prelude, children=[], text=None, line=i)
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
            node = RRCommand(
                name=command,
                prelude=prelude,
                children=[],
                text=text,
                line=i,
            )
        else:
            m.die(
                f"Line {i} doesn't contain a valid railroad-diagram command. Got:\n{line.strip()}",
            )
            return None

        activeCommands[str(indent)].children.append(node)
        activeCommands[str(indent + 1)] = node

    diagram = _createDiagram(tree)
    assert diagram is None or isinstance(diagram, rr.Diagram)
    return diagram


@dataclasses.dataclass
class RRCommand:
    name: str
    prelude: str | None
    children: list[RRCommand]
    text: str | None
    line: int


def _createDiagram(command: RRCommand) -> rr.DiagramItem | None:
    """
    From a tree of commands,
    create an actual Diagram class.
    Each command must be {command, prelude, children}
    """
    if command.name == "Diagram":
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.Diagram(*children)
    if command.name in ("T", "Terminal"):
        if command.children:
            m.die(f"Line {command.line} - Terminal commands cannot have children.")
            return None
        return rr.Terminal(command.text or "", command.prelude)
    if command.name in ("N", "NonTerminal"):
        if command.children:
            m.die(f"Line {command.line} - NonTerminal commands cannot have children.")
            return None
        return rr.NonTerminal(command.text or "", command.prelude)
    if command.name in ("C", "Comment"):
        if command.children:
            m.die(f"Line {command.line} - Comment commands cannot have children.")
            return None
        return rr.Comment(command.text or "", command.prelude)
    if command.name in ("S", "Skip"):
        if command.children:
            m.die(f"Line {command.line} - Skip commands cannot have children.")
            return None
        if command.text:
            m.die(f"Line {command.line} - Skip commands cannot have text.")
            return None
        return rr.Skip()
    if command.name in ("And", "Seq", "Sequence"):
        if command.prelude:
            m.die(f"Line {command.line} - Sequence commands cannot have preludes.")
            return None
        if not command.children:
            m.die(f"Line {command.line} - Sequence commands need at least one child.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.Sequence(*children)
    if command.name in ("Stack",):
        if command.prelude:
            m.die(f"Line {command.line} - Stack commands cannot have preludes.")
            return None
        if not command.children:
            m.die(f"Line {command.line} - Stack commands need at least one child.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.Stack(*children)
    if command.name in ("Or", "Choice"):
        if command.prelude == "":
            default = 0
        else:
            try:
                default = int(t.cast(str, command.prelude))
            except ValueError:
                m.die(f"Line {command.line} - Choice preludes must be an integer. Got:\n{command.prelude}")
                default = 0
        if not command.children:
            m.die(f"Line {command.line} - Choice commands need at least one child.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.Choice(default, *children)
    if command.name in ("Opt", "Optional"):
        if command.prelude not in (None, "", "skip"):
            m.die(f"Line {command.line} - Optional preludes must be nothing or 'skip'. Got:\n{command.prelude}")
            return None
        if len(command.children) != 1:
            m.die(f"Line {command.line} - Optional commands need exactly one child.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.Optional(children[0], skip=(command.prelude == "skip"))
    if command.name in ("Plus", "OneOrMore"):
        if command.prelude:
            m.die(f"Line {command.line} - OneOrMore commands cannot have preludes.")
            return None
        if 0 == len(command.children) > 2:
            m.die(f"Line {command.line} - OneOrMore commands must have one or two children.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        return rr.OneOrMore(*children)
    if command.name in ("Star", "ZeroOrMore"):
        if command.prelude not in (None, "", "skip"):
            m.die(f"Line {command.line} - ZeroOrMore preludes must be nothing or 'skip'. Got:\n{command.prelude}")
            return None
        if 0 == len(command.children) > 2:
            m.die(f"Line {command.line} - ZeroOrMore commands must have one or two children.")
            return None
        children = [_f for _f in [_createDiagram(child) for child in command.children] if _f]
        if not children:
            m.die(f"Line {command.line} - ZeroOrMore has no valid children.")
            return None
        repeat = children[1] if len(children) == 2 else None
        return rr.ZeroOrMore(children[0], repeat=repeat, skip=(command.prelude == "skip"))
    m.die(f"Line {command.line} - Unknown command '{command.name}'.")
    return None
