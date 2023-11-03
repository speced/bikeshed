#!/usr/bin/python3
from __future__ import annotations

import dataclasses
import itertools
import re
import string
import sys

import kdl

if __name__ == "__main__":
    from bikeshed import config, t
    from bikeshed import messages as m
else:
    from .. import config, t
    from .. import messages as m

if t.TYPE_CHECKING:
    Characters: t.TypeAlias = dict[str, list[str]]
    T = t.TypeVar("T")
    U = t.TypeVar("U")
    from pathlib import Path


@dataclasses.dataclass
class Font:
    md: FontMetadata
    characters: Characters

    def __init__(self, characters: Characters, md: FontMetadata) -> None:
        if len(characters) == 0:
            m.die("Font file has no character data at all.")
            raise Exception
        self.md = md
        self.characters = normalizeCharacters(characters, md)

    @staticmethod
    def fromPath(fontfilepath: str | Path = config.scriptPath("fonts", "smallblocks.kdl")) -> Font:
        try:
            with open(fontfilepath, encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:
            m.die(f"Couldn't find font file “{fontfilepath}”:\n{e}")
            raise e
        return Font.fromKdl(text)

    @staticmethod
    def fromKdl(kdlText: str) -> Font:
        doc = kdl.parse(kdlText)
        partialMd = getMetadata(doc)
        chars = {}
        for node in doc["characters"].nodes:
            lines = node.args[0].split("\n")
            chars[node.name] = lines
        md = partialMd.inferFromCharacters(chars)
        return Font(chars, md)

    def write(self, text: str) -> list[str]:
        output = [""] * self.md.height
        for letterIndex, letter in enumerate(text):
            if letter in self.characters:
                for i, line in enumerate(self.characters[letter]):
                    if letterIndex != 0:
                        output[i] += " "
                    output[i] += line
            else:
                m.die(f"The character “{letter}” doesn't appear in the specified font.")
                continue
        output = [line + "\n" for line in output]
        return output


@dataclasses.dataclass
class FontMetadata:
    height: int
    stripFirstLine: bool


@dataclasses.dataclass
class PartialFontMetadata:
    height: int | None = None
    stripFirstLine: bool | None = None

    def inferFromCharacters(
        self,
        chars: Characters,
        height: int | None = None,
        stripFirstLine: bool | None = None,
    ) -> FontMetadata:
        if self.stripFirstLine is None:
            self.stripFirstLine = inferStripFirstLine(chars)
        if self.height is None:
            self.height = inferHeight(chars, stripFirstLine=self.stripFirstLine)
        return FontMetadata(self.height, self.stripFirstLine)


def normalizeCharacters(chars: Characters, md: FontMetadata) -> Characters:
    # Ensure that:
    # * every character is the same height
    # * within each character, every line is the same length
    # * copy uppercase from lowercase, and vice versa,
    #   if both versions dont' exist
    # * if stripFirstLines is true, the first (empty) line of each is removed
    for name, lines in chars.items():
        if md.stripFirstLine:
            if lines[0].strip() == "":
                lines = lines[1:]
            else:
                m.die(f"Character '{name}' has a non-empty first line, but strip-first-line was set to True.")
        if len(lines) == md.height:
            pass
        elif len(lines) > md.height:
            m.die(f"Character '{name}' has more lines ({len(lines)}) than the declared font height ({md.height}).")
        elif len(lines) < md.height:
            lines.extend([""] * (md.height - len(lines)))
        width = max(len(line) for line in lines)
        for i, line in enumerate(lines):
            # Make sure the letter is a rectangle.
            if len(line) < width:
                lines[i] += " " * (width - len(line))
    for char in string.ascii_lowercase:
        # Allow people to specify only one case for letters if they want.
        if char in chars and char.upper() not in chars:
            chars[char.upper()] = chars[char]
        if char.upper() in chars and char not in chars:
            chars[char] = chars[char.upper()]
    return chars


def getMetadata(doc: kdl.Document) -> PartialFontMetadata:
    height = None
    stripFirstLine = None
    if doc.has("config"):
        config = doc.get("config")
        if "height" in config.props:
            height = int(config.props["height"])
        if "stripFirstLine" in config.props:
            stripFirstLine = bool(config.props["stripFirstLine"])
    return PartialFontMetadata(height=height, stripFirstLine=stripFirstLine)


def inferHeight(chars: Characters, stripFirstLine: bool) -> int:
    # All characters need to be the same height,
    # so the largest height must be the height of *all* characters.
    heights = []
    for lines in chars.values():
        if stripFirstLine and lines[0].strip() == "":
            charHeight = len(lines) - 1
        else:
            charHeight = len(lines)
        heights.append(charHeight)
    return max(heights)


def inferStripFirstLine(chars: Characters) -> bool:
    return all(lines[0].strip() == "" for lines in chars.values())


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser(description="Outputs text as giant ASCII art.")
    argparser.add_argument(
        "--font",
        dest="fontPath",
        default=config.scriptPath("fonts", "smallblocks.kdl"),
        help="What .kdl font file to use to render the text with.",
    )
    argparser.add_argument("text", help="Text to ASCII-ify.")
    options = argparser.parse_args()
    font = Font.fromPath(options.fontPath)
    for line in font.write(options.text):
        print(line, end="")  # noqa: T201


if __name__ == "__main__":
    main()
