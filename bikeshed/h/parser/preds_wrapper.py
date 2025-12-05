from __future__ import annotations

import os

_USE_RUST = os.environ.get("BIKESHED_USE_RUST", "").lower() in ("1", "true")

if _USE_RUST:
    try:
        import bikeshed_rust

        from . import preds as _preds

        isASCII = bikeshed_rust.is_ascii
        isASCIIAlpha = bikeshed_rust.is_ascii_alpha
        isASCIIAlphanum = bikeshed_rust.is_ascii_alphanum
        isASCIILowerAlpha = bikeshed_rust.is_ascii_lower_alpha
        isASCIIUpperAlpha = bikeshed_rust.is_ascii_upper_alpha
        isAttrNameChar = bikeshed_rust.is_attr_name_char
        isControl = bikeshed_rust.is_control
        isDigit = bikeshed_rust.is_digit
        isHexDigit = bikeshed_rust.is_hex_digit
        isNoncharacter = bikeshed_rust.is_noncharacter
        isTagnameChar = bikeshed_rust.is_tagname_char
        isWhitespace = bikeshed_rust.is_whitespace

        charRefs = _preds.charRefs
        xmlishTagnames = _preds.xmlishTagnames
        isXMLishTagname = _preds.isXMLishTagname
    except ImportError:
        from . import preds as _preds

        charRefs = _preds.charRefs
        xmlishTagnames = _preds.xmlishTagnames
        isASCII = _preds.isASCII
        isASCIIAlpha = _preds.isASCIIAlpha
        isASCIIAlphanum = _preds.isASCIIAlphanum
        isASCIILowerAlpha = _preds.isASCIILowerAlpha
        isASCIIUpperAlpha = _preds.isASCIIUpperAlpha
        isAttrNameChar = _preds.isAttrNameChar
        isControl = _preds.isControl
        isDigit = _preds.isDigit
        isHexDigit = _preds.isHexDigit
        isNoncharacter = _preds.isNoncharacter
        isTagnameChar = _preds.isTagnameChar
        isWhitespace = _preds.isWhitespace
        isXMLishTagname = _preds.isXMLishTagname

else:
    from . import preds as _preds

    charRefs = _preds.charRefs
    xmlishTagnames = _preds.xmlishTagnames
    isASCII = _preds.isASCII
    isASCIIAlpha = _preds.isASCIIAlpha
    isASCIIAlphanum = _preds.isASCIIAlphanum
    isASCIILowerAlpha = _preds.isASCIILowerAlpha
    isASCIIUpperAlpha = _preds.isASCIIUpperAlpha
    isAttrNameChar = _preds.isAttrNameChar
    isControl = _preds.isControl
    isDigit = _preds.isDigit
    isHexDigit = _preds.isHexDigit
    isNoncharacter = _preds.isNoncharacter
    isTagnameChar = _preds.isTagnameChar
    isWhitespace = _preds.isWhitespace
    isXMLishTagname = _preds.isXMLishTagname

__all__ = [
    "charRefs",
    "isASCII",
    "isASCIIAlpha",
    "isASCIIAlphanum",
    "isASCIILowerAlpha",
    "isASCIIUpperAlpha",
    "isAttrNameChar",
    "isControl",
    "isDigit",
    "isHexDigit",
    "isNoncharacter",
    "isTagnameChar",
    "isWhitespace",
    "isXMLishTagname",
    "xmlishTagnames",
]
