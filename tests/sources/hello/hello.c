#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <ctype.h>

static PyObject*
hello_hello(PyObject* self, PyObject* args)
{
    return PyUnicode_FromString("Hello, world");
}

static PyMethodDef hello_methods[] = {
    {"hello", hello_hello, METH_NOARGS, "say hello"},
    {NULL},
};

static struct PyModuleDef hello_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "hello",
    .m_methods = hello_methods,
};

PyMODINIT_FUNC
PyInit_hello(void)
{
    return PyModule_Create(&hello_module);
}
