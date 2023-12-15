To regen the styles, edit and run the below

```python
from pygments import token, style
from pygment.formatters import HtmlFormatter
class PrismStyle(style.Style):
    default_style = "#000000"
    styles = {
        token.Name: "#0077aa",
        token.Name.Tag: "#669900",
        token.Name.Builtin: "noinherit",
        token.Name.Variable: "#222222",
        token.Name.Other: "noinherit",
        token.Operator: "#999999",
        token.Punctuation: "#999999",
        token.Keyword: "#990055",
        token.Literal: "#000000",
        token.Literal.Number: "#000000",
        token.Literal.String: "#a67f59",
        token.Comment: "#708090"
    }
print HtmlFormatter(style=PrismStyle).get_style_defs('.highlight')
```