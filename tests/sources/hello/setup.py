from setuptools import setup, Extension

setup(
    name="hello-crossenv",
    version = 1.0,
    description = "A package we can build for test purposes",
    ext_modules = [
        Extension('hello', ['hello.c']),
    ],
)
