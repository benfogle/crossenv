Introduction
============

Requirements
------------

Crossenv requires Python 3.5 or higher (host and build). Significant work has
gone into cross-compiling Python in newer versions, and many of the techniques
needed to do the cross compilation properly are not available on older
releases.

Crossenv currently only supports Linux build machines. Other operating
systems may work, but they are untested and unsupported.


Vocabulary
----------

There is no standard vocabulary for the pieces that go into cross-compiling,
and different resources will often use contradictory terms. To prevent
confusion we use the GNU terminology exclusively, which is used by Python
itself.

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
------------

Python makes a note of the compiler and compiler flags used when it was built.
(This information can be viewed by running ``python3 -m sysconfig``.) When
``distutils`` or ``setuptools`` attempts to create an extension module, they
compile the extension using these recorded values along with reported
information about the currently running system.

Cross-python creates a virtual environment that, when activated, tricks
Build-Python into reporting all system information exactly as Host-python
would. When done correctly, a side effect of this is that ``distutils`` and
``setuptools`` will cross-compile when building packages. All of the normal
packaging machinery still works correctly, so dependencies, ABI tags, and so
forth all work as expected.


Installation
-----------------------------------------------------------------------------

Crossenv can be installed using pip (using build-python)::

    $ pip install crossenv

