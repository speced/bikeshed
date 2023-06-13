import re

from pygments.lexer import RegexLexer, bygroups
from pygments.token import Comment, Keyword, Literal, Name, Punctuation, Text


class CSSLexer(RegexLexer):
    name = "CSS"
    aliases = ["css"]
    filenames = ["*.css"]
    flags = re.DOTALL

    tokens = {
        "root": [
            (r"/\*", Comment, "comment"),
            (r"@[\w-]+", Name),
            (
                r"([+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)[eE][+-]?(?:\d+(?:\.\d+)?|\d*\.\d+))([a-zA-Z-]+|%)",
                bygroups(Literal.Number, Keyword),
            ),
            (
                r"[+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)[eE][+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)",
                Literal.Number,
            ),
            (
                r"([+-]?(?:\d+(?:\.\d+)?|\d*\.\d+))([a-zA-Z-]+|%)",
                bygroups(Literal.Number, Keyword),
            ),
            (r"[+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)", Literal.Number),
            (
                r"(^|{|;)(\s*)([\w-]+)(\s*)(:)",
                bygroups(Punctuation, Text, Keyword, Text, Punctuation),
            ),
            (
                r"(url)(\()([^)]*)(\))",
                bygroups(Name.Function, Punctuation, Literal.String, Punctuation),
            ),
            (r"(:?[\w-]+)(\()", bygroups(Name.Function, Punctuation)),
            (r"\"[^\"]*\"", Literal.String),
            (r"'[^']*'", Literal.String),
            (r"#?[\w-]+", Text),
            (r"[;,(){}\[\]]", Punctuation),
            (r"\s+", Text),
            (r".", Text),
        ],
        "comment": [(r"\*/", Comment, "#pop"), (r".", Comment)],
    }
