#!/usr/bin/python3
from __future__ import annotations

import dataclasses
import string

import kdl

if __name__ == "__main__":
    from bikeshed import config, t
    from bikeshed import messages as m
else:
    from .. import config, t
    from .. import messages as m

if t.TYPE_CHECKING:
    Glyphs: t.TypeAlias = dict[str, Glyph]
    T = t.TypeVar("T")
    U = t.TypeVar("U")
    from pathlib import Path


@dataclasses.dataclass
class Font:
    md: FontMetadata
    glyphs: Glyphs

    def __init__(self, glyphs: Glyphs, md: FontMetadata) -> None:
        if len(glyphs) == 0:
            m.die("Font file has no character data at all.")
            raise Exception
        self.md = md
        self.glyphs = normalizeCharacters(glyphs, md)

    @staticmethod
    def fromPath(fontfilepath: str | Path) -> Font:
        try:
            with open(fontfilepath, encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:
            m.die(f"Couldn't find font file “{fontfilepath}”:\n{e}")
            raise e
        return Font.fromKdl(text)

    @staticmethod
    def fromKdl(kdlText: str) -> Font:
        try:
            doc = kdl.parse(kdlText)
        except Exception as e:
            m.die("Invalid font:\n{e}")
            raise e
        partialMd = getMetadata(doc)
        glyphsNode = doc.get("glyphs")
        assert glyphsNode is not None
        assert len(glyphsNode.nodes) != 0
        glyphs: Glyphs = {}
        for node in glyphsNode.nodes:
            glyphs[node.name] = Glyph.fromKdl(node)
        md = partialMd.inferFromGlyphs(glyphs)

        return Font(glyphs, md)

    def write(self, text: str) -> list[str]:
        output = [""] * self.md.height
        for letterIndex, letter in enumerate(text):
            if letter in self.glyphs:
                for i, line in enumerate(self.glyphs[letter].data):
                    # Give letters one space of letter-spacing
                    if letterIndex != 0:
                        output[i] += " "
                    output[i] += line
            else:
                m.die(f"The character “{letter}” doesn't appear in the specified font.")
                continue
        output = [line + "\n" for line in output]
        return output


@dataclasses.dataclass
class Glyph:
    name: str
    data: list[str]
    width: int

    @property
    def height(self) -> int:
        return len(self.data)

    @staticmethod
    def fromKdl(node: kdl.Node) -> Glyph:
        width = node.props.get("width")
        if width is not None:
            width = int(width)
        lines = None
        for arg in node.args:
            if isinstance(arg, str):
                lines = arg.split("\n")
                break
        if lines is None:
            if width is not None:
                lines = [" " * width]
            else:
                m.die(f"Letter '{node.name}' doesn't contain any glyph data.")
                raise ValueError
        assert lines is not None

        if len(lines) > 2:
            # When I update to kdl v2, remove this adjuster,
            # since that'll just be part of multiline string syntax.
            # For now, remove the first and last (hopefully empty) lines
            # from multiline strings
            lines = lines[1:-1]

        # Make sure the char is rectangular
        maxWidth = max(len(line) for line in lines)
        if width:
            if width >= maxWidth:
                maxWidth = width
            else:
                m.die(f"Letter '{node.name}' is wider ({maxWidth}) than its declared width ({width}).")
                raise ValueError
        for i, line in enumerate(lines):
            if len(line) < maxWidth:
                lines[i] += " " * (maxWidth - len(line))

        return Glyph(
            name=node.name,
            data=lines,
            width=maxWidth,
        )


@dataclasses.dataclass
class FontMetadata:
    height: int


@dataclasses.dataclass
class PartialFontMetadata:
    height: int | None = None

    def inferFromGlyphs(self, glyphs: Glyphs) -> FontMetadata:
        if self.height is None:
            self.height = inferHeight(glyphs)
        return FontMetadata(self.height)


def normalizeCharacters(glyphs: Glyphs, md: FontMetadata) -> Glyphs:
    # Ensure that:
    # * every character is the same height
    # * within each character, every line is the same length
    # * copy uppercase from lowercase, and vice versa,
    #   if both versions dont' exist
    for name, glyph in glyphs.items():
        if glyph.height == md.height:
            pass
        elif glyph.height > md.height:
            m.die(f"Character '{name}' has more lines ({glyph.height}) than the declared font height ({md.height}).")
            raise ValueError
        elif glyph.height < md.height:
            glyph.data.extend([" " * glyph.width] * (md.height - glyph.height))
    for letter in string.ascii_lowercase:
        # Allow people to specify only one case for letters if they want.
        if letter in glyphs and letter.upper() not in glyphs:
            glyphs[letter.upper()] = dataclasses.replace(glyphs[letter], name=letter.upper())
        if letter.upper() in glyphs and letter not in glyphs:
            glyphs[letter] = dataclasses.replace(glyphs[letter.upper()], name=letter)
    return glyphs


def getMetadata(doc: kdl.Document) -> PartialFontMetadata:
    height = None
    if node := doc.get("config"):
        if "height" in node.props:
            height = int(node.props["height"])
    return PartialFontMetadata(height=height)


def inferHeight(glyphs: Glyphs) -> int:
    # All characters need to be the same height,
    # so the largest height must be the height of *all* characters.
    return max((x.height for x in glyphs.values()), default=0)


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser(description="Outputs text as giant ASCII art.")
    argparser.add_argument(
        "--font",
        dest="fontPath",
        default=config.scriptPath("fonts", "smallblocks.bsfont"),
        help="What KDL font file to use to render the text with.",
    )
    argparser.add_argument("text", help="Text to ASCII-ify.")
    options = argparser.parse_args()
    font = Font.fromPath(options.fontPath)
    for line in font.write(options.text):
        print(line, end="")  # noqa: T201


if __name__ == "__main__":
    main()
