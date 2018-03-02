Virtual Envrionments for Cross-Compiling Python Extension Modules
=============================================================================

Complete documentation is coming soon.

Porting a Python app to an embedded device can be complicated. Once you have
Python built for your system, you may find yourself needing to include many
third-party libraries. Pure-Python libraries usually just work, but many
popular libraries rely on compiled C code, which can be challenging to build.

This package is a tool for cross-compiling extension modules. It creates a
special virtual environment such that ``pip`` or ``setup.py`` will cross
compile packages for you, usually with no further work on your part.

It can be used to:

* Build binary wheels, for installation on target.
* Install packages to a directory for upload or inclusion in a firmware image.

**Note**: While this tool can cross-compile *most* Python packages, it can't
solve all the problems of cross-compiling. In some cases manual intervention
may still be necessary.

This tool requires Python 3.5 or higher (host and build). Significant work has
gone into cross-compiling Python in newer versions, and many of the techniques
needed to do the cross compilation properly are not available on older
releases.

This tool currently only supports Linux build machines.


Vocabulary
-----------------------------------------------------------------------------

+---------------+------------------------------------------------------------+
| Host          | The machine you are building **for**. (Android, iOS, other |
|               | embedded systems.)                                         |
+---------------+------------------------------------------------------------+
| Build         | The machine you are building **on**. (Probably your        |
|               | desktop.)                                                  |
+---------------+------------------------------------------------------------+
| Host-python   | The compiled Python binary and libraries that run on Host  |
+---------------+------------------------------------------------------------+
| Build-python  | The compiled Python binary and libraries that run on       |
|               | Build.                                                     |
+---------------+------------------------------------------------------------+
| Cross-python  | Build-python, configured specially to build packages that  |
|               | can be run with Host-python. This tool creates             |
|               | Cross-python.                                              |
+---------------+------------------------------------------------------------+


Requirements
-----------------------------------------------------------------------------

You will need:

1. A version of Python (3.5 or later) that runs on Build. (Build-python.)
2. A version of Python that will run on Host. (Host-python.) This must be the
   *same version* as Build-python.
3. The cross-compiling toolchain used to make Host-python. Make sure you set
   PATH correctly to use it.


Installation
-----------------------------------------------------------------------------

Crossenv can be installed using pip::

    $ pip install crossenv


Usage
-----------------------------------------------------------------------------

To create the virtual environment::

    $ /path/to/build/python3 -m crossenv /path/to/host/python3 venv

This creates a folder named ``venv``. The compiler to use along with any extra
flags needed are taken from information recorded when Host-python was compiled.
To activate the environment::

    $ . venv/bin/activate
    (cross) $

Now you can cross compile! To install a package to
``venv/cross/lib/python3.6/site-packages``, you can use pip directly::

    (cross) $ pip -v install numpy
    ...

You can use ``setup.py`` to build wheels::

    (cross) $ pip install wheel
    (cross) $ pip download numpy
    Collecting numpy
      Using cached numpy-1.14.1.zip
      Saved ./numpy-1.14.1.zip
    Successfully downloaded numpy
    (cross) $ unzip -q ./numpy-1.14.1.zip
    (cross) $ cd numpy-1.14.1
    (cross) $ python setup.py bdist_wheel
    ...
