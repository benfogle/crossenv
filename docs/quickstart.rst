"Quick" Start
=============

Cross compiling can be challenging, and crossenv is focused only on one
particular piece. As such, this section is not a complete guide.

Build build-python
------------------

**Don't trust a build-python that you didn't build yourself.** The version of
python that comes with a Linux distribution is usually patched by the
maintainers in ways that are subtly incompatible with the stock Python source.
Normally this isn't an issue, but when using crossenv, build-python will end up
running some of host-python's (unpatched) code. The end result is one of many
obscure errors.

**Build-python and host-python must be the exact same version.** As above, one
may need to execute the other's bytecode, which only works if they have the
same version.

For general build instructions refer to the `Python Developer's Guide`_. You
don't need a debug build, so ``configure --prefix=/path/to/build-python`` is
usually enough.

**At a minimum, you need zlib and openssl to build.** Since build-python only
exists to build packages, you can often get away with leaving most optional
components disabled. It's usually sufficient to build just enough to get pip
working, which requires the ``ssl`` and ``zlib`` modules. (More complicated
builds may require more. It depends very much on your specific requirements.)

Build or obtain host-python
---------------------------

In this quick start we assume you are building host-python yourself. In other
cases you may be targeting a pre-built system image. A pre-built image has it's
own challenges, which are covered elsewhere.

You will need to build any host dependencies beforehand. So, for example, if
you want host-python to be able to communicate over a network, you may need to
cross-compile OpenSSL. Building these dependencies is beyond the scope of this
project.

Building host-python requires a working build-python. We recommend putting
build-python in your :envvar:`$PATH` for the configure script to find. Here is
an example of a configure command used for testing crossenv against an ARM
host::

    $ PATH=/path/to/build-python/bin:$PATH \
        ./configure --prefix=/path/to/host-python \
                    --host=arm-linux-musleabihf \
                    --build=x86_64-linux-gnu \
                    --without-ensurepip \
                    ac_cv_buggy_getaddrinfo=no \
                    ac_cv_file__dev_ptmx=yes \
                    ac_cv_file__dev_ptc=no
    $ make
    $ make install

The `--host` option specifies the host triplet, such as ``aarch64-linux-gnu``.
Python will expect a compiler in you :envvar:`$PATH` named
``aarch64-linux-gnu-gcc``, but this can be overridden by passing
``CC=/path/to/cc`` on the command line. You can use ``CFLAGS`` and ``LDFLAGS``
to point Python to any dependencies it needs.

The ``ac_cv_*`` arguments are to set information about the system that
configure isn't able to determine when cross compiling. The first,
``ac_cv_buggy_getaddrinfo=no`` allows IPv6, and the other two are for the
benefit of `os.openpty`_. You may not need any of this functionality, but you
still need to supply the parameters.

Make the cross environment
--------------------------

First install crossenv::

    $ /path/to/build-python/bin/pip3 install crossenv

Build the cross-virtual environment::

    $ /path/to/build-python/bin/python3 -m crossenv \
        /path/to/host-python/bin/python3 \
        cross_venv

Activate the cross-virtual environment::

    $ . ./cross_venv/bin/activate

Build something::

    (cross) $ pip install numpy
    (cross) $ python setup.py install

Packages that you need at *build* time are best installed in build-python
explicitly::

    (cross) $ build-pip install cffi
    (cross) $ pip install bcrypt

    (cross) $ build-pip install wheel
    (cross) $ python setup.py bdist_wheel


Use the resulting packages
--------------------------

It's up to you to incorporate your cross-compiled module into your project. It
might be easiest to create a wheel, and then unzip it at the right location. If
you did a `pip install` you can find the installed libraries at
:file:`cross_venv/cross/lib/python{VERSION}/site-packages`.

.. _Python Developer's Guide: https://devguide.python.org/setup/
.. _os.openpty: https://docs.python.org/3/library/os.html#os.openpty
