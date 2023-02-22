from __future__ import annotations

import dataclasses
import itertools
import re
import sys

if __name__ == "__main__":
    from bikeshed import config, messages as m, t
else:
    from . import config, messages as m, t

if t.TYPE_CHECKING:
    Characters: t.TypeAlias = dict[str, list[str]]
    T = t.TypeVar("T")
    U = t.TypeVar("U")


@dataclasses.dataclass
class FontMetadata:
    height: int
    spaceWidth: int


class Font:
    """
    Explanation of the BSFONT font file format:

    BSFONT is a plain-text font format designed to be hand-authorable and easily readable.

    A BSFONT file starts with one or more metadata lines.
    These are lines of the form "Key: Value".
    * **Character Height**: Required.  It specifies how many lines tall each character in the font is.  (All letters must be the same height.)
    * **Space Width**: Optional.  This specifies the width of an ASCII space character in the font.  (Writing a space in the normal character format is hard to read.) If your font wants a space that isn't just whitespace, you can still specify it as a normal character.

    The first line that doesn't match the metadata format is assumed to be the start of the character data.
    The character data is composed of groups of lines each specifying how to render one character.
    The first line of each group is the character being described.  It should be the only text on the line.
    The next several lines (equal to the **Character Height**) are the character itself, rendered as ASCII art.
    Each letter is assumed to be monospace rectangular;
    if not all lines are the same width,
    they're end-padded with spaces to become rectangular.

    For ASCII letters, if you define only one casing,
    that rendering is used for both casings.
    That is, if you only want capital letters,
    just define it for "A", "B", etc,
    and it'll automatically apply to "a", "b", etc as well.

    Here is an example BSFONT file:

    ```
    Character Height: 7
    Space Width: 5
    A
       ███
      ██ ██
     ██   ██
    ██     ██
    █████████
    ██     ██
    ██     ██
    B
    ████████
    ██     ██
    ██     ██
    ████████
    ██     ██
    ██     ██
    ████████
    ```

    This defines a font capable of rendering text composed of "A", "B", "a", "b", and " ".

    """

    def __init__(self, fontfilename: str = config.scriptPath("bigblocks.bsfont")):
        try:
            with open(fontfilename, encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception as e:
            m.die(f"Couldn't find font file “{fontfilename}”:\n{e}")
            raise e
        self.metadata, lines = parseMetadata(lines)
        self.characters = parseCharacters(self.metadata, lines)

    def write(self, text: str) -> list[str]:
        output = [""] * self.metadata.height
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


def parseMetadata(lines: list[str]) -> tuple[FontMetadata, list[str]]:
    # Each metadata line is of the form "key: value".
    # First line that's not of that form ends the metadata.
    # Returns the parsed metadata, and the non-metadata lines
    i = 0
    height = None
    spaceWidth = None
    for i, line in enumerate(lines):
        match = re.match(r"([^:]+):\s+(\S.*)", line)
        if not match:
            break
        key = match.group(1)
        val = match.group(2)
        if key == "Character Height":
            height = int(val)
        elif key == "Space Width":
            spaceWidth = int(val)
        else:
            m.die(f"Unrecognized font metadata “{key}”")
            continue
    if height is None:
        m.die("Missing 'Character Height' metadata.")
        raise Exception("")
    if spaceWidth is None:
        m.die("Missing 'Space Width' metadata.")
        raise Exception("")
    md = FontMetadata(height, spaceWidth)
    return md, lines[i:]


def parseCharacters(md: FontMetadata, lines: list[str]) -> Characters:
    import string

    height = md.height
    characters: Characters = {}
    characters[" "] = [" " * md.spaceWidth] * height
    for bigcharlines in grouper(lines, height + 1, ""):
        littlechar = bigcharlines[0][0]
        bigchar = [line.strip("\n") for line in bigcharlines[1:]]
        width = max(len(line) for line in bigchar)
        for i, line in enumerate(bigchar):
            # Make sure the letter is a rectangle.
            if len(line) < width:
                bigchar[i] += " " * (width - len(line))
        characters[littlechar] = bigchar
    for char in string.ascii_lowercase:
        # Allow people to specify only one case for letters if they want.
        if char in characters and char.upper() not in characters:
            characters[char.upper()] = characters[char]
        if char.upper() in characters and char not in characters:
            characters[char] = characters[char.upper()]
    return characters


def replaceComments(font: Font, inputFilename: str | None = None, outputFilename: str | None = None) -> None:
    lines, inputFilename = getInputLines(inputFilename)
    replacements: list[tuple[int, list[str]]] = []
    for i, line in enumerate(lines):
        match = re.match(r"\s*<!--\s*Big Text:\s*(\S.*)-->", line)
        if match:
            newtext = ["<!--\n"] + font.write(match.group(1).strip()) + ["-->\n"]
            replacements.append((i, newtext))
    for r in reversed(replacements):
        lines[r[0] : r[0] + 1] = r[1]
    writeOutputLines(outputFilename, inputFilename, lines)


# Some utility functions


def grouper(iterable: t.Sequence[T], n: int, fillvalue: U) -> t.Generator[list[T | U], None, None]:
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return (list(t.cast("t.Iterable[T|U]", x)) for x in itertools.zip_longest(fillvalue=fillvalue, *args))


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


def main() -> None:
    import argparse

    argparser = argparse.ArgumentParser(description="Outputs text as giant ASCII art.")
    argparser.add_argument(
        "--font",
        dest="fontPath",
        default=config.scriptPath("bigblocks.bsfont"),
        help="What .bsfont file to use to render the text with.",
    )
    argparser.add_argument("text", help="Text to ASCII-ify.")
    options = argparser.parse_args()
    font = Font(options.fontPath)
    for line in font.write(options.text):
        print(line, end="")


if __name__ == "__main__":
    main()
