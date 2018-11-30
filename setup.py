from setuptools import setup
import os
import re

here = os.path.abspath(os.path.dirname(__file__))

def read(*path, default=None):
    try:
        with open(os.path.join(here, *path), encoding='utf-8') as f:
            return f.read()
    except IOError:
        return ''

long_description = read('README.rst')

def get_version():
    init_file = read('crossenv', '__init__.py')
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              init_file, re.MULTILINE)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

setup(
    name="crossenv",
    version=get_version(),
    description="A cross-compiling tool for Python extension modules",
    long_description=long_description,
    url="https://github.com/benfogle/crossenv",
    author="Benjamin Fogle",
    author_email="benfogle@gmail.com",
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    python_requires='>=3.4',
    packages=['crossenv'],
    package_data = {
        'crossenv' : ['scripts/*'],
    },
)


