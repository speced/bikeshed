# -*- coding: utf-8 -*-

import re
from pygments.lexer import *
from pygments.token import *


class CSSLexer(RegexLexer):
    name = "CSS"
    aliases = ['css']
    filenames = ['*.css']
    flags = re.DOTALL

    tokens = {
        "root": [
            (r"", Text, "rules"),
        ],
        "comment": [
            (r"\*/", Comment, "#pop"),
            (r".", Comment)
        ],
        "at-rule": [
            include("values"),
            (r";", Punctuation, "#pop"),
            (r"{\s*}", Punctuation, "#pop"),
            (r"{(?=[^;}]*{)", Punctuation, ("#pop", "rules")),
            (r"{(?=[^{}]*;)", Punctuation, ("#pop", "decls")),
            (r"", Text, "#pop")
        ],
        "rules": [
            (r"/\*", Comment, "comment"),
            (r"\s+", Text),
            (r"@[\w-]+", Name, "at-rule"),
            (r"}", Punctuation, "#pop"),
            (r"([^{]+)({)", bygroups(Name.Tag, Punctuation), "decls"),
        ],
        "decls": [
            (r";", Punctuation),
            (r"@[\w-]+", Name, "at-rule"),
            (r"([\w-]+)\s*(:)", bygroups(Keyword, Punctuation)),
            include("values"),
            (r"}", Punctuation, "#pop"),
            (r".+", Text)
        ],
        "values": [
            (r"/\*", Comment, "comment"),
            (r"[(),/]", Punctuation),
            (r"([+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)[eE][+-]?(?:\d+(?:\.\d+)?|\d*\.\d+))([a-zA-Z-]+|%)", bygroups(Literal.Number, Literal)),
            (r"[+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)[eE][+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)", Literal.Number),
            (r"([+-]?(?:\d+(?:\.\d+)?|\d*\.\d+))([a-zA-Z-]+|%)", bygroups(Literal.Number, Literal)),
            (r"[+-]?(?:\d+(?:\.\d+)?|\d*\.\d+)", Literal.Number),
            (r"(url)(\()([^)]*)(\))", bygroups(Name.Function, Punctuation, Literal.String, Punctuation)),
            (r"([\w-]+)(\()", bygroups(Name.Function, Punctuation)),
            (r"\"[^\"]*\"", Literal.String),
            (r"'[^']*'", Literal.String),
            (r"#?[\w-]+", Text),
            (r"\s+", Text)
        ]
    }
