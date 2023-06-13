import re

from pygments import formatters, style, token

# dark
text = "#657b83"
bg = "#002b36"

# light
# text = "#839496"
# bg = "#fdf6e3"

# both
yellow = "#b58900"
orange = "#cb4b16"
red = "#dc322f"
magenta = "#d33682"
violet = "#6c71c4"
blue = "#268bd2"
cyan = "#2aa198"
green = "#859900"


class PrismStyle(style.Style):
    default_style = text
    styles = {
        token.Name: blue,
        token.Name.Tag: yellow,
        token.Name.Builtin: "noinherit",
        token.Name.Variable: orange,
        token.Name.Other: "noinherit",
        token.Operator: text,
        token.Punctuation: text,
        token.Keyword: magenta,
        token.Literal: text,
        token.Literal.Number: text,
        token.Literal.String: violet,
        token.Comment: cyan,
    }


css = formatters.HtmlFormatter(style=PrismStyle).get_style_defs(".c")  # pylint: disable=no-member
css = re.sub(r"\.c \.(\w+)", r"c-[\1]", css)
print(css)  # noqa: T201
