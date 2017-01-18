# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
import re
from pygments.lexer import *
from pygments.token import *


class CSSLexer(RegexLexer):
    name = "CSS"
    aliases = ['css']
    filenames = ['*.css']
    flags = re.DOTALL

    tokens = {
        b"root": [
            (r"", Text, b"rules"),
        ],
        b"comment": [
            (r"\*/", Comment, b"#pop"),
            (r".", Comment)
        ],
        b"at-rule": [
            include(b"values"),
            (r";", Punctuation, b"#pop"),
            (r"{\s*}", Punctuation, b"#pop"),
            (r"{(?=[^;}]*{)", Punctuation, (b"#pop", b"rules")),
            (r"{(?=[^{}]*;)", Punctuation, (b"#pop", b"decls")),
            (r"", Text, b"#pop")
        ],
        b"rules": [
            (r"/\*", Comment, b"comment"),
            (r"\s+", Text),
            (r"@[\w-]+", Name, b"at-rule"),
            (r"}", Punctuation, b"#pop"),
            (r"([^{]+)({)", bygroups(Name.Tag, Punctuation), b"decls"),
        ],
        b"decls": [
            (r";", Punctuation),
            (r"@[\w-]+", Name, b"at-rule"),
            (r"([\w-]+)\s*(:)", bygroups(Keyword, Punctuation)),
            include(b"values"),
            (r"}", Punctuation, b"#pop"),
            (r".+", Text)
        ],
        b"values": [
            (r"/\*", Comment, b"comment"),
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
