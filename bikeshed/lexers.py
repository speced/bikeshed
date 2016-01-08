# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals
from pygments.lexer import *
from pygments.token import *

class CSSLexer(RegexLexer):
    name = "CSS"
    aliases = ['css']
    filenames = ['*.css']

    tokens = {
        b"root": [
            (r"\s+", Text),
            (r"[{}\):;]", Punctuation),
            (r"@[\w-]+", Name, b"at-prelude"),
            (r"([^{]+)({)", bygroups(Name.Tag, Punctuation), b"decls"),
            (r".+", Comment)
        ],
        b"at-prelude": [
            include(b"values"),
            (r";|{", Punctuation, b"#pop")
        ],
        b"decls": [
            (r";", Punctuation),
            (r"@[\w-]+", Name, b"at-prelude"),
            (r"([\w-]+)\s*(:)", bygroups(Name, Punctuation)),
            include(b"values"),
            (r"}", Punctuation, b"#pop"),
            (r".+", Text)
        ],
        b"values": [
            (r"[),/]", Punctuation),
            (r"(\d+)([\w-]+)", bygroups(Literal.Number, Literal)),
            (r"\d+", Literal.Number),
            (r"([\w-]+)(\()", bygroups(Name.Function, Punctuation)),
            (r"\"[^\"]*\"", Literal.String),
            (r"'[^']*'", Literal.String),
            (r"#?[\w-]+", Keyword),
            (r"\s+", Text),
        ]
    }
