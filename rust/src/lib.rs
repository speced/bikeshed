use pyo3::prelude::*;

mod preds;

#[pymodule]
fn bikeshed_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(preds::is_whitespace, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_digit, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_hex_digit, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_ascii_lower_alpha, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_ascii_upper_alpha, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_ascii_alpha, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_ascii_alphanum, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_ascii, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_control, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_noncharacter, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_attr_name_char, m)?)?;
    m.add_function(wrap_pyfunction!(preds::is_tagname_char, m)?)?;
    Ok(())
}
