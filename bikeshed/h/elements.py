from __future__ import annotations

INLINE_ELEMENTS: frozenset[str] = frozenset(
    {
        "a",
        "abbr",
        "b",
        "bdi",
        "bdo",
        "br",
        "bs-inline",
        "cite",
        "code",
        "css",
        "data",
        "dfn",
        "em",
        "i",
        "img",
        "kbd",
        "l",
        "mark",
        "math",  # inline by default; <math display=block> is block-level
        "meter",
        "progress",
        "q",
        "ruby",
        "s",
        "samp",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "time",
        "u",
        "var",
        "wbr",
        "[]",
    },
)

VOID_ELEMENTS: frozenset[str] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "command",
        "embed",
        "hr",
        "img",
        "input",
        "keygen",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    },
)

RAW_ELEMENTS: frozenset[str] = frozenset({"xmp", "script", "style"})
DEFAULT_OPAQUE_ELEMENTS: frozenset[str] = frozenset({"pre", "xmp", "script", "style"})
DEFAULT_BLOCK_ELEMENTS: frozenset[str] = frozenset({"bs-block"})

HEAD_ELEMENTS: frozenset[str] = frozenset(
    {
        "link",
        "meta",
        "script",
        "style",
        "title",
    },
)

HEADING_ELEMENTS: frozenset[str] = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    },
)

OMIT_END_TAG_ELEMENTS: frozenset[str] = frozenset(
    {
        "body",
        "col",
        "colgroup",
        "dd",
        "dt",
        "head",
        "html",
        "li",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
    },
)

ALWAYS_OMIT_END_TAG_ELEMENTS: frozenset[str] = OMIT_END_TAG_ELEMENTS - {"dt", "dd"}

AUTO_CLOSE_P_START_ELEMENTS: frozenset[str] = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "center",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "listing",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "plaintext",
        "pre",
        "search",
        "section",
        "summary",
        "table",
        "ul",
        "xmp",
    },
)

AUTO_CLOSE_P_END_ELEMENTS: frozenset[str] = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "caption",
        "center",
        "dd",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "html",
        "li",
        "listing",
        "main",
        "menu",
        "nav",
        "ol",
        "plaintext",
        "pre",
        "search",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    },
)

type AutoCloseRuleT = tuple[tuple[str, ...], tuple[str, ...] | None]

_LIST_SCOPES = ("ol", "ul")
_DL_SCOPES = ("dl",)
_TABLE_SCOPES = ("table",)
_RUBY_SCOPES = ("ruby",)
_TABLE_CELLS = ("td", "th")
_TABLE_SECTIONS = ("thead", "tbody", "tfoot", "caption", "colgroup")
_TABLE_SECTIONS_NO_COLGROUP = ("thead", "tbody", "tfoot", "caption")

# Start tags that implicitly close an open `<p>` only within a specific ancestor scope.
AUTO_CLOSE_P_SCOPED_START_ELEMENTS: dict[str, tuple[str, ...]] = {
    "li": _LIST_SCOPES,
    "dt": _DL_SCOPES,
    "dd": _DL_SCOPES,
    "td": _TABLE_SCOPES,
    "th": _TABLE_SCOPES,
    "tr": _TABLE_SCOPES,
    "thead": _TABLE_SCOPES,
    "tbody": _TABLE_SCOPES,
    "tfoot": _TABLE_SCOPES,
    "caption": _TABLE_SCOPES,
    "colgroup": _TABLE_SCOPES,
    "col": _TABLE_SCOPES,
}

# Ordered `(tags_to_close, scope_tags)` rules applied when opening a start tag.
AUTO_CLOSE_START_RULES: dict[str, tuple[AutoCloseRuleT, ...]] = {
    "li": ((("li",), _LIST_SCOPES),),
    "dt": ((("dt", "dd"), _DL_SCOPES),),
    "dd": ((("dt", "dd"), _DL_SCOPES),),
    "option": ((("option",), None),),
    "optgroup": ((("option",), None), (("optgroup",), None)),
    "td": ((_TABLE_CELLS, _TABLE_SCOPES),),
    "th": ((_TABLE_CELLS, _TABLE_SCOPES),),
    "tr": (
        (_TABLE_CELLS, _TABLE_SCOPES),
        (("tr",), _TABLE_SCOPES),
        (("caption", "colgroup"), _TABLE_SCOPES),
    ),
    "thead": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "tbody": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "tfoot": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "caption": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "colgroup": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "col": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS_NO_COLGROUP, _TABLE_SCOPES)),
    "rb": ((("rb", "rp", "rt"), _RUBY_SCOPES), (("rtc",), _RUBY_SCOPES)),
    "rtc": ((("rb", "rp", "rt"), _RUBY_SCOPES), (("rtc",), _RUBY_SCOPES)),
    "rp": ((("rb", "rp", "rt"), _RUBY_SCOPES),),
    "rt": ((("rb", "rp", "rt"), _RUBY_SCOPES),),
}

# Ordered `(tags_to_close, scope_tags)` rules applied when closing an end tag.
AUTO_CLOSE_END_RULES: dict[str, tuple[AutoCloseRuleT, ...]] = {
    "ol": ((("li",), _LIST_SCOPES),),
    "ul": ((("li",), _LIST_SCOPES),),
    "dl": ((("dt", "dd"), _DL_SCOPES),),
    "tr": ((_TABLE_CELLS, _TABLE_SCOPES),),
    "thead": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES)),
    "tbody": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES)),
    "tfoot": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES)),
    "table": ((_TABLE_CELLS, _TABLE_SCOPES), (("tr",), _TABLE_SCOPES), (_TABLE_SECTIONS, _TABLE_SCOPES)),
    "rtc": ((("rt",), _RUBY_SCOPES),),
    "ruby": ((("rt", "rb", "rp"), _RUBY_SCOPES), (("rtc",), _RUBY_SCOPES)),
    "optgroup": ((("option",), None),),
    "select": ((("option",), None), (("optgroup",), None)),
}
