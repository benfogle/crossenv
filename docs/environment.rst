Cross-Compiling Environment
===========================

This section documents the changes to the Python environment beyond just making
``cross-python`` behave like ``host-python``.

Environment variables
---------------------

Crossenv sets ``PYTHON_CROSSENV`` to a non-empty value.

The ``sys`` module
------------------

.. data:: sys.cross_compiling

    Set to ``True`` in ``cross-python``. May be used like so::

        if getattr(sys, 'cross_compiling', False):
            ...

.. data:: sys.build_path

    Analagous to :data:`sys.path`, but applies when importing packages from
    ``build-python``.  This path is searched just before the entries on
    :data:`sys.path` that point to the Python standard library.  This means
    that :data:`sys.build_path` is preferred when loading modules from the
    standard library, but prepending to :data:`sys.path` still works as
    expected.

The ``os`` module
-----------------

.. function:: os.uname()

    In addition to returning ``host-python``'s information, it always reports
    the ``node`` as "``build``".

The ``platform`` module
-----------------------

.. function:: platform.uname()

    In addition to returning ``host-python``'s information, it always reports
    the ``node`` as "``build``".
