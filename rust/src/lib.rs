use pyo3::{
    pymodule,
    types::{PyDict, PyModule, PyList},
    Bound, FromPyObject, PyObject, PyResult, Python,
}

#[pyfunction]
fn onehot_flat_encode_list() -> PyResult<String> {
}

#[pyfunction]
fn onehot_3d_encode_list() -> PyResult<String> {
}

#[pyfunction]
fn integer_encode_list() -> PyResult<String> {
}

#[pymodule]
fn resp_toolkit_rust_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(onehot_flat_encode_list, m)?)?;
}
