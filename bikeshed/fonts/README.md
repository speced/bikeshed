`bikeshed source --big-text` relies on a bespoke ASCII font format,
specified in [KDL](https://kdl.dev),
designed to be hand-authorable and easily readable.

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
