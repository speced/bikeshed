use pyo3::prelude::*;
use pyo3::types::PyString;

/// Helper to extract a character from either str or int
fn get_codepoint(obj: &Bound<'_, PyAny>) -> PyResult<Option<char>> {
    if let Ok(s) = obj.downcast::<PyString>() {
        let s = s.to_str()?;
        Ok(get_char(s))
    } else if let Ok(i) = obj.extract::<i64>() {
        if i < 0 || i > 0x10FFFF {
            return Ok(None);
        }
        Ok(char::from_u32(i as u32))
    } else {
        Ok(None)
    }
}

/// Convers a 1 character str to the char, returns None if the string is > 1
fn get_char(s: &str) -> Option<char> {
    if s.chars().count() != 1 {
        None
    } else {
        s.chars().next()
    }
}

fn is_whitespace_char(ch: char) -> bool {
    matches!(ch as u32, 0x9 | 0xA | 0xC | 0x20)
}

/// Check if a character is whitespace (tab, newline, form feed, or space)
#[pyfunction]
pub fn is_whitespace(ch: &Bound<'_, PyAny>) -> PyResult<Option<bool>> {
    Ok(get_codepoint(ch)?.map(is_whitespace_char))
}

/// Check if a character is a digit (0-9)
#[pyfunction]
pub fn is_digit(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_digit())
}

/// Check if a character is a hexadecimal digit
#[pyfunction]
pub fn is_hex_digit(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_hexdigit())
}

/// Check if a character is ASCII lowercase alpha
#[pyfunction]
pub fn is_ascii_lower_alpha(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_lowercase())
}

/// Check if a character is ASCII uppercase alpha
#[pyfunction]
pub fn is_ascii_upper_alpha(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_uppercase())
}

/// Check if a character is ASCII alpha (upper or lower)
#[pyfunction]
pub fn is_ascii_alpha(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_alphabetic())
}

/// Check if a character is ASCII alphanumeric
#[pyfunction]
pub fn is_ascii_alphanum(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii_alphanumeric())
}

/// Check if a character is ASCII (code point <= 127)
#[pyfunction]
pub fn is_ascii(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| c.is_ascii())
}

/// Check if a character is a control character
#[pyfunction]
pub fn is_control(ch: &Bound<'_, PyAny>) -> PyResult<Option<bool>> {
    Ok(get_codepoint(ch)?.map(|c| {
        let cp = c as u32;
        (cp <= 0x08) || (cp == 0x0B) || (0x0D..=0x1F).contains(&cp) || (0x7F..=0x9F).contains(&cp)
    }))
}

/// Check if a character is a noncharacter
#[pyfunction]
pub fn is_noncharacter(ch: &Bound<'_, PyAny>) -> PyResult<Option<bool>> {
    Ok(get_codepoint(ch)?.map(|c| {
        let cp = c as u32;
        (0xFDD0..=0xFDEF).contains(&cp) || (cp & 0xFFFE == 0xFFFE && cp <= 0x10FFFF)
    }))
}

/// Check if a character is valid for an attribute name
#[pyfunction]
pub fn is_attr_name_char(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| {
        if is_whitespace_char(c) {
            return false;
        }
        !matches!(c, '/' | '<' | '>' | '=' | '"' | '\'' | '\0')
    })
}

/// Check if a character is valid for a tag name
#[pyfunction]
pub fn is_tagname_char(ch: &str) -> Option<bool> {
    get_char(ch).map(|c| {
        if matches!(c, '-' | '.' | '_') || c.is_ascii_alphanumeric() {
            return true;
        }

        let cp = c as u32;
        match cp {
            0xB7 => true,
            0xC0..=0x1FFF => !matches!(cp, 0xD7 | 0xF7 | 0x37E),
            0x200C | 0x200D | 0x203F | 0x2040 => true,
            0x2070..=0x218F => true,
            0x2C00..=0x2FEF => true,
            0x3001..=0xD7FF => true,
            0xF900..=0xFDCF => true,
            0xFDF0..=0xFFFD => true,
            0x10000..=0xEFFFF => true,
            _ => false,
        }
    })
}
