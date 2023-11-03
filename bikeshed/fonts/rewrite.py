from __future__ import annotations

import re
import sys

from .. import messages as m
from .. import t

if t.TYPE_CHECKING:
    from .fonts import Font


def replaceComments(font: Font, inputFilename: str | None = None, outputFilename: str | None = None) -> None:
    lines, inputFilename = getInputLines(inputFilename)
    replacements: list[tuple[int, int, list[str]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"\s*<!--\s*Big Text:\s*((?:(?!-->).)*)", line)
        if not match:
            i += 1
            continue
        endLineI = i
        while "-->" not in lines[endLineI]:
            endLineI += 1
        afterComment = lines[endLineI].split("-->", maxsplit=1)[1]
        if afterComment.strip() != "":
            m.die("Big Text comments must be the only thing on their line(s).", lineNum=endLineI)
            i = endLineI + 1
            continue
        textToEmbiggen = match.group(1).strip()
        newtext = [match.group(0) + "\n", "\n"] + font.write(textToEmbiggen) + ["-->\n"]
        replacements.append((i, endLineI, newtext))
        i = endLineI + 1
    for i, endI, newLines in reversed(replacements):
        lines[i : endI + 1] = newLines
    writeOutputLines(outputFilename, inputFilename, lines)


def getInputLines(inputFilename: str | None) -> tuple[list[str], str]:
    if inputFilename is None:
        # Default to looking for a *.bs file.
        # Otherwise, look for a *.src.html file.
        # Otherwise, use standard input.
        import glob

        if glob.glob("*.bs"):
            inputFilename = glob.glob("*.bs")[0]
        elif glob.glob("*.src.html"):
            inputFilename = glob.glob("*.src.html")[0]
        else:
            inputFilename = "-"
    try:
        if inputFilename == "-":
            lines = list(sys.stdin.readlines())
        else:
            with open(inputFilename, encoding="utf-8") as fh:
                lines = fh.readlines()
    except FileNotFoundError:
        m.die(f"Couldn't find the input file at the specified location '{inputFilename}'.")
        return ([], "")
    except OSError:
        m.die(f"Couldn't open the input file '{inputFilename}'.")
        return ([], "")
    return lines, inputFilename


def writeOutputLines(outputFilename: str | None, inputFilename: str, lines: list[str]) -> None:
    if outputFilename is None:
        outputFilename = inputFilename
    try:
        if outputFilename == "-":
            sys.stdout.write("".join(lines))
        else:
            with open(outputFilename, "w", encoding="utf-8") as f:
                f.write("".join(lines))
    except Exception as e:
        m.die(f"Something prevented me from saving the output document to {outputFilename}:\n{e}")
