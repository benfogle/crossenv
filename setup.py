from setuptools import setup
import os

try:
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
        long_description = f.read()
except IOError:
    long_description = ''

setup(
    name="crossenv",
    version="0.4",
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


