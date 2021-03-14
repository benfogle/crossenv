Crossenv: A Virtual Environments for Cross-Compiling Python Extension Modules
=============================================================================

.. note:: This documentation is in the early stages.

Porting a Python app to an embedded device can be complicated. Once you have
Python built for your system, you may find yourself needing to include many
third-party libraries. Pure-Python libraries usually just work, but many
popular libraries rely on compiled C code, which can be challenging to build.

This package is a tool for cross-compiling extension modules. It creates a
special virtual environment such that ``pip`` or ``setup.py`` will cross
compile packages for you, often with no further work on your part.

It can be used to:

* Build binary wheels, for installation on target.
* Install packages to a directory for upload or inclusion in a firmware image.

.. note::
    While this tool can cross-compile *most* Python packages, it can't solve
    all the problems of cross-compiling, and it can't make cross-compiling a
    completely pain-free process. In some cases manual intervention may still
    be necessary.

This tool requires Python 3.5 or higher (host and build). Significant work has
gone into cross-compiling Python in newer versions, and many of the techniques
needed to do the cross compilation properly are not available on older
releases.

This tool currently only supports Linux build machines.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   intro
   quickstart
   environment
