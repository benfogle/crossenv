Virtual Environments for Cross-Compiling Python Extension Modules
=============================================================================

|build status| |test status|

Documentation is available online at https://crossenv.readthedocs.io and in the
``docs`` directory.

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


How it works
-----------------------------------------------------------------------------

Cross-python is set up carefully so that it reports all system information
exactly as Host-python would. When done correctly, a side effect of this is
that ``distutils`` and ``setuptools`` will cross-compile when building
packages. All of the normal packaging machinery still works correctly, so
dependencies, ABI tags, and so forth all work as expected.


Requirements
-----------------------------------------------------------------------------

You will need:

1. A version of Python (3.5 or later) that runs on Build. (Build-python.)
2. A version of Python that will run on Host. (Host-python.) This must be the
   *same version* as Build-python.
3. The cross-compiling toolchain used to make Host-python. Make sure you set
   PATH correctly to use it.
4. Any libraries your modules depend on, cross-compiled and installed
   somewhere Cross-python can get to them. For example, the ``cryptography``
   package depends on OpenSSL and libffi.


Installation
-----------------------------------------------------------------------------

Crossenv can be installed using pip::

    $ pip install crossenv


Usage
-----------------------------------------------------------------------------

To create the virtual environment::

    $ /path/to/build/python3 -m crossenv /path/to/host/python3 venv

This creates a folder named ``venv`` that contains two subordinate virtual
environments: one for Build-python, and one for Cross-python. When activated,
``python`` (or its alias ``cross-python``) can be used for cross compiling. If
needed, packages can be installed on Build (e.g., a package requires Cython to
install) with ``build-python``. There are equivalent ``pip``, ``cross-pip``,
and ``build-pip`` commands.

The cross-compiler to use, along with any extra flags needed, are taken from
information recorded when Host-python was compiled.  To activate the
environment::

    $ . venv/bin/activate

You can now see that ``python`` seems to think it's running on Host::

    (cross) $ python -m sysconfig
    ...

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

When you need packages like Cython or cffi installed to build another module,
sometimes satisfying dependencies can get tricky. If you simply ``pip install``
the module, you may find it builds Cython as a prerequisite *for the host* and
then tries to run it on the build machine. This will fail, of course, but if we
install the necessary package for ``build-python``, then ``pip`` will pick up
the correct version during install.

For example, to build bcrypt and python-cryptography::

    (cross) $ build-pip install cffi
    (cross) $ pip install bcrypt
    (cross) $ pip install cryptography

Some packages do explicit checks for existence of a package. For instance, a
package may do a check for Cython (other than simply trying to import it)
before proceeding with installation. If a package is installed with
``build-pip``, etc., then setuptools in ``cross-python`` does not recognize it
as installed. (Note that you can still import it even if setuptools can't see
it, so the naive check of ``import Cython`` will work fine so long as you did
``build-pip install Cython`` earlier.) This is by design. To selectively expose
build-python packages so that setuptools will count them as installed, you can
use the ``cross-expose`` script installed in the virtual environment.

Known Limitations
-----------------------------------------------------------------------------

* Upgrading ``cross-pip`` and ``build-pip`` must be done carefully, and it's
  best not to do so unless you need to. If you need to: upgrade ``cross-pip``
  first, then ``build-pip``.

* When installing scripts, the shebang (``#!``) line is wrong. This will
  need to be fixed up before using on Host.

* Any dependant libraries used during the build, such as OpenSSL, are *not*
  packaged in the wheel or install directory. You will need to ensure that
  these libraries are installed on Host and can be used. This is the normal
  Python behavior.

* Any setup-time requirement listed in ``setup.py`` under ``setup_requires``
  will be installed in Cross-python's virtual environment, not Build-python.
  This will mostly work anyway if they are pure-Python, but for packages
  with extension modules (Cython, etc.), you will need to install them into
  Build-python's environment first. It's often a good idea to do a
  ``build-pip install <whatever>`` prior to ``pip install <whatever>``.

.. |build status| image:: https://dev.azure.com/benfogle/crossenv/_apis/build/status/benfogle.crossenv?branchName=master
.. |test status| image:: https://img.shields.io/azure-devops/tests/benfogle/crossenv/1/master
